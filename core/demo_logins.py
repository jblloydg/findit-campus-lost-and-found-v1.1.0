"""Demo sign-ins kept only on this PC (CHG-008, v1.1.2).

Demo passwords are never written in the code or the repository. The first time the demo data
is made on a PC, each demo account gets a random password, saved in ``demo-logins.txt`` in the
Find-IT folder. Git ignores that file. FindIT.cmd (menu 2) shows it, and the developer test
scripts in ``tools/testing/`` read it.
"""
import secrets
from pathlib import Path

from django.conf import settings

HEADER = (
    "Find-IT demo sign-ins for THIS PC only (made by seed_demo).\n"
    "Fictional accounts for local testing. Do not share this file online or put it in Git.\n"
    "Students sign in with their email; verified students may also use their Student ID.\n"
    "\n"
)
_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no look-alike characters


def logins_path():
    if not settings.configured:  # developer test scripts run from the project folder without Django set up
        return Path.cwd() / "demo-logins.txt"
    return Path(getattr(settings, "FINDIT_DEMO_LOGINS_FILE", "") or Path(settings.BASE_DIR) / "demo-logins.txt")


def tester_passwords_path():
    if not settings.configured:
        return Path.cwd() / "tester-passwords.txt"
    return Path(getattr(settings, "FINDIT_TESTER_PASSWORDS_FILE", "") or Path(settings.BASE_DIR) / "tester-passwords.txt")


def fixed_passwords():
    """CHG-014: fixed passwords for the tester accounts, from ``tester-passwords.txt``.

    That file is ignored by Git in the shared repository; only the owner's private copy holds it,
    so the same tester sign-ins work on every PC that uses the private copy. One line per account:
    ``username or email | password`` (lines starting with # are notes). Without the file the
    tester accounts get random passwords like every other demo account.
    """
    path = tester_passwords_path()
    found = {}
    if not path.exists():
        return found
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) == 2 and parts[0] and len(parts[1]) >= 8:
            found[parts[0].lower()] = parts[1]
    return found


def new_password():
    """A random password that is easy to type: three groups of four, e.g. 'k7Qm-x2Pa-9TrE'."""
    return "-".join("".join(secrets.choice(_ALPHABET) for _ in range(4)) for _ in range(3))


def load():
    """{username: password} from this PC's demo-logins.txt (empty when it does not exist)."""
    path = logins_path()
    found = {}
    if not path.exists():
        return found
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = [part.strip() for part in line.split("|")]
        if len(parts) == 5 and parts[0] not in ("Role", ""):
            found[parts[1]] = parts[4]
    return found


def save(rows):
    """rows: (role label, username, email, student ID or '', password)."""
    lines = [HEADER, "Role | Username | Email | Student ID | Password\n"]
    for row in rows:
        lines.append(" | ".join(row) + "\n")
    path = logins_path()
    path.write_text("".join(lines), encoding="utf-8")
    return path


def password_for(login):
    """Developer test scripts: the password for a username or email on this PC."""
    path = logins_path()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            parts = [part.strip() for part in line.split("|")]
            if len(parts) == 5 and login in (parts[1], parts[2]):
                return parts[4]
    raise SystemExit(f"No demo password for {login}: run 'python manage.py seed_demo' first (it writes demo-logins.txt).")
