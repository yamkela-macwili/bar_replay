"""PyReplay Trader — Flask application entry point."""

from flask import Flask, render_template, jsonify, request

import config
from backend.data_module import load_symbol, get_available_symbols
from backend.replay_engine import ReplayEngine
from backend.execution_engine import ExecutionEngine
from backend.indicators import compute_indicators

app = Flask(__name__)

# ── Global State ──────────────────────────────────────────────
replay = None
execution = None
active_indicators = {}


def init_engines(symbol="EURUSD", timeframe="H1"):
    """Initialize or re-initialize the replay and execution engines."""
    global replay, execution, active_indicators
    df = load_symbol(symbol, timeframe)
    replay = ReplayEngine(df)
    execution = ExecutionEngine()
    active_indicators = {}


# ── Pages ─────────────────────────────────────────────────────
@app.route("/")
def index():
    """Serve the main application page."""
    symbols = get_available_symbols()
    return render_template("index.html", symbols=symbols)


# ── Data API ──────────────────────────────────────────────────
@app.route("/api/load", methods=["POST"])
def api_load():
    """Load a symbol and timeframe into the replay engine."""
    data = request.get_json(force=True)
    symbol = data.get("symbol", "EURUSD")
    timeframe = data.get("timeframe", "H1")

    try:
        init_engines(symbol, timeframe)
        return jsonify({
            "status": "ok",
            "symbol": symbol,
            "timeframe": timeframe,
            "total_bars": replay.total_bars,
        })
    except FileNotFoundError as e:
        return jsonify({"status": "error", "message": str(e)}), 404


@app.route("/api/data", methods=["GET"])
def api_data():
    """Get visible chart data and computed indicators."""
    if replay is None:
        return jsonify({"status": "error", "message": "No data loaded"}), 400

    visible = replay.get_visible_data()
    indicators_data = compute_indicators(visible, active_indicators)

    # Check SL/TP on current bar
    if execution and len(execution.open_positions) > 0:
        current_bar = replay.get_current_bar()
        execution.check_sl_tp(current_bar)

    current_price = float(visible.iloc[-1]["close"])

    return jsonify({
        "status": "ok",
        "bars": {
            "datetime": visible["datetime"].astype(str).tolist(),
            "open": visible["open"].tolist(),
            "high": visible["high"].tolist(),
            "low": visible["low"].tolist(),
            "close": visible["close"].tolist(),
            "volume": visible["volume"].tolist(),
        },
        "indicators": indicators_data,
        "progress": replay.get_progress(),
        "account": execution.get_account_state(current_price)
            if execution else None,
        "open_positions": execution.get_open_positions()
            if execution else [],
        "trade_history": execution.get_trade_history()
            if execution else [],
    })


# ── Replay Controls ──────────────────────────────────────────
@app.route("/api/step", methods=["POST"])
def api_step():
    """Step replay forward by one bar."""
    if replay is None:
        return jsonify({"status": "error", "message": "No data loaded"}), 400

    success = replay.step_forward()

    # Check SL/TP on the new bar
    if success and execution:
        current_bar = replay.get_current_bar()
        execution.check_sl_tp(current_bar)

    return jsonify({
        "status": "ok" if success else "end",
        "progress": replay.get_progress(),
    })


@app.route("/api/back", methods=["POST"])
def api_back():
    """Step replay backward by one bar."""
    if replay is None:
        return jsonify({"status": "error", "message": "No data loaded"}), 400

    success = replay.step_back()
    return jsonify({
        "status": "ok" if success else "start",
        "progress": replay.get_progress(),
    })


@app.route("/api/play", methods=["POST"])
def api_play():
    """Start auto-play."""
    if replay is None:
        return jsonify({"status": "error", "message": "No data loaded"}), 400

    replay.play()
    return jsonify({
        "status": "ok",
        "interval_ms": replay.get_interval_ms(),
        "progress": replay.get_progress(),
    })


@app.route("/api/pause", methods=["POST"])
def api_pause():
    """Pause auto-play."""
    if replay is None:
        return jsonify({"status": "error", "message": "No data loaded"}), 400

    replay.pause()
    return jsonify({
        "status": "ok",
        "progress": replay.get_progress(),
    })


