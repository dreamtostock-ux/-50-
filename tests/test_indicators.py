import numpy as np
import pandas as pd

from dividend_etf_score.indicators import enrich, intraday_vwap


def sample_bars(n=300):
    close = np.linspace(1.0, 1.3, n)
    volume = np.linspace(1000, 2000, n)
    return pd.DataFrame({
        "open": close - 0.001, "high": close + 0.005, "low": close - 0.005,
        "close": close, "volume": volume, "turnover": close * volume,
    }, index=pd.date_range("2025-01-01", periods=n, freq="D"))


def test_all_indicators_are_produced():
    result = enrich(sample_bars())
    expected = {"ma20", "ma120", "ema12", "macd", "rsi14", "kdj_j", "boll_lower", "atr14", "volatility20_pct"}
    assert expected.issubset(result.columns)
    assert 0 <= result.iloc[-1].rsi14 <= 100


def test_vwap_is_volume_weighted():
    bars = sample_bars(5)
    value = intraday_vwap(bars)
    assert float(bars.low.min()) <= value <= float(bars.high.max())
