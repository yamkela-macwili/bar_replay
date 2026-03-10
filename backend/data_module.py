"""Data module for loading and processing market data from various providers."""

import os
import pandas as pd
from abc import ABC, abstractmethod
import datetime
import portalocker
import time

import config

TIMEFRAME_MAP = {
    "M5": "5min", "M15": "15min",
    "H1": "1h", "H4": "4h"
}

class DataProvider(ABC):
    """Abstract base class for market data providers."""
    
    @abstractmethod
    def fetch_bars(self, symbol, timeframe, count, before=None):
        """Fetch historical bars.
        
        Args:
            symbol: Trading symbol.
            timeframe: Timeframe string.
            count: Number of bars to fetch.
            before: Optional datetime to fetch bars before.
            
        Returns:
            DataFrame with OHLCV data.
        """
        pass

    @abstractmethod
    def get_available_symbols(self):
        """Returns a list of available symbols."""
        pass


class CSVDataProvider(DataProvider):
    """Data provider that loads from local CSV files."""
    
    def fetch_bars(self, symbol, timeframe, count, before=None):
        import pandas as pd
        filename = f"{symbol}_{timeframe}.csv"
        filepath = os.path.join(config.DATA_DIR, filename)
        
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Data file not found: {filepath}")

        df = pd.read_csv(filepath)
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.sort_values("datetime")

        if before:
            before_dt = pd.to_datetime(before)
            df = df[df["datetime"] < before_dt]

        return df.tail(count).reset_index(drop=True)

    def get_available_symbols(self):
        symbols = []
        if not os.path.exists(config.DATA_DIR):
            return symbols

        for f in os.listdir(config.DATA_DIR):
            if f.endswith(".csv"):
                parts = f.replace(".csv", "").split("_")
                if len(parts) == 2:
                    symbols.append((parts[0], parts[1]))
        return symbols


class YFinanceDataProvider(DataProvider):
    """Data provider using yfinance with Parquet caching and symbol mapping."""
    
    def __init__(self):
        super().__init__()
        if not os.path.exists(config.CACHE_DIR):
            os.makedirs(config.CACHE_DIR, exist_ok=True)

    def _get_cache_path(self, symbol, timeframe):
        return os.path.join(config.CACHE_DIR, f"{symbol}_{timeframe}.parquet")

    def fetch_bars(self, symbol, timeframe, count, before=None):
        import pandas as pd
        import yfinance as yf
        
        yf_symbol = config.SYMBOL_MAP.get(symbol, symbol)
        
        # yfinance timeframe mapping (flexible for case and format)
        yf_tf_map = {
            "M5": "5m", "M15": "15m",
            "H1": "1h", "H4": "4h", 
            "4H": "4h", "1H": "1h"
        }
        interval = yf_tf_map.get(timeframe.upper(), "1h")
        cache_path = self._get_cache_path(symbol, timeframe)
        lock_path = cache_path + ".lock"
        
        # Ensure cache dir exists
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)

        with portalocker.Lock(lock_path, timeout=10) as fh:
            df = pd.DataFrame()
            if os.path.exists(cache_path):
                try:
                    df = pd.read_parquet(cache_path)
                except Exception as e:
                    print(f"⚠️ Cache read error for {symbol}: {e}. Rebuilding...")

            # Determine if we need to download more
            needs_download = False
            now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            
            if df.empty:
                needs_download = True
            elif not before: # Check if we need latest (1h heuristic)
                last_dt = df["datetime"].max()
                # Use now_utc for comparison to match tz-naive UTC stored in parquet
                if (now_utc - last_dt).total_seconds() > 3600:
                    needs_download = True
            
            if needs_download:
                # Extra guard: if last_dt is somehow after now_utc, don't request from yfinance
                if not df.empty and df["datetime"].max() >= now_utc:
                    print(f"ℹ️ Cache for {symbol} is already up-to-date or ahead ({df['datetime'].max()}). Skipping download.")
                    needs_download = False
                print(f"📡 Downloading {yf_symbol} ({interval}) from yfinance...")
                ticker = yf.Ticker(yf_symbol)
                try:
                    if df.empty:
                        # Initial migration to yfinance / new cache
                        new_df = ticker.history(period="max", interval=interval)
                    else:
                        # Appending new data
                        last_dt = df["datetime"].max()
                        new_df = ticker.history(start=last_dt, interval=interval)
                    
                    if not new_df.empty:
                        new_df = new_df.reset_index()
                        # handle both 'Date' and 'Datetime' index names
                        time_col = "Date" if "Date" in new_df.columns else "Datetime"
                        new_df = new_df.rename(columns={
                            time_col: "datetime",
                            "Open": "open", "High": "high", "Low": "low", 
                            "Close": "close", "Volume": "volume"
                        })
                        new_df = new_df[["datetime", "open", "high", "low", "close", "volume"]]
                        new_df["datetime"] = pd.to_datetime(new_df["datetime"], utc=True).dt.tz_localize(None)
                        
                        if df.empty:
                            df = new_df
                        else:
                            df = pd.concat([df, new_df])
                        
                        # Deduplicate and sort
                        df = df.drop_duplicates(subset=["datetime"]).sort_values("datetime").reset_index(drop=True)
                        
                        # Atomic write
                        df.to_parquet(cache_path)
                        print(f"✅ Cache updated for {symbol} ({len(df)} total bars)")
                except Exception as e:
                    print(f"❌ YFinance download failed for {symbol}: {e}")

        if df.empty:
            return pd.DataFrame()

        # Handle slicing for the engine ( rispettando MAX_BARS_LIMIT )
        df = df.sort_values("datetime")
        if before:
            before_dt = pd.to_datetime(before)
            df = df[df["datetime"] < before_dt]

        return df.tail(count).reset_index(drop=True)

    def get_available_symbols(self):
        return [(s, config.DEFAULT_TIMEFRAME) for s in config.SYMBOL_MAP.keys()]


def get_provider(provider_type="csv"):
    if provider_type == "yfinance":
        return YFinanceDataProvider()
    else:
        return CSVDataProvider()


# Utility functions (kept for backward compatibility or general use)

def load_symbol(symbol, timeframe, count=config.INITIAL_BAR_COUNT, provider_type="csv"):
    provider = get_provider(provider_type)
    return provider.fetch_bars(symbol, timeframe, count)

def resample_timeframe(df, target_tf):
    if target_tf not in TIMEFRAME_MAP:
        raise ValueError(f"Unknown timeframe: {target_tf}")

    freq = TIMEFRAME_MAP[target_tf]
    df = df.copy()
    df = df.set_index("datetime")

    resampled = df.resample(freq).agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum"
    }).dropna()

    return resampled.reset_index()

def get_available_symbols(provider_type="csv"):
    return get_provider(provider_type).get_available_symbols()
