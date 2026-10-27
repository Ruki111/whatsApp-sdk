"""Checks for the requests Meta sends to your webhook."""

import hashlib
import hmac


def verify_signature(app_secret: str, body: bytes, signature_header: str | None) -> bool:
    """Check a webhook's `X-Hub-Signature-256` header against the raw request body."""
    # An empty secret would accept a signature anyone can compute.
    if not app_secret or not signature_header:
        return False
    expected = "sha256=" + hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    # Bytes: compare_digest raises TypeError on non-ASCII strings from the header.
    return hmac.compare_digest(expected.encode(), signature_header.encode())


def verify_challenge(params: dict, verify_token: str) -> str | None:
    """Webhook setup handshake: the `hub.challenge` to echo back, or None to reject (403)."""
    if not verify_token:
        return None
    token = str(params.get("hub.verify_token") or "")
    if params.get("hub.mode") == "subscribe" and hmac.compare_digest(
        token.encode(), verify_token.encode()
    ):
        return str(params.get("hub.challenge") or "")
    return None
