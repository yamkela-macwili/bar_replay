## PyReplay Trader - Production Deployment Guide

### Architecture Overview

This application is built for **production Render deployment** with the following guarantees:

- **Fully Stateless**: Zero reliance on process memory; works across Gunicorn workers
- **Multi-Worker Safe**: Designed for `gunicorn -w 4 -k gthread app:app`
- **Session Isolated**: Each user gets UUID-based session with Redis storage
- **Horizontally Scalable**: Can scale to multiple instances/containers
- **Production-Grade**: Proper error handling, logging, serialization validation

---

## Local Development

### Prerequisites

- Python 3.11+
- Redis 7+

### Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start Redis
redis-server

# 3. Create .env (optional for dev)
cp .env.example .env

# 4. Run with Gunicorn
gunicorn -w 2 -k gthread app:app

# OR run with Flask dev server
python app.py
```

### Docker Compose (Local)

```bash
# Start Redis + API
docker-compose up

# Rebuild after changes
docker-compose up --build

# Stop services
docker-compose down

# View logs
docker-compose logs -f api
docker-compose logs -f redis
```

---

## Production Render Deployment

### Step 1: Create Render Account

1. Go to [https://render.com](https://render.com)
2. Sign up with GitHub account
3. Connect your GitHub repository

### Step 2: Set Up Redis (Managed)

Option A: Use Upstash Redis (recommended)

```
1. Go to https://upstash.com
2. Create free Upstash Redis database
3. Copy connection URL: redis://default:password@hostname:port
4. Keep this URL secure (it's a secret)
```

Option B: Use Render's Redis service

```yaml
# Add to render.yaml if using Render Redis
- type: redis
  name: pyreplay-redis
  plan: starter
```

### Step 3: Deploy to Render

#### Method 1: Using render.yaml (Recommended)

```bash
# Push to GitHub
git add .
git commit -m "Production ready deployment"
git push origin main

# In Render Dashboard:
# 1. Click "New" → "Web Service"
# 2. Connect GitHub repository
# 3. Select "Python" runtime
# 4. Render will auto-detect render.yaml configuration
# 5. Add environment variables (see Step 4)
```

#### Method 2: Manual Configuration

```bash
# In Render Dashboard:
1. New → Web Service
2. Connect repository
3. Settings:
   - Name: pyreplay-api
   - Runtime: Python 3.11
   - Build Command: pip install -r requirements.txt
   - Start Command: gunicorn -c gunicorn.conf.py app:app
   - Region: (select closest to you)
4. Continue to Step 4
```

### Step 4: Configure Environment Variables

In Render Dashboard → Environment:

```
ENVIRONMENT=production
FLASK_ENV=production
LOG_LEVEL=INFO
SECRET_KEY=<GENERATE_AND_SET_SECRET>
REDIS_URL=<UPSTASH_REDIS_URL>
```

**⚠️ CRITICAL: Generate SECRET_KEY**

```bash
# Run locally
python -c "import secrets; print(secrets.token_hex(32))"

# Copy output and paste into Render environment variable
```

### Step 5: Verify Deployment

```bash
# Check if app is running
curl https://your-app.onrender.com/health

# Expected response:
# {"status":"healthy","storage":{"healthy":true,"backend":"redis","connected":true}}

# Check logs in Render Dashboard
# Look for: "EngineStore initialized successfully"
```

---

## Architecture Details

### Request Flow

```
User Request
    ↓
Flask @before_request (initialize session)
    ↓
get_session_id() → Flask session cookie
    ↓
load_system() → Redis[session_uuid]
    ↓
Deserialize with dill + integrity check
    ↓
ReplaySystem (in-memory for this request only)
    ↓
Service layer (stateless operations)
    ↓
save_system() → Redis[session_uuid] (atomic)
    ↓
Response to client
```

### Session Storage

```
Redis Key: replay:engine:{uuid}
Value: dill.dumps(ReplaySystem)
TTL: 7200 seconds (2 hours)
Refresh: On every write
Compression: Auto (if > 1MB)
Integrity: SHA256 hash validation
```

### Multi-Worker Safety

```
Worker 1:  Load session → Modify → Save
Worker 2:  Load session → Modify → Save  (same session UUID)
Worker 3:  Load session → Modify → Save

Result: No race conditions, atomic writes, strict isolation
```

---

## Scaling Beyond Render

### Horizontal Scaling

To scale to multiple instances:

```bash
# Render: Settings → Instance Count = 2+
# Load balancer: Render auto-handles
# Sticky Sessions: Not needed (stateless)
```

### Managed Redis

For production scale, use:

- **Upstash Redis** (easiest, free tier available)
- **AWS ElastiCache** (better for high load)
- **Heroku Redis** (if migrating from Heroku)
- **Redis Cloud** (managed by Redis)

All compatible; just change `REDIS_URL`.

### Kubernetes Migration

If scaling to Kubernetes:

```yaml
# Pod 1, 2, 3... can all share same Redis
# StatefulSets: Not needed
# Init containers: Not needed (stateless)
# Service type: ClusterIP (internal routing)

# Update: REDIS_URL to K8s Redis service DNS
REDIS_URL: redis://redis-service.default.svc.cluster.local:6379/0
```

---

## Troubleshooting

### Issue: "Cannot connect to Redis"

```bash
# Check REDIS_URL format
redis://default:PASSWORD@HOST:PORT

# Test connection locally
redis-cli -u $REDIS_URL ping
# Should respond: PONG

# In Render:
1. Verify REDIS_URL in Environment
2. Check Upstash Redis is running
3. Check IP whitelist (if applicable)
```

### Issue: "Secret key must be >= 32 characters"

```bash
# Generate correct secret
python -c "import secrets; print(f'SECRET_KEY={secrets.token_hex(32)}')"

# Paste into Render Environment
```

### Issue: "Session corrupted" errors

```bash
# Redis data is corrupted or evicted
# Solution: Manual cleanup

# Local:
redis-cli FLUSHDB

# Render:
# In Upstash dashboard → Data Browser → Flush Database
```

### Issue: "Health check failing"

```bash
# Check logs:
curl https://your-app.onrender.com/health

# If 500: Check REDIS_URL
# If 410: Session corrupted, flush Redis
# If 200: All good

# View full logs in Render Dashboard
```

### Issue: "Out of memory" on Render

```bash
# Reduce session TTL
RENDER: SESSION_TTL=3600  (1 hour instead of 2)

# Or upgrade Render instance
RENDER: Settings → Plan = Standard or above
```

---

## Security Checklist

- [ ] `SECRET_KEY` is 32+ random characters
- [ ] `ENVIRONMENT=production` is set
- [ ] `DEBUG=False` (automatic in production config)
- [ ] Session cookies are `HttpOnly` and `Secure`
- [ ] REDIS_URL is in secrets (not committed)
- [ ] Upstash Redis password is strong
- [ ] SSL/TLS is enabled (Render handles)
- [ ] No git credentials or secrets in code
- [ ] Log level is `INFO` or above (not DEBUG in production)

---

## Monitoring

### Logs

```bash
# In Render Dashboard
# Settings → Logs

# Filter by:
# - Status: ERROR, WARNING
# - Component: app, redis
```

### Health Check

```bash
# Automated by Render every 30 seconds
GET /health

# Response includes:
# - Backend status (Redis connected)
# - Serialization health
# - Session storage status
```

### Metrics

```bash
# View in Render Dashboard → Metrics
# - CPU Usage
# - Memory Usage
# - Network I/O
# - Request count
```

---

## Maintenance

### Rolling Updates

```bash
# To deploy new code:
1. git push origin main
2. Render auto-detects
3. Starts new workers
4. Gracefully shuts down old workers
5. No user sessions lost (Redis persists state)
```

### Database Migrations

Not applicable; uses Redis only (no SQL database).

### Cleanup

```bash
# Expired sessions auto-cleanup (Redis TTL)
# No manual maintenance needed

# To force cleanup:
redis-cli FLUSHDB  # ⚠️ WARNING: Clears all sessions
```

---

## Support & Issues

### Check Deployment Logs

```bash
# Render Dashboard → Logs
# Look for:
# - "EngineStore initialized successfully"
# - "Server is ready"
# - Any ERROR or CRITICAL messages
```

### Test API Endpoints

```bash
curl -X GET https://your-app.onrender.com/health
curl -X GET https://your-app.onrender.com/api/session
```

### Validate Configuration

```bash
# Local test before deploying
export REDIS_URL="redis://localhost:6379/0"
export SECRET_KEY="test-key-12345678901234567890123456"
export ENVIRONMENT="production"

python app.py  # Should start without errors
```

---

## References

- [Render Docs](https://render.com/docs)
- [Gunicorn](https://gunicorn.org/)
- [Redis CLI](https://redis.io/commands/)
- [Flask Session](https://flask.palletsprojects.com/sessions/)
- [Upstash Redis](https://upstash.com/docs)

---

**Last Updated**: 2024  
**Status**: Production Ready  
**Version**: 1.0.0
