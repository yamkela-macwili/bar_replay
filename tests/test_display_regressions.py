"""Regression tests for chart data indexing and provider timeframe selection."""

import pandas as pd
import pytest

import config
from backend.data_module import YFinanceDataProvider, get_yfinance_interval
from backend.engine_system import ReplaySystem
from backend.replay_engine import ReplayEngine


@pytest.mark.parametrize("timeframe, interval", [
    ("M5", "5m"),
    ("M15", "15m"),
    ("H1", "1h"),
    ("H4", "1h"),
    ("D1", "1d"),
])
def test_supported_timeframes_map_to_exact_provider_intervals(timeframe, interval):
    assert get_yfinance_interval(timeframe) == interval


def test_unsupported_timeframe_is_rejected_instead_of_falling_back_to_hourly():
    for timeframe in ("M1", "H2"):
        with pytest.raises(ValueError, match="Unsupported timeframe"):
            get_yfinance_interval(timeframe)


def test_visible_bars_and_replay_index_use_separate_positions():
    data = pd.DataFrame({
        "datetime": pd.date_range("2024-01-01", periods=500, freq="h"),
        "open": range(500),
        "high": range(500),
        "low": range(500),
        "close": range(500),
        "volume": range(500),
    })
    replay = ReplayEngine(data, start_index=300)

    visible = replay.get_visible_data(max_bars=200)["bars"]
    assert len(visible) == 200
    assert visible.iloc[0]["close"] == 101
    assert visible.iloc[-1]["close"] == 300
    assert replay.get_progress()["current_index"] == 300


def test_replay_visible_data_is_safe_for_a_single_bar_dataset():
    data = pd.DataFrame({
        "datetime": [pd.Timestamp("2024-01-01")],
        "open": [1], "high": [1], "low": [1], "close": [1], "volume": [1],
    })
    replay = ReplayEngine(data)
    assert len(replay.get_visible_data()["bars"]) == 1


def test_replay_system_starts_at_latest_loaded_bar():
    data = pd.DataFrame({
        "datetime": pd.date_range("2024-01-01", periods=500, freq="h"),
        "open": range(500), "high": range(500), "low": range(500),
        "close": range(500), "volume": range(500),
    })
    system = ReplaySystem(data, "EURUSD", "H1", "csv")

    assert system.replay_engine.current_index == len(data) - 1
    assert len(system.replay_engine.get_visible_data()["bars"]) == 200


def test_latest_data_load_forces_yahoo_refresh_and_returns_provider_timestamp(monkeypatch, tmp_path):
    import yfinance as yf

    history = pd.DataFrame({
        "Open": [1.1, 1.2], "High": [1.2, 1.3],
        "Low": [1.0, 1.1], "Close": [1.15, 1.25], "Volume": [10, 20],
    }, index=pd.DatetimeIndex([
        "2026-10-18 12:00:00+00:00", "2026-10-18 13:00:00+00:00"
    ], name="Datetime"))
    calls = []

    class FakeTicker:
        def history(self, **kwargs):
            calls.append(kwargs)
            return history

    monkeypatch.setattr(config, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(yf, "Ticker", lambda _: FakeTicker())
    bars = YFinanceDataProvider().fetch_bars("EURUSD", "H1", count=20, refresh=True)

    assert calls == [{"period": "max", "interval": "1h"}]
    assert len(bars) == 2
    assert bars.iloc[-1]["datetime"] == pd.Timestamp("2026-10-18 13:00:00")
    assert bars.attrs["source_checked_at"]
    assert bars.attrs["source_refresh_error"] is None
