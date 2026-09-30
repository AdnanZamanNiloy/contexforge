"""Encryption for the API keys stored in the Model Hub.

Every other credential in ContextForge arrives through the environment, where
it is never written down.  The Model Hub is different: the user types provider
keys into the UI and they are persisted to SQLite.  That makes ``hub_models``
the one table holding live secrets at rest, and a backup or a stray copy of
``backend/data/`` hands over working credentials for every provider the user has
configured.

This module wraps that in Fernet (AES-128-CBC + HMAC-SHA256, authenticated), so
a key sitting in the database is not a usable credential without the encryption
key, which stays in the environment.

Design constraints, all of them deliberate:

* **No key, no encryption — but no failure either.**  With no
  ``CREDENTIAL_ENCRYPTION_KEY`` configured the store keeps working exactly as
  before, writing plaintext.  Refusing to start would lock out anyone upgrading
  an existing install; instead the condition is logged loudly, once.
* **Pre-existing rows keep working.**  A ciphertext is recognised by its version
  prefix, so a database written before this change decrypts as plaintext and is
  migrated in place on first write.  No separate migration step, and no window
  where an unmigrated row is unreadable.
* **A wrong key degrades to "cannot read", never to "silently wrong".**  If
  decryption fails the value is surfaced as a sentinel, not returned as garbage
  — a model with an unreadable key is disabled and reported, which is
  recoverable, instead of failing every request with a confusing provider error.
"""

from __future__ import annotations

import logging
from typing import Final

from app.config.settings import settings

__all__ = [
    "CREDENTIAL_UNREADABLE",
    "encrypt_secret",
    "encryption_available",
    "is_encrypted",
    "redact",
    "warn_once_if_unencrypted",
]

logger = logging.getLogger(__name__)

# Prefixed onto every ciphertext so an encrypted value is self-describing.  That
# is what lets a database holding a mix of plaintext and encrypted keys (the
# state right after an upgrade) be read correctly row by row.
_PREFIX: Final = "enc:v1:"

# Returned in place of a secret that is present but cannot be decrypted — for
# example after the encryption key was rotated or lost.  Distinct from None,
# which means "no key was stored", so a caller can tell "not configured" from
# "configured but unreadable" and report the difference.
CREDENTIAL_UNREADABLE: Final = "__cf_unreadable__"

_warned = False


def encryption_available() -> bool:
    """True when a usable encryption key is configured."""
    return bool(settings.CREDENTIAL_ENCRYPTION_KEY.strip())


def _fernet():
    """Build a Fernet instance, or return None if the key is unusable."""
    key = settings.CREDENTIAL_ENCRYPTION_KEY.strip()
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        return None
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except ValueError, TypeError:
        return None


def is_encrypted(value: str | None) -> bool:
    """True when *value* is a ciphertext produced by :func:`encrypt_secret`."""
    return isinstance(value, str) and value.startswith(_PREFIX)


def encrypt_secret(plaintext: str | None) -> str | None:
    """Encrypt *plaintext* for storage.

    Returns the ciphertext, or the input unchanged when no encryption key is
    configured or the value is empty.  Already-encrypted input is returned as-is
    so a re-write cannot double-encrypt.
    """
    if plaintext is None or plaintext == "":
        return plaintext
    if is_encrypted(plaintext):
        return plaintext
    fernet = _fernet()
    if fernet is None:
        return plaintext
    return _PREFIX + fernet.encrypt(plaintext.encode()).decode()


def decrypt_secret(value: str | None) -> str | None:
    """Decrypt a stored value.

    Plaintext (a row written before encryption was enabled) is returned
    unchanged.  A value that is encrypted but cannot be decrypted with the
    configured key yields :data:`CREDENTIAL_UNREADABLE`.
    """
    if value is None or value == "":
        return value
    if not is_encrypted(value):
        return value
    fernet = _fernet()
    if fernet is None:
        return CREDENTIAL_UNREADABLE
    try:
        return fernet.decrypt(value[len(_PREFIX) :].encode()).decode()
    except Exception as exc:
        logger.error(
            "Stored credential could not be decrypted with the configured key. "
            "Re-enter the API key for this model. (%s)",
            type(exc).__name__,
        )
        return CREDENTIAL_UNREADABLE


def redact(value: str | None) -> str | None:
    """Render a secret for a log line, keeping enough to identify it.

    Never returns the secret itself, including for short values: a four-character
    key is still a secret, and a prefix would leak most of it.
    """
    if not value:
        return None
    if value == CREDENTIAL_UNREADABLE:
        return CREDENTIAL_UNREADABLE
    if len(value) <= 8:
        return "***"
    return f"{value[:3]}…{value[-2:]}"


def warn_once_if_unencrypted() -> None:
    """Log a one-time warning when credentials are being stored in plaintext."""
    global _warned
    if _warned or encryption_available():
        return
    _warned = True
    logger.warning(
        "CREDENTIAL_ENCRYPTION_KEY is not set — API keys configured in the Model "
        "Hub are stored in plaintext in backend/data/model_hub/model_hub.db. Set "
        "CREDENTIAL_ENCRYPTION_KEY in backend/.env to encrypt them; generate one with "
        'python -c "from cryptography.fernet import Fernet; '
        'print(Fernet.generate_key().decode())".'
    )
