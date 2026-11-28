"""DES-005 (v2.0.0): the app version shown on every page comes from the VERSION file.

It is read once when Find-IT starts, never typed into pages. Change VERSION with every version.
"""
from pathlib import Path

from django.conf import settings


def read_version():
    try:
        text = (Path(settings.BASE_DIR) / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return text.splitlines()[0].strip() if text else ""


FINDIT_VERSION = read_version()
