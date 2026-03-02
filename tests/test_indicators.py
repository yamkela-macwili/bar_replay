"""Tests for the indicators module."""

import os
import sys
import pytest
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.indicators import (
    compute_sma, compute_ema, compute_rsi,
    compute_macd, compute_bollinger, compute_indicators
)
from backend.data_module import load_symbol


@pytest.fixture
def df():
    return load_symbol("EURUSD", "H1")


class TestSMA:
    def test_sma_length(self, df):
        sma = compute_sma(df, period=20)
        assert len(sma) == len(df)

    def test_sma_value(self, df):
        sma = compute_sma(df, period=5)
        # SMA at index 4 should be mean of first 5 closes
        expected = df["close"].iloc[:5].mean()
        assert abs(sma.iloc[4] - expected) < 1e-8


class TestEMA:
    def test_ema_length(self, df):
        ema = compute_ema(df, period=20)
        assert len(ema) == len(df)

    def test_ema_no_nan(self, df):
        ema = compute_ema(df, period=20)
        assert not ema.isna().any()


class TestRSI:
    def test_rsi_range(self, df):
        rsi = compute_rsi(df, period=14)
        assert rsi.min() >= 0
        assert rsi.max() <= 100

    def test_rsi_length(self, df):
        rsi = compute_rsi(df, period=14)
        assert len(rsi) == len(df)


class TestMACD:
    def test_macd_keys(self, df):
        result = compute_macd(df)
        assert "macd" in result
        assert "signal" in result
        assert "histogram" in result

    def test_macd_lengths(self, df):
        result = compute_macd(df)
        assert len(result["macd"]) == len(df)
        assert len(result["signal"]) == len(df)
        assert len(result["histogram"]) == len(df)


class TestBollinger:
    def test_bollinger_keys(self, df):
        result = compute_bollinger(df)
        assert "upper" in result
        assert "middle" in result
        assert "lower" in result

    def test_upper_above_lower(self, df):
        result = compute_bollinger(df, period=20)
        # After warmup, upper should be above lower
        valid = result["upper"].iloc[20:] >= result["lower"].iloc[20:]
        assert valid.all()


class TestComputeAll:
    def test_compute_multiple(self, df):
        active = {
            "sma": {"period": 20},
            "ema": {"period": 50},
            "rsi": {"period": 14},
        }
        result = compute_indicators(df, active)
        assert "SMA(20)" in result
        assert "EMA(50)" in result
        assert "RSI(14)" in result

    def test_compute_empty(self, df):
        result = compute_indicators(df, {})
        assert result == {}
