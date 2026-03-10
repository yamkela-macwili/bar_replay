"""Application configuration for PyReplay Trader.

Production-ready configuration with environment validation.
No development shortcuts allowed for Render deployment.
"""

import os
import logging
from pathlib import Path

# ────────────────────────────────────────────────────────────────────────────
# Environment & Deployment Configuration
# ────────────────────────────────────────────────────────────────────────────

ENVIRONMENT = os.environ.get("ENVIRONMENT", "development").lower()
IS_PRODUCTION = ENVIRONMENT == "production"

# Directory setup - works in containerized environments
BASE_DIR = Path(__file__).parent.resolve()
DATA_DIR = BASE_DIR / "data" / "sample"
CACHE_DIR = BASE_DIR / "data" / "cache"

# Ensure cache directory exists
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ────────────────────────────────────────────────────────────────────────────
# Security Configuration
# ────────────────────────────────────────────────────────────────────────────

SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    if IS_PRODUCTION:
        raise RuntimeError(
            "CRITICAL: SECRET_KEY environment variable not set. "
            "This is required for production deployment."
        )
    SECRET_KEY = "dev-only-key-change-in-production"
    logging.warning("Using development SECRET_KEY. Set SECRET_KEY environment variable for production.")

# Session configuration - production-grade
SESSION_COOKIE_SECURE = IS_PRODUCTION
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_NAME = "pyreplay_session"
PERMANENT_SESSION_LIFETIME = 7200  # 2 hours


# ────────────────────────────────────────────────────────────────────────────
# Redis & Persistence Configuration
# ────────────────────────────────────────────────────────────────────────────

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
REDIS_CONN_TIMEOUT = 5
REDIS_SOCKET_TIMEOUT = 5
REDIS_SOCKET_KEEPALIVE = True
REDIS_HEALTH_CHECK_INTERVAL = 30

SESSION_TTL = int(os.environ.get("SESSION_TTL", "7200"))  # 2 hours
SESSION_COMPRESSION_THRESHOLD = int(os.environ.get(
    "SESSION_COMPRESSION_THRESHOLD", "1048576"  # 1MB
))


# ────────────────────────────────────────────────────────────────────────────
# Trading Defaults (Immutable)
# ────────────────────────────────────────────────────────────────────────────

INITIAL_BALANCE = 10000.0
DEFAULT_SPREAD_PIPS = 2.0
DEFAULT_COMMISSION = 0.0
DEFAULT_LOT_SIZE = 0.1
PIP_VALUE = 0.0001  # For most FX pairs (USDJPY uses 0.01)


# ────────────────────────────────────────────────────────────────────────────
# MT5 Configuration (Stateless, Lazy-Loaded)
# ────────────────────────────────────────────────────────────────────────────

MT5_HOST = os.environ.get("MT5_HOST", "localhost")
MT5_PORT = int(os.environ.get("MT5_PORT", "18812"))
MT5_USE_LINUX = True
MT5_TIMEOUT = 10


# ────────────────────────────────────────────────────────────────────────────
# Replay Engine Defaults
# ────────────────────────────────────────────────────────────────────────────

DEFAULT_SPEED = 1
DEFAULT_VISIBLE_BARS = 100
INITIAL_BAR_COUNT = 200
LAZY_LOAD_COUNT = 100
MAX_BARS_LIMIT = 3000
DEFAULT_TIMEFRAME = "4H"


# ────────────────────────────────────────────────────────────────────────────
# Data Provider Configuration
# ────────────────────────────────────────────────────────────────────────────

DEFAULT_DATA_PROVIDER = "csv"  # Fallback to CSV if yfinance fails
DATA_FETCH_TIMEOUT = 30
YFINANCE_CACHE_TTL = 86400  # 24 hours

SYMBOL_MAP = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "AUDUSD": "AUDUSD=X",
    "USDCAD": "CAD=X",
    "USDCHF": "CHF=X",
    "NZDUSD": "NZDUSD=X",
    "XAUUSD": "GC=F",
    "BTCUSD": "BTC-USD"
}


# ────────────────────────────────────────────────────────────────────────────
# Server Configuration (Production-Ready)
# ────────────────────────────────────────────────────────────────────────────

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "5000"))
DEBUG = False  # ALWAYS False in any deployed environment
TESTING = False

# Gunicorn will override these, but kept for Flask dev server fallback
FLASK_ENV = "production" if IS_PRODUCTION else "development"


# ────────────────────────────────────────────────────────────────────────────
# Logging Configuration
# ────────────────────────────────────────────────────────────────────────────

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO" if IS_PRODUCTION else "DEBUG")
LOG_FORMAT = os.environ.get(
    "LOG_FORMAT",
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


# ────────────────────────────────────────────────────────────────────────────
# Validation: Ensure production safety
# ────────────────────────────────────────────────────────────────────────────

def validate_production_config():
    """Validate that production configuration is safe."""
    if not IS_PRODUCTION:
        return

    errors = []

    if not SECRET_KEY or len(SECRET_KEY) < 32:
        errors.append("SECRET_KEY must be >= 32 characters")

    if SESSION_COOKIE_SECURE is False:
        errors.append("SESSION_COOKIE_SECURE must be True in production")

    if SESSION_COOKIE_HTTPONLY is False:
        errors.append("SESSION_COOKIE_HTTPONLY must be True in production")

    if DEBUG is True:
        errors.append("DEBUG must be False in production")

    if errors:
        raise RuntimeError(
            f"Production configuration validation failed:\n" +
            "\n".join(f"  - {e}" for e in errors)
        )

    logging.info("✅ Production configuration validated successfully")


# Run validation on import
validate_production_config()
