#!/bin/sh
# Find-IT daily database backup for Linux servers (cron).
# Example crontab line (daily at 02:00):
#   0 2 * * * /srv/findit/Find-IT/scripts/backup_daily.sh
# Database credentials come from the environment file, never from this script.
set -eu
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"
mkdir -p logs
[ -f .env ] && set -a && . ./.env && set +a
PYTHON="${PYTHON:-$PROJECT_DIR/.venv/bin/python}"
[ -x "$PYTHON" ] || PYTHON=python3
echo "[$(date -Iseconds)] Starting daily backup" >> logs/backup-task.log
"$PYTHON" manage.py backup_db --kind daily >> logs/backup-task.log 2>&1
echo "[$(date -Iseconds)] Finished" >> logs/backup-task.log
