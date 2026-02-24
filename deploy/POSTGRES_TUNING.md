# PostgreSQL and Django Database Tuning (FDMS SaaS)

## DATABASE_URL usage

Production uses `fdms_project.settings_production`, which:

- Reads `DATABASE_URL` from the environment.
- If `DATABASE_URL` contains `postgres`, uses `dj_database_url.config(conn_max_age=600)` for the default database.
- Otherwise falls back to SQLite (not recommended for production).

Set in production:

```bash
export DATABASE_URL="postgres://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require"
```

For DigitalOcean Managed Database, use the connection string provided (usually includes `sslmode=require`).

## Pre-deploy check

Run before every deployment:

```bash
export DJANGO_SETTINGS_MODULE=fdms_project.settings_production
python manage.py check --deploy
```

This checks:

- Critical security settings (DEBUG, ALLOWED_HOSTS, etc.)
- Database connectivity
- Static files
- Other deployment-related issues

Fix any reported issues before going live.

## PostgreSQL connection pool tuning

Django uses one connection per process (Gunicorn worker). With `conn_max_age=600`, connections are reused for 10 minutes.

### Suggested settings (in DATABASE_URL or Django OPTIONS)

- **conn_max_age**: Already set to `600` in production (10 minutes). Keeps connections open and avoids connection storms.
- **conn_health_checks**: If using Django 4.1+, add `"CONN_HEALTH_CHECKS": True` in OPTIONS to validate connections before use.
- **max_connections (PostgreSQL server)**: For Gunicorn workers + Celery workers + beat, ensure `max_connections` is at least:
  - `(Gunicorn workers + Celery worker concurrency + 2)` per app instance. Example: 8 + 4 + 2 = 14; use 20–30 for safety if running one app server.

### PostgreSQL server (postgresql.conf) suggestions

- **max_connections**: 100–200 for single-node deployment.
- **shared_buffers**: 25% of RAM (e.g. 2GB on 8GB box).
- **effective_cache_size**: 50–75% of RAM.
- **work_mem**: 16–32MB for reporting/aggregation if needed.

Managed databases (e.g. DigitalOcean) often tune these; adjust only if you self-host PostgreSQL.

## Connection exhaustion

If you see "too many connections":

1. Reduce Gunicorn workers or Celery concurrency.
2. Ensure `conn_max_age` is set (we use 600) so connections are reused.
3. Increase PostgreSQL `max_connections` or scale read replicas.
