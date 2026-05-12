from typing import Literal

from pydantic import BaseModel, Field, field_validator


Action = Literal["buy", "hold", "sell"]


class AnalyzeRequest(BaseModel):
    symbols: list[str] = Field(..., min_length=1, max_length=6)
    capital: int = Field(..., ge=10_000, le=10_000_000)

    @field_validator("symbols")
    @classmethod
    def normalize_symbols(cls, symbols: list[str]) -> list[str]:
        cleaned = []
        for symbol in symbols:
            value = symbol.strip().upper()
            if value and value not in cleaned:
                cleaned.append(value)
        if not cleaned:
            raise ValueError("至少输入一支股票")
        if len(cleaned) > 6:
            raise ValueError("股票数量最多 6 支")
        return cleaned


class PriceSnapshot(BaseModel):
    symbol: str
    name: str
    close: float
    change_pct: float
    volume_ratio: float
    volatility: float
    price_source: str = "unknown"
    data_quality: float = 1.0


class TechnicalSignal(BaseModel):
    symbol: str
    ma_trend: float
    rsi: float
    bollinger_position: float
    momentum: float
    volume_signal: float
    score: float


class FundamentalSignal(BaseModel):
    symbol: str
    pe: float
    pb: float
    roe: float
    cashflow_coverage: float
    growth: float
    score: float
    data_quality: float = 1.0


class NewsSignal(BaseModel):
    symbol: str
    sentiment: float
    event_heat: float
    summary: str
    score: float
    data_quality: float = 1.0


class MasterOpinion(BaseModel):
    master: str
    philosophy: str
    system_prompt: str = ""
    symbol: str
    factors: dict[str, float]
    visible_factors: dict[str, float] = Field(default_factory=dict)
    preferred_factors: dict[str, float] = Field(default_factory=dict)
    factor_whitelist: list[str] = Field(default_factory=list)
    banned_factors: list[str] = Field(default_factory=list)
    style_prior: dict[str, float] = Field(default_factory=dict)
    action: Action
    confidence: float
    score: float
    revised_score: float | None = None
    revised_confidence: float | None = None
    reason: str


class DebateRound(BaseModel):
    round_name: str
    speaker: str
    opponent: str = ""
    target_symbol: str
    stance: Action
    argument: str
    attack_strength: float = 0.0
    defense_strength: float = 0.0
    confidence_delta: float
    factor_delta: dict[str, float] = Field(default_factory=dict)
    revised_score: float | None = None
    revised_confidence: float | None = None
    style_distance: float = 0.0


class PortfolioPosition(BaseModel):
    symbol: str
    name: str
    action: Action
    weight: float
    amount: float
    shares: int = 0
    alpha: float = 0.0
    risk_penalty: float = 0.0
    final_score: float = 0.0
    disagreement: float = 0.0
    data_quality: float = 1.0
    rationale: str


class AnalyzeResponse(BaseModel):
    request: AnalyzeRequest
    prices: list[PriceSnapshot]
    technical_signals: list[TechnicalSignal]
    fundamental_signals: list[FundamentalSignal]
    news_signals: list[NewsSignal]
    master_opinions: list[MasterOpinion]
    debate: list[DebateRound]
    portfolio: list[PortfolioPosition]
    cash: float
    summary: str
