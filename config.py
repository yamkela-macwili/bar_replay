"""Application configuration for PyReplay Trader."""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Point DATA_DIR at the repository `data/` folder (samples live here in this repo)
DATA_DIR = os.path.join(BASE_DIR, "data")

# Trading defaults
INITIAL_BALANCE = 10000.0
DEFAULT_SPREAD_PIPS = 2.0
DEFAULT_COMMISSION = 0.0
DEFAULT_LOT_SIZE = 0.1
PIP_VALUE = 0.0001  # For most FX pairs (USDJPY uses 0.01)

# MT5 Configuration
MT5_HOST = "localhost"
MT5_PORT = 18812
MT5_USE_LINUX = True  # Use mt5linux bridge

# Replay defaults
DEFAULT_SPEED = 1  # 1x speed
DEFAULT_VISIBLE_BARS = 100  # Number of bars visible on chart at once
INITIAL_BAR_COUNT = 200     # Initial number of bars to load
LAZY_LOAD_COUNT = 100       # Number of bars to fetch when scrolling back
MAX_BARS_LIMIT = 3000       # Maximum number of bars to keep in RAM
DEFAULT_TIMEFRAME = "4H"

# Data paths
CACHE_DIR = os.path.join(BASE_DIR, "data", "cache")

# Symbol Mappings (UI -> yfinance)
SYMBOL_MAP = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "AUDUSD": "AUDUSD=X",
    "USDCAD": "USDCAD=X",
    "XAUUSD": "XAUUSD=X",
    "BTCUSD": "BTC-USD",
    "USDCHF": "USDCHF=X",
    "NZDUSD": "NZDUSD=X",
    "USD_INDEX": "DX-Y.NYB"
}

# Scalability & Sessions
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
SESSION_TTL = 7200  # 2 hours inactivity timeout
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-12345")

# Server
HOST = "0.0.0.0"
PORT = 5000
DEBUG = True
