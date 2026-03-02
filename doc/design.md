

# DESIGN DOCUMENT

We are modeling UI behavior after:

* TradingView Bar Replay

---

# 1. Layout Architecture

```
---------------------------------------------------------
| Top Navigation Bar                                    |
---------------------------------------------------------
| Chart Area (Candlestick)                              |
|                                                       |
|                                                       |
---------------------------------------------------------
| Replay Controls | Speed | Date Picker | Stats Panel  |
---------------------------------------------------------
| Trade History | Equity Curve | Strategy Metrics      |
---------------------------------------------------------
```

---

# 2. UI Components

## 2.1 Top Bar

* Symbol selector dropdown
* Timeframe dropdown
* Indicator button
* Strategy attach button
* Replay toggle

---

## 2.2 Chart Area

* Candlestick chart (Plotly recommended)
* Indicators overlay
* Trade markers:

  * Green arrow (buy)
  * Red arrow (sell)
  * SL/TP lines

---

## 2.3 Replay Control Panel

Buttons:

| Button | Function      |
| ------ | ------------- |
| ⏮      | Jump back     |
| ◀      | Step backward |
| ▶      | Play          |
| ⏸      | Pause         |
| ▶▶     | Step forward  |
| ⏭      | Jump forward  |

Speed selector:

* 1x
* 2x
* 5x
* 10x

---

## 2.4 Stats Panel

Display:

* Balance
* Equity
* Floating PnL
* Closed PnL
* Max Drawdown
* Win rate
* Total trades

---

# 3. UX Principles

* Dark theme (like TradingView)
* Smooth bar reveal animation
* No lag during replay
* Hotkeys support (space = play/pause)

---
