from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .config import load_config, resolve_path
from .data_sources import MockMarketDataSource, build_market_source
from .engine import DualLayerEngine
from .scoring import ScoringModel
from .static_data import build_static_provider


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="515450 红利低波50ETF 实时评分")
    p.add_argument("--config", default="config.yaml", help="YAML 配置文件")
    p.add_argument("--source", choices=["auto", "futu", "mock"], help="覆盖配置中的行情源")
    p.add_argument("--interval", type=float, help="刷新秒数，默认读取配置")
    p.add_argument("--cycles", type=int, default=0, help="运行次数，0 表示持续运行")
    p.add_argument("--once", action="store_true", help="只输出一次")
    p.add_argument("--json", action="store_true", help="逐行输出 JSON")
    return p


def _table(result) -> Table:
    table = Table(title=f"{result.code} 红利低波双层评分  {result.timestamp:%Y-%m-%d %H:%M:%S}")
    table.add_column("数据源")
    table.add_column("最新价", justify="right")
    table.add_column("涨跌", justify="right")
    table.add_column("战略", justify="right")
    table.add_column("战术", justify="right")
    table.add_column("综合", justify="right", style="bold cyan")
    table.add_column("买入", justify="right", style="green")
    table.add_column("卖出", justify="right", style="red")
    table.add_column("日内T", justify="right", style="yellow")
    table.add_column("仓位", justify="right")
    table.add_row(
        result.source, f"{result.last_price:.4f}", f"{result.change_pct:+.2f}%",
        f"{result.strategic_score:.1f}", f"{result.tactical_score:.1f}",
        f"{result.comprehensive_score:.1f}", f"{result.buy_signal:.1f}",
        f"{result.sell_signal:.1f}", f"{result.intraday_t_signal:.1f}", f"{result.position_pct:.0f}%",
    )
    table.caption = (
        f"VWAP偏离 {result.diagnostics['vwap_deviation_pct']:+.2f}% | "
        f"相对异常 {result.diagnostics['relative_change_pct']:+.2f}% | "
        f"RSI {result.diagnostics['rsi14']:.1f} | 超跌奖励 +{result.oversold_bonus:.0f}"
    )
    return table


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    config_path = Path(args.config)
    if not config_path.exists() and args.config == "config.yaml":
        config_path = Path(__file__).resolve().parents[2] / "config.yaml"
    config = load_config(config_path)
    runtime = config["runtime"]
    selected = args.source or runtime["source"]
    source = build_market_source(config, selected)
    console = Console(stderr=not args.json)
    try:
        source.connect()
        # 连接成功不代表订阅权限和所需数据都可用；auto 模式先做一次完整探测。
        if selected == "auto":
            source.get_snapshot()
    except Exception as exc:
        if selected == "auto" and runtime.get("allow_mock_fallback", True):
            console.print(f"[yellow]Futu OpenD 不可用，已切换模拟行情：{exc}[/yellow]")
            source.close()
            source = MockMarketDataSource(config["instrument"]["code"], config["instrument"]["benchmarks"])
            source.connect()
        else:
            console.print(f"[red]行情源连接失败：{exc}[/red]")
            return 2

    static_cfg = config["static_data"]
    provider = build_static_provider(
        static_cfg["provider"], resolve_path(config, static_cfg["path"]), runtime,
        static_cfg.get("valuation_proxy", "SH.000922"),
    )
    engine = DualLayerEngine(
        source, provider, ScoringModel(config),
        refresh_time=str(runtime.get("strategic_refresh_time", "15:05")),
    )
    interval = args.interval if args.interval is not None else float(runtime["interval_seconds"])
    cycles = 1 if args.once else args.cycles
    count = 0
    try:
        while cycles == 0 or count < cycles:
            result = engine.tick()
            if args.json:
                print(json.dumps(result.to_dict(), ensure_ascii=False))
            else:
                console.print(_table(result))
            count += 1
            if cycles == 0 or count < cycles:
                time.sleep(max(0.0, interval))
    except KeyboardInterrupt:
        console.print("\n已停止。")
    finally:
        source.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
