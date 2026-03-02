# PyReplay Trader

A professional-grade bar replay trading simulator inspired by TradingView. Step through market history bar by bar, execute simulated trades, and analyze performance with real-time metrics.

## Features

- **📊 Candlestick Chart** — Interactive Plotly.js chart with pan, zoom, and hover
- **⏯️ Replay Controls** — Play, pause, step forward/back, jump, adjustable speed (1x–10x)
- **💹 Trading Simulation** — Buy/sell with configurable lot size, stop loss, take profit
- **📈 Technical Indicators** — SMA, EMA, RSI, MACD, Bollinger Bands (toggle on/off)
- **📋 Account Stats** — Balance, equity, floating P&L, win rate, max drawdown
- **⌨️ Keyboard Shortcuts** — Space (play/pause), arrows (step), B/S (buy/sell)
- **🎨 Dark Theme** — TradingView-inspired professional UI

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Generate sample data (if not present)
python generate_sample_data.py

# 3. Run the app
python app.py
```

Open **http://localhost:5000** in your browser.

## Project Structure

```
bar_replay/
├── app.py                  # Flask entry point + API
├── config.py               # Settings (balance, spread, etc.)
├── backend/
│   ├── data_module.py      # Data loading & resampling
│   ├── replay_engine.py    # Replay state machine
│   ├── execution_engine.py # Trade simulation
│   ├── indicators.py       # Technical indicators
│   └── strategy_engine.py  # Strategy base class (Phase 2)
├── static/
│   ├── css/style.css       # Dark theme CSS
│   └── js/app.js           # Frontend logic
├── templates/
│   └── index.html          # Main page
├── data/sample/            # Sample OHLCV data
└── tests/                  # Unit tests (48 tests)
```

## API Endpoints

| Endpoint          | Method | Purpose                     |
|-------------------|--------|-----------------------------|
| `/api/load`       | POST   | Load symbol + timeframe     |
| `/api/data`       | GET    | Get chart data + indicators |
| `/api/step`       | POST   | Step forward 1 bar          |
| `/api/back`       | POST   | Step backward 1 bar         |
| `/api/play`       | POST   | Start auto-play             |
| `/api/pause`      | POST   | Pause replay                |
| `/api/jump`       | POST   | Jump to index/date          |
| `/api/speed`      | POST   | Set replay speed            |
| `/api/trade`      | POST   | Buy/sell/close/modify       |
| `/api/indicators` | POST   | Toggle indicators           |
| `/api/stats`      | GET    | Account stats               |

## Running Tests

```bash
python -m pytest tests/ -v
```

## Tech Stack

- **Backend:** Python 3.11+, Flask, Pandas, NumPy
- **Frontend:** Plotly.js, Vanilla JS, CSS
- **Data:** CSV (MT5 integration planned)