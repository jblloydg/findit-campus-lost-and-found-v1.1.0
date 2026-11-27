"""Daily backups and restore.

A backup is a folder under settings.BACKUP_DIR (default ``backups/``, which
Git ignores) named by its UTC time, e.g. ``20261127-093000``:

    data.json      every database row, in Django's portable JSON format
                   (works on SQLite now and PostgreSQL later)
    media.zip      uploaded photos
    private_media.zip  report attachments (session 1), if any
    manifest.json  when it was made, why, row counts, database engine

Restoring replaces the whole database and the media folder with a backup.
A safety backup of the current state is always made first.
"""
import json
import shutil
import zipfile
from datetime import datetime, timedelta, timezone as dt_timezone
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.db import connection, transaction

EXCLUDE = [
    "contenttypes",
    "auth.permission",
    "sessions.session",
    "admin.logentry",
    "captcha.captchastore",
    "core.idempotencykey",
]
STATUS_FILE = "last_status.json"
NAME_FORMAT = "%Y%m%d-%H%M%S"


def backup_root():
    root = Path(settings.BACKUP_DIR)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write_status(ok, message, name=""):
    data = {"ok": ok, "message": message, "name": name, "at": datetime.now(dt_timezone.utc).isoformat()}
    (backup_root() / STATUS_FILE).write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def last_status():
    path = backup_root() / STATUS_FILE
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def list_backups():
    items = []
    for folder in sorted(backup_root().iterdir(), reverse=True):
        manifest = folder / "manifest.json"
        if folder.is_dir() and manifest.exists():
            try:
                info = json.loads(manifest.read_text(encoding="utf-8"))
            except ValueError:
                continue
            info["name"] = folder.name
            info["size_bytes"] = sum(p.stat().st_size for p in folder.iterdir() if p.is_file())
            items.append(info)
    return items


def latest_successful_backup_time():
    for info in list_backups():
        try:
            return datetime.fromisoformat(info["created_at"])
        except (KeyError, ValueError):
            continue
    return None


def create_backup(reason="manual"):
    now = datetime.now(dt_timezone.utc)
    name = now.strftime(NAME_FORMAT)
    folder = backup_root() / name
    suffix = 1
    while folder.exists():
        folder = backup_root() / f"{name}-{suffix}"
        suffix += 1
    folder.mkdir(parents=True)
    try:
        data_path = folder / "data.json"
        call_command(
            "dumpdata", exclude=EXCLUDE, natural_foreign=True, natural_primary=True,
            indent=1, output=str(data_path), verbosity=0,
        )
        media_root = Path(settings.MEDIA_ROOT)
        media_files = 0
        with zipfile.ZipFile(folder / "media.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
            if media_root.exists():
                for path in media_root.rglob("*"):
                    if path.is_file():
                        archive.write(path, path.relative_to(media_root).as_posix())
                        media_files += 1
        private_root = Path(settings.PRIVATE_MEDIA_ROOT) if getattr(settings, "PRIVATE_MEDIA_ROOT", None) else None
        private_files = 0
        if private_root and private_root.exists():
            with zipfile.ZipFile(folder / "private_media.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for path in private_root.rglob("*"):
                    if path.is_file():
                        archive.write(path, path.relative_to(private_root).as_posix())
                        private_files += 1
        rows = json.loads(data_path.read_text(encoding="utf-8"))
        counts = {}
        for row in rows:
            counts[row["model"]] = counts.get(row["model"], 0) + 1
        manifest = {
            "created_at": now.isoformat(),
            "reason": reason,
            "database_engine": connection.vendor,
            "row_count": len(rows),
            "media_files": media_files,
            "private_files": private_files,
            "models": counts,
            "format": 1,
        }
        (folder / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    except Exception as exc:  # record the failure for the admin page, then re-raise
        shutil.rmtree(folder, ignore_errors=True)
        _write_status(False, f"Backup failed: {exc}")
        raise
    prune_backups()
    _write_status(True, f"Backup {folder.name} created ({reason}).", folder.name)
    return folder


def prune_backups(keep_days=None):
    keep_days = settings.BACKUP_KEEP_DAYS if keep_days is None else keep_days
    cutoff = datetime.now(dt_timezone.utc) - timedelta(days=keep_days)
    removed = []
    backups = list_backups()
    for info in backups[1:]:  # never delete the newest backup
        try:
            created = datetime.fromisoformat(info["created_at"])
        except (KeyError, ValueError):
            continue
        if created < cutoff:
            shutil.rmtree(backup_root() / info["name"], ignore_errors=True)
            removed.append(info["name"])
    return removed


def run_daily_backup_if_due():
    """Called by the timer runner (process_due --loop). Makes at most one backup a day."""
    last = latest_successful_backup_time()
    if last is None or datetime.now(dt_timezone.utc) - last >= timedelta(hours=24):
        try:
            return create_backup("daily")
        except Exception:
            return None
    return None


def restore_backup(name):
    folder = backup_root() / name
    data_path = folder / "data.json"
    if not data_path.exists():
        raise FileNotFoundError(f"No backup named {name} in {backup_root()}.")
    safety = create_backup(f"safety copy before restoring {name}")
    with transaction.atomic():
        call_command("flush", interactive=False, verbosity=0)
        call_command("loaddata", str(data_path), verbosity=0)
    media_root = Path(settings.MEDIA_ROOT)
    media_zip = folder / "media.zip"
    if media_zip.exists():
        if media_root.exists():
            shutil.rmtree(media_root)
        media_root.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(media_zip) as archive:
            for member in archive.namelist():
                target = (media_root / member).resolve()
                if not str(target).startswith(str(media_root.resolve())):
                    raise ValueError(f"Unsafe path in media.zip: {member}")
            archive.extractall(media_root)
    private_zip = folder / "private_media.zip"
    private_root = Path(settings.PRIVATE_MEDIA_ROOT) if getattr(settings, "PRIVATE_MEDIA_ROOT", None) else None
    if private_zip.exists() and private_root:
        if private_root.exists():
            shutil.rmtree(private_root)
        private_root.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(private_zip) as archive:
            for member in archive.namelist():
                if not str((private_root / member).resolve()).startswith(str(private_root.resolve())):
                    raise ValueError(f"Unsafe path in private_media.zip: {member}")
            archive.extractall(private_root)
    _write_status(True, f"Restored {name}. Safety copy of the previous state: {safety.name}.", name)
    return safety
