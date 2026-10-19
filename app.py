"""PyReplay Trader — Flask application entry point."""

# Ensure the project root is on sys.path so `import config` works when the
# app is executed as a script from different working directories or by
# gunicorn. This is a minimal, safe change that doesn't alter behavior.
import os
import sys
import math
repo_root = os.path.dirname(os.path.abspath(__file__))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from flask import Flask, render_template, jsonify, request, session
import pandas as pd
import uuid

import config
from backend import data_module
from backend import engine_system
from backend.engine_store import store

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

@app.before_request
def ensure_session():
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())

def get_system():
    """Retrieve the current user's ReplaySystem from the store."""
    sid = session.get("session_id")
    # Fallback to request indices if session cookie is missing/empty
    if not sid:
        if request.is_json:
            sid = request.json.get("session_id")
        else:
            sid = request.args.get("session_id")
            
    if not sid:
        return None
        
    return store.get(sid)

def save_system(system):
    """Save the current user's ReplaySystem back to the store."""
    if system and system.session_id:
        store.set(system.session_id, system)


def as_utc_iso(value):
    """Serialize provider timestamps as explicit UTC instead of ambiguous naive time."""
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert("UTC")
    return timestamp.isoformat().replace("+00:00", "Z")

def init_engines(symbol="EURUSD", timeframe="H1", provider="csv", session_id=None,
                 initial_balance=None):
    """Initialize or re-initialize the replay and execution engines."""
    from backend.engine_system import EngineFactory
    
    # Use provided ID, or fallback to current session
    if not session_id:
        session_id = session.get("session_id")
        
    # Only allow safe/cache-backed providers for the chart UI. Reject or
    # coerce legacy/local providers to the cache-backed yfinance provider.
    allowed_providers = {"yfinance"}
    if provider not in allowed_providers:
        provider = "yfinance"

    new_system = EngineFactory.create(
        symbol, timeframe, provider, session_id=session_id,
        initial_balance=initial_balance
    )
    save_system(new_system)
    return new_system

# ── Pages ─────────────────────────────────────────────────────
@app.route("/")
def index():
    """Serve the main application page."""
    # Use yfinance/cache-backed symbols for the UI — hide CSV/MT5 choices
    symbols = data_module.get_available_symbols("yfinance")
    return render_template(
        "index.html", symbols=symbols, initial_balance=config.INITIAL_BALANCE
    )


