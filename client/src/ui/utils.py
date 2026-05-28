"""Shared utility functions for the UI layer.

Constants that were previously here (DEV_MODE_TOKEN etc.) live in constants.py.
"""

import base64
import json
import os
import pathlib
import platform
import subprocess
from datetime import datetime, date

from constants import NOW_FMT

_STORE_BINARY = pathlib.Path(__file__).parents[3] / "message-store" / "build" / "zebra-store"
_CACHE_FILE   = pathlib.Path.home() / ".zebra" / "messages.json"


def _write_cache(inbox: list, sent: list) -> None:
    """Persist message METADATA to the local JSON cache for the C++ store.

    Decrypted ``plaintext`` and internal UI flags (``_mine``, ``_key_warning``,
    ``_forwarded_to`` …) are stripped before writing: the indexer only needs the
    ciphertext envelope (ids, ciphertext, nonce, timestamps), and cleartext must
    never be persisted here. Durable plaintext lives solely in the KEK-encrypted
    message cache owned by the keystore.
    """
    def _sanitize(m: dict) -> dict:
        return {k: v for k, v in m.items()
                if k != "plaintext" and not k.startswith("_")}
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = [_sanitize(m) for m in (inbox + sent)]
        _CACHE_FILE.write_text(json.dumps(payload, default=str))
    except Exception as e:
        print(f"[cache] write error: {e}")


def _run_store_binary() -> None:
    """Call the C++ zebra-store binary to index the local cache (Linux only)."""
    if platform.system() != "Linux":
        return
    if not _STORE_BINARY.exists():
        return
    try:
        result = subprocess.run(
            [str(_STORE_BINARY), str(_CACHE_FILE)],
            capture_output=True, text=True, timeout=5)
        if result.stdout:
            print(result.stdout, end="")
        if result.returncode != 0 and result.stderr:
            print(f"[zebra-store] {result.stderr.strip()}")
    except Exception as e:
        print(f"[zebra-store] {e}")


def _dummy_msg_fields(plaintext=""):
    """Return fake crypto fields that satisfy backend validation."""
    b64 = lambda b: base64.b64encode(b).decode()
    return {
        "enc":        b64(os.urandom(32)),
        "ciphertext": plaintext,
        "nonce":      b64(os.urandom(12)),
        "signature":  b64(os.urandom(64)),
        "seqNo":      0,
        "digest":     "0x" + "00" * 32,
    }


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
