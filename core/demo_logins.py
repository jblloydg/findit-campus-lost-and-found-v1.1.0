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


def tester_accounts_path():
    if not settings.configured:
        return Path.cwd() / "tester-accounts.txt"
    return Path(getattr(settings, "FINDIT_TESTER_ACCOUNTS_FILE", "") or Path(settings.BASE_DIR) / "tester-accounts.txt")


def tester_accounts():
    """CHG-014: the owner's tester accounts, from ``tester-accounts.txt`` (private).

    Accounts are sensitive, so nothing about them is in the shared code: the file is ignored by
    Git in the shared repository and only the owner's private copy holds it. One line per account:
    ``Student ID | email | first name | last name | FOUND or LOST | password`` (# = note).
    The FOUND tester posts a found item and the LOST tester a lost item; seed_demo then starts a
    chat on each post between them. Without the file there are no tester accounts.
    """
    path = tester_accounts_path()
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) == 6 and parts[4].upper() in ("FOUND", "LOST") and len(parts[5]) >= 8 and "@" in parts[1]:
            rows.append({"username": parts[0], "email": parts[1].lower(), "first_name": parts[2],
                         "last_name": parts[3], "posts": parts[4].upper(), "password": parts[5]})
    return rows


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
