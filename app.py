"""Flask application entry point for PyReplay Trader.

Production-ready: stateless, multi-worker safe, Redis-backed.
Deploy with: gunicorn -w 4 -k gthread app:app
"""

from flask import Flask, render_template, jsonify, request, session
import uuid

import config
from backend.logging_config import setup_logging, get_logger
from backend.engine_store import EngineStore, DeserializationError, SerializationError
from backend import data_module
from backend.services import (
    ReplayService,
    TradeService,
    IndicatorService,
    DataService,
)

# Initialize logging
logger = setup_logging(__name__)

# Create Flask app
app = Flask(__name__)

# Flask configuration
app.config.update(
    SECRET_KEY=config.SECRET_KEY,
    DEBUG=config.DEBUG,
    TESTING=config.TESTING,
    SESSION_COOKIE_SECURE=config.SESSION_COOKIE_SECURE,
    SESSION_COOKIE_HTTPONLY=config.SESSION_COOKIE_HTTPONLY,
    SESSION_COOKIE_SAMESITE=config.SESSION_COOKIE_SAMESITE,
    SESSION_COOKIE_NAME=config.SESSION_COOKIE_NAME,
    PERMANENT_SESSION_LIFETIME=config.PERMANENT_SESSION_LIFETIME,
)

app.permanent_session_lifetime = config.PERMANENT_SESSION_LIFETIME

# Initialize EngineStore
try:
    engine_store = EngineStore(config.REDIS_URL)
    logger.info("EngineStore initialized")
except Exception as e:
    logger.error(f"Failed to initialize EngineStore: {e}")
    raise RuntimeError("Cannot start without storage backend") from e


# Session management

@app.before_request
def initialize_session():
    """Ensure session UUID exists."""
    session.permanent = True
    if "session_id" not in session:
        session_id = str(uuid.uuid4())
        session["session_id"] = session_id
        logger.info(f"Created session: {session_id}")


def get_session_id():
    """Get or validate session UUID."""
    sid = session.get("session_id")
    if not sid or not isinstance(sid, str) or len(sid) != 36:
        raise ValueError("Invalid session")
    return sid


def load_system():
    """Load ReplaySystem from storage."""
    sid = get_session_id()
    system = engine_store.get(sid)
    if system:
        logger.debug(f"Loaded system for {sid}")
    return system


def save_system(system):
    """Atomically save ReplaySystem."""
    sid = get_session_id()
    engine_store.set(sid, system)
    logger.debug(f"Saved system for {sid}")


# Error handlers

@app.errorhandler(ValueError)
def handle_value_error(error):
    """Handle validation errors."""
    logger.warning(f"Validation error: {error}")
    return jsonify({"status": "error", "message": str(error)}), 400


@app.errorhandler(DeserializationError)
def handle_deserialization_error(error):
    """Handle corrupted session."""
    logger.error(f"Deserialization error: {error}")
    return jsonify({
        "status": "error",
        "message": "Session corrupted. Please refresh."
    }), 410


@app.errorhandler(SerializationError)
def handle_serialization_error(error):
    """Handle serialization failures."""
    logger.error(f"Serialization error: {error}")
    return jsonify({
        "status": "error",
        "message": "Cannot save state. Try again."
    }), 500


@app.errorhandler(500)
def handle_internal_error(error):
    """Handle unexpected errors."""
    logger.error(f"Internal error: {error}", exc_info=True)
    return jsonify({
        "status": "error",
        "message": "Internal server error."
    }), 500


# Health & Status

@app.route("/health", methods=["GET"])
def health_check():
    """Health check for Render."""
    health = {
        "status": "healthy",
        "storage": engine_store.health_check(),
    }
    return jsonify(health), 200


@app.route("/api/session", methods=["GET"])
def api_session():
    """Get session UUID."""
    try:
        sid = get_session_id()
        return jsonify({"status": "ok", "session_id": sid}), 200
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400


# Pages

@app.route("/")
def index():
    """Serve main page."""
    symbols = DataService.get_available_symbols("csv")
    return render_template("index.html", symbols=symbols)


# Data Loading

@app.route("/api/load", methods=["POST"])
def api_load():
    """Load symbol and initialize replay."""
    try:
        data = request.get_json(force=True)
        symbol = data.get("symbol", "EURUSD")
        timeframe = data.get("timeframe", "H1")
        provider = data.get("provider", "csv")
        sid = get_session_id()

        result = ReplayService.load_symbol(sid, symbol, timeframe, provider)

        from backend.engine_system import EngineFactory
        system = EngineFactory.create(symbol, timeframe, provider, session_id=sid)
        save_system(system)

        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Load failed: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/data", methods=["GET"])
