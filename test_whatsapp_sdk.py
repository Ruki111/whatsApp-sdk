import asyncio

import httpx

from whatsapp_sdk import WhatsApp, WhatsAppError


async def main() -> None:
    seen: list[httpx.Request] = []

    def graph(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/bad"):
            return httpx.Response(400, json={"error": {"code": 100, "error_user_msg": "Nope"}})
        if request.url.path.endswith("/proxy"):
            return httpx.Response(200, json=["not", "an", "object"])
        if request.url.path.endswith("/media"):
            return httpx.Response(200, json={})
        return httpx.Response(200, json={"messages": [{"id": "wamid.1"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(graph)) as client:
        wa = WhatsApp("tok", waba_id="w1", phone_number_id="p1", graph_version="v99.0", client=client)

        await wa.send_template_message(to="1", name="hi", language="en", marketing_messages=True)
        sent = seen[-1]
        assert str(sent.url) == "https://graph.facebook.com/v99.0/p1/marketing_messages"
        assert sent.headers["authorization"] == "Bearer tok"
        assert b'"product_policy":"CLOUD_API_FALLBACK"' in sent.content

        await wa.send_template_message(to="1", name="hi", language="en", phone_number_id="p2")
        assert seen[-1].url.path == "/v99.0/p2/messages"

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

    print("ok")


if __name__ == "__main__":
    asyncio.run(main())
