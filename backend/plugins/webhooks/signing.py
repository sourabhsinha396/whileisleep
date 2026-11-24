"""Signatures, both ways, as Standard Webhooks has them (https://www.standardwebhooks.com), so people
can check and make them with a library they already have."""

import base64
import binascii
import hashlib
import hmac
import re
import secrets
import time

PREFIX = "whsec_"
# A request older (or newer) than this is refused, so a captured one can't be replayed later.
TOLERANCE_SECONDS = 300


def new_secret() -> str:
    return PREFIX + base64.b64encode(secrets.token_bytes(32)).decode()


def signature(secret: str, id: str, timestamp: str, body: bytes) -> str:
    key = base64.b64decode(secret.removeprefix(PREFIX))
    digest = hmac.new(key, f"{id}.{timestamp}.".encode() + body, hashlib.sha256).digest()
    return "v1," + base64.b64encode(digest).decode()


def headers(secret: str, id: str, body: bytes) -> dict:
    timestamp = str(int(time.time()))
    return {
        "webhook-id": id,
        "webhook-timestamp": timestamp,
        "webhook-signature": signature(secret, id, timestamp, body),
    }


def is_genuine(secret: str, sent, body: bytes) -> bool:
    id, timestamp = sent.get("webhook-id", ""), sent.get("webhook-timestamp", "")
    if not id or not re.fullmatch(r"[0-9]{1,12}", timestamp):
        return False
    if abs(time.time() - int(timestamp)) > TOLERANCE_SECONDS:
        return False
    try:
        expected = signature(secret, id, timestamp, body).encode()
    except (ValueError, binascii.Error):
        return False
    # There may be several: "v1,aaa v1,bbb".
    return any(hmac.compare_digest(expected, one.encode()) for one in sent.get("webhook-signature", "").split())
