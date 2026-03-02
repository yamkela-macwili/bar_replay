# TECHNICAL ARCHITECTURE 

---

# 1. System Architecture

```
MT5 → Data Loader → Replay Engine → Strategy Engine
                                 ↓
                           Execution Engine
                                 ↓
                          Flask API Layer
                                 ↓
                           Frontend (JS)
```

---

# 2. Backend Stack

* Python 3.11
* Flask (REST API)
* MetaTrader5 API
* Pandas
* NumPy
* TA-Lib
* Redis (optional state store)
* Docker

---

# 3. Core Modules

---

## 3.1 Data Module

Responsibilities:

* Fetch historical data from MT5
* Cache to CSV or PostgreSQL
* Normalize timeframes

Functions:

```python
load_symbol(symbol, timeframe, start, end)
resample_timeframe(df, tf)
```

---

## 3.2 Replay Engine

Core class:

```python
class ReplayEngine:
    def __init__(self, data):
        self.data = data
        self.current_index = 0
        self.speed = 1
        self.state = "paused"

    def step_forward(self):
        self.current_index += 1

    def step_back(self):
        self.current_index -= 1

    def play(self):
        self.state = "playing"
```

---

## 3.3 Execution Engine

Handles:

* Position tracking
* Order simulation
* SL/TP hit detection
* Spread simulation

---

## 3.4 Strategy Engine

Accepts:

```python
class BaseStrategy:
    def on_bar(self, bar, context):
        pass
```

User strategies extend this.

---

## 3.5 Flask API

Endpoints:

| Endpoint | Method | Purpose                |
| -------- | ------ | ---------------------- |
| /load    | POST   | Load symbol/timeframe  |
| /step    | POST   | Move replay forward    |
| /back    | POST   | Move replay backward   |
| /trade   | POST   | Buy/Sell               |
| /stats   | GET    | Strategy metrics       |
| /data    | GET    | Get visible chart data |

---

# 4. Frontend

Option 1 (Recommended):

* Flask + Jinja
* Plotly.js

Option 2 (Professional):

* Separate React frontend

---

# 5. Docker Architecture

Dockerfile:

* Base: python:3.11
* Install:

  * MetaTrader5
  * Flask
  * Pandas
* Volume mount:

  * MT5 data directory

---

# 6. Key Engineering Challenges

1. Reverse replay (must track state history)
2. Realistic execution modeling
3. Synchronizing UI and backend state
4. Handling multi-timeframe aggregation
5. MT5 connection reliability under Wine

---

# 🚀 Reality Check

This is not a small project.

You're building:

* A mini trading simulator
* A visual replay engine
* A strategy testing platform

It’s closer to building a lightweight version of:

* MetaTrader 5 strategy tester
* Combined with TradingView replay UX

---


