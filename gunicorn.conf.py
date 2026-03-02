"""Gunicorn configuration for PyReplay Trader production deployment.

This configuration is optimized for:
- Multi-worker concurrency (thread-based for stateless operations)
- Proper graceful shutdown
- Comprehensive logging
- Container environments (Render)
- Resource efficiency
"""

import multiprocessing
import logging

# ────────────────────────────────────────────────────────────────────────────
# Basic Server Settings
# ────────────────────────────────────────────────────────────────────────────

bind = "0.0.0.0:5000"
backlog = 2048

# Workers and Threads
# Use thread-based workers for stateless Flask app
# Each worker has multiple threads for concurrent requests
workers = multiprocessing.cpu_count() * 2  # Common formula for I/O-bound apps
worker_class = "gthread"  # Thread-based worker class
threads = 2  # Threads per worker
worker_connections = 1000
timeout = 30

# ────────────────────────────────────────────────────────────────────────────
# Process Naming & Daemonization
# ────────────────────────────────────────────────────────────────────────────

proc_name = "pyreplay-trader"
umask = 0o022
tmp_upload_dir = None
daemon = False  # Run in foreground for container

# ────────────────────────────────────────────────────────────────────────────
# Logging
# ────────────────────────────────────────────────────────────────────────────

loglevel = "info"
accesslog = "-"  # stdout
errorlog = "-"   # stderr
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# ────────────────────────────────────────────────────────────────────────────
# Graceful Shutdown
# ────────────────────────────────────────────────────────────────────────────

graceful_timeout = 30
keep_alive = 5

# ────────────────────────────────────────────────────────────────────────────
# Server Hooks (For Container Liveness Checks)
# ────────────────────────────────────────────────────────────────────────────

def when_ready(server):
    """Hook called when the server is ready to accept requests."""
    print("[gunicorn] Server is ready. Spawning workers.")


def on_starting(server):
    """Hook called just before a master process is initialized."""
    print("[gunicorn] Starting master process.")


def on_exit(server):
    """Hook called just after a worker has exited."""
    print("[gunicorn] Worker exit detected.")


# ────────────────────────────────────────────────────────────────────────────
# Security
# ────────────────────────────────────────────────────────────────────────────

limit_request_line = 4096
limit_request_fields = 100
limit_request_field_size = 8190

# ────────────────────────────────────────────────────────────────────────────
# SSL/TLS (set via environment or reverse proxy in production)
# ────────────────────────────────────────────────────────────────────────────

keyfile = None
certfile = None
ssl_version = "TLS"

# ────────────────────────────────────────────────────────────────────────────
# Deployment Notes
# ────────────────────────────────────────────────────────────────────────────

# Usage:
#   gunicorn -c gunicorn.conf.py app:app
#
# For Render:
#   - No modifications needed; this config works as-is
#   - Render will inject PORT via environment variable
#   - SSL/TLS termination is handled by Render
#
# For local testing:
#   gunicorn -w 4 -k gthread app:app
#
# For performance tuning:
#   - Increase workers if CPU-bound operations increase
#   - Increase threads per worker if I/O-bound operations increase
#   - Monitor with: gunicorn --access-logfile - --error-logfile - app:app
