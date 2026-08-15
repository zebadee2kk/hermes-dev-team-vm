import json

import httpx

from forge_controller.telegram_governance import MobileNotificationRequest
from forge_controller.telegram_notify_client import TelegramNotificationClient


def test_notification_client_sends_only_typed_mobile_payload_and_transport_auth() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("authorization")
        seen["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "decision_id": "D1",
                "mobile_safe": True,
                "mobile_safe_summary": "Safe summary",
                "message_id": 77,
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        client = TelegramNotificationClient(
            socket_path="/run/forge-telegram/notify.sock",
            transport_key="k" * 32,
            client=http,
        )
        result = client.notify(
            MobileNotificationRequest(
                decision_id="D1",
                mobile_safe=True,
                mobile_safe_summary="Safe summary",
            )
        )

    assert seen["authorization"] == "Bearer " + "k" * 32
    assert seen["payload"] == {
        "decision_id": "D1",
        "mobile_safe": True,
        "mobile_safe_summary": "Safe summary",
    }
    assert result.message_id == 77
