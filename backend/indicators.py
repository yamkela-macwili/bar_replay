"""Technical indicators computed with Pandas/NumPy."""

import numpy as np
import pandas as pd


def compute_sma(df, period=20, column="close"):
    """Compute Simple Moving Average.

    Args:
        df: DataFrame with OHLCV data.
        period: Lookback period.
        column: Column to compute SMA on.

    Returns:
        Series with SMA values.
    """
    return df[column].rolling(window=period, min_periods=1).mean()


def compute_ema(df, period=20, column="close"):
    """Compute Exponential Moving Average.

    Args:
        df: DataFrame with OHLCV data.
        period: Lookback period.
        column: Column to compute EMA on.

    Returns:
        Series with EMA values.
    """
    return df[column].ewm(span=period, adjust=False).mean()


def compute_rsi(df, period=14, column="close"):
    """Compute Relative Strength Index.

    Args:
        df: DataFrame with OHLCV data.
        period: Lookback period.
        column: Column to compute RSI on.

    Returns:
        Series with RSI values (0-100).
    """
    delta = df[column].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)

    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def compute_macd(df, fast=12, slow=26, signal=9, column="close"):
    """Compute MACD (Moving Average Convergence Divergence).

    Args:
        df: DataFrame with OHLCV data.
        fast: Fast EMA period.
        slow: Slow EMA period.
        signal: Signal line period.
        column: Column to compute MACD on.

    Returns:
        Dict with 'macd', 'signal', 'histogram' Series.
    """
    fast_ema = df[column].ewm(span=fast, adjust=False).mean()
    slow_ema = df[column].ewm(span=slow, adjust=False).mean()
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line

    return {
        "macd": macd_line,
        "signal": signal_line,
        "histogram": histogram,
    }


def compute_bollinger(df, period=20, std_dev=2.0, column="close"):
    """Compute Bollinger Bands.

    Args:
        df: DataFrame with OHLCV data.
        period: Lookback period for the moving average.
        std_dev: Number of standard deviations.
        column: Column to compute bands on.

    Returns:
        Dict with 'upper', 'middle', 'lower' Series.
    """
    middle = df[column].rolling(window=period, min_periods=1).mean()
    std = df[column].rolling(window=period, min_periods=1).std().fillna(0)
    upper = middle + std_dev * std
    lower = middle - std_dev * std

    return {
        "upper": upper,
        "middle": middle,
        "lower": lower,
    }


def compute_indicators(df, active_indicators):
    """Compute all active indicators on a DataFrame.

    Args:
        df: DataFrame with OHLCV data.
        active_indicators: Dict mapping indicator name to its settings.
            Example: {
                "sma": {"period": 20},
                "ema": {"period": 50},
                "rsi": {"period": 14},
                "macd": {"fast": 12, "slow": 26, "signal": 9},
                "bollinger": {"period": 20, "std_dev": 2.0}
            }

    Returns:
        Dict mapping indicator name to values (serializable).
    """
    results = {}

    for name, settings in active_indicators.items():
        if name == "sma":
            period = settings.get("period", 20)
            vals = compute_sma(df, period)
            results[f"SMA({period})"] = vals.round(5).tolist()

        elif name == "ema":
            period = settings.get("period", 50)
            vals = compute_ema(df, period)
            results[f"EMA({period})"] = vals.round(5).tolist()

        elif name == "rsi":
            period = settings.get("period", 14)
            vals = compute_rsi(df, period)
            results[f"RSI({period})"] = vals.round(2).tolist()

        elif name == "macd":
            macd = compute_macd(
                df,
                settings.get("fast", 12),
                settings.get("slow", 26),
                settings.get("signal", 9)
            )
            results["MACD"] = macd["macd"].round(5).tolist()
            results["MACD_Signal"] = macd["signal"].round(5).tolist()
            results["MACD_Hist"] = macd["histogram"].round(5).tolist()

        elif name == "bollinger":
            bb = compute_bollinger(
                df,
                settings.get("period", 20),
                settings.get("std_dev", 2.0)
            )
            results["BB_Upper"] = bb["upper"].round(5).tolist()
            results["BB_Middle"] = bb["middle"].round(5).tolist()
            results["BB_Lower"] = bb["lower"].round(5).tolist()

    return results
