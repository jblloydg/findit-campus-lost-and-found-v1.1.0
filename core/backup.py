"""Database backup, validation, retention, and restore for Find-IT.

Supports the two databases Find-IT uses:
  * SQLite (local development)  -> consistent copy with SQLite's online backup API
  * PostgreSQL (hosting)        -> pg_dump custom format, restored with pg_restore

Every backup is written to a temporary name, validated, given a SHA-256 checksum
file, and only then renamed to its final date-based name, so a failed run never
leaves a half-written file that looks like a backup and never overwrites an
existing one. Every attempt is appended to backup-log.jsonl in the backup folder.

Backups are never served by the website. Restore is command-line only.
"""
import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.db import connections
from django.utils import timezone

logger = logging.getLogger("findit.backup")

KINDS = ("daily", "manual", "pre-restore")
FILENAME_RE = re.compile(r"^findit-(?P<kind>daily|manual|pre-restore)-(?P<stamp>\d{8}-\d{6})(?:-\d+)?\.(?P<ext>sqlite3|dump)$")
REQUIRED_TABLES = ("django_migrations", "auth_user", "core_profile", "core_itempost")
LOG_NAME = "backup-log.jsonl"


class BackupError(Exception):
    """A backup or restore step failed. The message is safe to show to an operator."""


