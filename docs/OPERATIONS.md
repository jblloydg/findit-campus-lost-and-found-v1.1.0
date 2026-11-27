# Find-IT Operations Guide

This guide covers backups, restore, the daily schedule, deployment settings, logging, and uptime monitoring.
Run every command from the `Find-IT` folder with the virtual environment active
(Windows: `.\.venv\Scripts\Activate.ps1`; Linux: `source .venv/bin/activate`).

---

## 1. Database backups

Find-IT detects the active database automatically:

| Database | When | Method | File |
| --- | --- | --- | --- |
| SQLite | Local development (default) | SQLite online backup API (a consistent copy, even while the site runs) | `findit-<kind>-YYYYMMDD-HHMMSS.sqlite3` |
| PostgreSQL | Hosting (`DATABASE_URL` set) | `pg_dump --format=custom` | `findit-<kind>-YYYYMMDD-HHMMSS.dump` |

`<kind>` is `daily` (the scheduled task), `manual`, or `pre-restore` (the automatic safety copy taken before a restore).

### Commands

```powershell
python manage.py backup_db                # manual backup + retention clean-up
python manage.py backup_db --kind daily   # what the scheduled task runs
python manage.py list_backups             # status, files, retention
python manage.py restore_db FILE --check-only   # validate only, changes nothing
python manage.py restore_db FILE          # restore (asks you to type RESTORE)
```

### What every backup run does

1. Writes the backup to a temporary `.partial` file.
2. Validates it:
   - **SQLite:** the file must pass `PRAGMA integrity_check` and contain the Find-IT tables.
   - **PostgreSQL:** `pg_restore --list` must read the file, and it must contain the Find-IT table data.
3. Renames the file to its final date-and-time name. If that name already exists, it adds `-2`, `-3`, and so on, so **an existing backup is never overwritten**.
4. Writes a `.sha256` checksum file next to the backup.
5. Appends a line to `backup-log.jsonl` with the time, action, status, file, size, checksum, and message, and also writes it to the application log.
6. Applies the retention policy.

If any step fails, the partial file is deleted, the failure is logged, and the command exits with an error code. That error code is what makes Task Scheduler or cron show the run as failed.

### Where backups are stored

`FINDIT_BACKUP_DIR` (default: the `backups/` folder inside `Find-IT`).

- It is **not** under `static/` or `media/`, and the website has no URL that serves it.
- `backups/`, `*.sqlite3`, and `*.dump`-style database files are in `.gitignore`. **Never commit backups**, because they contain real user data.
- For real use, point `FINDIT_BACKUP_DIR` at a folder on a **different disk** or a synced, access-controlled location, so a disk failure doesn't take the database and its backups together.

### Retention

| Setting | Default | Meaning |
| --- | --- | --- |
| `FINDIT_BACKUP_RETENTION_DAYS` | 14 | Backups older than this many days can be removed |
| `FINDIT_BACKUP_MIN_KEEP` | 7 | The newest N intact backups are always kept, however old |

Retention never deletes the only intact backup. It also never deletes a backup whose checksum doesn't match, so damaged files stay in place for someone to inspect.

### PostgreSQL notes

- The server needs the PostgreSQL client tools (`pg_dump`, `pg_restore`) at the **same major version as the server or newer**.
- The password comes from `DATABASE_URL`. It is passed to `pg_dump` through the `PGPASSWORD` environment variable, never on the command line, and it is never written to the log.

---

## 2. Restoring a backup

1. **Stop** the website and the timer runner (close the `start_findit.ps1` window, or stop the service).
2. Check the file:
   ```powershell
   python manage.py list_backups
   python manage.py restore_db findit-daily-20261127-020000.sqlite3 --check-only
   ```
3. Restore it:
   ```powershell
   python manage.py restore_db findit-daily-20261127-020000.sqlite3
   ```
   Type `RESTORE` when asked. Find-IT will then:
   - validate the file: it must exist, match its checksum, be the right database type, and pass its integrity check
   - save the **current** database as a `findit-pre-restore-…` backup
   - replace the data, using the SQLite backup API or `pg_restore --clean --single-transaction`
   - run an integrity check (SQLite) and log the result
4. Run `python manage.py migrate`, in case the backup came from an older Find-IT version.
5. Start the site again.

If anything is wrong with the file, the restore is refused and **nothing changes**. If the restore itself fails, the message names the pre-restore safety copy. Restore that copy the same way to go back.

Restore is deliberately **command-line only**. Someone needs access to the server to run it, and nobody can trigger it from the website.

Uploaded pictures (`media/`) and report attachments (`private_media/`) are files, not database rows. Back up those folders with the server's normal file backup.

---

## 3. Scheduling the daily backup

> The scripts are included and the backup command is tested. **The daily schedule is not active until you register it on the machine that runs Find-IT and confirm a successful run.**

### Windows (Task Scheduler)

