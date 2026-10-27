"""Errors raised by the client, and how to tell whether a request is safe to resend."""

import httpx

# Meta error codes that clear up on their own (outage, rate and throughput limits, template
# still syncing); see https://developers.facebook.com/documentation/business-messaging/whatsapp/support/error-codes
RETRYABLE_CODES = frozenset({2, 4, 80007, 130429, 131000, 131016, 131056, 133004, 134101})


class WhatsAppError(Exception):
    """A non-2xx response, a 200 carrying an `error` object, or no response at all.

    `retryable`: sending the same request again is safe and may succeed (connection never
    made, 429, 5xx except a write's gateway error, or a transient Meta code). `maybe_sent`: the request went out but no
    answer came back, so a message may have been delivered; don't resend it blindly."""

    def __init__(self, status_code: int, payload: dict | None, *, retryable: bool | None = None,
                 maybe_sent: bool = False) -> None:
        self.status_code = status_code
        self.payload = payload or {}
        error = self.payload.get("error", {})
        self.code = error.get("code")
        if retryable is None:
            retryable = (status_code == 429 or status_code >= 500
                         or error.get("is_transient") is True or self.code in RETRYABLE_CODES)
        self.retryable = retryable
        self.maybe_sent = maybe_sent
        self.subcode = error.get("error_subcode")
        self.title = error.get("error_user_title")
        # error_user_msg is the human-readable one ("Variables can't be at the
        # start or end of the template."); `message` is the generic fallback.
        self.message = (
            error.get("error_user_msg")
            or error.get("message")
            or "WhatsApp Cloud API request failed"
        )
        super().__init__(self.message)

    @property
    def detail(self) -> dict:
        return {
            "message": self.message,
            "title": self.title,
            "code": self.code,
            "subcode": self.subcode,
            "retryable": self.retryable,
        }


def _error(message: str) -> WhatsAppError:
    return WhatsAppError(502, {"error": {"message": message}}, retryable=False)


def _unreached(exc: httpx.HTTPError, method: str) -> WhatsAppError:
    message = f"Could not reach the Graph API: {exc}"
    # PoolTimeout: no connection was free, so nothing was sent.
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)):
        return WhatsAppError(502, {"error": {"message": message}}, retryable=True)
    # The request may have reached Meta: only reads are safe to repeat.
    return WhatsAppError(502, {"error": {"message": message}}, retryable=method == "GET",
                         maybe_sent=method != "GET")


def _parse(response: httpx.Response, method: str = "GET") -> dict:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    # Non-object bodies (e.g. from a proxy) count as empty so they can't escape WhatsAppError.
    if not isinstance(payload, dict):
        payload = {}
    if method != "GET" and response.status_code in (502, 503, 504):
        # A gateway error can arrive after Meta already acted on the request.
        raise WhatsAppError(response.status_code, payload, retryable=False, maybe_sent=True)
    if response.status_code >= 400 or "error" in payload:
        raise WhatsAppError(response.status_code, payload)
    return payload
