"""keccak256 digest (``pycryptodome``).

Computes the message digest that the server records on-chain. The digest is
taken over the *plaintext*, never the ciphertext — otherwise the on-chain
record is meaningless (README *Security Notes*).
"""

from __future__ import annotations


def keccak256_hex(plaintext: bytes) -> str:
    """Return ``0x``-prefixed hex of ``keccak256(plaintext)``."""
    from Crypto.Hash import keccak  # lazy import — optional dependency

    h = keccak.new(digest_bits=256)
    h.update(plaintext)
    return "0x" + h.hexdigest()
