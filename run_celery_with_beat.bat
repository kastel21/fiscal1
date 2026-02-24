@echo off
REM Run Celery worker + Beat so periodic tasks (e.g. Ping every 5 min) run automatically.
REM Requires: Redis running, DJANGO_SETTINGS_MODULE or run from project root.
cd /d "%~dp0"
celery -A fdms_project worker --beat -l info
