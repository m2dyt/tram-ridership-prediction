import base64
import hmac
import json
from datetime import UTC, datetime

from tram.application.errors import ApplicationError


class SystemClock:
    def now(self):
        return datetime.now(UTC)


class SignedCursor:
    def __init__(self, secret: str):
        if len(secret) < 32:
            raise ValueError("Cursor secret is too short")
        self.secret = secret.encode()

    def encode(self, payload):
        data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        signature = hmac.digest(self.secret, data, "sha256")
        return base64.urlsafe_b64encode(signature + data).decode().rstrip("=")

    def decode(self, token):
        try:
            if len(token) > 4096:
                raise ValueError("Oversized cursor")
            raw = base64.b64decode(token + "=" * (-len(token) % 4), altchars=b"-_", validate=True)
            signature, data = raw[:32], raw[32:]
            if not hmac.compare_digest(signature, hmac.digest(self.secret, data, "sha256")):
                raise ValueError("Signature mismatch")
            payload = json.loads(data)
            if (
                set(payload) != {"fingerprint", "offset", "before", "expires_at"}
                or type(payload["offset"]) is not int
                or payload["offset"] < 0
            ):
                raise ValueError("Invalid payload")
            return payload
        except (ValueError, TypeError, KeyError, UnicodeDecodeError) as exc:
            raise ApplicationError("INVALID_CURSOR", "Invalid pagination cursor") from exc
