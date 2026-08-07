from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd


@dataclass
class MarketSnapshot:
    code: str
    timestamp: datetime
    last_price: float
    prev_close: float
    open_price: float
    high_price: float
    low_price: float
    volume: float
    turnover: float
    bid_price: float | None = None
    ask_price: float | None = None
    bid_volume: float = 0.0
    ask_volume: float = 0.0
    vwap: float | None = None
    daily_bars: pd.DataFrame = field(default_factory=pd.DataFrame, repr=False)
    minute_bars: pd.DataFrame = field(default_factory=pd.DataFrame, repr=False)
    benchmark_changes: dict[str, float] = field(default_factory=dict)
    benchmark_bars: dict[str, pd.DataFrame] = field(default_factory=dict, repr=False)
    iopv: float | None = None
    premium_pct: float | None = None
    fund_shares: float | None = None
    fund_share_change_pct: float | None = None
    market_field_status: dict[str, dict[str, Any]] = field(default_factory=dict)
    source: str = "unknown"

    @property
    def change_pct(self) -> float:
        if self.prev_close <= 0:
            return 0.0
        return (self.last_price / self.prev_close - 1.0) * 100.0


@dataclass
class StaticFactors:
    as_of: str
    bond_10y_yield_pct: float
    dividend_yield_pct: float
    earnings_yield_pct: float
    pb_percentile_pct: float
    pe_percentile_pct: float
    market_environment_score: float
    source_note: str = ""
    data_quality: int = 50
    field_as_of: dict[str, str] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)
    quality_detail: dict[str, Any] = field(default_factory=dict)
    valuation_proxy: str = ""
    valuation_history_count: int = 0

    @property
    def dividend_spread_pct(self) -> float:
        return self.dividend_yield_pct - self.bond_10y_yield_pct

    @property
    def erp_pct(self) -> float:
        return self.earnings_yield_pct - self.bond_10y_yield_pct


@dataclass
class ScoreResult:
    timestamp: datetime
    code: str
    source: str
    last_price: float
    change_pct: float
    strategic_score: float
    tactical_score: float
    comprehensive_score: float
    buy_signal: float
    sell_signal: float
    intraday_t_signal: float
    position_pct: float
    oversold_bonus: float
    data_quality: int
    factors: dict[str, float]
    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data
