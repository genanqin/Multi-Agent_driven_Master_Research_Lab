from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable

import numpy as np

from app.config import get_settings
from app.models.schemas import FundamentalSignal, MasterOpinion, NewsSignal, TechnicalSignal
from app.services.llm_client import LLMClient, LLMMessage


FactorMap = dict[str, float]


@dataclass(frozen=True)
class MasterStyle:
    name: str
    philosophy: str
    system_prompt: str
    factor_preference: dict[str, float]
    style_prior: dict[str, float]
    risk_aversion: float
    horizon: str
    scorer: str


MASTER_STYLES = [
    MasterStyle(
        name="Buffett",
        philosophy="价值投资与护城河，偏好高质量、现金流稳健、可长期持有的公司。",
        system_prompt="你是 Buffett 风格 Agent。你能看到所有因子，但应强烈偏向质量、估值、现金流和长期风险证据，不被短期情绪牵着走。",
        factor_preference={"quality": 1.0, "value": 0.9, "cashflow": 0.95, "risk": 0.82, "growth": 0.45, "sentiment": 0.12, "technical": 0.12},
        style_prior={"quality": 0.95, "value": 0.82, "growth": 0.55, "risk_aversion": 0.9, "horizon": 1.0, "reflexivity": 0.1},
        risk_aversion=0.86,
        horizon="极长",
        scorer="buffett",
    ),
    MasterStyle(
        name="Graham",
        philosophy="深度价值与安全边际，重视低估值、资产保护和下行风险。",
        system_prompt="你是 Graham 风格 Agent。你能看到所有因子，但应强烈偏向估值、安全边际和财务稳健性，对成长叙事和情绪信号保持怀疑。",
        factor_preference={"value": 1.0, "risk": 0.98, "quality": 0.72, "cashflow": 0.76, "growth": 0.12, "sentiment": 0.08, "technical": 0.08},
        style_prior={"quality": 0.75, "value": 1.0, "growth": 0.2, "risk_aversion": 1.0, "horizon": 0.82, "reflexivity": 0.05},
        risk_aversion=0.93,
        horizon="长",
        scorer="graham",
    ),
    MasterStyle(
        name="Lynch",
        philosophy="GARP 成长，寻找合理估值下的可持续增长。",
        system_prompt="你是 Lynch 风格 Agent。你能看到所有因子，但应强烈偏向成长、合理估值、质量和产业热度，寻找 GARP 型机会。",
        factor_preference={"growth": 1.0, "value": 0.62, "quality": 0.68, "sentiment": 0.55, "momentum": 0.45, "risk": 0.36},
        style_prior={"quality": 0.6, "value": 0.55, "growth": 0.95, "risk_aversion": 0.52, "horizon": 0.58, "reflexivity": 0.35},
        risk_aversion=0.55,
        horizon="中",
        scorer="lynch",
    ),
    MasterStyle(
        name="Soros",
        philosophy="反身性宏观与事件驱动，重视趋势、预期差和情绪反馈。",
        system_prompt="你是 Soros 风格 Agent。你能看到所有因子，但应强烈偏向趋势、情绪、事件热度和反身性反馈，不做长期护城河叙事。",
        factor_preference={"technical": 1.0, "momentum": 0.82, "sentiment": 0.95, "event_heat": 0.9, "risk": 0.38, "value": 0.16, "quality": 0.12},
        style_prior={"quality": 0.25, "value": 0.25, "growth": 0.58, "risk_aversion": 0.22, "horizon": 0.18, "reflexivity": 1.0},
        risk_aversion=0.35,
        horizon="短",
        scorer="soros",
    ),
    MasterStyle(
        name="Dalio",
        philosophy="全天候配置，追求风险均衡、分散和稳健暴露。",
        system_prompt="你是 Dalio 风格 Agent。你能看到所有因子，但应强烈偏向风险均衡、质量、估值与波动控制，优先降低组合脆弱性。",
        factor_preference={"risk": 1.0, "volatility_control": 0.92, "quality": 0.76, "value": 0.58, "growth": 0.48, "technical": 0.42},
        style_prior={"quality": 0.82, "value": 0.62, "growth": 0.55, "risk_aversion": 0.92, "horizon": 0.58, "reflexivity": 0.25},
        risk_aversion=0.82,
        horizon="中",
        scorer="dalio",
    ),
    MasterStyle(
        name="Templeton",
        philosophy="逆向价值，偏好悲观情绪中的低估修复机会。",
        system_prompt="你是 Templeton 风格 Agent。你能看到所有因子，但应强烈偏向低估值、逆向情绪、质量底线和风险补偿。",
        factor_preference={"value": 0.96, "sentiment_contrarian": 0.86, "risk": 0.72, "quality": 0.64, "growth": 0.32, "sentiment": 0.18},
        style_prior={"quality": 0.68, "value": 0.92, "growth": 0.45, "risk_aversion": 0.72, "horizon": 0.72, "reflexivity": 0.32},
        risk_aversion=0.74,
        horizon="中长",
        scorer="templeton",
    ),
]


