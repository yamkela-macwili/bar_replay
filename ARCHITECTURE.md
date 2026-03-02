# Architecture Reference Guide

Quick reference for developers working on PyReplay Trader.

## Statefulness Principle

**RULE: No state in app memory. All state in Redis.**

```python
# ❌ WRONG - State in app memory
_current_system = None

def get_system():
    return _current_system

# ✅ CORRECT - State in Redis
def get_system():
    sid = get_session_id()
    return engine_store.get(sid)  # Load from Redis
```

## Session Flow

```
Request arrives
    ↓
@app.before_request → initialize_session()
    └─ Create UUID if missing, store in Flask cookie
    ↓
Route handler → get_session_id()
    └─ Extract and validate UUID from session
    ↓
load_system() → engine_store.get(sid)
    └─ Fetch from Redis, deserialize
    ↓
Service layer (stateless)
    └─ Perform operation on in-memory object
    ↓
save_system(system) → engine_store.set(sid, system)
    └─ Serialize and atomically save to Redis
    ↓
Response sent
    └─ Flask cookie contains UUID for next request
```

## Adding New Endpoints

### 1. Add to Service Layer

```python
# backend/services.py

class MyService:
    @staticmethod
    def my_operation(system: ReplaySystem, param: str):
        """Perform operation."""
        # Access in-memory system
        # Return dict (JSON serializable)
        return {"status": "ok", "result": ...}
```

### 2. Add Route Handler

```python
# app.py

@app.route("/api/my-operation", methods=["POST"])
def api_my_operation():
    """Call my_operation."""
    try:
        system = load_system()  # Get from Redis
        if system is None:
            return jsonify({"status": "error", "message": "No data"}), 400

        data = request.get_json(force=True)
        param = data.get("param")
        
        result = MyService.my_operation(system, param)
        save_system(system)  # Save to Redis
        
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Operation failed: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500
```

## Modifying ReplaySystem

ReplaySystem must stay **dill-serializable**.

```python
# ✅ OK - Native Python objects
class ReplaySystem:
    self.data = pd.DataFrame(...)  # dill serializes
    self.balance = 10000.0         # dill serializes

# ❌ PROBLEM - Non-serializable objects
class ReplaySystem:
    self.mt5 = MetaTrader5(...)    # Cannot serialize!
    self.socket = socket.socket()  # Cannot serialize!
```

**Solution: Use adapters**

```python
# ✅ CORRECT
class MT5Adapter:
    """Stateless wrapper, not stored."""
    def __init__(self, host, port):
        self.host = host
        self.port = port
    
    def fetch_bars(self, symbol, timeframe):
        # Lazy initialize on each call
        mt5 = MetaTrader5(self.host, self.port)
        return mt5.copy_rates(symbol, timeframe)

# In route:
adapter = MT5Adapter(config.MT5_HOST, config.MT5_PORT)
bars = adapter.fetch_bars(symbol, timeframe)
```

## Error Handling Pattern

```python
@app.route("/api/something", methods=["POST"])
def api_something():
    try:
        system = load_system()
        if system is None:
            return jsonify({"status": "error", "message": "No data"}), 400

        # Your logic
        result = do_something(system)
        save_system(system)
        
        return jsonify(result), 200

    except ValueError as e:
        # Validation error (user's fault)
        logger.warning(f"Validation error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400
    
    except (DeserializationError, SerializationError) as e:
        # Corruption or storage error (system's fault)
        logger.error(f"Storage error: {e}")
        return jsonify({"status": "error", "message": "Try again later"}), 500
    
    except Exception as e:
        # Unexpected error (log everything)
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "Internal error"}), 500
```

## Testing Statelessness

