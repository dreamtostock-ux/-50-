import pytest

from dividend_etf_score import sync


class FailingSource:
    def __init__(self):
        self.closed = False

    def connect(self):
        raise ConnectionError("OpenD not ready")

    def get_snapshot(self):
        raise AssertionError("snapshot should not run")

    def close(self):
        self.closed = True


def test_failed_initial_connection_always_closes_sdk_context(monkeypatch):
    source = FailingSource()
    monkeypatch.setattr(sync, "build_market_source", lambda config, requested: source)

    with pytest.raises(ConnectionError, match="OpenD not ready"):
        sync._open_source({}, "futu")

    assert source.closed is True
