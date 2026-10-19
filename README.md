# PyReplay Trader

A professional-grade bar replay trading simulator inspired by TradingView. Step through market history bar by bar, execute simulated trades, and analyze performance with real-time metrics.

## Features

- **👥 Multi-User Scalability** — Isolated concurrent replay sessions via Redis-backed state management
- **📊 Professional Charting** — Interactive Plotly.js chart with technical indicators (SMA, EMA, RSI, MACD, BB)
- **🖍️ Chart Drawings** — Horizontal/vertical lines and rays, trend lines, rectangles, and long/short position zones; drawings can be edited and are saved per symbol/timeframe
- **📱 Responsive Layout** — Chart, replay controls, and account/trading panels adapt to tablet and phone widths
- **⏯️ Replay Controls** — Play, pause, step forward/back, jump, adjustable speed (1x–10x)
- **💹 Trading Simulation** — Buy/sell with SL/TP, isolated account stats, and real-time equity tracking
- **🔄 Smart Caching** — Thread-safe Parquet caching with Yahoo Finance as the default data provider
- **⌨️ Keyboard Shortcuts** — Space (play/pause), arrows (step), B/S (buy/sell)

## Data and TradingView Scope

This project is a bar-replay trading simulator inspired by TradingView, not a replacement for TradingView Supercharts. It currently provides one chart, five intervals (M5, M15, H1, H4, D1), a small indicator set, basic drawings, and simulated orders. It does not provide a live tick stream, exchange subscriptions, alerts, watchlists, news, Pine Script, or broker connectivity.

Loading a chart asks Yahoo Finance for the latest available bars and displays the newest returned timestamp in the chart header. Yahoo availability and market hours determine that timestamp; when a market is closed or the refresh fails, the app shows the last available bar and flags a failed refresh instead of fabricating a bar for today. H4 bars are aggregated from hourly data.

## Quick Start (Scaling Mode)

The system is now production-ready and supports horizontal scaling via Docker and Redis.

```bash
# 1. Start the platform with Docker Compose
docker-compose up --build
```
This starts the Flask API and a Redis instance for session state. Open **http://localhost:5000** in your browser.

### Local Development (No Docker)
If you don't have Docker, the system will fall back to `fakeredis`:
```bash
pip install -r requirements.txt
python app.py
```

## Project Structure

```
bar_replay/
├── app.py                  # Flask entry point (Stateless / Session-aware)
├── config.py               # Production settings (Redis URL, TTL, etc.)
├── docker-compose.yml      # Orchestration for scaling
├── backend/
│   ├── engine_store.py     # Redis-backed session management
│   ├── data_module.py      # Thread-safe caching & yfinance provider
│   ├── engine_system.py    # Isolated ReplaySystem lifecycle
│   ├── replay_engine.py    # Replay state machine
│   ├── execution_engine.py # Trade simulation
│   └── indicators.py       # Technical indicators
├── static/                 # Frontend assets (Vanilla JS + Plotly)
└── tests/                  # Unit tests (including multi-user isolation tests)
```

## API Endpoints (Session-bound)

| Endpoint          | Method | Purpose                     |
|-------------------|--------|-----------------------------|
| `/api/session`    | GET    | Bootstrap user session ID   |
| `/api/load`       | POST   | Load symbol + timeframe     |
| `/api/data`       | GET    | Get chart data + indicators |
| `/api/step`       | POST   | Step forward 1 bar          |
| `/api/trade`      | POST   | Buy/sell/close/modify       |
| `/api/indicators` | POST   | Toggle indicators           |

## Tech Stack

- **Backend:** Python 3.11+, Flask, Redis (dill serialization), Pandas, PyArrow
- **Frontend:** Vanilla JS, Plotly.js, CSS
- **Concurrency:** portalocker (file-level cache locking)
