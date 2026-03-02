"""Data module for loading and processing market data."""

import os
import pandas as pd

import config


TIMEFRAME_MAP = {
    "M1": "1min", "M5": "5min", "M15": "15min",
    "H1": "1h", "H4": "4h", "D1": "1D"
}


def load_csv(filepath):
    """Load OHLCV data from a CSV file into a DataFrame.

    Args:
        filepath: Path to the CSV file.

    Returns:
        DataFrame with columns: datetime, open, high, low, close, volume.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If required columns are missing.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Data file not found: {filepath}")

    df = pd.read_csv(filepath)
    df["datetime"] = pd.to_datetime(df["datetime"])

    required = {"datetime", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    df = df.sort_values("datetime").reset_index(drop=True)
    return df


def load_symbol(symbol, timeframe, start=None, end=None):
    """Load data for a symbol and timeframe from sample data directory.

    Args:
        symbol: Trading symbol, e.g. 'EURUSD'.
        timeframe: Timeframe string, e.g. 'H1', 'M5'.
        start: Optional start datetime string for filtering.
        end: Optional end datetime string for filtering.

    Returns:
        DataFrame with OHLCV data.
    """
    filename = f"{symbol}_{timeframe}.csv"
    filepath = os.path.join(config.DATA_DIR, filename)
    df = load_csv(filepath)

    if start:
        df = df[df["datetime"] >= pd.to_datetime(start)]
    if end:
        df = df[df["datetime"] <= pd.to_datetime(end)]

    return df.reset_index(drop=True)


def resample_timeframe(df, target_tf):
    """Resample OHLCV data to a different timeframe.

    Args:
        df: DataFrame with datetime, open, high, low, close, volume.
        target_tf: Target timeframe string, e.g. 'H4', 'D1'.

    Returns:
        Resampled DataFrame.
    """
    if target_tf not in TIMEFRAME_MAP:
        raise ValueError(
            f"Unknown timeframe: {target_tf}. "
            f"Valid: {list(TIMEFRAME_MAP.keys())}"
        )

    freq = TIMEFRAME_MAP[target_tf]
    df = df.copy()
    df = df.set_index("datetime")

    resampled = df.resample(freq).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum"
    }).dropna()

    resampled = resampled.reset_index()
    return resampled


def get_available_symbols():
    """List available symbols from the data directory.

    Returns:
        List of (symbol, timeframe) tuples.
    """
    symbols = []
    if not os.path.exists(config.DATA_DIR):
        return symbols

    for f in os.listdir(config.DATA_DIR):
        if f.endswith(".csv"):
            parts = f.replace(".csv", "").split("_")
            if len(parts) == 2:
                symbols.append((parts[0], parts[1]))

    return symbols
