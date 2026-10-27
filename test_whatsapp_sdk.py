import asyncio
import hashlib
import hmac
import json

import httpx

from whatsapp_sdk import WhatsApp, WhatsAppError, verify_signature


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
        assert seen[-1].url.params["fields"] == (
            'template_analytics.start(1).end(2).granularity(DAILY).template_ids(["t1"])')

        assert await wa.download_media("m1") == b"bytes"
        assert seen[-1].headers["authorization"] == "Bearer tok"

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

    signature = "sha256=" + hmac.new(b"secret", b"{}", hashlib.sha256).hexdigest()
    assert verify_signature("secret", b"{}", signature)
    assert not verify_signature("secret", b"{}", "sha256=bad")
    assert not verify_signature("secret", b"{}", None)

    print("ok")


if __name__ == "__main__":
    asyncio.run(main())
