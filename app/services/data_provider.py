from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import pandas as pd

from app.config import get_settings
from app.models.schemas import FundamentalSignal, NewsSignal, PriceSnapshot
from app.services.llm_client import LLMClient, LLMMessage


@dataclass(frozen=True)
class MarketDataset:
    prices: list[PriceSnapshot]
    history: dict[str, pd.DataFrame]
    fundamentals: list[FundamentalSignal]
    news: list[NewsSignal]
    data_note: str


class DataProvider:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.llm = LLMClient()

    def load(self, symbols: list[str]) -> MarketDataset:
        if self.settings.enable_akshare:
            try:
                return self._load_from_akshare(symbols)
            except Exception:
                pass
        return self._load_mock(symbols)

    def resolve_symbols(self, symbols: list[str]) -> list[str]:
        resolved: list[str] = []
        for symbol in symbols:
            code = self._resolve_symbol(symbol)
            if code not in resolved:
                resolved.append(code)
        return resolved

    def _resolve_symbol(self, symbol: str) -> str:
        value = symbol.strip().upper()
        numeric = self._normalize_a_share_code(value)
        if numeric.isdigit() and len(numeric) == 6:
            return numeric
        static_names = {
            "贵州茅台": "600519",
            "平安银行": "000001",
            "宁德时代": "300750",
            "万科A": "000002",
            "万 科Ａ": "000002",
            "招商银行": "600036",
            "比亚迪": "002594",
        }
        compact = value.replace(" ", "").replace("　", "")
        if compact in static_names:
            return static_names[compact]
        if self.settings.enable_akshare:
            try:
                code = self._resolve_symbol_from_akshare(compact)
                if code:
                    return code
            except Exception:
                pass
        return value

    @staticmethod
    @lru_cache(maxsize=1)
    def _a_share_code_name_table() -> dict[str, str]:
        import akshare as ak

        df = ak.stock_info_a_code_name()
        mapping: dict[str, str] = {}
        for _, row in df.iterrows():
            code = str(row.get("code", "")).strip()
            name = str(row.get("name", "")).strip()
            if code and name:
                mapping[name.upper().replace(" ", "").replace("　", "")] = code
        return mapping

    def _resolve_symbol_from_akshare(self, compact_name: str) -> str | None:
        mapping = self._a_share_code_name_table()
        if compact_name in mapping:
            return mapping[compact_name]
        matches = [(name, code) for name, code in mapping.items() if compact_name and compact_name in name]
        if len(matches) == 1:
            return matches[0][1]
        return None

    def _load_from_akshare(self, symbols: list[str]) -> MarketDataset:
        import akshare as ak

        prices: list[PriceSnapshot] = []
        history: dict[str, pd.DataFrame] = {}
        fundamentals: list[FundamentalSignal] = []
        news: list[NewsSignal] = []
        notes = ["AKShare 近4季度财务指标 + 近半年研报/近3个月新闻"]

        for symbol in symbols:
            code = self._normalize_a_share_code(symbol)
            hist, price_source, price_quality = self._akshare_price_history(ak, symbol, code)
            notes.append(f"{symbol} 行情:{price_source}")

            latest = hist.iloc[-1]
            volume_ratio = float(latest["volume"] / max(hist["volume"].tail(20).mean(), 1))
            volatility = float(hist["close"].pct_change().tail(30).std() * math.sqrt(252))
            prices.append(
                PriceSnapshot(
                    symbol=symbol,
                    name=self._akshare_stock_name(ak, code) or code,
                    close=float(latest["close"]),
                    change_pct=float(latest.get("change_pct", 0)),
                    volume_ratio=volume_ratio,
                    volatility=volatility,
                    price_source=price_source,
                    data_quality=price_quality,
                )
            )
            history[symbol] = hist
            fundamentals.append(self._akshare_fundamental(ak, symbol, code, hist))
            news.append(self._akshare_news_signal(ak, symbol, code, hist))

        return MarketDataset(prices, history, fundamentals, news, "；".join(dict.fromkeys(notes)))

    def _akshare_price_history(self, ak, symbol: str, code: str) -> tuple[pd.DataFrame, str, float]:
        attempts = [
            ("东方财富日线", lambda: self._eastmoney_price_history(ak, code)),
            ("腾讯日线", lambda: self._tencent_price_history(ak, code)),
            ("新浪日线", lambda: self._sina_price_history(ak, code)),
        ]
        errors: list[str] = []
        for source, loader in attempts:
            try:
                hist = loader()
                hist = self._normalize_price_history(hist)
                if len(hist) < 30:
                    raise ValueError(f"only {len(hist)} rows")
                quality = 1.0 if source == "东方财富日线" else 0.92 if source == "腾讯日线" else 0.86
                return hist, source, quality
            except Exception as exc:
                errors.append(f"{source}: {type(exc).__name__}")
        return self._mock_history(symbol), f"本地模拟({'; '.join(errors)})", 0.35

    def _eastmoney_price_history(self, ak, code: str) -> pd.DataFrame:
        end_date = pd.Timestamp.today().strftime("%Y%m%d")
        start_date = (pd.Timestamp.today() - pd.DateOffset(months=9)).strftime("%Y%m%d")
        return ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust="qfq",
            timeout=12,
        ).rename(
            columns={
                "日期": "date",
                "开盘": "open",
                "收盘": "close",
                "最高": "high",
                "最低": "low",
                "成交量": "volume",
                "涨跌幅": "change_pct",
            }
        )

    def _tencent_price_history(self, ak, code: str) -> pd.DataFrame:
        end_date = pd.Timestamp.today().strftime("%Y%m%d")
        start_date = (pd.Timestamp.today() - pd.DateOffset(months=9)).strftime("%Y%m%d")
        return ak.stock_zh_a_hist_tx(
            symbol=self._with_exchange_prefix(code),
            start_date=start_date,
            end_date=end_date,
            adjust="qfq",
            timeout=12,
        ).rename(columns={"amount": "volume"})

    def _sina_price_history(self, ak, code: str) -> pd.DataFrame:
        end_date = pd.Timestamp.today().strftime("%Y%m%d")
        start_date = (pd.Timestamp.today() - pd.DateOffset(months=9)).strftime("%Y%m%d")
        return ak.stock_zh_a_daily(
            symbol=self._with_exchange_prefix(code),
            start_date=start_date,
            end_date=end_date,
            adjust="qfq",
        ).rename(columns={"date": "date", "volume": "volume"})

    def _normalize_price_history(self, hist: pd.DataFrame) -> pd.DataFrame:
        if hist.empty:
            raise ValueError("empty price history")
        work = hist.copy().tail(180)
        required = ["date", "open", "close", "high", "low"]
        for column in required:
            if column not in work:
                raise ValueError(f"missing {column}")
        if "volume" not in work:
            work["volume"] = 1
        work["date"] = pd.to_datetime(work["date"], errors="coerce")
        for column in ["open", "close", "high", "low", "volume"]:
            work[column] = pd.to_numeric(work[column], errors="coerce")
        if "change_pct" not in work:
            work["change_pct"] = work["close"].pct_change().fillna(0) * 100
        else:
            work["change_pct"] = pd.to_numeric(work["change_pct"], errors="coerce")
            work["change_pct"] = work["change_pct"].fillna(work["close"].pct_change().fillna(0) * 100)
        work = work.dropna(subset=["date", "open", "close", "high", "low", "volume"])
        return work.sort_values("date").reset_index(drop=True)

    def _load_mock(self, symbols: list[str]) -> MarketDataset:
        prices: list[PriceSnapshot] = []
        history: dict[str, pd.DataFrame] = {}
        fundamentals: list[FundamentalSignal] = []
        news: list[NewsSignal] = []

        for symbol in symbols:
            hist = self._mock_history(symbol)
            latest = hist.iloc[-1]
            history[symbol] = hist
            prices.append(
                PriceSnapshot(
                    symbol=symbol,
                    name=f"{symbol} 模拟",
                    close=round(float(latest["close"]), 2),
                    change_pct=round(float(latest["change_pct"]), 2),
                    volume_ratio=round(float(latest["volume"] / hist["volume"].tail(20).mean()), 2),
                    volatility=round(float(hist["close"].pct_change().tail(30).std() * math.sqrt(252)), 3),
                    price_source="本地模拟",
                    data_quality=0.35,
                )
            )
            fundamentals.append(self._mock_fundamental(symbol, hist))
            news.append(self._mock_news(symbol, hist, suffix="当前为离线演示数据，接入 API 后会替换为真实新闻。"))

        return MarketDataset(prices, history, fundamentals, news, "离线确定性模拟数据")

    def _mock_history(self, symbol: str) -> pd.DataFrame:
        rng = np.random.default_rng(self._seed(symbol))
        days = 180
        drift = rng.uniform(-0.0008, 0.0015)
        noise = rng.normal(drift, rng.uniform(0.012, 0.028), days)
        base = rng.uniform(8, 90)
        close = base * np.cumprod(1 + noise)
        high = close * (1 + rng.uniform(0.002, 0.035, days))
        low = close * (1 - rng.uniform(0.002, 0.035, days))
        open_ = close * (1 + rng.normal(0, 0.008, days))
        volume = rng.integers(80_000, 2_800_000, days)
        return pd.DataFrame(
            {
                "date": pd.date_range(end=pd.Timestamp.today(), periods=days),
                "open": open_,
                "close": close,
                "high": high,
                "low": low,
                "volume": volume,
                "change_pct": pd.Series(close).pct_change().fillna(0) * 100,
            }
        )

    def _mock_fundamental(self, symbol: str, hist: pd.DataFrame) -> FundamentalSignal:
        rng = np.random.default_rng(self._seed(symbol, "fundamental"))
        pe = float(rng.uniform(8, 55))
        pb = float(rng.uniform(0.8, 7.5))
        roe = float(rng.uniform(3, 28))
        cashflow = float(rng.uniform(0.35, 2.4))
        growth = float(rng.uniform(-8, 36))
        value_score = 1 - min(pe / 60, 1) * 0.55 - min(pb / 8, 1) * 0.45
        quality_score = min(roe / 30, 1) * 0.6 + min(cashflow / 2.5, 1) * 0.4
        growth_score = max(min((growth + 10) / 50, 1), 0)
        score = float(np.clip(value_score * 0.35 + quality_score * 0.4 + growth_score * 0.25, 0, 1))
        return FundamentalSignal(
            symbol=symbol,
            pe=round(pe, 2),
            pb=round(pb, 2),
            roe=round(roe, 2),
            cashflow_coverage=round(cashflow, 2),
            growth=round(growth, 2),
            score=round(score, 3),
            data_quality=0.35,
        )

    def _akshare_fundamental(self, ak, symbol: str, code: str, hist: pd.DataFrame) -> FundamentalSignal:
        try:
            market_symbol = self._with_market_suffix(code)
            raw = ak.stock_financial_analysis_indicator_em(symbol=market_symbol, indicator="按单季度")
            if raw.empty:
                raise ValueError("empty financial indicators")
            df = raw.copy()
            df["REPORT_DATE"] = pd.to_datetime(df["REPORT_DATE"], errors="coerce")
            df = df.dropna(subset=["REPORT_DATE"]).sort_values("REPORT_DATE", ascending=False).head(4)
            if df.empty:
                raise ValueError("no quarterly financial rows")
            for column in [
                "EPSJB",
                "BPS",
                "PER_NETCASH",
                "TOTALOPERATEREVETZ",
                "PARENTNETPROFITTZ",
                "DPNP_YOY_RATIO",
                "ROE_DILUTED",
            ]:
                if column in df:
                    df[column] = pd.to_numeric(df[column], errors="coerce")

            latest_price = float(hist["close"].iloc[-1])
            eps_ttm = float(df["EPSJB"].fillna(0).sum()) if "EPSJB" in df else 0
            latest_bps = float(df["BPS"].dropna().iloc[0]) if "BPS" in df and not df["BPS"].dropna().empty else 0
            cash_ttm = float(df["PER_NETCASH"].fillna(0).sum()) if "PER_NETCASH" in df else 0
            pe = latest_price / eps_ttm if eps_ttm > 0 else 99.0
            pb = latest_price / latest_bps if latest_bps > 0 else 9.9
            roe = float(df["ROE_DILUTED"].dropna().mean()) if "ROE_DILUTED" in df and not df["ROE_DILUTED"].dropna().empty else 0
            growth_values = []
            for column in ["TOTALOPERATEREVETZ", "PARENTNETPROFITTZ", "DPNP_YOY_RATIO"]:
                if column in df:
                    growth_values.extend(df[column].dropna().astype(float).tolist())
            growth = float(np.clip(np.mean(growth_values), -50, 80)) if growth_values else 0
            cashflow = cash_ttm / max(abs(eps_ttm), 0.1)
            return self._fundamental_signal_from_values(symbol, pe, pb, roe, cashflow, growth, data_quality=1.0)
        except Exception:
            return self._mock_fundamental(symbol, hist)

    def _fundamental_signal_from_values(
        self,
        symbol: str,
        pe: float,
        pb: float,
        roe: float,
        cashflow: float,
        growth: float,
        data_quality: float = 1.0,
    ) -> FundamentalSignal:
        pe = float(np.clip(pe, 0, 120))
        pb = float(np.clip(pb, 0, 20))
        cashflow = float(np.clip(cashflow, -5, 8))
        value_score = 1 - min(pe / 60, 1) * 0.55 - min(pb / 8, 1) * 0.45
        quality_score = min(max(roe, 0) / 30, 1) * 0.6 + min(max(cashflow, 0) / 2.5, 1) * 0.4
        growth_score = max(min((growth + 10) / 50, 1), 0)
        score = float(np.clip(value_score * 0.35 + quality_score * 0.4 + growth_score * 0.25, 0, 1))
        return FundamentalSignal(
            symbol=symbol,
            pe=round(pe, 2),
            pb=round(pb, 2),
            roe=round(roe, 2),
            cashflow_coverage=round(cashflow, 2),
            growth=round(growth, 2),
            score=round(score, 3),
            data_quality=round(data_quality, 3),
        )

    def _mock_news(self, symbol: str, hist: pd.DataFrame, suffix: str) -> NewsSignal:
        rng = np.random.default_rng(self._seed(symbol, "news"))
        trend = float(hist["close"].pct_change(20).iloc[-1])
        sentiment = float(np.clip(0.5 + trend * 2.2 + rng.normal(0, 0.16), 0, 1))
        heat = float(np.clip(abs(trend) * 4 + rng.uniform(0.1, 0.9), 0, 1))
        tone = "偏积极" if sentiment >= 0.6 else "偏谨慎" if sentiment <= 0.42 else "中性"
        return NewsSignal(
            symbol=symbol,
            sentiment=round(sentiment, 3),
            event_heat=round(heat, 3),
            summary=f"{symbol} 近期文本信号{tone}，事件热度 {heat:.2f}。{suffix}",
            score=round(sentiment * 0.7 + heat * 0.3, 3),
            data_quality=0.35,
        )

    def _akshare_news_signal(self, ak, symbol: str, code: str, hist: pd.DataFrame) -> NewsSignal:
        try:
            reports = self._akshare_research_reports(ak, code)
            news_items = self._akshare_news_items(ak, code)
            if not reports and not news_items:
                raise ValueError("no report or news rows")
            sentiment = self._text_sentiment_score(reports, news_items)
            heat = float(np.clip((len(reports) / 6) * 0.45 + (len(news_items) / 10) * 0.55, 0, 1))
            summary = self._llm_news_summary(symbol, reports, news_items, sentiment, heat)
            if not summary:
                report_text = "；".join(item["text"] for item in reports[:3]) or "近半年未取得个股研报"
                news_text = "；".join(item["text"] for item in news_items[:4]) or "近三个月未取得个股新闻"
                summary = (
                    f"研报样本 {len(reports)} 篇：{report_text}。"
                    f"新闻样本 {len(news_items)} 条：{news_text}。"
                )
            return NewsSignal(
                symbol=symbol,
                sentiment=round(sentiment, 3),
                event_heat=round(heat, 3),
                summary=summary,
                score=round(sentiment * 0.72 + heat * 0.28, 3),
                data_quality=round(float(np.clip((len(reports) / 6) * 0.5 + (len(news_items) / 10) * 0.5, 0.2, 1)), 3),
            )
        except Exception:
            return self._mock_news(symbol, hist, suffix="AKShare 文本接口暂不可用，已回退本地文本代理。")

    def _akshare_research_reports(self, ak, code: str) -> list[dict[str, str]]:
        df = ak.stock_research_report_em(symbol=code)
        if df.empty or "日期" not in df:
            return []
        cutoff = pd.Timestamp.today().normalize() - pd.DateOffset(months=6)
        work = df.copy()
        work["日期"] = pd.to_datetime(work["日期"], errors="coerce")
        work = work.dropna(subset=["日期"])
        work = work[work["日期"] >= cutoff].sort_values("日期", ascending=False)
        if work.empty:
            return []
        work["month"] = work["日期"].dt.to_period("M")
        work = work.groupby("month", sort=False).head(1).head(6)
        items = []
        for _, row in work.iterrows():
            date = row["日期"].strftime("%Y-%m-%d")
            rating = self._clean_text(row.get("东财评级", "未评级"))
            org = self._clean_text(row.get("机构", "未知机构"))
            title = self._clean_text(row.get("报告名称", "未命名研报"))
            forecast_pe = row.get("2026-盈利预测-市盈率", "")
            extra = f"，预测PE {forecast_pe}" if pd.notna(forecast_pe) and str(forecast_pe) else ""
            items.append({"date": date, "source": org, "text": f"{date} {org}《{title}》，评级{rating}{extra}"})
        return items

    def _akshare_news_items(self, ak, code: str) -> list[dict[str, str]]:
        df = ak.stock_news_em(symbol=code)
        if df.empty or "发布时间" not in df:
            return []
        cutoff = pd.Timestamp.today().normalize() - pd.DateOffset(months=3)
        work = df.copy()
        work["发布时间"] = pd.to_datetime(work["发布时间"], errors="coerce")
        work = work.dropna(subset=["发布时间"])
        work = work[work["发布时间"] >= cutoff].sort_values("发布时间", ascending=False).head(10)
        items = []
        for _, row in work.iterrows():
            date = row["发布时间"].strftime("%Y-%m-%d")
            source = self._clean_text(row.get("文章来源", "未知来源"))
            title = self._clean_text(row.get("新闻标题", "未命名新闻"))
            content = self._clean_text(row.get("新闻内容", ""))
            excerpt = content[:90]
            items.append({"date": date, "source": source, "text": f"{date} {source}：{title}。{excerpt}"})
        return items

    def _text_sentiment_score(self, reports: list[dict[str, str]], news_items: list[dict[str, str]]) -> float:
        positive = ["买入", "增持", "推荐", "增长", "上涨", "改善", "稳健", "超预期", "突破", "盈利"]
        negative = ["卖出", "减持", "下调", "下降", "下滑", "亏损", "承压", "风险", "不及预期", "处罚"]
        text = "\n".join(item["text"] for item in [*reports, *news_items])
        pos = sum(text.count(word) for word in positive)
        neg = sum(text.count(word) for word in negative)
        return float(np.clip(0.5 + (pos - neg) * 0.045, 0.05, 0.95))

    def _llm_news_summary(
        self,
        symbol: str,
        reports: list[dict[str, str]],
        news_items: list[dict[str, str]],
        sentiment: float,
        heat: float,
    ) -> str | None:
        if not self.llm.enabled:
            return None
        prompt = (
            "请根据AKShare取得的个股研报和新闻样本，生成中文新闻/情绪摘要。"
            "要求：100-180字，只输出最终摘要，不输出思考过程；不得编造样本外事实；"
            "同时点明研报数量、新闻数量、情绪方向和主要风险。\n"
            f"股票：{symbol}\n情绪分：{sentiment:.3f}\n热度：{heat:.3f}\n"
            f"近半年研报（每月最多1篇）：{[item['text'] for item in reports]}\n"
            f"近3个月新闻（最多10条）：{[item['text'] for item in news_items]}"
        )
        try:
            return self.llm.complete(
                [
                    LLMMessage(role="system", content="你是A股新闻情绪分析Agent，只能基于给定样本做摘要。"),
                    LLMMessage(role="user", content=prompt),
                ],
                temperature=0.2,
            )
        except Exception:
            return None

    def _akshare_stock_name(self, ak, code: str) -> str | None:
        try:
            df = ak.stock_individual_info_em(symbol=code, timeout=8)
            row = df[df["item"] == "股票简称"]
            if not row.empty:
                return str(row.iloc[0]["value"])
        except Exception:
            pass
        try:
            report = ak.stock_research_report_em(symbol=code)
            if not report.empty and "股票简称" in report:
                names = report["股票简称"].dropna()
                if not names.empty:
                    return str(names.iloc[0])
        except Exception:
            pass
        try:
            financial = ak.stock_financial_analysis_indicator_em(symbol=self._with_market_suffix(code), indicator="按单季度")
            if not financial.empty and "SECURITY_NAME_ABBR" in financial:
                names = financial["SECURITY_NAME_ABBR"].dropna()
                if not names.empty:
                    return str(names.iloc[0])
        except Exception:
            pass
        return None

    def _normalize_a_share_code(self, symbol: str) -> str:
        return "".join(char for char in symbol if char.isdigit()) or symbol

    def _with_market_suffix(self, code: str) -> str:
        if code.startswith(("0", "3")):
            return f"{code}.SZ"
        if code.startswith(("6", "8", "9")):
            return f"{code}.SH"
        return code

    def _with_exchange_prefix(self, code: str) -> str:
        if code.startswith(("0", "3")):
            return f"sz{code}"
        if code.startswith(("6", "8", "9")):
            return f"sh{code}"
        return code

    def _clean_text(self, value) -> str:
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return ""
        return " ".join(str(value).replace("\n", " ").split())

    def _seed(self, *parts: str) -> int:
        digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
        return int(digest[:16], 16) % (2**32)
