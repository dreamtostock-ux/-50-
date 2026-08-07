from __future__ import annotations

from datetime import date, datetime, time, timedelta

from .data_sources import MarketDataSource
from .models import ScoreResult
from .scoring import ScoringModel
from .static_data import StaticFactorProvider


class DualLayerEngine:
    """战略层按交易日缓存；战术层每个 tick 重新计算。"""

    def __init__(self, source: MarketDataSource, static_provider: StaticFactorProvider, model: ScoringModel, refresh_time: str = "15:05"):
        self.source = source
        self.static_provider = static_provider
        self.model = model
        self._strategic_day: date | None = None
        self._strategic_cache = None
        self._static = None
        hour, minute = (int(part) for part in refresh_time.split(":"))
        self._refresh_time = time(hour, minute)

    def _strategic_period(self, timestamp: datetime) -> date:
        """15:05 后进入当日战略周期；盘中继续使用上一收盘周期。"""
        if timestamp.time() >= self._refresh_time:
            return timestamp.date()
        return timestamp.date() - timedelta(days=1)

    def refresh_strategic(self, force: bool = False) -> None:
        snapshot = self.source.get_snapshot()
        period = self._strategic_period(snapshot.timestamp)
        if force or self._strategic_day != period or self._strategic_cache is None:
            self._static = self.static_provider.load()
            self._strategic_cache = self.model.strategic(snapshot, self._static)
            self._strategic_day = period

    def tick(self) -> ScoreResult:
        snapshot = self.source.get_snapshot()
        period = self._strategic_period(snapshot.timestamp)
        if self._strategic_day != period or self._strategic_cache is None or self._static is None:
            self._static = self.static_provider.load()
            self._strategic_cache = self.model.strategic(snapshot, self._static)
            self._strategic_day = period
        return self.model.evaluate(snapshot, self._static, self._strategic_cache)
