import asyncio
import hashlib
import hmac
import json

import httpx

from whatsapp_sdk import WhatsApp, WhatsAppError, verify_challenge, verify_signature


async def main() -> None:
    seen: list[httpx.Request] = []

    def graph(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        if path.endswith("/bad"):
            return httpx.Response(400, json={"error": {"code": 100, "error_user_msg": "Nope"}})
        if path.endswith("/proxy"):
            return httpx.Response(200, json=["not", "an", "object"])
        if path.endswith("/media"):
            return httpx.Response(200, json={})
        if path.endswith("/m1"):
            return httpx.Response(200, json={"url": "https://lookaside.fbsbx.com/file"})
        if request.url.host == "lookaside.fbsbx.com":
            return httpx.Response(200, content=b"bytes")
        if path.endswith("/debug_token"):
            return httpx.Response(200, json={"data": {"app_id": "app1"}})
        if path.endswith("/uploads"):
            return httpx.Response(200, json={"id": "upload:1"})
        if path.endswith("/upload:1"):
            return httpx.Response(200, json={"h": "handle"})
        return httpx.Response(200, json={"success": True})

    def body() -> dict:
        return json.loads(seen[-1].content)

    async with httpx.AsyncClient(transport=httpx.MockTransport(graph)) as client:
        wa = WhatsApp("tok", waba_id="w1", phone_number_id="p1", graph_version="v99.0", client=client)

        await wa.send_template_message(to="1", name="hi", language="en", marketing_messages=True)
        assert str(seen[-1].url) == "https://graph.facebook.com/v99.0/p1/marketing_messages"
        assert seen[-1].headers["authorization"] == "Bearer tok"
        assert body()["product_policy"] == "CLOUD_API_FALLBACK"

        await wa.send_template_message(to="1", name="hi", language="en", phone_number_id="p2")
        assert seen[-1].url.path == "/v99.0/p2/messages"

        await wa.send_text("1", "yo", reply_to="wamid.0")
        assert body()["text"] == {"body": "yo", "preview_url": False}
        assert body()["context"] == {"message_id": "wamid.0"}

        await wa.send_media("1", "image", link="https://x/y.jpg")
        assert body()["image"] == {"link": "https://x/y.jpg"}

        await wa.mark_message_read("wamid.1", typing=True)
        assert body()["typing_indicator"] == {"type": "text"}

        # Graph wants arrays in the query string as JSON, and unset values left out.
        await wa.delete_message_template(hsm_ids=["1", "2"])
        assert seen[-1].url.params["hsm_ids"] == '["1", "2"]' and "name" not in seen[-1].url.params

        await wa.block_users(["15551234567"])
        assert seen[-1].method == "POST" and body()["block_users"] == [{"user": "15551234567"}]

        await wa.get_analytics("template_analytics", start=1, end=2, granularity="DAILY",
                               template_ids=["t1"])
        assert seen[-1].url.path == "/v99.0/w1/template_analytics"
        assert seen[-1].url.params["template_ids"] == '["t1"]'

        await wa.get_analytics("pricing_analytics", start=1, end=2, granularity="DAILY",
                               dimensions=["COUNTRY"])
        assert seen[-1].url.params["fields"] == (
            'pricing_analytics.start(1).end(2).granularity(DAILY).dimensions(["COUNTRY"])')

        assert await wa.download_media("m1") == b"bytes"
        assert seen[-1].headers["authorization"] == "Bearer tok"

        # The token never leaves Meta's hosts, and oversized files stop mid-stream.
        for url in ("https://evil.example/f", "http://lookaside.fbsbx.com/f",
                    "https://lookaside.fbsbx.com:8443/f", "https://evilfbsbx.com/f"):
            count = len(seen)
            try:
                [c async for c in wa.iter_media(url)]
            except WhatsAppError as error:
                assert "Untrusted" in error.message and len(seen) == count
            else:
                raise AssertionError(f"{url} was fetched")
        try:
            await wa.download_media("m1", max_bytes=3)
        except WhatsAppError as error:
            assert "size limit" in error.message
        else:
            raise AssertionError("max_bytes not enforced")

        await wa.list_catalog_products("c1", fields="name", limit=100, filter={"name": {"i_contains": "x"}})
        assert seen[-1].url.path == "/v99.0/c1/products"
        assert json.loads(seen[-1].url.params["filter"]) == {"name": {"i_contains": "x"}}
        await wa.list_flows(fields="id,name", limit=100)
        assert seen[-1].url.params["limit"] == "100"

        assert await wa.upload_template_sample(file_name="a.png", file_type="image/png", content=b"x") == "handle"
        assert seen[-1].headers["authorization"] == "OAuth tok"

        await wa.subscribe_app_to_waba()
        assert seen[-1].content == b""

        try:
            await wa.request("GET", "bad")
        except WhatsAppError as error:
            assert (error.status_code, error.code, error.message) == (400, 100, "Nope")
        else:
            raise AssertionError("4xx did not raise")

        assert await wa.request("GET", "proxy") == {}

        try:
            await wa.upload_message_media(file_name="a.jpg", file_type="image/jpeg", content=b"x")
        except WhatsAppError as error:
            assert error.status_code == 502
        else:
            raise AssertionError("missing media id did not raise")


        # BSUIDs go in `recipient`, groups keep `to` with recipient_type=group.
        await wa.send_text("US.13491208655302741918", "hi")
        assert body()["recipient"] == "US.13491208655302741918" and "to" not in body()
        await wa.send("g1", "text", {"body": "all"}, recipient_type="group")
        assert body()["to"] == "g1" and body()["recipient_type"] == "group"

        pages = iter([
            {"data": [{"id": 1}], "paging": {"cursors": {"after": "c1"}, "next": "https://n"}},
            {"data": [{"id": 2}], "paging": {"cursors": {"after": "c2"}}},
        ])
        paged = WhatsApp("tok", client=httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: seen.append(request) or httpx.Response(200, json=next(pages)))))
        assert [item["id"] async for item in paged.paginate("w1/flows", limit=1)] == [1, 2]
        assert seen[-1].url.params["after"] == "c1"

        signed = WhatsApp("tok", client=client, app_secret="s3")
        await signed.get_phone_number("p1")
        proof = hmac.new(b"s3", b"tok", hashlib.sha256).hexdigest()
        assert seen[-1].url.params["appsecret_proof"] == proof
        await wa.get_phone_number("p1")
        assert "appsecret_proof" not in seen[-1].url.params

    # Retry classification: what a queue worker needs to decide resend vs give up.
    def failing(exc: Exception):
        def handler(request: httpx.Request) -> httpx.Response:
            raise exc
        return WhatsApp("tok", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    async def error_of(wa: WhatsApp, method: str = "POST") -> WhatsAppError:
        try:
            await wa.request(method, "p1/messages")
        except WhatsAppError as error:
            return error
        raise AssertionError("no error")

    never_sent = await error_of(failing(httpx.ConnectError("refused")))
    assert never_sent.retryable and not never_sent.maybe_sent
    lost = await error_of(failing(httpx.ReadTimeout("slow")))
    assert not lost.retryable and lost.maybe_sent
    assert (await error_of(failing(httpx.ReadTimeout("slow")), "GET")).retryable

    def status(code: int, error: dict):
        return WhatsApp("tok", client=httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(code, json={"error": error}))))

    assert (await error_of(status(429, {}))).retryable
    assert (await error_of(status(503, {}))).retryable
    assert (await error_of(status(400, {"code": 130429}))).retryable
    assert (await error_of(status(400, {"code": 100, "is_transient": True}))).retryable
    assert not (await error_of(status(400, {"code": 131026}))).retryable

    assert verify_challenge({"hub.mode": "subscribe", "hub.verify_token": "v", "hub.challenge": "42"}, "v") == "42"
    assert verify_challenge({"hub.mode": "subscribe", "hub.verify_token": "x", "hub.challenge": "42"}, "v") is None

    redirecting = WhatsApp("tok", client=httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(302, headers={"location": "https://evil.example/"}))))
    try:
        [c async for c in redirecting.iter_media("https://lookaside.fbsbx.com/f")]
    except WhatsAppError as error:
        assert "redirect" in error.message
    else:
        raise AssertionError("redirect followed")

    signature = "sha256=" + hmac.new(b"secret", b"{}", hashlib.sha256).hexdigest()
    assert verify_signature("secret", b"{}", signature)
    assert not verify_signature("secret", b"{}", "sha256=bad")
    assert not verify_signature("secret", b"{}", None)

    print("ok")


if __name__ == "__main__":
    asyncio.run(main())
