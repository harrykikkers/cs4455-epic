"""Local cryptography — all E2EE happens here.

Pure functions over bytes: no network, no I/O beyond the keystore. The full
pipeline from the README *Cryptographic Protocol* is implemented:
:mod:`messaging` (static ECDH + HKDF + AES-256-GCM + Ed25519 seal/open),
:mod:`signing`, :mod:`aead`, :mod:`kdf`, :mod:`digest`, and :mod:`keystore`.
"""
