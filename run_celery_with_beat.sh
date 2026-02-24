#!/usr/bin/env bash
# Run Celery worker + Beat so periodic tasks (e.g. Ping every 5 min) run automatically.
# Requires: Redis running. Run from project root.
cd "$(dirname "$0")"
celery -A fdms_project worker --beat -l info