@dataclass
class BackupFile:
    path: Path
    kind: str
    created: datetime
    size: int
    checksum_ok: bool | None  # None when no checksum file exists

    @property
    def name(self):
        return self.path.name


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def backup_dir():
    path = Path(settings.BACKUP_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _db_settings():
    return settings.DATABASES["default"]


def engine():
    name = _db_settings()["ENGINE"]
    if name.endswith("sqlite3"):
        return "sqlite"
    if "postgresql" in name:
        return "postgresql"
    raise BackupError(f"Backups are not supported for the database engine {name}.")


def extension_for(engine_name):
    return "sqlite3" if engine_name == "sqlite" else "dump"


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _checksum_path(path):
    return path.with_name(path.name + ".sha256")


def checksum_matches(path):
    sidecar = _checksum_path(path)
    if not sidecar.exists():
        return None
    expected = sidecar.read_text().split()[0].strip()
    return expected == sha256_of(path)


def write_log(action, status, message="", **extra):
    entry = {
        "time": timezone.localtime().isoformat(timespec="seconds"),
        "action": action,
        "status": status,
        "message": message,
        **extra,
    }
    try:
        with open(backup_dir() / LOG_NAME, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    except OSError:
        logger.exception("Could not write the backup log.")
    log = logger.info if status == "success" else logger.error
    log("backup %s %s: %s %s", action, status, message, extra.get("file", ""))
    return entry


def read_log(limit=50):
    path = backup_dir() / LOG_NAME
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
            entry["when"] = datetime.fromisoformat(entry["time"])
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
        entries.append(entry)
    return entries[-limit:][::-1]


def _pg_env_and_args():
    db = _db_settings()
    env = os.environ.copy()
    if db.get("PASSWORD"):
        env["PGPASSWORD"] = str(db["PASSWORD"])  # passed through the environment, never on the command line
    args = []
    if db.get("HOST"):
        args += ["-h", str(db["HOST"])]
    if db.get("PORT"):
        args += ["-p", str(db["PORT"])]
    if db.get("USER"):
        args += ["-U", str(db["USER"])]
    return env, args, str(db["NAME"])


def _run(command, env=None):
    try:
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=60 * 30)
    except FileNotFoundError as exc:
        raise BackupError(f"{command[0]} was not found. Install the PostgreSQL client tools on this server.") from exc
    except subprocess.TimeoutExpired as exc:
        raise BackupError(f"{command[0]} took longer than 30 minutes and was stopped.") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()[-1:] or ["no details"]
        raise BackupError(f"{command[0]} failed: {detail[0]}")
    return result.stdout


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_backup_file(path, expected_engine=None):
    """Raise BackupError unless path is a complete, readable Find-IT backup."""
    path = Path(path)
    if not path.is_file():
        raise BackupError(f"Backup file not found: {path}")
    if path.stat().st_size == 0:
        raise BackupError("The backup file is empty.")
    if checksum_matches(path) is False:
        raise BackupError("The backup file does not match its checksum. It may be damaged or changed.")
    kind = "sqlite" if path.suffix == ".sqlite3" else "postgresql" if path.suffix == ".dump" else None
    if kind is None:
        raise BackupError("Unknown backup type. Expected a .sqlite3 or .dump file.")
    if expected_engine and kind != expected_engine:
        raise BackupError(f"This is a {kind} backup, but the active database is {expected_engine}.")
    if kind == "sqlite":
        _validate_sqlite(path)
    else:
        _validate_pg_dump(path)
    return kind


def _validate_sqlite(path):
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            result = connection.execute("PRAGMA integrity_check").fetchone()[0]
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            connection.close()
    except sqlite3.DatabaseError as exc:
        raise BackupError(f"The file is not a readable SQLite database ({exc}).") from exc
    if result != "ok":
        raise BackupError(f"SQLite integrity check failed: {result}")
    missing = [table for table in REQUIRED_TABLES if table not in tables]
    if missing:
        raise BackupError(f"This is not a Find-IT database backup (missing tables: {', '.join(missing)}).")


def _validate_pg_dump(path):
    listing = _run(["pg_restore", "--list", str(path)])
    missing = [table for table in REQUIRED_TABLES if f"TABLE DATA public {table} " not in listing]
    if missing:
        raise BackupError(f"This is not a complete Find-IT backup (missing table data: {', '.join(missing)}).")


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------

def _final_path(kind, engine_name):
    stamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
    folder = backup_dir()
    base = f"findit-{kind}-{stamp}"
    ext = extension_for(engine_name)
    candidate = folder / f"{base}.{ext}"
    counter = 2
    while candidate.exists():  # never overwrite an existing backup
        candidate = folder / f"{base}-{counter}.{ext}"
        counter += 1
    return candidate


def create_backup(kind="manual"):
    """Create, validate, and checksum one backup. Returns the final Path. Raises BackupError."""
    if kind not in KINDS:
        raise BackupError(f"Unknown backup kind {kind}.")
    engine_name = engine()
    final = _final_path(kind, engine_name)
    partial = final.with_name(final.name + ".partial")
    try:
        if engine_name == "sqlite":
            source_path = Path(_db_settings()["NAME"])
            if not source_path.exists():
                raise BackupError(f"The SQLite database {source_path.name} does not exist yet. Run migrate first.")
            source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
            target = sqlite3.connect(partial)
            try:
                with target:
                    source.backup(target)
            finally:
                target.close()
                source.close()
        else:
            env, args, name = _pg_env_and_args()
            _run(["pg_dump", "--format=custom", "--no-owner", "--no-privileges", *args, "-f", str(partial), name], env=env)
        _validate_by_engine(partial, engine_name)
        partial.replace(final)
        checksum = sha256_of(final)
        _checksum_path(final).write_text(f"{checksum}  {final.name}\n")
    except Exception as exc:
        partial.unlink(missing_ok=True)
        message = str(exc) if isinstance(exc, BackupError) else f"Unexpected error: {exc.__class__.__name__}: {exc}"
        write_log("backup", "failed", message, kind=kind, engine=engine_name)
        raise BackupError(message) from exc
    write_log(
        "backup", "success", "Backup created and validated.", kind=kind, engine=engine_name,
        file=final.name, size=final.stat().st_size, sha256=checksum,
    )
    return final


def _validate_by_engine(path, engine_name):
    if path.stat().st_size == 0:
        raise BackupError("The new backup file is empty.")
    if engine_name == "sqlite":
        _validate_sqlite(path)
    else:
        _validate_pg_dump(path)


# ---------------------------------------------------------------------------
# Listing and retention
# ---------------------------------------------------------------------------

def list_backups():
    files = []
    for path in backup_dir().iterdir():
        match = FILENAME_RE.match(path.name)
        if not match or not path.is_file():
            continue
        created = timezone.make_aware(datetime.strptime(match["stamp"], "%Y%m%d-%H%M%S"))
        files.append(BackupFile(path, match["kind"], created, path.stat().st_size, checksum_matches(path)))
    return sorted(files, key=lambda f: (f.created, f.name), reverse=True)


def apply_retention(retention_days=None, min_keep=None, now=None):
    """Delete backups older than the retention period, but always keep the newest
    `min_keep` intact backups, and never delete the only intact backup.
    Damaged backups (checksum mismatch) are never deleted automatically; they are
    left for an operator to inspect. Returns the list of deleted file names."""
    retention_days = settings.BACKUP_RETENTION_DAYS if retention_days is None else retention_days
    min_keep = max(1, settings.BACKUP_MIN_KEEP if min_keep is None else min_keep)
    now = now or timezone.now()
    cutoff = now - timedelta(days=retention_days)
    intact = [f for f in list_backups() if f.checksum_ok]
    protected = {f.path for f in intact[:min_keep]}
    deleted = []
    for item in intact:
        if item.path in protected or item.created >= cutoff:
            continue
        if len(intact) - len(deleted) <= 1:
            break  # never remove the last intact backup
        item.path.unlink(missing_ok=True)
        _checksum_path(item.path).unlink(missing_ok=True)
        deleted.append(item.name)
    if deleted:
        write_log("retention", "success", f"Removed {len(deleted)} expired backup(s).", files=deleted)
    return deleted


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------

def resolve_backup_path(name_or_path):
    candidate = Path(name_or_path)
    if not candidate.is_absolute() and not candidate.exists():
        candidate = backup_dir() / name_or_path
    return candidate.resolve()


def restore_backup(name_or_path):
    """Validate a backup, back up the current database, then restore. Raises BackupError."""
    engine_name = engine()
    path = resolve_backup_path(name_or_path)
    try:
        validate_backup_file(path, expected_engine=engine_name)
    except BackupError as exc:
        write_log("restore", "failed", f"Validation failed: {exc}", file=path.name)
        raise

    safety_copy = None
    try:
        if engine_name == "sqlite":
            live = Path(_db_settings()["NAME"])
            if live.exists():
                safety_copy = create_backup("pre-restore")
            connections.close_all()
            source = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            target = sqlite3.connect(live, timeout=30)
            try:
                with target:
                    source.backup(target)
                result = target.execute("PRAGMA integrity_check").fetchone()[0]
            finally:
                target.close()
                source.close()
            if result != "ok":
                raise BackupError(f"Integrity check after restore failed: {result}")
        else:
            safety_copy = create_backup("pre-restore")
            connections.close_all()
            env, args, name = _pg_env_and_args()
            _run([
                "pg_restore", "--clean", "--if-exists", "--no-owner", "--no-privileges",
                "--single-transaction", "--exit-on-error", *args, "-d", name, str(path),
            ], env=env)
    except Exception as exc:
        message = str(exc) if isinstance(exc, BackupError) else f"Unexpected error: {exc.__class__.__name__}: {exc}"
        hint = f" The database before the restore attempt is saved as {safety_copy.name}." if safety_copy else ""
        write_log("restore", "failed", message + hint, file=path.name)
        raise BackupError(message + hint) from exc
    write_log(
        "restore", "success", "Database restored from backup.", file=path.name,
        safety_copy=safety_copy.name if safety_copy else "",
    )
    return safety_copy


def status_summary():
    """Data for the administrator backup status page."""
    log = read_log(200)
    backups = list_backups()
    last_attempt = next((e for e in log if e.get("action") == "backup"), None)
    last_success = next((e for e in log if e.get("action") == "backup" and e.get("status") == "success"), None)
    try:
        engine_name = engine()
    except BackupError:
        engine_name = "unsupported"
    return {
        "engine": engine_name,
        "backups": backups,
        "intact_count": sum(1 for b in backups if b.checksum_ok),
        "last_attempt": last_attempt,
        "last_success": last_success,
        "recent_log": log[:15],
        "retention_days": settings.BACKUP_RETENTION_DAYS,
        "min_keep": settings.BACKUP_MIN_KEEP,
        "backup_dir": str(backup_dir()),
    }


def disk_free_bytes():
    try:
        return shutil.disk_usage(backup_dir()).free
    except OSError:
        return None
