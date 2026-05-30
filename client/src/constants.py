"""Application-level constants shared across the client.

Environment/server config lives in config.py.
Crypto domain constants (_AAD, _INFO) stay private to their modules.
UI styling (colours, widget sizes) stays inline — that's normal for CTk.
"""

# Dev mode bypass — must match the token the login screen injects
DEV_MODE_TOKEN = "dev-token" # Bypasses encryption and networking to test how ui looks

# Password policy (enforced in register_frame and change-password)
MIN_PASSWORD_LENGTH = 12

# Message polling cadence (milliseconds)
POLL_INTERVAL_MS = 10_000 # Every 10 seconds main_frame.py calls _load()

# Conversation list preview truncation
PREVIEW_MAX_CHARS = 34

# Datetime format used when writing and parsing local timestamps
NOW_FMT = "%Y-%m-%d %H:%M"
