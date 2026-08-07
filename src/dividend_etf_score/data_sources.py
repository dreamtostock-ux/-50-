from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

from .indicators import intraday_vwap
from .models import MarketSnapshot


class MarketDataSource(ABC):
    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def get_snapshot(self) -> MarketSnapshot: ...

    @abstractmethod
    def close(self) -> None: ...


class MockMarketDataSource(MarketDataSource):
    """确定性模拟源：每次读取都会产生一个新 tick，便于离线测试。"""

    def __init__(self, code: str, benchmarks: dict[str, str], seed: int = 515450):
        self.code = code
        self.benchmarks = benchmarks
        self.rng = np.random.default_rng(seed)
        self.tick = 0
        self.daily = self._bars(300, "B", 1.245, 0.0045, 2_800_000)
        self.minute = self._bars(120, "min", float(self.daily.close.iloc[-1]), 0.00065, 65_000)

    def _bars(self, periods: int, freq: str, start: float, sigma: float, volume: float) -> pd.DataFrame:
        idx = pd.date_range(end=pd.Timestamp.now().floor("min"), periods=periods, freq=freq)
        returns = self.rng.normal(0.00008, sigma, periods)
        close = start * np.exp(np.cumsum(returns))
        open_ = np.r_[start, close[:-1]]
        spread = np.abs(self.rng.normal(sigma * 0.7, sigma * 0.25, periods))
        high = np.maximum(open_, close) * (1 + spread)
        low = np.minimum(open_, close) * (1 - spread)
        vol = self.rng.lognormal(np.log(volume), 0.3, periods)
        return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": vol, "turnover": vol * close}, index=idx)

    def connect(self) -> None:
        return None

    def get_snapshot(self) -> MarketSnapshot:
        self.tick += 1
        shock = self.rng.normal(-0.00002, 0.0008)
        old = float(self.minute.close.iloc[-1])
        price = max(0.1, old * (1 + shock))
        now = pd.Timestamp.now()
        vol = float(self.rng.integers(10_000, 90_000))
        row = pd.DataFrame({
            "open": [old], "high": [max(old, price)], "low": [min(old, price)],
            "close": [price], "volume": [vol], "turnover": [vol * price],
        }, index=[now])
        self.minute = pd.concat([self.minute, row]).tail(240)
        vwap = intraday_vwap(self.minute)
        prev_close = float(self.daily.close.iloc[-2])
        benchmark_noise = self.rng.normal(0, 0.08, len(self.benchmarks))
        base_change = (price / prev_close - 1) * 100
        changes = {key: float(base_change * 0.45 + noise) for (key, _), noise in zip(self.benchmarks.items(), benchmark_noise)}
        imbalance = float(self.rng.uniform(-0.18, 0.18))
        depth = 500_000
        return MarketSnapshot(
            code=self.code, timestamp=datetime.now(), last_price=price, prev_close=prev_close,
            open_price=float(self.minute.open.iloc[0]), high_price=float(self.minute.high.max()),
            low_price=float(self.minute.low.min()), volume=float(self.minute.volume.sum()),
            turnover=float(self.minute.turnover.sum()), bid_price=price - 0.001,
            ask_price=price + 0.001, bid_volume=depth * (1 + imbalance),
            ask_volume=depth * (1 - imbalance), vwap=vwap, daily_bars=self.daily.copy(),
            minute_bars=self.minute.copy(), benchmark_changes=changes,
            benchmark_bars={key: self.daily.copy() for key in self.benchmarks},
            iopv=price * 0.9995, premium_pct=0.05, fund_shares=13_855_835_136,
            fund_share_change_pct=0.0,
            market_field_status={
                "realtime_market": {"available": True, "source": "mock", "as_of": now.date().isoformat()},
                "iopv_premium": {"available": True, "source": "mock", "as_of": now.date().isoformat()},
                "fund_shares": {"available": True, "source": "mock", "as_of": now.date().isoformat()},
            }, source="mock",
        )

    def close(self) -> None:
        return None


