from __future__ import annotations

from collections import defaultdict

import numpy as np

from app.models.schemas import DebateRound, FundamentalSignal, MasterOpinion, NewsSignal, PortfolioPosition, PriceSnapshot
from app.services.llm_client import LLMClient, LLMMessage


class InvestmentManagerAgent:
    max_single_weight = 0.60
    lot_size = 100
    system_prompt = (
        "你是专业的A股投资经理。你的结论应体现组合管理、风险预算和交易约束意识，"
        "少堆砌数字，更多用金融投资经理的语言说明为什么买、为什么不买、为什么保留现金。"
    )

    def __init__(self) -> None:
        self.llm = LLMClient()

    def allocate(
        self,
        capital: int,
        prices: list[PriceSnapshot],
        fundamentals: list[FundamentalSignal],
        news: list[NewsSignal],
        opinions: list[MasterOpinion],
        debate: list[DebateRound],
    ) -> tuple[list[PortfolioPosition], float, str]:
        price_by_symbol = {item.symbol: item for item in prices}
        fund_quality = {item.symbol: item.data_quality for item in fundamentals}
        news_quality = {item.symbol: item.data_quality for item in news}

        grouped: dict[str, list[MasterOpinion]] = defaultdict(list)
        for opinion in opinions:
            grouped[opinion.symbol].append(opinion)

        final_scores: dict[str, float] = {}
        diagnostics: dict[str, dict[str, float | str]] = {}
        actions: dict[str, str] = {}

        for symbol, symbol_opinions in grouped.items():
            revised_scores = np.array([item.revised_score if item.revised_score is not None else item.score for item in symbol_opinions], dtype=float)
            revised_confidences = np.array(
                [item.revised_confidence if item.revised_confidence is not None else item.confidence for item in symbol_opinions],
                dtype=float,
            )
            weights = np.clip(revised_confidences, 0.15, 0.98)
            alpha = float(np.average(revised_scores, weights=weights))
            disagreement = float(np.std(revised_scores))
            price = price_by_symbol[symbol]
            volatility_scaled = float(np.clip(price.volatility / 0.65, 0, 1))
            data_quality = float(np.clip((price.data_quality * 0.4 + fund_quality.get(symbol, 0.5) * 0.32 + news_quality.get(symbol, 0.5) * 0.28), 0, 1))
            data_uncertainty = 1 - data_quality
            risk_penalty = float(np.clip(0.16 * volatility_scaled + 0.14 * disagreement + 0.18 * data_uncertainty, 0, 0.5))
            final_score = float(max(alpha - risk_penalty - 0.32, 0))
            final_scores[symbol] = final_score

            buy_votes = int(np.sum(revised_scores >= 0.64))
            sell_votes = int(np.sum(revised_scores <= 0.41))
            hold_votes = len(symbol_opinions) - buy_votes - sell_votes
            actions[symbol] = "buy" if final_score > 0 and buy_votes >= max(hold_votes, sell_votes) else "sell" if sell_votes > buy_votes and sell_votes >= hold_votes else "hold"
            diagnostics[symbol] = {
                "alpha": round(alpha, 3),
                "risk_penalty": round(risk_penalty, 3),
                "final_score": round(final_score, 3),
                "disagreement": round(disagreement, 3),
                "data_quality": round(data_quality, 3),
                "votes": f"买入 {buy_votes}、持有 {hold_votes}、卖出 {sell_votes}",
            }

        investable = {symbol: score for symbol, score in final_scores.items() if score > 0 and actions[symbol] == "buy"}
        target_weights = self._constrained_weights(investable)
        lot_plan = self._lot_plan(capital, target_weights, price_by_symbol)

        positions: list[PortfolioPosition] = []
        for symbol in grouped:
            shares = lot_plan.get(symbol, 0)
            price = price_by_symbol[symbol]
            amount = round(shares * price.close, 2)
            weight = amount / capital if capital > 0 else 0
            if shares == 0 and actions[symbol] == "buy":
                actions[symbol] = "hold"
            diag = diagnostics[symbol]
            rationale = (
                f"投资经理评分：alpha {diag['alpha']:.2f}，风险惩罚 {diag['risk_penalty']:.2f}，"
                f"最终分 {diag['final_score']:.2f}；{diag['votes']}；"
                f"{'满足一手交易约束' if shares else '未满足买入阈值或一手交易约束'}。"
            )
            positions.append(
                PortfolioPosition(
                    symbol=symbol,
                    name=price.name,
                    action=actions[symbol],
                    weight=round(weight, 4),
                    amount=amount,
                    shares=shares,
                    alpha=float(diag["alpha"]),
                    risk_penalty=float(diag["risk_penalty"]),
                    final_score=float(diag["final_score"]),
                    disagreement=float(diag["disagreement"]),
                    data_quality=float(diag["data_quality"]),
                    rationale=rationale,
                )
            )

        invested = sum(item.amount for item in positions)
        cash = round(max(capital - invested, 0), 2)
        summary = self._summary(positions, cash, debate)
        return positions, cash, summary

    def _constrained_weights(self, scores: dict[str, float]) -> dict[str, float]:
        if not scores:
            return {}
        remaining = dict(scores)
        weights = {symbol: 0.0 for symbol in scores}
        remaining_budget = 1.0
        while remaining and remaining_budget > 1e-9:
            total_score = sum(remaining.values())
            if total_score <= 0:
                break
            capped = []
            for symbol, score in remaining.items():
                proposed = remaining_budget * score / total_score
                if weights[symbol] + proposed >= self.max_single_weight:
                    capped.append(symbol)
            if not capped:
                for symbol, score in remaining.items():
                    weights[symbol] += remaining_budget * score / total_score
                break
            for symbol in capped:
                add = max(self.max_single_weight - weights[symbol], 0)
                weights[symbol] += add
                remaining_budget -= add
                remaining.pop(symbol, None)
        return {symbol: round(weight, 6) for symbol, weight in weights.items() if weight > 0}

    def _lot_plan(self, capital: int, target_weights: dict[str, float], price_by_symbol: dict[str, PriceSnapshot]) -> dict[str, int]:
        plan: dict[str, int] = {}
        spent = 0.0
        for symbol, target_weight in sorted(target_weights.items(), key=lambda item: item[1], reverse=True):
            price = price_by_symbol[symbol].close
            max_amount = min(capital * target_weight, capital * self.max_single_weight)
            available = max(capital - spent, 0)
            budget = min(max_amount, available)
            lot_cost = price * self.lot_size
            if budget < lot_cost:
                plan[symbol] = 0
                continue
            shares = int(budget // lot_cost) * self.lot_size
            amount = shares * price
            if amount + spent > capital:
                shares = int((capital - spent) // lot_cost) * self.lot_size
                amount = shares * price
            plan[symbol] = max(shares, 0)
            spent += amount
        return plan

    def _summary(self, positions: list[PortfolioPosition], cash: float, debate: list[DebateRound]) -> str:
        llm_summary = self._llm_summary(positions, cash, debate)
        if llm_summary:
            return llm_summary
        active = [item for item in positions if item.shares > 0]
        if not active:
            candidates = [item for item in sorted(positions, key=lambda item: item.final_score, reverse=True) if item.final_score > 0]
            watchlist = "、".join(item.symbol for item in candidates[:2]) or "当前标的"
            return f"投资经理结论：本轮没有形成可以落到一手交易约束的买入方案。即便部分标的有正向信号，安全边际、分歧或价格门槛仍不足，建议保持现金，并继续观察 {watchlist} 的后续确认。"
        active_text = "、".join(f"{item.symbol}({item.name})" for item in active)
        contested = [item.target_symbol for item in debate[:4]]
        debate_text = "、".join(dict.fromkeys(contested)) or "核心标的"
        return f"投资经理结论：组合选择以 {active_text} 为主要配置对象。大师辩论显示 {debate_text} 的分歧仍需尊重，因此仓位按交易手数落地后保留未使用现金，不追求满仓，优先保证可执行性和风险缓冲。"

    def _llm_summary(self, positions: list[PortfolioPosition], cash: float, debate: list[DebateRound]) -> str | None:
        if not self.llm.enabled:
            return None
        active = [
            {
                "symbol": item.symbol,
                "name": item.name,
                "action": item.action,
                "shares": item.shares,
                "qualitative_score": "较强" if item.final_score >= 0.25 else "一般" if item.final_score > 0 else "不足",
                "risk_state": "可控" if item.risk_penalty < 0.12 else "需折扣",
            }
            for item in positions
        ]
        debate_text = [item.argument for item in debate[-12:]]
        prompt = (
            "请以A股投资经理口吻输出最终投资决定总结。要求：120-220字，专业、克制、文本化，"
            "尽量少使用具体数字；要结合大师辩论内容，说明买入、观望和现金保留的原因；"
            "不要给出收益承诺，不要输出思考过程。\n"
            f"组合执行结果：{active}\n"
            f"剩余现金状态：{'较多' if cash > 0 else '很少'}\n"
            f"辩论摘要：{debate_text}"
        )
        try:
            return self.llm.complete(
                [
                    LLMMessage(role="system", content=self.system_prompt),
                    LLMMessage(role="user", content=prompt),
                ],
                temperature=0.28,
            )
        except Exception:
            return None
