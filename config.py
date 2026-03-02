"""Application configuration for PyReplay Trader."""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data", "sample")

# Trading defaults
INITIAL_BALANCE = 10000.0
DEFAULT_SPREAD_PIPS = 2.0
DEFAULT_COMMISSION = 0.0
DEFAULT_LOT_SIZE = 0.1
PIP_VALUE = 0.0001  # For most FX pairs (USDJPY uses 0.01)

# Replay defaults
DEFAULT_SPEED = 1  # 1x speed
DEFAULT_VISIBLE_BARS = 100  # Number of bars visible on chart at once

# Server
HOST = "0.0.0.0"
PORT = 5000
DEBUG = True
