from __future__ import annotations

import numpy as np
import pandas as pd


def enrich(bars: pd.DataFrame) -> pd.DataFrame:
    """计算系统所需的全部技术指标；输入至少包含 OHLCV。"""
    df = bars.copy().sort_index()
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)

    for window in (5, 10, 20, 60, 120, 250):
        df[f"ma{window}"] = close.rolling(window, min_periods=1).mean()
    for span in (5, 12, 20, 26):
        df[f"ema{span}"] = close.ewm(span=span, adjust=False).mean()

    df["macd"] = df["ema12"] - df["ema26"]
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = (df["macd"] - df["macd_signal"]) * 2

    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["rsi14"] = (100 - 100 / (1 + rs)).fillna(50).clip(0, 100)

    lowest = low.rolling(9, min_periods=1).min()
    highest = high.rolling(9, min_periods=1).max()
    rsv = ((close - lowest) / (highest - lowest).replace(0, np.nan) * 100).fillna(50)
    df["kdj_k"] = rsv.ewm(com=2, adjust=False).mean()
    df["kdj_d"] = df["kdj_k"].ewm(com=2, adjust=False).mean()
    df["kdj_j"] = 3 * df["kdj_k"] - 2 * df["kdj_d"]

    mid = close.rolling(20, min_periods=2).mean()
    std = close.rolling(20, min_periods=2).std(ddof=0)
    df["boll_mid"] = mid
    df["boll_upper"] = mid + 2 * std
    df["boll_lower"] = mid - 2 * std
    df["boll_position"] = ((close - df["boll_lower"]) / (df["boll_upper"] - df["boll_lower"]).replace(0, np.nan)).fillna(0.5)

    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    df["atr14"] = tr.ewm(alpha=1 / 14, adjust=False, min_periods=1).mean()
    df["volatility20_pct"] = close.pct_change().rolling(20, min_periods=5).std(ddof=0).fillna(0) * np.sqrt(252) * 100
    df["volume_ma20"] = df["volume"].rolling(20, min_periods=1).mean()
    return df


def intraday_vwap(bars: pd.DataFrame) -> float:
    if bars.empty:
        return float("nan")
    typical = (bars["high"] + bars["low"] + bars["close"]) / 3.0
    volume = bars["volume"].clip(lower=0)
    total = float(volume.sum())
    return float((typical * volume).sum() / total) if total > 0 else float(bars["close"].iloc[-1])
