"""Demo script: show the encrypted archive is opaque, then decrypt and view it.
Run from the repo root:  python demo_archive.py <username>
"""
import sys, os, subprocess, getpass

sys.path.insert(0, "client/src")
from crypto.keystore import Keystore
from config import keystore_path_for

username = sys.argv[1] if len(sys.argv) > 1 else input("Username: ")
ks = Keystore(keystore_path_for(username))
password = getpass.getpass(f"Password for {username}: ")
ks.unlock(password)

archive = ks.archive_path()
key_hex = ks.archive_key_hex()
binary  = "message-store/build/message-store"

print(f"\n--- Archive file location ---")
print(archive)

print(f"\n--- Raw bytes (first 40) — proves it is encrypted ---")
with open(archive, "rb") as f: # read, binary mode (opens file as raw bytes)
    raw = f.read(40)
print(raw.hex())

print(f"\n--- Decrypted contents (via C++ binary) ---")
env = {**os.environ, "MESSAGE_STORE_KEY": key_hex}
subprocess.run([binary, "list", "--archive", archive], env=env)

