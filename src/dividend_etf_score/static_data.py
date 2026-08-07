from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from io import StringIO
from pathlib import Path

import pandas as pd
import requests
import yaml

from .models import StaticFactors


class StaticFactorProvider(ABC):
    """外部静态因子的可插拔接口。"""

    @abstractmethod
    def load(self) -> StaticFactors:
        raise NotImplementedError


class FileStaticFactorProvider(StaticFactorProvider):
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self) -> StaticFactors:
        with self.path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
        return StaticFactors(**raw)


class TrustedCompositeFactorProvider(StaticFactorProvider):
    """官方国债 + Futu十年估值历史 + 带日期的股息率发布值。"""

    CHINABOND_URL = "https://yield.chinabond.com.cn/cbweb-pbc-web/pbc/more?locale=cn_zh"

    def __init__(self, path: str | Path, timeout: int = 12, host: str = "127.0.0.1", port: int = 11111,
                 valuation_proxy: str = "SH.000922"):
        self.file = FileStaticFactorProvider(path)
        self.timeout = timeout
        self.host = host
        self.port = port
        self.valuation_proxy = valuation_proxy

    def _official_bond_10y(self) -> tuple[float, str]:
        response = requests.get(self.CHINABOND_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=self.timeout)
        response.raise_for_status()
        for table in pd.read_html(StringIO(response.text)):
            columns = [str(col) for col in table.columns]
            if "10年" not in columns:
                continue
            first = table.iloc[:, 0].astype(str)
            matches = table[first.str.contains("中债国债收益率曲线", na=False)]
            if not matches.empty:
                import re
                match = re.search(r"(20\d{2}-\d{2}-\d{2})\(%\)", response.text)
                return float(matches.iloc[0]["10年"]), match.group(1) if match else date.today().isoformat()
        raise ValueError("中债官方页面未找到 10 年期国债列")

    def _futu_valuation(self, valuation_type: int) -> tuple[float, float, str, int]:
        """取红利指数代理的当前估值、十年历史分位和样本量。"""
        from futu import OpenQuoteContext, RET_OK

        ctx = OpenQuoteContext(host=self.host, port=self.port)
        try:
            ret, data = ctx.get_valuation_detail(
                self.valuation_proxy, valuation_type=valuation_type, interval_type=7,
            )
            if ret != RET_OK or not isinstance(data, dict):
                raise RuntimeError(str(data))
            trend = data.get("trend") or {}
            current = float(trend["current_value"])
            percentile = float(trend["valuation_percentile"])
            as_of = str(data.get("last_update_time_str") or date.today().isoformat())[:10]
            return current, percentile, as_of, len(trend.get("historical_items") or [])
        finally:
            ctx.close()

    def _published_dividend_yield(self, url: str, fallback: float, fallback_date: str) -> tuple[float, str]:
        """自动复核带明确发布日期的公开股息率；解析失败时保留上次已核验值。"""
        import re

        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=self.timeout)
        response.raise_for_status()
        text = response.text
        patterns = [r"股息率[^%]{0,40}?([0-9]+(?:\.[0-9]+)?)%", r"股息率为\s*([0-9]+(?:\.[0-9]+)?)%"]
        for pattern in patterns:
            matches = [float(value) for value in re.findall(pattern, text) if 1.0 <= float(value) <= 15.0]
            if matches:
                # 页面常混入站点当前日期；仅验证数值，沿用人工核验过的指标基准日。
                return matches[0], fallback_date
        return fallback, fallback_date

    def load(self) -> StaticFactors:
        factors = self.file.load()
        failures: list[str] = []
        try:
            value, as_of = self._official_bond_10y()
            factors.bond_10y_yield_pct = value
            factors.field_as_of["bond_10y_yield_pct"] = as_of
            factors.sources["bond_10y_yield_pct"] = self.CHINABOND_URL
            factors.as_of = max(factors.as_of, as_of)
        except Exception as exc:
            failures.append(f"bond_10y:{type(exc).__name__}")

        try:
            pe, pe_pct, pe_date, pe_count = self._futu_valuation(1)
            factors.earnings_yield_pct = 100.0 / pe
            factors.pe_percentile_pct = pe_pct
            factors.field_as_of["earnings_yield_pct"] = pe_date
            factors.field_as_of["pe_percentile_pct"] = pe_date
            factors.sources["earnings_yield_pct"] = f"Futu OpenD {self.valuation_proxy} PE={pe:.3f}x（红利指数代理）"
            factors.sources["pe_percentile_pct"] = f"Futu OpenD {self.valuation_proxy} 10年PE历史"
            factors.valuation_history_count = max(factors.valuation_history_count, pe_count)
        except Exception as exc:
            failures.append(f"pe_history:{type(exc).__name__}")

        try:
            pb, pb_pct, pb_date, pb_count = self._futu_valuation(2)
            factors.pb_percentile_pct = pb_pct
            factors.field_as_of["pb_percentile_pct"] = pb_date
            factors.sources["pb_percentile_pct"] = f"Futu OpenD {self.valuation_proxy} 10年PB历史；当前PB={pb:.3f}x"
            factors.valuation_history_count = max(factors.valuation_history_count, pb_count)
        except Exception as exc:
            failures.append(f"pb_history:{type(exc).__name__}")

        dividend_url = factors.sources.get("dividend_yield_pct", "")
        try:
            dividend, dividend_date = self._published_dividend_yield(
                dividend_url, factors.dividend_yield_pct,
                factors.field_as_of.get("dividend_yield_pct", factors.as_of),
            )
            factors.dividend_yield_pct = dividend
            factors.field_as_of["dividend_yield_pct"] = dividend_date
        except Exception as exc:
            failures.append(f"dividend_yield:{type(exc).__name__}")

        factors.valuation_proxy = self.valuation_proxy
        factors.as_of = max([factors.as_of, *factors.field_as_of.values()])
        factors.quality_detail = {
            "provider_failures": failures,
            "valuation_proxy": self.valuation_proxy,
            "valuation_history_count": factors.valuation_history_count,
            "exact_tracking_index_valuation_available": False,
        }
        return factors


def build_static_provider(kind: str, path: str | Path, runtime: dict | None = None,
                          valuation_proxy: str = "SH.000922") -> StaticFactorProvider:
    if kind == "file":
        return FileStaticFactorProvider(path)
    if kind == "trusted_composite":
        runtime = runtime or {}
        return TrustedCompositeFactorProvider(
            path, host=str(runtime.get("host", "127.0.0.1")), port=int(runtime.get("port", 11111)),
            valuation_proxy=valuation_proxy,
        )
    raise ValueError(f"未知静态因子源: {kind}。可实现 StaticFactorProvider 后在此注册。")
