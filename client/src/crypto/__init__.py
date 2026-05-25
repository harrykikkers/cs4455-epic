"""Local cryptography — all E2EE happens here.

Pure functions over bytes: no network, no I/O beyond the keystore. With the
exception of :mod:`digest`, every module here is PLANNED — the public
surface is defined but the operations raise ``NotImplementedError`` until
the pipeline described in the README *Cryptographic Protocol* is built.
"""
