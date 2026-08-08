from dividend_etf_score.config import load_config, resolve_path
from dividend_etf_score.data_sources import MockMarketDataSource
from dividend_etf_score.engine import DualLayerEngine
from dividend_etf_score.scoring import ScoringModel
from dividend_etf_score.static_data import FileStaticFactorProvider
from datetime import datetime
import pytest


def test_mock_engine_scores_are_bounded():
    config = load_config("config.yaml")
    source = MockMarketDataSource(config["instrument"]["code"], config["instrument"]["benchmarks"])
    provider = FileStaticFactorProvider(resolve_path(config, config["static_data"]["path"]))
    engine = DualLayerEngine(source, provider, ScoringModel(config))
    result = engine.tick()
    for value in [result.strategic_score, result.tactical_score, result.comprehensive_score,
                  result.buy_signal, result.sell_signal, result.intraday_t_signal, result.position_pct]:
        assert 0 <= value <= 100
    assert result.source == "mock"
    assert "vwap_deviation_pct" in result.diagnostics
    assert "quality_detail" in result.diagnostics
    quality = result.diagnostics["quality_detail"]
    assert quality["overall"] == result.data_quality
    assert quality["completeness"] > 0
    assert quality["freshness"] > 0
    assert quality["source_quality"] > 0
    assert "market_environment_score" in result.diagnostics
    assert "daily_rsi14" in result.diagnostics
    assert "intraday_rsi14" in result.diagnostics
    assert "daily_rsi" in result.factors
    assert "iopv" in result.diagnostics
    assert "fund_shares" in result.diagnostics
    assert result.diagnostics["latest_trading_date"] == source.daily.index.max().date().isoformat()


def test_strategic_score_is_cached_intraday():
    config = load_config("config.yaml")
    source = MockMarketDataSource(config["instrument"]["code"], config["instrument"]["benchmarks"])
    provider = FileStaticFactorProvider(resolve_path(config, config["static_data"]["path"]))
    engine = DualLayerEngine(source, provider, ScoringModel(config))
    first = engine.tick()
    second = engine.tick()
    assert first.strategic_score == second.strategic_score
    assert first.last_price != second.last_price


def test_strategic_period_rolls_after_close():
    config = load_config("config.yaml")
    source = MockMarketDataSource(config["instrument"]["code"], config["instrument"]["benchmarks"])
    provider = FileStaticFactorProvider(resolve_path(config, config["static_data"]["path"]))
    engine = DualLayerEngine(source, provider, ScoringModel(config), refresh_time="15:05")
    assert engine._strategic_period(datetime(2026, 8, 7, 14, 59)).isoformat() == "2026-08-06"
    assert engine._strategic_period(datetime(2026, 8, 7, 15, 5)).isoformat() == "2026-08-07"


def test_factor_weights_are_normalized():
    config = load_config("config.yaml")
    assert sum(config["engine"]["strategic_factors"].values()) == pytest.approx(1.0)
    assert sum(config["engine"]["tactical_factors"].values()) == pytest.approx(1.0)
