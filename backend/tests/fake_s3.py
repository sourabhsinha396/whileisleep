"""A customer's bucket in memory, behind real httpx. It checks every signature with its own
reading of AWS Signature Version 4, so signing is tested against something other than itself.
"""

import hashlib
import hmac
import re

import httpx

ENDPOINT = "https://account.r2.example.com"
PUBLIC = "https://files.example.com"
SETTINGS = {
    "endpoint_url": ENDPOINT,
    "bucket": "acme-uploads",
    "access_key_id": "AKIDEXAMPLE",
    "secret_access_key": "customer-secret",
    "public_base_url": PUBLIC,
}


def hmac256(key: bytes, text: str) -> bytes:
    return hmac.new(key, text.encode(), hashlib.sha256).digest()


def signature_ok(request: httpx.Request, secret: str) -> bool:
    match = re.fullmatch(
        r"AWS4-HMAC-SHA256 Credential=([^/]+)/(\d{8})/([^/]+)/s3/aws4_request, SignedHeaders=([^,]+), Signature=(\w+)",
        request.headers.get("Authorization", ""),
    )
    if not match:
        return False
    key_id, date, region, signed, signature = match.groups()
    body = request.read()
    if key_id != SETTINGS["access_key_id"] or "host" not in signed.split(";"):
        return False
    if request.headers["X-Amz-Content-SHA256"] != hashlib.sha256(body).hexdigest():
        return False
    canonical = "\n".join(
        [
            request.method,
            request.url.raw_path.decode().partition("?")[0],
            "",
            *[f"{name}:{request.headers[name].strip()}" for name in signed.split(";")],
            "",
            signed,
            request.headers["X-Amz-Content-SHA256"],
        ]
    )
    to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            request.headers["X-Amz-Date"],
            f"{date}/{region}/s3/aws4_request",
            hashlib.sha256(canonical.encode()).hexdigest(),
        ]
    )
    key = f"AWS4{secret}".encode()
    for part in (date, region, "s3", "aws4_request"):
        key = hmac256(key, part)
    return hmac.compare_digest(hmac256(key, to_sign).hex(), signature)


class FakeBucket:
    def __init__(self):
        self.secret = SETTINGS["secret_access_key"]
        self.files: dict[str, bytes] = {}
        self.headers: dict[str, dict] = {}
        self.requests: list[tuple[str, str]] = []
        # Methods to answer with a status, like a key without that permission.
        self.answers: dict[str, int] = {}
        self.public = True

    def handle(self, request: httpx.Request) -> httpx.Response:
        host, path = request.headers["Host"], request.url.path
        self.requests.append((request.method, f"https://{host}{path}"))
        if f"https://{host}" == PUBLIC:
            body = self.files.get(path.removeprefix("/")) if self.public else None
            return httpx.Response(404 if body is None else 200, content=body or b"not here")
        assert f"https://{host}" == ENDPOINT, f"unexpected host {host}"
        if not signature_ok(request, self.secret):
            return httpx.Response(403, content=b"<Error><Code>SignatureDoesNotMatch</Code></Error>")
        if request.method in self.answers:
            return httpx.Response(self.answers[request.method], content=b"<Error>internal details</Error>")
        bucket, _, name = path.removeprefix("/").partition("/")
        if bucket != SETTINGS["bucket"]:
            return httpx.Response(404)
        if request.method == "PUT":
            self.files[name] = request.read()
            self.headers[name] = dict(request.headers)
            return httpx.Response(200)
        assert request.method == "DELETE"
        self.files.pop(name, None)
        return httpx.Response(204)
