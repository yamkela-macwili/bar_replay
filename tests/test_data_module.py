"""Tests for the data module."""

import os
import pytest
import pandas as pd

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.data_module import load_csv, load_symbol, resample_timeframe


SAMPLE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "sample", "EURUSD_H1.csv"
)


class TestLoadCSV:
    def test_load_valid_csv(self):
        df = load_csv(SAMPLE_PATH)
        assert len(df) == 500
        assert list(df.columns) == [
            "datetime", "open", "high", "low", "close", "volume"
        ]
        assert pd.api.types.is_datetime64_any_dtype(df["datetime"])

    def test_load_missing_file(self):
        with pytest.raises(FileNotFoundError):
            load_csv("/nonexistent/file.csv")

    def test_data_sorted_by_datetime(self):
        df = load_csv(SAMPLE_PATH)
        assert df["datetime"].is_monotonic_increasing


class TestLoadSymbol:
    def test_load_eurusd_h1(self):
        df = load_symbol("EURUSD", "H1")
        assert len(df) == 500

    def test_load_with_date_filter(self):
        df = load_symbol("EURUSD", "H1", start="2024-01-03")
        assert df.iloc[0]["datetime"] >= pd.Timestamp("2024-01-03")

    def test_load_unknown_symbol(self):
        with pytest.raises(FileNotFoundError):
            load_symbol("XXXYYY", "H1")


class TestResample:
    def test_resample_to_h4(self):
        df = load_symbol("EURUSD", "H1")
        resampled = resample_timeframe(df, "H4")
        assert len(resampled) < len(df)
        assert "open" in resampled.columns

    def test_invalid_timeframe(self):
        df = load_symbol("EURUSD", "H1")
        with pytest.raises(ValueError):
            resample_timeframe(df, "INVALID")
