#!/usr/bin/env bash
#
# PostgreSQL backup script for FDMS SaaS.
# Requires: DATABASE_URL set (postgres://...), pg_dump on PATH.
# Usage: ./scripts/backup_db.sh [BACKUP_DIR]
# Default BACKUP_DIR: ./backups (relative to script's project root) or set BACKUP_DIR env.
#
# Retention: backups older than 14 days are deleted.
# Logging: logs to stdout and optionally to BACKUP_DIR/backup_db.log.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKUP_DIR="${1:-${BACKUP_DIR:-$PROJECT_ROOT/backups}}"
RETENTION_DAYS=14
LOG_FILE="${LOG_FILE:-$BACKUP_DIR/backup_db.log}"

log() {
    echo "[$(date -Iseconds)] $*"
    if [[ -d "$BACKUP_DIR" ]]; then
        echo "[$(date -Iseconds)] $*" >> "$LOG_FILE" 2>/dev/null || true
    fi
}

if [[ -z "${DATABASE_URL:-}" ]]; then
    log "ERROR: DATABASE_URL is not set. Cannot run pg_dump."
    exit 1
fi

if [[ "$DATABASE_URL" != *"postgres"* ]] && [[ "$DATABASE_URL" != *"postgresql"* ]]; then
    log "WARNING: DATABASE_URL does not look like PostgreSQL. Skipping backup (use PostgreSQL in production)."
    exit 0
fi

mkdir -p "$BACKUP_DIR"
BACKUP_FILE="$BACKUP_DIR/backup_$(date +%F_%H%M%S).sql"

log "Starting PostgreSQL backup to $BACKUP_FILE"
if pg_dump "$DATABASE_URL" --no-owner --no-acl > "$BACKUP_FILE" 2>/dev/null; then
    log "Backup completed: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"
else
    log "ERROR: pg_dump failed."
    exit 1
fi

log "Removing backups older than $RETENTION_DAYS days"
while IFS= read -r -d '' f; do
    log "Deleted: $f"
    rm -f "$f"
done < <(find "$BACKUP_DIR" -maxdepth 1 -name 'backup_*.sql' -type f -mtime +$RETENTION_DAYS -print0 2>/dev/null)

log "Backup run finished."