class MasterAgentOrchestrator:
    def __init__(self) -> None:
        self.llm = LLMClient()
        self.settings = get_settings()
        self.scorers: dict[str, Callable[[FactorMap], float]] = {
            "buffett": self._score_buffett,
            "graham": self._score_graham,
            "lynch": self._score_lynch,
            "soros": self._score_soros,
            "dalio": self._score_dalio,
            "templeton": self._score_templeton,
        }

    def analyze(
        self,
        technicals: list[TechnicalSignal],
        fundamentals: list[FundamentalSignal],
        news: list[NewsSignal],
    ) -> list[MasterOpinion]:
        tech_by_symbol = {item.symbol: item for item in technicals}
        fund_by_symbol = {item.symbol: item for item in fundamentals}
        news_by_symbol = {item.symbol: item for item in news}
        opinions: list[MasterOpinion] = []
        for symbol in tech_by_symbol:
            tech = tech_by_symbol[symbol]
            fund = fund_by_symbol[symbol]
            text = news_by_symbol[symbol]
            factors = self._factor_vector(tech, fund, text)
            for style in MASTER_STYLES:
                opinions.append(self._opinion(style, symbol, factors, tech, fund, text))
        return opinions

    def _factor_vector(self, tech: TechnicalSignal, fund: FundamentalSignal, news: NewsSignal) -> FactorMap:
        value = 1 - np.clip(fund.pe / 65 * 0.55 + fund.pb / 9 * 0.45, 0, 1)
        quality = np.clip(fund.roe / 30 * 0.5 + fund.cashflow_coverage / 2.6 * 0.34 + fund.score * 0.16, 0, 1)
        growth = np.clip((fund.growth + 10) / 52, 0, 1)
        risk = np.clip(1 - (tech.rsi > 75) * 0.24 - max(tech.bollinger_position - 0.82, 0) * 0.7 - max(0.45 - fund.score, 0), 0, 1)
        return {
            "quality": round(float(quality), 3),
            "value": round(float(value), 3),
            "growth": round(float(growth), 3),
            "technical": tech.score,
            "momentum": tech.momentum,
            "volume_signal": tech.volume_signal,
            "sentiment": news.score,
            "event_heat": news.event_heat,
            "cashflow": round(float(np.clip(fund.cashflow_coverage / 2.5, 0, 1)), 3),
            "roe": round(float(np.clip(fund.roe / 30, 0, 1)), 3),
            "risk": round(float(risk), 3),
            "volatility_control": round(float(np.clip(1 - tech.bollinger_position * 0.28 - max(tech.rsi - 70, 0) / 100, 0, 1)), 3),
            "sentiment_contrarian": round(float(np.clip(1 - abs(news.sentiment - 0.42) * 1.7, 0, 1)), 3),
        }

    def _opinion(
        self,
        style: MasterStyle,
        symbol: str,
        factors: FactorMap,
        tech: TechnicalSignal,
        fund: FundamentalSignal,
        news: NewsSignal,
    ) -> MasterOpinion:
        visible_factors = dict(factors)
        preferred_factors = self._preferred_factors(style, factors)
        baseline_score = self.scorers[style.scorer](visible_factors)
        baseline_confidence = self._confidence(style, baseline_score, preferred_factors)
        baseline_action = self._action_from_score(baseline_score)
        decision = self._llm_decision(style, symbol, visible_factors, preferred_factors, baseline_score, baseline_confidence, tech, fund, news)
        action, score, confidence, reason = self._guarded_decision(
            decision,
            style,
            symbol,
            visible_factors,
            baseline_action,
            baseline_score,
            baseline_confidence,
            tech,
            fund,
            news,
        )
        return MasterOpinion(
            master=style.name,
            philosophy=style.philosophy,
            system_prompt=style.system_prompt,
            symbol=symbol,
            factors=factors,
            visible_factors=visible_factors,
            preferred_factors=preferred_factors,
            factor_whitelist=list(factors.keys()),
            banned_factors=[],
            style_prior=style.style_prior,
            action=action,
            confidence=round(confidence, 3),
            score=round(float(score), 3),
            revised_score=round(float(score), 3),
            revised_confidence=round(confidence, 3),
            reason=reason,
        )

    def _preferred_factors(self, style: MasterStyle, factors: FactorMap) -> FactorMap:
        preferred = {}
        for key, preference in style.factor_preference.items():
            if key in factors:
                preferred[key] = round(float(factors[key] * preference), 3)
        return preferred or dict(factors)

    def _action_from_score(self, score: float) -> str:
        if score >= 0.64:
            return "buy"
        if score <= 0.41:
            return "sell"
        return "hold"

    def _llm_decision(
        self,
        style: MasterStyle,
        symbol: str,
        visible_factors: FactorMap,
        preferred_factors: FactorMap,
        baseline_score: float,
        baseline_confidence: float,
        tech: TechnicalSignal,
        fund: FundamentalSignal,
        news: NewsSignal,
    ) -> dict[str, object] | None:
        if self.settings.master_decision_mode.lower() == "rules" or not self.llm.enabled:
            return None
        prompt = (
            "你必须作为一个独立投资大师 Agent 直接决定本轮观点，而不是复述规则模型。"
            "但规则模型是风险锚点，不得无视。只允许基于给定数据，不得引用外部事实、实时价格、未提供公告或个人记忆。"
            "输出必须是严格 JSON，不要 Markdown，不要解释 JSON 之外的内容。\n"
            "JSON schema: {\"action\":\"buy|hold|sell\", \"score\":0到1数字, \"confidence\":0到1数字, \"reason\":\"80到160字中文理由\"}\n"
            "决策约束：score 越高越偏买入；若要显著偏离 baseline_score，reason 必须说明给定因子中的冲突证据；"
            "reason 必须体现你的大师风格，不能混用其他大师人格。\n"
            f"大师：{style.name}\n"
            f"投资哲学：{style.philosophy}\n"
            f"风格优先因子：{style.factor_preference}\n"
            f"股票：{symbol}\n"
            f"baseline_action：{self._action_from_score(baseline_score)}\n"
            f"baseline_score：{baseline_score:.3f}\n"
            f"baseline_confidence：{baseline_confidence:.3f}\n"
            f"全部可见因子：{visible_factors}\n"
            f"按风格加权后的偏好证据：{preferred_factors}\n"
            f"技术原始数据：RSI={tech.rsi}, 技术分={tech.score}, 动量={tech.momentum}, 布林位置={tech.bollinger_position}\n"
            f"财务原始数据：PE={fund.pe}, PB={fund.pb}, ROE={fund.roe}, 现金流覆盖={fund.cashflow_coverage}, 增长={fund.growth}, 财务分={fund.score}\n"
            f"新闻原始数据：情绪={news.sentiment}, 热度={news.event_heat}, 摘要={news.summary}"
        )
        try:
            raw = self.llm.complete(
                [
                    LLMMessage(role="system", content=self._isolated_system_prompt(style)),
                    LLMMessage(role="user", content=prompt),
                ],
                temperature=0.18,
            )
            return self._parse_llm_json(raw)
        except Exception:
            return None

    def _isolated_system_prompt(self, style: MasterStyle) -> str:
        return (
            f"{style.system_prompt}\n"
            "人格隔离规则：你只代表当前这一位大师 Agent，不得模拟、迎合、引用或综合其他大师观点；"
            "不得声称自己是裁判、投资经理、系统或多个 Agent 的共识。"
            "你可以看到全部因子，但必须按自己的投资哲学重新判断买入、持有或卖出。"
            "你必须承认数据边界：只能使用用户提供的结构化因子、技术数据、财务数据和新闻摘要。"
            "输出必须服从用户消息中的 JSON schema。"
        )

    def _parse_llm_json(self, raw: str) -> dict[str, object] | None:
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        match = re.search(r"\{.*\}", text, flags=re.S)
        if match:
            text = match.group(0)
        payload = json.loads(text)
        if not isinstance(payload, dict):
            return None
        return payload

    def _guarded_decision(
        self,
        decision: dict[str, object] | None,
        style: MasterStyle,
        symbol: str,
        visible_factors: FactorMap,
        baseline_action: str,
        baseline_score: float,
        baseline_confidence: float,
        tech: TechnicalSignal,
        fund: FundamentalSignal,
        news: NewsSignal,
    ) -> tuple[str, float, float, str]:
        fallback_reason = self._reason(style, symbol, visible_factors, baseline_score, tech, fund, news)
        if not decision:
            return baseline_action, baseline_score, baseline_confidence, fallback_reason

        raw_action = str(decision.get("action", "")).strip().lower()
        if raw_action not in {"buy", "hold", "sell"}:
            raw_action = baseline_action

        raw_score = self._coerce_unit_float(decision.get("score"), baseline_score)
        raw_confidence = self._coerce_unit_float(decision.get("confidence"), baseline_confidence)
        max_delta = float(np.clip(self.settings.master_llm_max_score_delta, 0.0, 0.4))
        score = float(np.clip(raw_score, baseline_score - max_delta, baseline_score + max_delta))
        score = float(np.clip(score, 0, 1))

        risk = visible_factors.get("risk", 0.5)
        data_quality_proxy = float(np.clip((fund.data_quality * 0.45 + news.data_quality * 0.25 + visible_factors.get("volatility_control", 0.5) * 0.3), 0, 1))
        if raw_action == "buy" and (baseline_score < 0.46 or risk < 0.28 or data_quality_proxy < 0.28):
            score = min(score, 0.63)
        if raw_action == "sell" and baseline_score > 0.72 and risk > 0.55:
            score = max(score, 0.42)

        action = self._action_from_score(score)
        confidence = float(np.clip(raw_confidence, baseline_confidence - 0.16, baseline_confidence + 0.16))
        confidence = float(np.clip(confidence, 0.2, 0.98))
        reason = self._clean_reason(decision.get("reason"), fallback_reason)
        if action != raw_action:
            reason = f"{reason} 护栏校验后，观点调整为{self._action_label(action)}。"
        return action, score, confidence, reason

    def _coerce_unit_float(self, value: object, default: float) -> float:
        try:
            return float(np.clip(float(value), 0, 1))
        except (TypeError, ValueError):
            return float(default)

    def _clean_reason(self, value: object, fallback: str) -> str:
        text = " ".join(str(value or "").split())
        if not text:
            return fallback
        return text[:220]

    def _action_label(self, action: str) -> str:
        return {"buy": "买入", "hold": "持有", "sell": "卖出"}.get(action, "持有")

    def _score_buffett(self, f: FactorMap) -> float:
        moat = min(f.get("quality", 0), f.get("cashflow", 0) * 1.08)
        return float(np.clip(0.38 * moat + 0.26 * f.get("value", 0) + 0.16 * f.get("risk", 0) + 0.12 * f.get("growth", 0) + 0.08 * f.get("quality", 0), 0, 1))

    def _score_graham(self, f: FactorMap) -> float:
        margin = min(f.get("value", 0), f.get("risk", 0))
        quality_floor = 0.75 if f.get("quality", 0) >= 0.42 else 0.55
        return float(np.clip((0.58 * margin + 0.26 * f.get("value", 0) + 0.16 * f.get("cashflow", 0)) * quality_floor, 0, 1))

    def _score_lynch(self, f: FactorMap) -> float:
        garp = f.get("growth", 0) * (0.55 + 0.45 * f.get("value", 0))
        return float(np.clip(0.42 * garp + 0.22 * f.get("quality", 0) + 0.18 * f.get("sentiment", 0) + 0.18 * f.get("momentum", 0), 0, 1))

    def _score_soros(self, f: FactorMap) -> float:
        reflexive = f.get("technical", 0) * 0.42 + f.get("sentiment", 0) * 0.34 + f.get("event_heat", 0) * 0.18
        risk_gate = 0.72 + 0.28 * f.get("risk", 0)
        return float(np.clip(reflexive * risk_gate + 0.06 * f.get("momentum", 0), 0, 1))

    def _score_dalio(self, f: FactorMap) -> float:
        balance = 1 - float(np.std([f.get("quality", 0), f.get("value", 0), f.get("growth", 0), f.get("technical", 0)]))
        return float(np.clip(0.34 * f.get("risk", 0) + 0.24 * f.get("quality", 0) + 0.16 * f.get("value", 0) + 0.12 * f.get("growth", 0) + 0.08 * f.get("volatility_control", 0) + 0.06 * balance, 0, 1))

    def _score_templeton(self, f: FactorMap) -> float:
        contrarian_value = f.get("value", 0) * (0.72 + 0.28 * f.get("sentiment_contrarian", 0))
        return float(np.clip(0.42 * contrarian_value + 0.22 * f.get("risk", 0) + 0.18 * f.get("quality", 0) + 0.1 * f.get("growth", 0) + 0.08 * f.get("sentiment_contrarian", 0), 0, 1))

    def _confidence(self, style: MasterStyle, score: float, visible_factors: FactorMap) -> float:
        preferred = [visible_factors[key] for key in style.factor_preference if key in visible_factors]
        coverage = len(preferred) / max(len(style.factor_preference), 1)
        conviction = abs(score - 0.5)
        dispersion = float(np.std(list(visible_factors.values()))) if visible_factors else 0.5
        return float(np.clip(0.42 + conviction * 0.72 + coverage * 0.12 - dispersion * 0.08 + style.risk_aversion * 0.04, 0.32, 0.95))

    def _reason(
        self,
        style: MasterStyle,
        symbol: str,
        visible_factors: FactorMap,
        score: float,
        tech: TechnicalSignal,
        fund: FundamentalSignal,
        news: NewsSignal,
    ) -> str:
        llm_reason = self._llm_reason(style, symbol, visible_factors, score, tech, fund, news)
        if llm_reason:
            return llm_reason
        preferred_factors = self._preferred_factors(style, visible_factors)
        strongest = sorted(preferred_factors.items(), key=lambda item: item[1], reverse=True)[:2]
        weakest = sorted(preferred_factors.items(), key=lambda item: item[1])[:1]
        strong_text = "、".join(f"{key}={value:.2f}" for key, value in strongest) or "可见证据不足"
        weak_text = f"{weakest[0][0]}={weakest[0][1]:.2f}" if weakest else "无明显短板"
        preferred = sorted(style.factor_preference.items(), key=lambda item: item[1], reverse=True)[:3]
        preference_text = "、".join(key for key, _ in preferred)
        return f"{style.name} 能看到全部因子，但明显偏向 {preference_text}。对 {symbol} 的独立评分为 {score:.2f}，主要支撑为 {strong_text}；短板为 {weak_text}。"

    def _llm_reason(
        self,
        style: MasterStyle,
        symbol: str,
        visible_factors: FactorMap,
        score: float,
        tech: TechnicalSignal,
        fund: FundamentalSignal,
        news: NewsSignal,
    ) -> str | None:
        if not self.llm.enabled:
            return None
        prompt = (
            "请按该大师的独立人格给出中文投资理由。"
            "要求：80-140字，只输出最终理由，不输出思考过程；你能看到所有因子，但必须明显体现该大师的风格偏好，"
            "不得编造未提供事实。\n"
            f"大师：{style.name}\n哲学：{style.philosophy}\n股票：{symbol}\n"
            f"独立评分：{score:.3f}\n全部因子：{visible_factors}\n风格因子偏好：{style.factor_preference}\n"
            f"技术原始数据：RSI={tech.rsi}, 技术分={tech.score}, 动量={tech.momentum}\n"
            f"财务原始数据：PE={fund.pe}, PB={fund.pb}, ROE={fund.roe}, 增长={fund.growth}, 财务分={fund.score}\n"
            f"新闻原始数据：情绪={news.sentiment}, 热度={news.event_heat}, 摘要={news.summary}"
        )
        try:
            return self.llm.complete(
                [
                    LLMMessage(role="system", content=style.system_prompt),
                    LLMMessage(role="user", content=prompt),
                ],
                temperature=0.25,
            )
        except Exception:
            return None