# ── Data API ──────────────────────────────────────────────────
@app.route("/api/load", methods=["POST"])
def api_load():
    """Load a symbol and timeframe into the replay engine."""
    data = request.get_json(force=True)
    symbol = data.get("symbol", "EURUSD")
    if symbol not in config.SYMBOL_MAP:
        return jsonify({"status": "error", "message": f"Unsupported symbol: {symbol}"}), 400
    timeframe = data.get("timeframe", "H1")
    timeframe = str(timeframe).upper()
    if timeframe not in {"M5", "M15", "H1", "H4", "D1"}:
        return jsonify({
            "status": "error",
            "message": f"Unsupported timeframe: {timeframe}. Choose M5, M15, H1, H4, or D1."
        }), 400
    initial_balance = data.get("initial_balance")
    if initial_balance is not None:
        try:
            initial_balance = float(initial_balance)
            if not math.isfinite(initial_balance) or initial_balance <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({
                "status": "error",
                "message": "Balance must be a positive number."
            }), 400
    provider = data.get("provider", "csv")
    session_id = data.get("session_id") # Explicit ID from frontend

    try:
        system = init_engines(
            symbol, timeframe, provider, session_id=session_id,
            initial_balance=initial_balance
        )
        return jsonify({
            "status": "ok",
            "symbol": symbol,
            "timeframe": timeframe,
            "total_bars": system.replay_engine.total_bars,
            "start_index": system.replay_engine.current_index,
            "visible_count": config.INITIAL_BAR_COUNT,
            "session_id": system.session_id
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/api/data", methods=["GET"])
def api_data():
    """Get visible chart data and computed indicators."""
    system = get_system()
    if system is None:
        return jsonify({"status": "error", "message": "No data loaded"}), 400

    visible = system.replay_engine.get_visible_data(max_bars=config.INITIAL_BAR_COUNT)
    bars = visible["bars"]
    indicators_data = visible["indicators"]

    # Check SL/TP on current bar
    if system.execution_engine and len(system.execution_engine.open_positions) > 0:
        current_bar = system.replay_engine.get_current_bar()
        system.execution_engine.check_sl_tp(current_bar)
        save_system(system)

    current_price = float(bars.iloc[-1]["close"])
    progress = system.replay_engine.get_progress()
    progress["current_datetime"] = as_utc_iso(progress["current_datetime"])
    latest_bar = system.replay_engine.data["datetime"].iloc[-1]

    account = system.execution_engine.get_account_state(current_price)
    save_system(system)

    return jsonify({
        "status": "ok",
        "bars": {
            "datetime": [as_utc_iso(value) for value in bars["datetime"]],
            "open": bars["open"].tolist(),
            "high": bars["high"].tolist(),
            "low": bars["low"].tolist(),
            "close": bars["close"].tolist(),
            "volume": bars["volume"].tolist(),
        },
        "indicators": indicators_data,
        "progress": progress,
        "market_data": {
            "latest_bar": as_utc_iso(latest_bar),
            "checked_at": getattr(system, "source_checked_at", None),
            "refresh_error": getattr(system, "source_refresh_error", None),
            "provider": system.provider,
            "symbol": system.symbol,
            "timeframe": system.timeframe,
        },
        "account": account,
        "open_positions": system.execution_engine.get_open_positions(current_price),
        "trade_history": system.execution_engine.get_trade_history(),
        "session_id": system.session_id
    })


@app.route("/api/session", methods=["GET"])
def api_session():
    """Bootstrap a session for the client."""
    return jsonify({
        "status": "ok",
        "session_id": session.get("session_id")
    })


@app.route("/api/account/balance", methods=["POST"])
def api_set_balance():
    """Set the account's cash balance, preserving live positions and P&L."""
    system = get_system()
    if system is None:
        return jsonify({"status": "error", "message": "No data loaded"}), 400

    data = request.get_json(force=True)
    try:
        system.execution_engine.set_balance(data.get("balance"))
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400

    current_price = float(system.replay_engine.get_current_bar()["close"])
    account = system.execution_engine.get_account_state(current_price)
    save_system(system)
    return jsonify({
        "status": "ok",
        "account": account,
    })


@app.route("/api/data/load_more", methods=["GET"])
def api_load_more():
    """Fetch more bars for lazy loading (backward or forward)."""
    system = get_system()
    if system is None:
        return jsonify({"status": "error", "message": "No data loaded"}), 400

    direction = request.args.get("direction", "backward")
    
    try:
        from backend import data_module
        provider = data_module.get_provider(system.provider)
        
        if direction == "backward":
            anchor_time = system.replay_engine.data["datetime"].min().isoformat()
            new_data = provider.fetch_bars(
                system.symbol, system.timeframe, 
                count=config.LAZY_LOAD_COUNT, 
                before=anchor_time
            )
            num_added = system.replay_engine.prepend_data(new_data)
        else:
            num_added = 0
            
        if num_added > 0:
            system.refresh_indicators()
            save_system(system)
            
        return jsonify({
            "status": "ok",
            "added": num_added,
            "direction": direction,
            "total_bars": system.replay_engine.total_bars,
            "current_index": system.replay_engine.current_index,
            "session_id": system.session_id
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


# ── Replay Controls ──────────────────────────────────────────
@app.route("/api/step", methods=["POST"])
def api_step():
    """Step replay forward by one bar."""
    system = get_system()
    if system is None:
        return jsonify({"status": "error", "message": "No data loaded"}), 400

    success = system.replay_engine.step_forward()

    # Check SL/TP on the new bar
    if success and system.execution_engine:
        current_bar = system.replay_engine.get_current_bar()
        system.execution_engine.check_sl_tp(current_bar)
    
    save_system(system)

    return jsonify({
        "status": "ok" if success else "end",
        "progress": system.replay_engine.get_progress(),
    })


@app.route("/api/back", methods=["POST"])
def api_back():
    """Step replay backward by one bar."""
    system = get_system()
    if system is None:
        return jsonify({"status": "error", "message": "No data loaded"}), 400

    success = system.replay_engine.step_back()
    save_system(system)
    return jsonify({
        "status": "ok" if success else "start",
        "progress": system.replay_engine.get_progress(),
    })


@app.route("/api/play", methods=["POST"])
def api_play():
    """Start auto-play."""
    system = get_system()
    if system is None:
        return jsonify({"status": "error", "message": "No data loaded"}), 400

    system.replay_engine.play()
    save_system(system)
    return jsonify({
        "status": "ok",
        "interval_ms": system.replay_engine.get_interval_ms(),
        "progress": system.replay_engine.get_progress(),
    })


@app.route("/api/pause", methods=["POST"])
def api_pause():
    """Pause auto-play."""
    system = get_system()
    if system is None:
        return jsonify({"status": "error", "message": "No data loaded"}), 400

    system.replay_engine.pause()
    save_system(system)
    return jsonify({
        "status": "ok",
        "progress": system.replay_engine.get_progress(),
    })


@app.route("/api/jump", methods=["POST"])
def api_jump():
    """Jump to a specific index or date."""
    system = get_system()
    if system is None:
        return jsonify({"status": "error", "message": "No data loaded"}), 400

    data = request.get_json(force=True)
    index = data.get("index")
    date = data.get("date")

    if index is not None:
        success = system.replay_engine.jump_to(int(index))
    elif date:
        success = system.replay_engine.jump_to_date(date)
    else:
        return jsonify({"status": "error", "message": "Provide index or date"}), 400

    save_system(system)
    return jsonify({
        "status": "ok" if success else "error",
        "progress": system.replay_engine.get_progress(),
    })


@app.route("/api/speed", methods=["POST"])
def api_speed():
    """Set replay speed."""
    system = get_system()
    if system is None:
        return jsonify({"status": "error", "message": "No data loaded"}), 400

    data = request.get_json(force=True)
    speed = int(data.get("speed", 1))

    success = system.replay_engine.set_speed(speed)
    save_system(system)
    return jsonify({
        "status": "ok" if success else "error",
        "speed": system.replay_engine.speed,
        "interval_ms": system.replay_engine.get_interval_ms(),
    })


# ── Trading API ───────────────────────────────────────────────
@app.route("/api/trade", methods=["POST"])
def api_trade():
    """Execute a trading action (buy, sell, close, modify, close_all)."""
    system = get_system()
    if system is None:
        return jsonify({"status": "error", "message": "No data loaded"}), 400

    data = request.get_json(force=True)
    action = data.get("action")
    current_bar = system.replay_engine.get_current_bar()
    current_price = float(current_bar["close"])
    current_time = current_bar["datetime"]

    if action in ("buy", "sell"):
        lot_size = data.get("lot_size", config.DEFAULT_LOT_SIZE)
        sl = data.get("sl")
        tp = data.get("tp")

        try:
            lot_size = float(lot_size)
            sl = float(sl) if sl is not None else None
            tp = float(tp) if tp is not None else None
            if (not math.isfinite(lot_size) or lot_size <= 0 or
                    (sl is not None and (not math.isfinite(sl) or sl <= 0)) or
                    (tp is not None and (not math.isfinite(tp) or tp <= 0))):
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({
                "status": "error",
                "message": "Lot size must be positive, and stop loss/take profit must be positive prices."
            }), 400

        result = system.execution_engine.open_position(
            direction=action,
            lot_size=lot_size,
            sl=sl,
            tp=tp,
            current_price=current_price,
            current_time=current_time,
            symbol=system.symbol,
        )
        save_system(system)
        return jsonify({
            "status": "ok" if result else "error",
            "position": result,
            "account": system.execution_engine.get_account_state(current_price),
        })

    elif action == "close":
        position_id = data.get("position_id")
        result = system.execution_engine.close_position(
            position_id, current_price, current_time
        )
        save_system(system)
        return jsonify({
            "status": "ok" if result else "error",
            "position": result,
            "account": system.execution_engine.get_account_state(current_price),
        })

    elif action == "close_all":
        results = system.execution_engine.close_all_positions(current_price, current_time)
        save_system(system)
        return jsonify({
            "status": "ok",
            "closed": results,
            "account": system.execution_engine.get_account_state(current_price),
        })

    elif action == "modify":
        position_id = data.get("position_id")
        sl = data.get("sl")
        tp = data.get("tp")
        try:
            sl = float(sl) if sl is not None else None
            tp = float(tp) if tp is not None else None
            if ((sl is not None and (not math.isfinite(sl) or sl <= 0)) or
                    (tp is not None and (not math.isfinite(tp) or tp <= 0))):
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({
                "status": "error",
                "message": "Stop loss and take profit must be positive finite prices."
            }), 400
        result = system.execution_engine.modify_position(position_id, sl=sl, tp=tp)
        save_system(system)
        return jsonify({
            "status": "ok" if result else "error",
            "position": result,
        })

    return jsonify({"status": "error", "message": f"Unknown action: {action}"}), 400


# ── Indicators API ────────────────────────────────────────────
@app.route("/api/indicators", methods=["POST"])
def api_indicators():
    """Toggle indicators on/off or update settings."""
    system = get_system()
    if system is None:
        return jsonify({"status": "error", "message": "No data loaded"}), 400

    data = request.get_json(force=True)
    action = data.get("action", "toggle")
    name = data.get("name")
    settings = data.get("settings", {})

    allowed_names = {"sma", "ema", "rsi", "macd", "bollinger"}
    if action not in {"toggle", "set", "remove", "clear"}:
        return jsonify({"status": "error", "message": "Unknown indicator action"}), 400
    if action != "clear" and name not in allowed_names:
        return jsonify({"status": "error", "message": "Unknown indicator"}), 400
    if not isinstance(settings, dict):
        return jsonify({"status": "error", "message": "Indicator settings must be an object"}), 400
    try:
        if name in {"sma", "ema", "rsi", "bollinger"}:
            period = int(settings.get("period", 20))
            if period < 2 or period > 500:
                raise ValueError
            settings["period"] = period
        if name == "macd":
            fast = int(settings.get("fast", 12))
            slow = int(settings.get("slow", 26))
            signal = int(settings.get("signal", 9))
            if fast < 2 or slow <= fast or signal < 1 or slow > 500 or signal > 500:
                raise ValueError
            settings.update(fast=fast, slow=slow, signal=signal)
        if name == "bollinger":
            std_dev = float(settings.get("std_dev", 2.0))
            if not math.isfinite(std_dev) or std_dev <= 0 or std_dev > 10:
                raise ValueError
            settings["std_dev"] = std_dev
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Invalid indicator parameters"}), 400

    if action == "toggle":
        if name in system.active_indicators:
            del system.active_indicators[name]
        else:
            system.active_indicators[name] = settings
    elif action == "set":
        system.active_indicators[name] = settings
    elif action == "remove":
        system.active_indicators.pop(name, None)
    elif action == "clear":
        system.active_indicators = {}
    
    try:
        system.refresh_indicators()
    except Exception as e:
        return jsonify({"status": "error", "message": f"Could not compute indicators: {e}"}), 400
    save_system(system)

    return jsonify({
        "status": "ok",
        "active_indicators": system.active_indicators,
    })


@app.route("/api/stats", methods=["GET"])
def api_stats():
    """Get account stats and trade history."""
    system = get_system()
    if system is None:
        return jsonify({"status": "error", "message": "No data loaded"}), 400

    current_price = float(system.replay_engine.get_current_bar()["close"])

    return jsonify({
        "status": "ok",
        "account": system.execution_engine.get_account_state(current_price),
        "open_positions": system.execution_engine.get_open_positions(),
        "trade_history": system.execution_engine.get_trade_history(),
    })


# ── Entry Point ───────────────────────────────────────────────
if __name__ == "__main__":
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
