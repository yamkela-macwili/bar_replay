# Running PyReplay Trader in Docker

## Quick Start (TL;DR)

```bash
# 1. Navigate to project directory
cd /home/yamkelamacwili/Desktop/porfolio_projects/bar_replay

# 2. Build and start containers
docker-compose up --build

# 3. Open browser
open http://localhost:5000

# 4. Stop containers
docker-compose down
```

---

## Prerequisites

You need Docker and Docker Compose installed:

```bash
# Check if Docker is installed
docker --version

# Check if Docker Compose is installed
docker-compose --version
```

If not installed:
- **macOS/Windows:** Download [Docker Desktop](https://www.docker.com/products/docker-desktop)
- **Linux:** Follow [Docker installation guide](https://docs.docker.com/engine/install/)

---

## Docker Setup Included

The project includes complete Docker configuration:

- **Dockerfile** - Container image definition
- **docker-compose.yml** - Multi-container orchestration (Redis + API)
- **.dockerignore** - Files to exclude from image

### What docker-compose.yml includes:

#### Redis Service
```yaml
redis:
  image: redis:7-alpine
  ports: 6379:6379
  healthcheck: redis-cli ping
  volumes: redis_data:/data
```

#### API Service
```yaml
api:
  build: .  # Uses Dockerfile
  ports: 5000:5000
  environment: ENVIRONMENT, REDIS_URL, etc.
  depends_on: redis (with health check)
  healthcheck: curl /health endpoint
```

---

## How to Run

### Option 1: Docker Compose (Recommended)

**Start everything:**
```bash
cd /home/yamkelamacwili/Desktop/porfolio_projects/bar_replay
docker-compose up --build
```

**Output:**
```
redis_1  | Ready to accept connections
api_1    | Running on http://0.0.0.0:5000
```

**Access the app:**
- Web UI: http://localhost:5000
- API: http://localhost:5000/api/session
- Health Check: http://localhost:5000/health

**Stop:**
```bash
docker-compose down
```

---

### Option 2: Build & Run Manually

**Build the image:**
```bash
docker build -t pyreplay-trader .
```

**Run with local Redis (if available):**
```bash
docker run -d \
  -p 5000:5000 \
  -e REDIS_URL=redis://host.docker.internal:6379/0 \
  -e ENVIRONMENT=development \
  --name pyreplay \
  pyreplay-trader
```

**Check logs:**
```bash
docker logs -f pyreplay
```

**Stop:**
```bash
docker stop pyreplay
docker rm pyreplay
```

---

### Option 3: Development Mode (Hot Reload)

**With docker-compose:**
```bash
docker-compose up
```

The Dockerfile includes a volume mount for the app directory, so code changes auto-reload.

**Edit code → Saved → Flask reloads → Test immediately**

```bash
# Example: Edit app.py
# docker-compose will reload Flask automatically
nano app.py
# Changes are live!
```

---

## Testing the Container

### 1. Health Check

```bash
curl http://localhost:5000/health
```

Expected response:
```json
{
  "status": "healthy",
  "storage": {
    "backend": "redis",
    "connected": true,
    "healthy": true
  }
}
```

### 2. Session API

```bash
curl http://localhost:5000/api/session
```

Expected response:
```json
{
  "status": "ok",
  "session_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
}
```

### 3. Load Data

```bash
curl -X POST http://localhost:5000/api/load \
  -H "Content-Type: application/json" \
  -d '{"symbol": "EURUSD", "timeframe": "H1", "provider": "csv"}'
```

### 4. Get Chart Data

```bash
curl http://localhost:5000/api/data
```

### 5. Open Web UI

```bash
# macOS
open http://localhost:5000

# Linux
xdg-open http://localhost:5000

# Windows
start http://localhost:5000
```

---

## Docker Compose Commands

### View running containers:
```bash
docker-compose ps
```

Output:
```
NAME                COMMAND                  SERVICE     STATUS
pyreplay_redis      redis-server ...         redis       running
pyreplay_api        gunicorn -w 4 ...        api         running
```

### View logs:
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f api
docker-compose logs -f redis
```

### Stop services:
```bash
docker-compose stop
```

### Remove everything (including volumes):
```bash
docker-compose down -v
```

### Rebuild images:
```bash
docker-compose up --build
```

### Run one-time commands:
```bash
# Run test in container
docker-compose run api python -m pytest

# Run Python code
docker-compose run api python -c "print('Hello')"
```

---

## Environment Variables

Default values in `docker-compose.yml`:

```yaml
environment:
  - ENVIRONMENT=development        # development or production
  - FLASK_ENV=development          # Flask environment
  - REDIS_URL=redis://redis:6379/0 # Redis connection
  - SECRET_KEY=dev-secret-key-...  # Session encryption
  - LOG_LEVEL=DEBUG                # Logging level
```

### Change for Production:

Create `.env.production` file:
```bash
ENVIRONMENT=production
REDIS_URL=redis://default:password@host:port
SECRET_KEY=your-32-char-secret-key-here
LOG_LEVEL=INFO
```

Then run:
```bash
docker-compose --env-file .env.production up
```

---

## Container Architecture

```
┌─────────────────────────────────────────┐
│         Docker Host (localhost)          │
├─────────────────────────────────────────┤
│                                         │
│  ┌────────────────────────────────┐   │
│  │  Redis Container               │   │
│  │  - Port 6379                   │   │
│  │  - Health Check: redis-cli     │   │
│  │  - Volume: redis_data          │   │
│  └────────────────────────────────┘   │
│              ▲                         │
│              │                         │
│              │ redis://redis:6379     │
│              │                         │
│  ┌────────────────────────────────┐   │
│  │  Flask API Container           │   │
│  │  - Port 5000                   │   │
│  │  - Gunicorn: 4 workers         │   │
│  │  - Health Check: /health       │   │
│  │  - Volume: ./app (hot reload)  │   │
│  └────────────────────────────────┘   │
│              ▲                         │
│              │                         │
│              │ http://localhost:5000  │
│              │                         │
│         Your Browser                  │
│                                         │
└─────────────────────────────────────────┘
```

---

## Troubleshooting

### Container won't start

**Check logs:**
```bash
docker-compose logs api
```

**Common issues:**

1. **Port already in use:**
   ```bash
   # Change port in docker-compose.yml
   ports:
     - "5001:5000"  # Use 5001 instead
   
   # Or kill existing container
   lsof -i :5000
   kill -9 <PID>
   ```

2. **Redis connection failed:**
   ```bash
   # Ensure redis service is healthy
   docker-compose logs redis
   
   # Rebuild and restart
   docker-compose down
   docker-compose up --build
   ```

3. **Out of disk space:**
   ```bash
   # Clean up Docker
   docker system prune -a --volumes
   ```

### Container crashes after starting

**Check logs:**
```bash
docker-compose logs api --tail 50
```

**Common fixes:**
```bash
# Rebuild image (sometimes helps)
docker-compose up --build

# Start in debug mode
docker-compose up api (no -d flag to see real-time logs)
```

### Can't access from browser

**Verify container is running:**
```bash
docker-compose ps
```

**Test health endpoint:**
```bash
curl http://localhost:5000/health
```

**Check if port is accessible:**
```bash
netstat -an | grep 5000  # macOS/Linux
netstat -ano | findstr 5000  # Windows
```

---

## Performance Tips

### 1. Use BuildKit for faster builds:
```bash
DOCKER_BUILDKIT=1 docker-compose up --build
```

### 2. Cache layers effectively:
```dockerfile
# In Dockerfile, install deps before copying code
RUN pip install -r requirements.txt  # Cached
COPY . /app                          # Fresh each time
```

### 3. Reduce image size:
```bash
docker images
# Check image size
docker history pyreplay-trader
```

### 4. Enable health checks:
```bash
docker-compose ps
# Shows health status
```

---

## Production Deployment

For production on Render:

1. **Build image:**
   ```bash
   docker build -t pyreplay-trader:latest .
   ```

2. **Push to registry (if needed):**
   ```bash
   docker tag pyreplay-trader:latest your-registry/pyreplay-trader:latest
   docker push your-registry/pyreplay-trader:latest
   ```

3. **Use render.yaml:**
   ```bash
   # Render auto-detects and deploys
   # See DEPLOYMENT.md for details
   ```

---

## Advanced: Custom Configuration

### Run with custom Redis:

```bash
docker-compose run -e REDIS_URL=redis://custom-redis:6379 api
```

### Run specific Python version:

Edit Dockerfile:
```dockerfile
FROM python:3.11-slim  # Change version here
```

### Run with mounted data:

```bash
docker-compose run -v /path/to/data:/app/data api
```

---

## Next Steps

1. **Run locally:** `docker-compose up --build`
2. **Test:** `curl http://localhost:5000/health`
3. **Develop:** Edit code, watch auto-reload
4. **Deploy:** See DEPLOYMENT.md for Render instructions

---

## Quick Reference

| Command | Purpose |
|---------|---------|
| `docker-compose up --build` | Start all containers (rebuild) |
| `docker-compose up` | Start all containers |
| `docker-compose down` | Stop all containers |
| `docker-compose logs -f` | View logs (all) |
| `docker-compose logs -f api` | View logs (API only) |
| `docker-compose ps` | List running containers |
| `docker-compose exec api bash` | Shell into API container |
| `docker-compose run api python -c "..."` | Run Python code |

---

## Support

- **Container issues?** → Check `docker-compose logs`
- **Build failures?** → See `docker build --progress=plain`
- **More help?** → See DEPLOYMENT.md and ARCHITECTURE.md

---

**Ready to run?**

```bash
cd /home/yamkelamacwili/Desktop/porfolio_projects/bar_replay
docker-compose up --build
# Opens http://localhost:5000
```

🚀 Done!