```python
import uuid
from backend.engine_store import EngineStore
from backend.engine_system import ReplaySystem

# Test 1: Session isolation
sid1 = str(uuid.uuid4())
sid2 = str(uuid.uuid4())

store = EngineStore()

system1 = ReplaySystem(data1, "EURUSD", "H1", "csv", session_id=sid1)
system2 = ReplaySystem(data2, "GBPUSD", "H4", "csv", session_id=sid2)

store.set(sid1, system1)
store.set(sid2, system2)

loaded1 = store.get(sid1)
loaded2 = store.get(sid2)

assert loaded1.symbol == "EURUSD"
assert loaded2.symbol == "GBPUSD"
# No cross-contamination ✓

# Test 2: Worker independence
# Start two workers with same session UUID
# Both load from Redis, modify independently, save
# Verify: Last write wins (atomic)
```

## Production Checklist Before Deploy

```bash
# 1. Test locally
docker-compose up --build

# 2. Test with Gunicorn
gunicorn -w 4 -k gthread app:app

# 3. Verify health endpoint
curl http://localhost:5000/health

# 4. Test multi-worker
# Open two browser windows with same session
# Verify state is isolated/consistent

# 5. Check syntax
python -m py_compile *.py backend/*.py

# 6. Validate requirements
pip install -r requirements.txt --dry-run

# 7. Generate SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"

# 8. Set up Upstash Redis
# Get connection URL from https://upstash.com

# 9. Deploy to Render
git push origin main
# Set env vars in Render Dashboard
```

## Key Files

| File | Purpose |
|------|---------|
| `app.py` | Flask routes (stateless) |
| `config.py` | Configuration (environment-based) |
| `backend/engine_store.py` | Redis storage with integrity |
| `backend/services.py` | Business logic (stateless) |
| `backend/logging_config.py` | Structured logging |
| `gunicorn.conf.py` | Production server config |
| `Dockerfile` | Container image |
| `docker-compose.yml` | Local orchestration |
| `render.yaml` | Render deployment config |
| `requirements.txt` | Python dependencies (pinned) |

## Debugging

**See logs:**
```bash
# Local development
docker-compose logs -f api

# Production (Render)
# Dashboard → Logs
```

**Check session storage:**
```bash
# Local Redis
redis-cli KEYS "replay:engine:*"
redis-cli GET "replay:engine:12345..."

# Upstash
# Dashboard → Data Browser
```

**Simulate multi-worker:**
```bash
gunicorn -w 4 -k gthread app:app --access-logfile - --error-logfile -
```

**Check statefulness:**
```python
# app.py startup
print("✅ No global state defined")
print("✅ EngineStore initialized")
print("✅ Redis connected")
```

## Common Gotchas

### ❌ Storing state in routes

```python
# WRONG - persists across requests
system = None

@app.route("/api/load")
def api_load():
    global system
    system = load_data()  # Shared!
```

### ❌ Keeping connections open

```python
# WRONG - connection kept across workers
socket = socket.socket()

@app.route("/api/data")
def api_data():
    socket.send(...)  # Shared!
```

### ❌ Trusting multiple saves

```python
# WRONG - second save might fail silently
save_system(system)
modify_system(system)
# Don't save again!
```

### ✅ Correct patterns

```python
# Load → Modify → Save (once per request)
system = load_system()
service_method(system)
save_system(system)
```

## Performance Tips

**Reduce serialization size:**
- Clean old trade history periodically
- Limit indicator history to active indicators
- Compress DataFrames before storage

**Reduce Redis load:**
- Only save on meaningful changes
- Use TTL refresh on read (automatic)
- Batch operations when possible

**Reduce requests:**
- Load more bars at once
- Cache indicator calculations in system
- Minimize frontend polling

## References

- [Redis Commands](https://redis.io/commands/)
- [dill Documentation](https://dill.readthedocs.io/)
- [Flask Sessions](https://flask.palletsprojects.com/sessions/)
- [Gunicorn](https://gunicorn.org/)
- [Render Docs](https://render.com/docs/)

---

**Remember:** If state is in Python variables, it's a bug. State belongs in Redis.
