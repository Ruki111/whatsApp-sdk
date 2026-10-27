"""The client, and the Embedded Signup token exchange."""

import httpx

from ._base import GRAPH_URL
from .account import AccountAPI
from .business import BusinessAPI
from .errors import _error, _parse, _unreached
from .messages import MessagesAPI


class WhatsApp(MessagesAPI, AccountAPI, BusinessAPI):
    """One set of credentials. Pass a shared `client` to pool connections across many sends;
    without one, each call opens and closes its own.

    `waba_id` and `phone_number_id` are defaults; every method that uses one also accepts it
    as an argument."""


async def exchange_code(code: str, *, app_id: str, app_secret: str,
                        graph_version: str = "v26.0") -> str:
    """Embedded Signup: trade the code the popup returned for the customer's business token."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(
                f"{GRAPH_URL}/{graph_version}/oauth/access_token",
                params={"client_id": app_id, "client_secret": app_secret, "code": code},
            )
        except httpx.HTTPError as exc:
            raise _unreached(exc, "GET") from exc
    token = _parse(response).get("access_token")
    if not token:
        raise _error("Meta returned no access token")
    return token