1. Open PowerShell in the `Find-IT` folder and register the task. The default time is 2:00 AM:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\register_backup_task.ps1
   # or choose a time:  ... -File .\scripts\register_backup_task.ps1 -Time "23:30"
   ```
2. Test it right away:
   ```powershell
   Start-ScheduledTask -TaskName "Find-IT Daily Backup"
   Get-ScheduledTaskInfo -TaskName "Find-IT Daily Backup"   # LastTaskResult 0 = success
   python manage.py list_backups
   ```
3. The task runs `scripts\backup_daily.ps1`, which writes its output to `logs\backup-task.log`. With *StartWhenAvailable* set, it runs as soon as the PC is back on if it was off at 2:00 AM.
4. The PC (or server) must be **on**, or turned on later that day, for the backup to happen.

### Linux (cron)

```sh
chmod +x scripts/backup_daily.sh
crontab -e
# add:
0 2 * * * /srv/findit/Find-IT/scripts/backup_daily.sh
```

The script loads `.env` for `DATABASE_URL` and writes to `logs/backup-task.log`.

**Check every week.** Open **Admin → Backups** in Find-IT. It shows the last successful backup and the last attempt, and it shows a warning when the last attempt failed or no backup exists.

---

## 4. Production configuration checklist

Set these as environment variables on the server, never in code. `.env.example` lists all of them.

| Variable | Production value |
| --- | --- |
| `DJANGO_DEBUG` | `0`. The site refuses to start with the default secret key when DEBUG is off |
| `DJANGO_SECRET_KEY` | A long random value, e.g. `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `DJANGO_ALLOWED_HOSTS` | The site's host name |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://<host>` |
| `DATABASE_URL` | PostgreSQL connection URL. Connections are reused and health-checked |
| `REDIS_URL` | Needed for chat with more than one process; also shares sign-in throttling |
| `DJANGO_BEHIND_PROXY` | `1` only if a trusted proxy or PaaS terminates HTTPS |
| `DJANGO_HSTS_SECONDS` | Starts at 3600; raise it to 31536000 once HTTPS is confirmed working |
| `DJANGO_EMAIL_HOST` (+ user, password, port) | Needed for password-reset emails |

When DEBUG is off, Find-IT turns on:

- HTTPS redirect
- secure, HTTP-only cookies
- HSTS
- `nosniff`
- `same-origin` referrer policy
- `X-Frame-Options: DENY`
- WhiteNoise for compressed, cache-busted static files

`python manage.py check --deploy` with production variables leaves two warnings, W005 (include subdomains) and W021 (preload). Both depend on the school's domain policy, so they are configurable rather than forced on (`DJANGO_HSTS_INCLUDE_SUBDOMAINS`).

Also:

- Run `python manage.py collectstatic --noinput` on deploy.
- Serve `media/` through the web server or object storage. **Never** serve `private_media/` or the backup folder.

---

## 5. Errors and logging

- Logs go to the console **and** to `logs/findit.log` (`FINDIT_LOG_DIR`). The file rotates at 5 MB and keeps 5 old files.
  - Warnings and above are logged from everything.
  - Find-IT's own events (backups, errors) are logged at INFO.
  - Server errors are logged with a full traceback.
- Request bodies are **never** logged. Password fields are marked sensitive (`sensitive_post_parameters`), so even Django's error reports hide them.
- Users see friendly pages with no technical details:
  - **403:** you don't have access, with the reason.
  - **404:** page not found.
  - **500:** "Something went wrong", recorded for administrators.
  - **503:** the database is unavailable, and the page says plainly that the action was **not saved**.
  - **Expired form (CSRF):** asks the user to refresh and resubmit.
- Important multi-step writes (claims, returns, account changes, reports) run inside database transactions. If a step fails, nothing is half-saved.
- SQLite waits up to 20 seconds for a lock before failing, which avoids "database is locked" errors when the website and the timer runner write at the same moment.

---

## 6. Uptime monitoring

Find-IT has a health endpoint for monitors: **`GET /health/`**

- `200 {"status": "ok", "database": "ok"}` means the app and the database are working.
- `503 {"status": "error", "database": "error"}` means the database can't be reached. The details go to the log only.

The endpoint needs no login and reveals nothing else.

Recommended setup once Find-IT is hosted:

| What | How |
| --- | --- |
| Application availability | An external HTTP monitor (e.g. UptimeRobot, Better Stack, or the host's own checks) calls `https://<host>/health/` every 1–5 minutes and alerts by email or SMS when it isn't 200 |
| Database availability | Covered by `/health/` (it runs a query). Also turn on the database provider's own alerts (storage, connections) |
| Server or hosting status | The hosting provider's status page and resource alerts (CPU, memory, disk) |
| Errors | Review `logs/findit.log`, or forward it to the host's log service. Optionally add an error tracker (e.g. Sentry) later |
| Backups | **Admin → Backups**, plus `LastTaskResult` (Windows) or `logs/backup-task.log` |

No uptime percentage can be claimed until a monitor has collected data over a real period, for example 30 days.
