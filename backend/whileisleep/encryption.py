"""Encrypts secrets before they reach the database (LLM keys, tool headers).

A database dump or a read-only SQL injection then shows ciphertext, not customers' API keys.
Uses Fernet (AES-128-CBC + HMAC) from `cryptography`.

Keys come from settings.ENCRYPTION_KEYS: the first encrypts, all of them decrypt, so a key
is rotated by putting the new one first and keeping the old one until every row is re-saved.
With no keys configured (development), one is derived from SECRET_KEY.
"""

import base64
import hashlib
import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings

log = logging.getLogger(__name__)

# Marks a stored value as encrypted, and with which scheme.
PREFIX = "enc1:"


def derived_key(secret: str) -> bytes:
    return base64.urlsafe_b64encode(hashlib.sha256(b"whileisleep.encryption:" + secret.encode()).digest())


@lru_cache(maxsize=4)
def _fernet(keys: tuple[str, ...], secret_key: str) -> MultiFernet:
    material = [key.encode() for key in keys] or [derived_key(secret_key)]
    return MultiFernet([Fernet(key) for key in material])


def fernet() -> MultiFernet:
    return _fernet(tuple(settings.ENCRYPTION_KEYS), settings.SECRET_KEY)


def encrypt(plain: str) -> str:
    """'' stays '' so empty fields stay cheap to test for."""
    if not plain:
        return ""
    return PREFIX + fernet().encrypt(plain.encode()).decode()


def is_encrypted(stored: str) -> bool:
    return isinstance(stored, str) and stored.startswith(PREFIX)


def decrypt(stored: str) -> str:
    """The plain value. Values saved before encryption existed come back unchanged.

    A value no configured key can open (a lost or wrong ENCRYPTION_KEYS) reads as empty and
    is logged, so the dashboard still loads and the owner can enter the secret again.
    """
    if not stored or not is_encrypted(stored):
        return stored or ""
    try:
        return fernet().decrypt(stored[len(PREFIX) :].encode()).decode()
    except InvalidToken:
        log.error("A stored secret could not be decrypted. Check ENCRYPTION_KEYS.")
        return ""


def new_key() -> str:
    """A fresh key for ENCRYPTION_KEYS."""
    return Fernet.generate_key().decode()
