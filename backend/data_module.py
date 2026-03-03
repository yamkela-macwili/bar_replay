"""Data module for loading and processing market data from various providers."""

import os
import pandas as pd
from abc import ABC, abstractmethod
import datetime
import portalocker
import time

import config

TIMEFRAME_MAP = {
    "M1": "1min", "M5": "5min", "M15": "15min",
    "H1": "1h", "H4": "4h", "D1": "1D"
}

MT5_TIMEFRAME_MAP = None # Lazy import

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
    def __init__(self):
        # ensure cache dir exists for potential parquet lookups
        if not os.path.exists(config.CACHE_DIR):
            try:
                os.makedirs(config.CACHE_DIR, exist_ok=True)
            except Exception:
                # best-effort; downstream will still work if CSVs exist
                pass

    def fetch_bars(self, symbol, timeframe, count, before=None):
        """Try parquet cache first, then fall back to CSV files.

        This makes local development work with parity to the yfinance
        provider which writes parquet caches under `config.CACHE_DIR`.
        """
        import pandas as pd

        # Prefer parquet cache when available (atomic writes guarded by a lock)
        parquet_path = os.path.join(config.CACHE_DIR, f"{symbol}_{timeframe}.parquet")
        lock_path = parquet_path + ".lock"

        df = pd.DataFrame()
        # attempt to read parquet under lock
        try:
            # use portalocker to avoid race with writers
            with portalocker.Lock(lock_path, timeout=5):
                if os.path.exists(parquet_path):
                    try:
                        df = pd.read_parquet(parquet_path)
                    except Exception as e:
                        print(f"⚠️ Parquet read failed for {symbol}_{timeframe}: {e}. Falling back to CSV.")
        except Exception:
            # lock acquisition failed or other issue - continue to try CSV
            df = pd.DataFrame()

        # If parquet cache didn't yield results, fall back to CSV in DATA_DIR
        if df.empty:
            csv_filename = f"{symbol}_{timeframe}.csv"
            csv_path = os.path.join(config.DATA_DIR, csv_filename)
            if not os.path.exists(csv_path):
                raise FileNotFoundError(f"Data file not found in cache or samples: {parquet_path} / {csv_path}")

            df = pd.read_csv(csv_path)
            # Normalize datetime
            df["datetime"] = pd.to_datetime(df["datetime"])

        # ensure ordering
        df = df.sort_values("datetime")

        if before:
            before_dt = pd.to_datetime(before)
            df = df[df["datetime"] < before_dt]

        return df.tail(count).reset_index(drop=True)

    def get_available_symbols(self):
        """Return available (symbol, timeframe) tuples from both cache and sample dirs."""
        seen = set()
        results = []

        # look in cache dir for parquet files
        if os.path.exists(config.CACHE_DIR):
            for f in os.listdir(config.CACHE_DIR):
                if f.endswith(".parquet"):
                    parts = f.replace(".parquet", "").split("_")
                    if len(parts) == 2:
                        key = (parts[0], parts[1])
                        if key not in seen:
                            seen.add(key)
                            results.append(key)

        # look in data dir for csv samples (don't duplicate)
        if os.path.exists(config.DATA_DIR):
            for f in os.listdir(config.DATA_DIR):
                if f.endswith(".csv"):
                    parts = f.replace(".csv", "").split("_")
                    if len(parts) == 2:
                        key = (parts[0], parts[1])
                        if key not in seen:
                            seen.add(key)
                            results.append(key)

        return results


