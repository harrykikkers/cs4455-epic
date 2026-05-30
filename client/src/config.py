"""Environment configuration — server URL, keystore path, timeouts.

Pure configuration: no GUI imports, so the ``api``/``services`` layers and
the test suite can import it without pulling in CustomTkinter. Values are
read from the environment (optionally via a local ``.env`` file); see
``.env.example`` for the full set.
"""

from __future__ import annotations

import os
from pathlib import Path

try:  # optional — .env loading is a convenience, not a requirement
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

SERVER_URL = os.environ.get("SERVER_URL", "http://localhost:3000")
KEYSTORE_PATH = os.path.expanduser(
    os.environ.get(
        "KEYSTORE_PATH",
        str(Path.home() / ".secure_messenger" / "keystore.json"),
    )
) # where the client looks for the user's private keys; created if it doesn't exist

REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "10")) # prevents app from hanging forever

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

# Alias kept for the UI/API layers (and existing tests) that import BASE_URL.
BASE_URL = SERVER_URL # Just an alias as they are the same thing

# Verify TLS for any non-local host.
_LOCAL_HOSTS = ("localhost", "127.0.0.1") # If the server URL contains any of these, we assume it's a local dev server and skip TLS verification.
VERIFY_SSL = not any(host in BASE_URL for host in _LOCAL_HOSTS) # the requests library will verify the full certificate and host name
# prevents MITM attacks