class FutuMarketDataSource(MarketDataSource):
    def __init__(self, code: str, benchmarks: dict[str, str], host: str, port: int, daily_bars: int = 300, minute_bars: int = 240):
        self.code = code
        self.benchmarks = benchmarks
        self.host = host
        self.port = port
        self.daily_count = daily_bars
        self.minute_count = minute_bars
        self.ctx: Any = None
        self._share_cache_date: str | None = None
        self._share_cache: tuple[float | None, float | None] = (None, None)
        self._share_cache_source = "未获取"
        self._share_history_path = Path(__file__).resolve().parents[2] / "data" / "fund_shares_history.csv"

    def connect(self) -> None:
        from futu import OpenQuoteContext, RET_OK, SubType

        self.ctx = OpenQuoteContext(host=self.host, port=self.port)
        codes = [self.code, *self.benchmarks.values()]
        ret, data = self.ctx.subscribe(codes, [SubType.QUOTE], subscribe_push=False)
        if ret != RET_OK:
            self.close()
            raise ConnectionError(f"Futu QUOTE 订阅失败: {data}")
        # 深度、分时和 1 分钟 K 线只订阅主标的；权限不足时仍可由快照/K线补足。
        self.ctx.subscribe([self.code], [SubType.ORDER_BOOK, SubType.RT_DATA, SubType.K_1M], subscribe_push=False)
        self.ctx.subscribe(codes, [SubType.K_DAY], subscribe_push=False)

    @staticmethod
    def _frame(raw: pd.DataFrame) -> pd.DataFrame:
        if raw is None or raw.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "turnover"])
        df = raw.copy()
        if "time_key" in df:
            df.index = pd.to_datetime(df["time_key"])
        cols = ["open", "high", "low", "close", "volume", "turnover"]
        for col in cols:
            if col not in df:
                df[col] = 0.0
        return df[cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)

    def _ok(self, response: tuple[Any, Any], label: str) -> pd.DataFrame:
        from futu import RET_OK
        ret, data = response
        if ret != RET_OK:
            raise RuntimeError(f"Futu {label} 失败: {data}")
        return data

    def _fund_shares(self, as_of: str) -> tuple[float | None, float | None]:
        """每天最多查询一次ETF总份额，并与本地历史的上一有效日比较。"""
        if self._share_cache_date == as_of:
            return self._share_cache
        shares: float | None = None
        share_source = "tencent_market_cap_div_price"
        try:
            response = requests.get(
                "https://qt.gtimg.cn/q=sh515450",
                headers={"User-Agent": "Mozilla/5.0"}, timeout=10,
            )
            response.raise_for_status()
            values = response.content.decode("gbk").split('"')[1].split("~")
            price = float(values[3])
            market_cap_yi = float(values[44])
            if price > 0 and market_cap_yi > 0:
                shares = market_cap_yi * 100_000_000 / price
        except Exception:
            shares = None
        try:
            response = requests.get(
                "https://push2.eastmoney.com/api/qt/stock/get",
                params={"secid": "1.515450", "fields": "f57,f58,f84", "fltt": "2", "invt": "2"},
                headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"},
                timeout=10,
            )
            response.raise_for_status()
            raw = (response.json().get("data") or {}).get("f84")
            if raw not in (None, "-", 0, "0"):
                shares = float(raw)
                share_source = "eastmoney_push2_f84"
        except Exception:
            pass

        previous: float | None = None
        history = pd.DataFrame(columns=["date", "shares", "source"])
        try:
            if self._share_history_path.exists():
                history = pd.read_csv(self._share_history_path, dtype={"date": str})
                older = history.loc[history["date"] < as_of]
                if not older.empty:
                    previous = float(older.sort_values("date").iloc[-1]["shares"])
            if shares is not None:
                row = pd.DataFrame([{"date": as_of, "shares": shares, "source": share_source}])
                history = pd.concat([history.loc[history["date"] != as_of], row], ignore_index=True)
                self._share_history_path.parent.mkdir(parents=True, exist_ok=True)
                history.sort_values("date").to_csv(self._share_history_path, index=False, encoding="utf-8")
        except Exception:
            previous = None
        change = (shares / previous - 1.0) * 100 if shares and previous else None
        self._share_cache_date = as_of
        self._share_cache = (shares, change)
        self._share_cache_source = share_source if shares is not None else "未获取"
        return self._share_cache

    def get_snapshot(self) -> MarketSnapshot:
        if self.ctx is None:
            raise RuntimeError("Futu 数据源尚未连接")
        from futu import AuType, KLType

        quote = self._ok(self.ctx.get_stock_quote([self.code, *self.benchmarks.values()]), "报价")
        main = quote.loc[quote["code"] == self.code].iloc[-1]
        daily_raw = self._ok(self.ctx.get_cur_kline(self.code, self.daily_count, KLType.K_DAY, AuType.QFQ), "日K")
        minute_raw = self._ok(self.ctx.get_cur_kline(self.code, self.minute_count, KLType.K_1M, AuType.QFQ), "分钟K")
        daily = self._frame(daily_raw)
        minute = self._frame(minute_raw)

        benchmark_bars: dict[str, pd.DataFrame] = {}
        for key, code in self.benchmarks.items():
            try:
                raw = self._ok(self.ctx.get_cur_kline(code, min(self.daily_count, 300), KLType.K_DAY, AuType.QFQ), f"{key}日K")
                benchmark_bars[key] = self._frame(raw)
            except Exception:
                continue

        bid_price = ask_price = None
        bid_volume = ask_volume = 0.0
        try:
            order_book = self._ok(self.ctx.get_order_book(self.code, num=10), "盘口")
            bids, asks = order_book.get("Bid", []), order_book.get("Ask", [])
            if bids:
                bid_price, bid_volume = float(bids[0][0]), float(bids[0][1])
            if asks:
                ask_price, ask_volume = float(asks[0][0]), float(asks[0][1])
        except Exception:
            pass

        benchmark_changes = {}
        for key, code in self.benchmarks.items():
            rows = quote.loc[quote["code"] == code]
            if not rows.empty:
                r = rows.iloc[-1]
                benchmark_changes[key] = float((float(r["last_price"]) / float(r["prev_close_price"]) - 1) * 100) if float(r["prev_close_price"]) else 0.0

        premium_pct = iopv = None
        try:
            market = self._ok(self.ctx.get_market_snapshot([self.code]), "市场快照")
            trust_premium = pd.to_numeric(market.iloc[-1].get("trust_premium"), errors="coerce")
            if pd.notna(trust_premium):
                premium_pct = float(trust_premium)
                denominator = 1.0 + premium_pct / 100.0
                iopv = float(main["last_price"]) / denominator if denominator > 0 else None
        except Exception:
            pass
        as_of = datetime.now().date().isoformat()
        fund_shares, fund_share_change = self._fund_shares(as_of)

        vwap = intraday_vwap(minute)
        return MarketSnapshot(
            code=self.code, timestamp=datetime.now(), last_price=float(main["last_price"]),
            prev_close=float(main["prev_close_price"]), open_price=float(main.get("open_price", 0)),
            high_price=float(main.get("high_price", 0)), low_price=float(main.get("low_price", 0)),
            volume=float(main.get("volume", 0)), turnover=float(main.get("turnover", 0)),
            bid_price=bid_price, ask_price=ask_price, bid_volume=bid_volume, ask_volume=ask_volume,
            vwap=vwap, daily_bars=daily, minute_bars=minute,
            benchmark_changes=benchmark_changes, benchmark_bars=benchmark_bars,
            iopv=iopv, premium_pct=premium_pct, fund_shares=fund_shares,
            fund_share_change_pct=fund_share_change,
            market_field_status={
                "realtime_market": {"available": True, "source": "Futu OpenD", "as_of": as_of},
                "benchmark_history": {"available": len(benchmark_bars) == len(self.benchmarks), "source": "Futu OpenD", "as_of": as_of},
                "iopv_premium": {"available": premium_pct is not None, "source": "Futu OpenD trust_premium（IOPV反推）", "as_of": as_of},
                "fund_shares": {"available": fund_shares is not None, "source": self._share_cache_source, "as_of": as_of},
                "fund_share_change": {"available": fund_share_change is not None, "source": "本地每日份额历史", "as_of": as_of},
            }, source=f"futu@{self.host}:{self.port}",
        )

    def close(self) -> None:
        if self.ctx is not None:
            self.ctx.close()
            self.ctx = None


def build_market_source(config: dict[str, Any], override: str | None = None) -> MarketDataSource:
    runtime = config["runtime"]
    instrument = config["instrument"]
    source = override or runtime["source"]
    if source == "mock":
        return MockMarketDataSource(instrument["code"], instrument["benchmarks"])
    if source in {"futu", "auto"}:
        return FutuMarketDataSource(
            instrument["code"], instrument["benchmarks"], runtime["host"], int(runtime["port"]),
            int(runtime["daily_bars"]), int(runtime["minute_bars"]),
        )
    raise ValueError(f"未知行情源: {source}")
