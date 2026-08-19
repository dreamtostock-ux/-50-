from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from urllib import error, request

from .config import load_config, resolve_path
from .data_sources import MockMarketDataSource, build_market_source
from .engine import DualLayerEngine
from .scoring import ScoringModel
from .static_data import build_static_provider


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="把 515450 实时评分写入网页的每日历史库")
    p.add_argument("--site-url", default=os.getenv("SCORE_SITE_URL", "http://localhost:3000"))
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--source", choices=["auto", "futu", "mock"], default="auto")
    p.add_argument("--interval", type=float, default=30)
    p.add_argument("--reconnect-delay", type=float, default=10, help="行情源断线后的重连等待秒数")
    p.add_argument("--cycles", type=int, default=0, help="0 表示持续运行")
    p.add_argument("--once", action="store_true")
    p.add_argument("--ingest-key", default=os.getenv("SCORE_INGEST_KEY", ""))
    p.add_argument("--sites-token", default=os.getenv("OAI_SITES_BYPASS_TOKEN", ""))
    return p


def _post(url: str, payload: dict, ingest_key: str, sites_token: str) -> None:
    endpoint = url.rstrip("/") + "/api/scores"
    headers = {"content-type": "application/json; charset=utf-8"}
    if ingest_key:
        headers["x-ingest-key"] = ingest_key
    if sites_token:
        headers["OAI-Sites-Authorization"] = f"Bearer {sites_token}"
    # ASCII转义可避免部分本地Worker在Windows下错误地按Latin-1解释请求体。
    req = request.Request(endpoint, data=json.dumps(payload, ensure_ascii=True).encode("ascii"), headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=15) as response:
            if response.status >= 300:
                raise RuntimeError(f"网页返回 HTTP {response.status}")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"网页写入失败 HTTP {exc.code}: {body[:300]}") from exc


def _open_source(config: dict, requested_source: str):
    """创建并验证行情连接；失败时必须关闭SDK线程，避免进程假存活。"""
    source = build_market_source(config, requested_source)
    try:
        source.connect()
        # 连接成功不代表行情接口已就绪，首个快照同时作为健康检查。
        source.get_snapshot()
        return source
    except Exception:
        source.close()
        raise


def _connect_with_retry(config: dict, requested_source: str, reconnect_delay: float, once: bool):
    while True:
        try:
            return _open_source(config, requested_source)
        except Exception as exc:
            if requested_source == "auto" and config["runtime"].get("allow_mock_fallback", True):
                print(f"Futu 暂不可用，切换模拟行情：{exc}", flush=True)
                source = MockMarketDataSource(config["instrument"]["code"], config["instrument"]["benchmarks"])
                source.connect()
                return source
            if once:
                print(f"行情源连接失败：{exc}", flush=True)
                return None
            delay = max(1.0, reconnect_delay)
            print(f"行情源连接失败：{exc}；{delay:g} 秒后重连", flush=True)
            time.sleep(delay)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    config_path = Path(args.config)
    if not config_path.exists() and args.config == "config.yaml":
        config_path = Path(__file__).resolve().parents[2] / "config.yaml"
    config = load_config(config_path)
    source = _connect_with_retry(config, args.source, args.reconnect_delay, args.once)
    if source is None:
        return 2

    static_cfg = config["static_data"]
    provider = build_static_provider(
        static_cfg["provider"], resolve_path(config, static_cfg["path"]), config["runtime"],
        static_cfg.get("valuation_proxy", "SH.000922"),
    )
    def make_engine(current_source):
        return DualLayerEngine(current_source, provider, ScoringModel(config), config["runtime"].get("strategic_refresh_time", "15:05"))

    engine = make_engine(source)
    cycles = 1 if args.once else args.cycles
    count = 0
    try:
        while cycles == 0 or count < cycles:
            try:
                score = engine.tick()
                payload = score.to_dict()
                calendar_date = score.timestamp.date().isoformat()
                latest_trading_date = score.diagnostics.get("latest_trading_date")
                payload["as_of_date"] = calendar_date
                if latest_trading_date == calendar_date:
                    _post(args.site_url, payload, args.ingest_key, args.sites_token)
                    print(f"{score.timestamp:%Y-%m-%d %H:%M:%S} 已记录：综合 {score.comprehensive_score:.1f} / 可信度 {score.data_quality}", flush=True)
                else:
                    print(f"{score.timestamp:%Y-%m-%d %H:%M:%S} 非交易日或尚未开盘，跳过每日记录（最近交易日 {latest_trading_date or '未知'}）", flush=True)
            except Exception as exc:
                print(f"采集异常：{exc}；关闭旧连接并重新连接", flush=True)
                source.close()
                if args.once:
                    return 3
                time.sleep(max(1.0, args.reconnect_delay))
                source = _connect_with_retry(config, args.source, args.reconnect_delay, False)
                engine = make_engine(source)
                continue
            count += 1
            if cycles == 0 or count < cycles:
                time.sleep(max(0, args.interval))
    except KeyboardInterrupt:
        print("已停止同步。", flush=True)
    finally:
        source.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
