from __future__ import annotations

import numpy as np
import pandas as pd

from app.models.schemas import FundamentalSignal, NewsSignal, TechnicalSignal


class MarketTechnicalAgent:
    def analyze(self, history: dict[str, pd.DataFrame]) -> list[TechnicalSignal]:
        signals: list[TechnicalSignal] = []
        for symbol, hist in history.items():
            close = hist["close"].astype(float)
            volume = hist["volume"].astype(float)
            ma20 = close.rolling(20).mean()
            ma60 = close.rolling(60).mean()
            trend = float(np.clip((ma20.iloc[-1] / ma60.iloc[-1] - 1) * 8 + 0.5, 0, 1))
            rsi = self._rsi(close).iloc[-1]
            upper, lower = self._bollinger(close)
            bollinger_position = float(np.clip((close.iloc[-1] - lower.iloc[-1]) / max(upper.iloc[-1] - lower.iloc[-1], 0.01), 0, 1))
            momentum = float(np.clip(close.pct_change(20).iloc[-1] * 4 + 0.5, 0, 1))
            volume_signal = float(np.clip(volume.iloc[-1] / max(volume.tail(20).mean(), 1) / 2, 0, 1))
            rsi_score = float(1 - abs(rsi - 55) / 55)
            score = float(np.clip(trend * 0.32 + rsi_score * 0.22 + bollinger_position * 0.16 + momentum * 0.2 + volume_signal * 0.1, 0, 1))
            signals.append(
                TechnicalSignal(
                    symbol=symbol,
                    ma_trend=round(trend, 3),
                    rsi=round(float(rsi), 2),
                    bollinger_position=round(bollinger_position, 3),
                    momentum=round(momentum, 3),
                    volume_signal=round(volume_signal, 3),
                    score=round(score, 3),
                )
            )
        return signals

    def _rsi(self, close: pd.Series, period: int = 14) -> pd.Series:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = -delta.clip(upper=0).rolling(period).mean()
        rs = gain / loss.replace(0, np.nan)
        return (100 - 100 / (1 + rs)).fillna(50)

    def _bollinger(self, close: pd.Series) -> tuple[pd.Series, pd.Series]:
        ma = close.rolling(20).mean()
        std = close.rolling(20).std().fillna(0)
        return ma + 2 * std, ma - 2 * std


class FundamentalAgent:
    def analyze(self, fundamentals: list[FundamentalSignal]) -> list[FundamentalSignal]:
        return fundamentals


class NewsSentimentAgent:
    def analyze(self, news: list[NewsSignal]) -> list[NewsSignal]:
        return news