class MT5DataProvider(DataProvider):
    """Data provider using mt5linux (RPyC bridge to MT5)."""
    
    def __init__(self, host=None, port=None):
        self.host = host or config.MT5_HOST
        self.port = port or config.MT5_PORT
        self.mt5 = None
        
    def _connect(self):
        if self.mt5:
            return True
            
        try:
            from mt5linux import MetaTrader5
            self.mt5 = MetaTrader5(self.host, self.port)
            if not self.mt5.initialize():
                print(f"MT5 initialize failed, error code = {self.mt5.last_error()}")
                return False
            return True
        except Exception as e:
            print(f"Failed to connect to MT5 bridge: {e}")
            return False

    def fetch_bars(self, symbol, timeframe, count, before=None):
        import pandas as pd
        if not self._connect():
            raise ConnectionError("Could not connect to MT5")

        # Map timeframe to MT5 constant
        import mt5linux
        tf_map = {
            "M1": mt5linux.TIMEFRAME_M1,
            "M5": mt5linux.TIMEFRAME_M5,
            "M15": mt5linux.TIMEFRAME_M15,
            "H1": mt5linux.TIMEFRAME_H1,
            "H4": mt5linux.TIMEFRAME_H4,
            "D1": mt5linux.TIMEFRAME_D1,
        }
        
        mt5_tf = tf_map.get(timeframe)
        if mt5_tf is None:
            raise ValueError(f"Unsupported timeframe for MT5: {timeframe}")

        if before:
            # Fetch bars before specific time
            before_dt = pd.to_datetime(before)
            rates = self.mt5.copy_rates_from(symbol, mt5_tf, before_dt, count)
        else:
            # Fetch latest bars
            rates = self.mt5.copy_rates_from_pos(symbol, mt5_tf, 0, count)

        if rates is None or len(rates) == 0:
            return pd.DataFrame()

        df = pd.DataFrame(rates)
        df['datetime'] = pd.to_datetime(df['time'], unit='s')
        df = df[['datetime', 'open', 'high', 'low', 'close', 'tick_volume']]
        df.columns = ['datetime', 'open', 'high', 'low', 'close', 'volume']
        return df

    def get_available_symbols(self):
        if not self._connect():
            return []
        symbols = self.mt5.symbols_get()
        return [(s.name, "H1") for s in symbols] if symbols else []


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
        # yfinance optionally imports `curl_cffi.requests` if curl_cffi is
        # installed. In some environments curl_cffi imports eventlet which
        # pulls in green socket wrappers that lack `sendmsg`, causing
        # an AttributeError during import (see GreenSocket.sendmsg). To
        # avoid that, pre-register a lightweight shim module named
        # `curl_cffi` that exposes the standard `requests` API. This
        # prevents yfinance from importing the real curl_cffi package.
        try:
            import sys, types
            import requests as _real_requests
            if 'curl_cffi' not in sys.modules:
                # Create a requests-like shim that tolerates the
                # `impersonate` kwarg used by yfinance when curl_cffi
                # is present. We subclass the real requests.Session to
                # accept and ignore that extra kwarg.
                class _ShimSession(_real_requests.Session):
                    def __init__(self, *args, **kwargs):
                        kwargs.pop('impersonate', None)
                        super().__init__(*args, **kwargs)

                shim = types.ModuleType('curl_cffi')
                shim.requests = types.ModuleType('curl_cffi.requests')
                shim.requests.Session = _ShimSession
                # expose top-level helpers
                shim.requests.get = _real_requests.get
                shim.requests.post = _real_requests.post
                shim.requests.request = _real_requests.request
                shim.requests.utils = getattr(_real_requests, 'utils', None)
                shim.requests.Response = getattr(_real_requests, 'Response', None)
                shim.requests.exceptions = getattr(_real_requests, 'exceptions', None)
                shim.requests.adapters = getattr(_real_requests, 'adapters', None)
                shim.requests.models = getattr(_real_requests, 'models', None)
                # requests.sessions module contains the Session class reference
                shim.requests.session = getattr(_real_requests, 'sessions', types.SimpleNamespace(Session=_ShimSession))
                sys.modules['curl_cffi'] = shim
        except Exception:
            # If anything goes wrong here, fall back and let yfinance
            # import proceed (it may raise the original error).
            pass

        import yfinance as yf
        
        yf_symbol = config.SYMBOL_MAP.get(symbol, symbol)
        
        # yfinance timeframe mapping (flexible for case and format)
        yf_tf_map = {
            "M1": "1m", "M5": "5m", "M15": "15m",
            "H1": "1h", "H4": "4h", "D1": "1d",
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
    if provider_type == "mt5":
        return MT5DataProvider()
    elif provider_type == "yfinance":
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