def api_data():
    """Get chart data and indicators."""
    try:
        system = load_system()
        if system is None:
            return jsonify({"status": "error", "message": "No data"}), 400

        result = ReplayService.get_visible_data(system)
        save_system(system)
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"api_data failed: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/data/load_more", methods=["GET"])
def api_load_more():
    """Lazy load bars."""
    try:
        system = load_system()
        if system is None:
            return jsonify({"status": "error", "message": "No data"}), 400

        direction = request.args.get("direction", "backward")
        result = ReplayService.load_more_bars(system, direction)
        save_system(system)
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Load more failed: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


# Replay Controls

@app.route("/api/step", methods=["POST"])
def api_step():
    """Step forward."""
    try:
        system = load_system()
        if system is None:
            return jsonify({"status": "error", "message": "No data"}), 400

        result = ReplayService.step_forward(system)
        save_system(system)
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Step failed: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/back", methods=["POST"])
def api_back():
    """Step backward."""
    try:
        system = load_system()
        if system is None:
            return jsonify({"status": "error", "message": "No data"}), 400

        result = ReplayService.step_back(system)
        save_system(system)
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Back failed: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/play", methods=["POST"])
def api_play():
    """Start auto-play."""
    try:
        system = load_system()
        if system is None:
            return jsonify({"status": "error", "message": "No data"}), 400

        result = ReplayService.play(system)
        save_system(system)
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Play failed: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/pause", methods=["POST"])
def api_pause():
    """Pause auto-play."""
    try:
        system = load_system()
        if system is None:
            return jsonify({"status": "error", "message": "No data"}), 400

        result = ReplayService.pause(system)
        save_system(system)
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Pause failed: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/jump", methods=["POST"])
def api_jump():
    """Jump to index or date."""
    try:
        system = load_system()
        if system is None:
            return jsonify({"status": "error", "message": "No data"}), 400

        data = request.get_json(force=True)
        index = data.get("index")
        date = data.get("date")

        result = ReplayService.jump(system, index=index, date=date)
        save_system(system)
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Jump failed: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/speed", methods=["POST"])
def api_speed():
    """Set replay speed."""
    try:
        system = load_system()
        if system is None:
            return jsonify({"status": "error", "message": "No data"}), 400

        data = request.get_json(force=True)
        speed = int(data.get("speed", 1))

        result = ReplayService.set_speed(system, speed)
        save_system(system)
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Speed failed: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


# Trading

@app.route("/api/trade", methods=["POST"])
def api_trade():
    """Execute trade action."""
    try:
        system = load_system()
        if system is None:
            return jsonify({"status": "error", "message": "No data"}), 400

        data = request.get_json(force=True)
        action = data.get("action")

        if action in ("buy", "sell"):
            result = TradeService.open_position(
                system,
                direction=action,
                lot_size=float(data.get("lot_size", config.DEFAULT_LOT_SIZE)),
                sl=float(data.get("sl")) if data.get("sl") else None,
                tp=float(data.get("tp")) if data.get("tp") else None,
            )
        elif action == "close":
            result = TradeService.close_position(system, data.get("position_id"))
        elif action == "close_all":
            result = TradeService.close_all_positions(system)
        elif action == "modify":
            result = TradeService.modify_position(
                system,
                data.get("position_id"),
                sl=float(data.get("sl")) if data.get("sl") else None,
                tp=float(data.get("tp")) if data.get("tp") else None,
            )
        else:
            return jsonify({"status": "error", "message": f"Unknown: {action}"}), 400

        save_system(system)
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Trade failed: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


# Indicators

@app.route("/api/indicators", methods=["POST"])
def api_indicators():
    """Manage indicators."""
    try:
        system = load_system()
        if system is None:
            return jsonify({"status": "error", "message": "No data"}), 400

        data = request.get_json(force=True)
        action = data.get("action", "toggle")
        name = data.get("name")
        settings = data.get("settings", {})

        if action == "toggle":
            result = IndicatorService.toggle_indicator(system, name, settings)
        elif action == "set":
            result = IndicatorService.set_indicator(system, name, settings)
        elif action == "remove":
            result = IndicatorService.remove_indicator(system, name)
        elif action == "clear":
            result = IndicatorService.clear_indicators(system)
        else:
            return jsonify({"status": "error", "message": f"Unknown: {action}"}), 400

        save_system(system)
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Indicator failed: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


# Stats

@app.route("/api/stats", methods=["GET"])
def api_stats():
    """Get account stats."""
    try:
        system = load_system()
        if system is None:
            return jsonify({"status": "error", "message": "No data"}), 400

        result = DataService.get_account_stats(system)
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Stats failed: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


# Startup

if __name__ == "__main__":
    logger.warning("Dev server. Use: gunicorn -w 4 -k gthread app:app")
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
