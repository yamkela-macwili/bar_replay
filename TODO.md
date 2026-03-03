
You are a senior Python backend engineer and systems architect.

You must refactor the PyReplay Trader application according to the requirements below.

⚠️ CRITICAL RULE:
You are NOT allowed to change how the program behaves from a user perspective.
You are NOT allowed to redesign the architecture.
You are NOT allowed to modify business logic.
You are NOT allowed to change API contracts.
You are NOT allowed to change response formats.
You are NOT allowed to alter replay logic.

Only perform the changes explicitly requested.

If something is unclear, preserve existing behavior.

---

# 🎯 OBJECTIVES

## 1️⃣ Completely Remove MT5

You must:

* Remove all MetaTrader5 (MT5) API usage.
* Remove all MT5 imports.
* Remove any MT5 initialization logic.
* Remove any MT5-specific data adapters.
* Remove sample/static hardcoded data.

MT5 must not exist anywhere in the project after this refactor.

The replay engine must remain fully functional.

Do NOT break serialization compatibility.

---

## 2️⃣ Use yfinance as the ONLY Data Provider

The application must fetch market data exclusively using:

```python
yfinance
```

No fallback providers.
No MT5.
No sample data.

All historical market data must come from Yahoo Finance.

---

## 3️⃣ Enforce Strict Symbol Whitelist

The application must ONLY allow these symbols:

```python
[
    "EURUSD=X",
    "USDJPY=X",
    "GBPUSD=X",
    "USDCHF=X",
    "AUDUSD=X",
    "USDCAD=X",
    "NZDUSD=X",
    "XAUUSD=X",
    "BTC-USD",
    "DX-Y.NYB"
]
```

Requirements:

* Reject any symbol not in this list.
* Validate symbol server-side.
* Do NOT trust frontend.
* Return clean error message if invalid symbol requested.
* Do NOT crash.

---

## 4️⃣ Production-Grade Data Caching (Mandatory)

All downloaded data must be cached locally.

Requirements:

* Cache format: Parquet
* Use persistent disk storage (container-safe path)
* Use `portalocker` to prevent concurrent write corruption
* Cache per:

  * Symbol
  * Timeframe
* If cached data exists AND is fresh → use cached version
* If stale → refresh and overwrite safely
* No duplicate simultaneous downloads

⚠️ Freshness rule:
Data is considered fresh if the latest bar is within reasonable timeframe tolerance (respect timeframe logic).

Do NOT fetch remote data on every request.

---

## 5️⃣ Default Startup Dataset (Critical)

On application startup:

* Automatically download:

  * Symbol: `"EURUSD=X"`
  * Timeframe: 1H
  * Max bars: 1000
* Cache it immediately.
* Use it as the default dataset.
* Chart must populate with this dataset automatically on first load.

If cache already exists → use it.

No user interaction required.

---

## 6️⃣ Preserve Replay Behavior EXACTLY

You must NOT:

* Change replay stepping behavior
* Change account simulation
* Change trade execution simulation
* Change API route names
* Change response schemas
* Change Redis storage format
* Change session handling
* Change TTL logic

The ONLY behavioral difference:
Data now comes exclusively from yfinance.

Everything else must remain identical.

---

## 7️⃣ Ensure Render Deployment Safety

This application will be deployed to Render.

Before finalizing changes, you MUST verify:

### Environment Safety

* No localhost-only assumptions
* No hardcoded file paths
* Cache directory configurable via environment variable
* Safe default if not set

### Dependency Safety

* yfinance added to requirements.txt
* MetaTrader5 removed from requirements.txt
* No unused dependencies remain

### Container Safety

* File caching works inside container
* Cache directory created automatically if missing
* App does not crash if cache folder empty
* Works with:

```bash
gunicorn -w 4 -k gthread app:app
```

### Startup Safety

* Default dataset preload does NOT block indefinitely
* If Yahoo temporarily fails → graceful error handling
* App must still boot even if preload fails

### Logging

* Clear logging for:

  * Cache hit
  * Cache miss
  * Cache refresh
  * Symbol validation failure

No silent failures.

---

# 🧠 Structural Discipline Rules

You must:

* Keep architecture modular
* Not introduce globals
* Not introduce stateful singletons
* Not break Redis-based EngineStore
* Not alter multi-user isolation
* Not introduce race conditions
* Not introduce blocking calls inside request handlers unnecessarily

If you must modify data layer:

* Only modify data provider layer
* Do NOT leak changes into replay engine

---

# 🧪 Final Mandatory Verification Checklist

Before returning final answer, internally verify:

* MT5 completely removed
* Only yfinance used
* All 10 symbols enforced
* Default EURUSD 1H 1000 cached
* Cache protected with portalocker
* No replay logic altered
* No API routes altered
* No Redis logic altered
* Multi-user still works
* Gunicorn multi-worker safe
* No Render deployment issues expected

If anything violates production-readiness → fix it before responding.

---

# ❌ Absolutely Forbidden

* Do not redesign the app
* Do not simplify architecture
* Do not refactor unrelated modules
* Do not change business logic
* Do not introduce breaking changes
* Do not remove features
* Do not modify chart format
* Do not convert to async unless already async

---

# ✅ Deliverables

Provide:

1. Updated data provider implementation
2. Symbol validation layer
3. Cache layer with locking
4. Startup preload logic
5. Updated requirements.txt
6. Explanation confirming production safety for Render

Do NOT provide pseudo code.
Provide production-grade Python code only.

---

This refactor must be clean, minimal, safe, and deployment-ready.

If unsure about a change — preserve original behavior.

---


