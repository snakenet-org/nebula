#    (c) snakenet.org, All rights reserved
"""
@ai-purpose: Envelope encryption for SecretValue.ciphertext under NEBULAR_MASTER_KEY.
@ai-context: The ONLY module allowed to touch plaintext secret values outside a request handler that
  just decrypted one for a caller who's allowed to see it (see nebular.secrets' can_reveal-gated
  reveal path). NEBULAR_MASTER_KEY may be any operator-chosen string, not a pre-formatted Fernet key
  — _derive_fernet_key() folds it through SHA-256 then base64-urlsafe-encodes the digest, since
  Fernet requires exactly 32 url-safe base64 bytes and forcing operators to pre-generate one via
  `Fernet.generate_key()` would be needless friction for "set a passphrase when you spawn the
  container." The derived Fernet instance is cached (module-level, built once from settings.
  require_master_key() on first use) rather than re-derived per call. Fernet itself supplies
  authenticated encryption (AES-128-CBC + HMAC-SHA256) plus a timestamp, so decrypt_value already
  detects both tampering and (implicitly) a wrong key — a wrong key doesn't decrypt to garbage
  plaintext, it raises InvalidToken, which is what makes the VaultMeta canary check in main.py's
  startup lifespan effective at catching a misconfigured NEBULAR_MASTER_KEY early.
@ai-rules:
  - Never log a plaintext value or the derived Fernet key.
  - encrypt_value/decrypt_value are the only sanctioned way to read/write SecretValue.ciphertext —
    no other module should import `cryptography.fernet` directly.
  - Maintain 100% type-hinting coverage.
@dependencies: cryptography
@version: 1.0.0
@author: Marc Fiedler <marc@snakenet.org>
@date: 2026-08-05
"""

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from nebular.config import settings

# Re-exported so callers can catch a wrong-key/tampered-ciphertext failure without importing
# `cryptography` themselves.
DecryptionError = InvalidToken

# The canary plaintext VaultMeta stores encrypted, checked once at startup (see main.py's lifespan)
# to fail fast on a wrong NEBULAR_MASTER_KEY rather than surfacing as a confusing per-request error.
CANARY_PLAINTEXT = "nebular-ok"


def _derive_fernet_key(raw: str) -> bytes:
    """Fold an arbitrary operator-chosen passphrase into a 32-byte url-safe base64 Fernet key."""
    digest = hashlib.sha256(raw.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    """Lazily build (and cache) the Fernet instance from NEBULAR_MASTER_KEY.

    Deferred to first use rather than built at import time so importing this module never fails
    just because the env var isn't set yet (e.g. `alembic` autogenerate never encrypts anything).
    """
    return Fernet(_derive_fernet_key(settings.require_master_key()))


def encrypt_value(plain: str) -> str:
    """Encrypt a plaintext secret value, returning the Fernet token as a str (URL-safe base64)."""
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_value(token: str) -> str:
    """Decrypt a Fernet token back to its plaintext value.

    Raises DecryptionError (cryptography.fernet.InvalidToken) on a wrong key or corrupted/tampered
    ciphertext — callers should let this propagate as a 500, not swallow it, since a decrypt failure
    here always indicates a configuration or data-integrity problem, never an expected outcome.
    """
    return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
