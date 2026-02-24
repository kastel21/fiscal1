"""
Production Gunicorn config for FDMS SaaS.
Use: gunicorn fdms_project.wsgi:application --config gunicorn.conf.py

Ensure DJANGO_SETTINGS_MODULE=fdms_project.settings_production in the environment.
"""

import multiprocessing
import os

# Bind
bind = "0.0.0.0:8000"

# Workers: (2 x CPU cores) + 1, min 2, max 8 for fiscal workload
workers = min(max(multiprocessing.cpu_count() * 2 + 1, 2), 8)
worker_class = "sync"
worker_connections = 1000
threads = 1

# Timeouts (FDMS/CloseDay can be slow)
timeout = 120
graceful_timeout = 30
keepalive = 5

# Logging
accesslog = os.environ.get("GUNICORN_ACCESS_LOG", "-")
errorlog = os.environ.get("GUNICORN_ERROR_LOG", "-")
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "fdms_gunicorn"

# Security: do not expose server version
server_tokens = False

# Preload app once, then fork workers (reduces memory; ensure no lazy state)
preload_app = False  # Set True only if app has no per-worker state; Celery/DB prefer False
