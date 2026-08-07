from __future__ import annotations

from datetime import date, datetime
from typing import Any

import numpy as np

from .indicators import enrich
from .models import MarketSnapshot, ScoreResult, StaticFactors


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return float(max(low, min(high, value)))


def step_score(value: float, levels: list[float]) -> float:
    return float(np.interp(value, [levels[0] - (levels[1] - levels[0]), *levels, levels[-1] + (levels[-1] - levels[-2])], [0, 25, 50, 75, 90, 100]))


class ScoringModel:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.thresholds = config["thresholds"]

    @staticmethod
    def _market_environment(snapshot: MarketSnapshot, volatility_pct: float) -> tuple[float, dict[str, float]]:
        """根据沪深300/红利指数趋势、相对强弱和波动率每日自动计算。"""
        trend_scores: dict[str, float] = {}
        for key, bars in snapshot.benchmark_bars.items():
            if bars.empty or len(bars) < 20:
                continue
            close = bars["close"].astype(float)
            last = float(close.iloc[-1])
            ma20 = float(close.tail(20).mean())
            ma60 = float(close.tail(min(60, len(close))).mean())
            trend_scores[key] = clamp(50 + (last / ma20 - 1) * 350 + (ma20 / ma60 - 1) * 250)
        dividend_trend = trend_scores.get("dividend", 50.0)
        csi300_trend = trend_scores.get("csi300", 50.0)
        relative = snapshot.benchmark_changes.get("dividend", 0.0) - snapshot.benchmark_changes.get("csi300", 0.0)
        volatility_guard = max(0.0, volatility_pct - 16.0) * 0.7
        score = clamp(dividend_trend * 0.55 + csi300_trend * 0.30 + clamp(50 + relative * 12) * 0.15 - volatility_guard)
        return score, {
            "market_env_dividend_trend": dividend_trend,
            "market_env_csi300_trend": csi300_trend,
            "market_env_relative_pct": relative,
            "market_env_volatility_guard": volatility_guard,
        }

    @staticmethod
    def _age_score(as_of: str | None, fresh_days: int) -> float:
        if not as_of:
            return 0.0
        try:
            age = max(0, (date.today() - datetime.strptime(as_of[:10], "%Y-%m-%d").date()).days)
        except (ValueError, TypeError):
            return 0.0
        if age <= fresh_days:
            return 100.0
        return clamp(100 - (age - fresh_days) * 2.5)

    def _quality(self, snapshot: MarketSnapshot, static: StaticFactors) -> tuple[int, dict[str, Any]]:
        today = snapshot.timestamp.date().isoformat()
        fields = {
            "实时行情": (True, today, 1, 98.0),
            "基准指数历史": (bool(snapshot.benchmark_bars), today, 1, 96.0),
            "10年国债": (static.bond_10y_yield_pct > 0, static.field_as_of.get("bond_10y_yield_pct"), 5, 100.0),
            "股息率": (static.dividend_yield_pct > 0, static.field_as_of.get("dividend_yield_pct"), 45, 68.0),
            "PE及盈利收益率": (static.earnings_yield_pct > 0, static.field_as_of.get("pe_percentile_pct"), 2, 84.0),
            "PB历史分位": (static.pb_percentile_pct >= 0, static.field_as_of.get("pb_percentile_pct"), 2, 84.0),
            "市场环境": (bool(snapshot.benchmark_bars), today, 1, 96.0),
            "IOPV折溢价": (snapshot.premium_pct is not None, today if snapshot.premium_pct is not None else None, 1, 90.0),
            "ETF总份额": (snapshot.fund_shares is not None, today if snapshot.fund_shares is not None else None, 2, 78.0),
            "份额变化": (snapshot.fund_share_change_pct is not None, today if snapshot.fund_share_change_pct is not None else None, 2, 72.0),
        }
        completeness = sum(1 for available, *_ in fields.values() if available) / len(fields) * 100
        freshness_values = [self._age_score(as_of, days) if available else 0.0 for available, as_of, days, _ in fields.values()]
        source_values = [grade if available else 0.0 for available, _, _, grade in fields.values()]
        freshness = float(np.mean(freshness_values))
        source_quality = float(np.mean(source_values))
        exactness_penalty = 5 if not static.quality_detail.get("exact_tracking_index_valuation_available", False) else 0
        overall = int(round(completeness * 0.40 + freshness * 0.30 + source_quality * 0.30 - exactness_penalty))
        return overall, {
            "overall": overall,
            "completeness": round(completeness, 1),
            "freshness": round(freshness, 1),
            "source_quality": round(source_quality, 1),
            "exactness_penalty": exactness_penalty,
            "available_fields": sum(1 for available, *_ in fields.values() if available),
            "total_fields": len(fields),
            "field_status": {name: {"available": available, "as_of": as_of, "source_grade": grade}
                             for name, (available, as_of, _, grade) in fields.items()},
            "provider": static.quality_detail,
        }

    def strategic(self, snapshot: MarketSnapshot, static: StaticFactors) -> tuple[float, dict[str, float], dict[str, float]]:
        daily = enrich(snapshot.daily_bars)
        last = daily.iloc[-1]
        price = snapshot.last_price
        ma120 = float(last["ma120"])
        ma250 = float(last["ma250"])
        trend = clamp(50 + (price / ma120 - 1) * 400 + (ma120 / ma250 - 1) * 300)
        daily_rsi14 = float(last["rsi14"])
        daily_rsi_score = clamp(150 - 2 * daily_rsi14)
        if price < ma250 and ma120 < ma250:
            daily_rsi_score = min(daily_rsi_score, 65.0)
        volatility_pct = float(last["volatility20_pct"])
        market_environment, market_detail = self._market_environment(snapshot, volatility_pct)
        static.market_environment_score = market_environment
        static.field_as_of["market_environment_score"] = snapshot.timestamp.date().isoformat()
        static.sources["market_environment_score"] = "Futu沪深300/中证红利日K + 515450二十日波动率"
        factors = {
            "dividend_spread": step_score(static.dividend_spread_pct, self.thresholds["dividend_spread_pct"]),
            "erp": step_score(static.erp_pct, self.thresholds["erp_pct"]),
            "pb_percentile": clamp(100 - static.pb_percentile_pct),
            "pe_percentile": clamp(100 - static.pe_percentile_pct),
            "dividend_yield": step_score(static.dividend_yield_pct, self.thresholds["dividend_yield_pct"]),
            "daily_rsi": daily_rsi_score,
            "long_trend": trend,
            "market_environment": clamp(static.market_environment_score),
        }
        weights = self.config["engine"]["strategic_factors"]
        score = sum(factors[k] * float(weights[k]) for k in weights) / sum(map(float, weights.values()))
        diagnostics = {
            "bond_10y_yield_pct": static.bond_10y_yield_pct,
            "dividend_yield_pct": static.dividend_yield_pct,
            "dividend_spread_pct": static.dividend_spread_pct,
            "earnings_yield_pct": static.earnings_yield_pct,
            "erp_pct": static.erp_pct,
            "pb_percentile_pct": static.pb_percentile_pct,
            "pe_percentile_pct": static.pe_percentile_pct,
            "daily_rsi14": daily_rsi14, "daily_rsi_score": daily_rsi_score,
            "ma120": ma120, "ma250": ma250, "market_environment_score": market_environment,
            **market_detail,
        }
        return clamp(score), factors, diagnostics

    def tactical(self, snapshot: MarketSnapshot) -> tuple[float, float, dict[str, float], dict[str, float]]:
        daily = enrich(snapshot.daily_bars)
        minute = enrich(snapshot.minute_bars)
        dlast, mlast = daily.iloc[-1], minute.iloc[-1]
        price = snapshot.last_price
        rsi = float(mlast["rsi14"])
        k = float(mlast["kdj_k"])
        j = float(mlast["kdj_j"])
        macd_hist = float(mlast["macd_hist"])
        macd_scale = max(abs(float(mlast["close"])) * 0.001, 1e-9)
        boll_pos = float(mlast["boll_position"])
        vwap = float(snapshot.vwap or price)
        vwap_dev = (price / vwap - 1) * 100 if vwap else 0.0
        benchmark = np.mean(list(snapshot.benchmark_changes.values())) if snapshot.benchmark_changes else 0.0
        relative = snapshot.change_pct - float(benchmark)
        book_total = snapshot.bid_volume + snapshot.ask_volume
        imbalance = (snapshot.bid_volume - snapshot.ask_volume) / book_total if book_total > 0 else 0.0

        factors = {
            "rsi": clamp((55 - rsi) * 2.2),
            "macd": clamp(50 + macd_hist / macd_scale * 35),
            "kdj": clamp(70 - 0.45 * k - 0.15 * j),
            "boll": clamp((1.0 - boll_pos) * 100),
            "vwap_deviation": clamp(50 - vwap_dev / float(self.thresholds["vwap_scale_pct"]) * 50),
            "intraday_change": clamp(50 - snapshot.change_pct * 15),
            "relative_anomaly": clamp(50 - relative / float(self.thresholds["relative_anomaly_scale_pct"]) * 50),
            "orderbook": clamp(50 + imbalance * 100),
        }
        weights = self.config["engine"]["tactical_factors"]
        score = sum(factors[k] * float(weights[k]) for k in weights) / sum(map(float, weights.values()))

        ma20 = float(dlast["ma20"])
        ma20_dev = (price / ma20 - 1) * 100 if ma20 else 0.0
        avg_volume = float(dlast["volume_ma20"])
        estimated_day_volume = snapshot.volume
        volume_ratio = estimated_day_volume / avg_volume if avg_volume else 1.0
        bonus = 0.0
        if volume_ratio <= float(self.thresholds["heavy_volume_ratio"]):
            for threshold, points in zip(self.thresholds["oversold_ma20_pct"], self.thresholds["oversold_bonus"]):
                if ma20_dev <= float(threshold):
                    bonus = float(points)
        bonus = min(bonus, float(self.thresholds["oversold_max_bonus"]))
        diagnostics = {
            "rsi14": rsi, "intraday_rsi14": rsi, "kdj_k": k, "kdj_j": j, "macd_hist": macd_hist,
            "boll_position": boll_pos, "vwap": vwap, "vwap_deviation_pct": vwap_dev,
            "relative_change_pct": relative, "orderbook_imbalance": imbalance,
            "ma20": ma20, "ma20_deviation_pct": ma20_dev, "volume_ratio": volume_ratio,
            "atr14": float(dlast["atr14"]), "volatility20_pct": float(dlast["volatility20_pct"]),
        }
        return clamp(score + bonus), bonus, factors, diagnostics

    def evaluate(self, snapshot: MarketSnapshot, static: StaticFactors, cached_strategic: tuple[float, dict[str, float], dict[str, float]] | None = None) -> ScoreResult:
        strategic, sf, sd = cached_strategic or self.strategic(snapshot, static)
        tactical, bonus, tf, td = self.tactical(snapshot)
        sw = float(self.config["engine"]["strategic_weight"])
        tw = float(self.config["engine"]["tactical_weight"])
        comprehensive = clamp((strategic * sw + tactical * tw) / (sw + tw))
        buy = clamp(strategic * 0.55 + tactical * 0.45 + bonus * 0.25)
        overbought = clamp((td["rsi14"] - 60) * 2.5 + max(td["vwap_deviation_pct"], 0) * 12 + max(snapshot.change_pct, 0) * 7)
        sell = clamp((100 - strategic) * 0.45 + overbought * 0.55)
        t_signal = clamp(tf["vwap_deviation"] * 0.35 + tf["relative_anomaly"] * 0.30 + tf["intraday_change"] * 0.20 + tf["orderbook"] * 0.15 + bonus)
        position = 0.0
        for min_score, pct in self.thresholds["position_bands"]:
            if comprehensive >= float(min_score):
                position = float(pct)
                break
        data_quality, quality_detail = self._quality(snapshot, static)
        return ScoreResult(
            timestamp=snapshot.timestamp, code=snapshot.code, source=snapshot.source,
            last_price=round(snapshot.last_price, 4), change_pct=round(snapshot.change_pct, 3),
            strategic_score=round(strategic, 2), tactical_score=round(tactical, 2),
            comprehensive_score=round(comprehensive, 2), buy_signal=round(buy, 2),
            sell_signal=round(sell, 2), intraday_t_signal=round(t_signal, 2),
            position_pct=position, oversold_bonus=bonus, data_quality=data_quality,
            factors={**sf, **{f"tactical_{k}": v for k, v in tf.items()}},
            diagnostics={
                **sd, **td,
                "iopv": snapshot.iopv,
                "premium_pct": snapshot.premium_pct,
                "fund_shares": snapshot.fund_shares,
                "fund_share_change_pct": snapshot.fund_share_change_pct,
                "valuation_proxy": static.valuation_proxy,
                "valuation_history_count": static.valuation_history_count,
                "static_as_of": static.as_of,
                "static_source_note": static.source_note,
                "field_as_of": static.field_as_of,
                "sources": static.sources,
                "market_field_status": snapshot.market_field_status,
                "quality_detail": quality_detail,
            },
        )