@app.route("/api/jump", methods=["POST"])
def api_jump():
    """Jump to a specific index or date."""
    if replay is None:
        return jsonify({"status": "error", "message": "No data loaded"}), 400

    data = request.get_json(force=True)
    index = data.get("index")
    date = data.get("date")

    if index is not None:
        success = replay.jump_to(int(index))
    elif date:
        success = replay.jump_to_date(date)
    else:
        return jsonify({"status": "error", "message": "Provide index or date"}), 400

    return jsonify({
        "status": "ok" if success else "error",
        "progress": replay.get_progress(),
    })


@app.route("/api/speed", methods=["POST"])
def api_speed():
    """Set replay speed."""
    if replay is None:
        return jsonify({"status": "error", "message": "No data loaded"}), 400

    data = request.get_json(force=True)
    speed = int(data.get("speed", 1))

    success = replay.set_speed(speed)
    return jsonify({
        "status": "ok" if success else "error",
        "speed": replay.speed,
        "interval_ms": replay.get_interval_ms(),
    })


# ── Trading API ───────────────────────────────────────────────
@app.route("/api/trade", methods=["POST"])
def api_trade():
    """Execute a trading action (buy, sell, close, modify, close_all)."""
    if replay is None or execution is None:
        return jsonify({"status": "error", "message": "No data loaded"}), 400

    data = request.get_json(force=True)
    action = data.get("action")
    current_bar = replay.get_current_bar()
    current_price = float(current_bar["close"])
    current_time = current_bar["datetime"]

    if action in ("buy", "sell"):
        lot_size = data.get("lot_size", config.DEFAULT_LOT_SIZE)
        sl = data.get("sl")
        tp = data.get("tp")

        if sl is not None:
            sl = float(sl)
        if tp is not None:
            tp = float(tp)

        result = execution.open_position(
            direction=action,
            lot_size=float(lot_size),
            sl=sl,
            tp=tp,
            current_price=current_price,
            current_time=current_time,
        )
        return jsonify({
            "status": "ok" if result else "error",
            "position": result,
            "account": execution.get_account_state(current_price),
        })

    elif action == "close":
        position_id = data.get("position_id")
        result = execution.close_position(
            position_id, current_price, current_time
        )
        return jsonify({
            "status": "ok" if result else "error",
            "position": result,
            "account": execution.get_account_state(current_price),
        })

    elif action == "close_all":
        results = execution.close_all_positions(current_price, current_time)
        return jsonify({
            "status": "ok",
            "closed": results,
            "account": execution.get_account_state(current_price),
        })

    elif action == "modify":
        position_id = data.get("position_id")
        sl = data.get("sl")
        tp = data.get("tp")
        if sl is not None:
            sl = float(sl)
        if tp is not None:
            tp = float(tp)
        result = execution.modify_position(position_id, sl=sl, tp=tp)
        return jsonify({
            "status": "ok" if result else "error",
            "position": result,
        })

    return jsonify({"status": "error", "message": f"Unknown action: {action}"}), 400


# ── Indicators API ────────────────────────────────────────────
@app.route("/api/indicators", methods=["POST"])
def api_indicators():
    """Toggle indicators on/off or update settings."""
    global active_indicators

    data = request.get_json(force=True)
    action = data.get("action", "toggle")
    name = data.get("name")
    settings = data.get("settings", {})

    if action == "toggle":
        if name in active_indicators:
            del active_indicators[name]
        else:
            active_indicators[name] = settings
    elif action == "set":
        active_indicators[name] = settings
    elif action == "remove":
        active_indicators.pop(name, None)
    elif action == "clear":
        active_indicators = {}

    return jsonify({
        "status": "ok",
        "active_indicators": active_indicators,
    })


@app.route("/api/stats", methods=["GET"])
def api_stats():
    """Get account stats and trade history."""
    if execution is None or replay is None:
        return jsonify({"status": "error", "message": "No data loaded"}), 400

    current_price = float(replay.get_current_bar()["close"])

    return jsonify({
        "status": "ok",
        "account": execution.get_account_state(current_price),
        "open_positions": execution.get_open_positions(),
        "trade_history": execution.get_trade_history(),
    })


# ── Entry Point ───────────────────────────────────────────────
if __name__ == "__main__":
    # Auto-load EURUSD H1 on startup
    try:
        init_engines("EURUSD", "H1")
        print("✅ Loaded EURUSD H1 data")
    except FileNotFoundError:
        print("⚠️  No sample data found. Upload via /api/load")

    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
