"""Shared utility functions for the UI layer.

Constants that were previously here (DEV_MODE_TOKEN etc.) live in constants.py.
"""

import os
import pathlib
import shutil
from datetime import datetime, date

from constants import NOW_FMT

# Repo root is four levels up from this file: client/src/ui/utils.py -> repo.
_REPO_ROOT    = pathlib.Path(__file__).parents[3]

# Name of the C++ message-store archive binary used by the Download action.
# Resolution order (see resolve_store_binary): MESSAGE_STORE_BIN env override,
# the default cmake build location, then a PATH lookup.
_ARCHIVE_BINARY_NAME = "message-store"
_ARCHIVE_BINARY      = _REPO_ROOT / "message-store" / "build" / _ARCHIVE_BINARY_NAME


def resolve_store_binary() -> str | None:
    """Locate the C++ ``message-store`` archive binary, or ``None`` if absent.

    Resolution order, per the message-store CLI contract:

    1. ``MESSAGE_STORE_BIN`` environment override (an explicit path),
    2. the default cmake build location ``<repo>/message-store/build/message-store``,
    3. a ``PATH`` lookup via :func:`shutil.which`.

    Returns the resolved path as a string, or ``None`` when no binary is found
    (the caller surfaces a "build message-store first" error in that case).
    """
    override = os.environ.get("MESSAGE_STORE_BIN")
    if override and os.path.exists(override):
        return override
    if _ARCHIVE_BINARY.exists():
        return str(_ARCHIVE_BINARY)
    return shutil.which(_ARCHIVE_BINARY_NAME)


def _format_time(raw, short=False):
    """Format an ISO/SQL timestamp for display in the UI."""
    if not raw:
        return ""
    try:
        raw_s = str(raw)
        dt = None
        for fmt in (NOW_FMT, "%Y-%m-%dT%H:%M:%S.%fZ",
                    "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
            try:
                dt = datetime.strptime(raw_s, fmt)
                break
            except ValueError:
                continue
        if dt is None:
            return raw_s
        today = date.today()
        hour = dt.strftime("%I:%M %p").lstrip("0")
        if dt.date() == today:
            return hour
        elif dt.year == today.year:
            day = str(dt.day)
            return f"{dt.strftime('%b')} {day}" if short else f"{dt.strftime('%b')} {day}, {hour}"
        else:
            return f"{dt.strftime('%b')} {dt.day} {dt.year}"
    except (ValueError, TypeError):
        return str(raw) if raw else ""
