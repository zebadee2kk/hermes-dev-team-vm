from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from forge_controller.assurance import DecisionRecord
from forge_controller.models import AuthorityLevel, DecisionAction, DecisionClassification
from forge_controller.telegram_governance import (
    CallbackCodec,
    MobileNotificationRequest,
    TelegramGovernanceError,
    TelegramGovernanceService,
    TelegramNotificationApp,
    TelegramStateStore,
)

OWNER_CHAT = 123456
OWNER_USER = 654321
CALLBACK_KEY = b"t" * 32
NOTIFY_KEY = "n" * 32


class FakeBot:
    def __init__(self) -> None:
        self.webhook_deleted = False
        self.messages: list[dict[str, object]] = []
        self.answers: list[tuple[str, str]] = []
        self.cleared: list[tuple[int, int]] = []
        self.updates: list[dict[str, object]] = []
        self.offsets: list[int] = []

    def delete_webhook(self) -> None:
        self.webhook_deleted = True

    def send_message(self, *, chat_id: int, text: str, reply_markup=None) -> int:
        message_id = len(self.messages) + 10
        self.messages.append(
            {
                "chat_id": chat_id,
                "text": text,
                "reply_markup": reply_markup,
                "message_id": message_id,
            }
        )
        return message_id

    def get_updates(self, *, offset: int, timeout: int = 50):
        self.offsets.append(offset)
        return list(self.updates)

    def answer_callback_query(self, callback_query_id: str, text: str) -> None:
        self.answers.append((callback_query_id, text))

    def clear_keyboard(self, *, chat_id: int, message_id: int) -> None:
        self.cleared.append((chat_id, message_id))


class FakeForge:
    def __init__(self, decisions: list[DecisionRecord]) -> None:
        self.decisions = {decision.decision_id: decision for decision in decisions}
        self.actions: list[tuple[str, DecisionAction]] = []

    def get_decision(self, decision_id: str) -> DecisionRecord | None:
        return self.decisions.get(decision_id)

    def apply_action(self, decision_id: str, action: DecisionAction) -> dict[str, object]:
        self.actions.append((decision_id, action))
        decision = self.decisions[decision_id]
        if action in {DecisionAction.YES, DecisionAction.NO}:
            self.decisions[decision_id] = decision.model_copy(
                update={"status": "RESOLVED", "owner_action": action}
            )
        return {"already_handled": False, "disposition": action.value.lower()}


def _decision(
    decision_id: str = "decision-123",
    *,
    authority: AuthorityLevel = AuthorityLevel.L2,
    defer_allowed: bool = True,
) -> DecisionRecord:
    return DecisionRecord(
        decision_id=decision_id,
        project_id="forge",
        task_id="task-1",
        question="CONFIDENTIAL full question that must never be sent to Telegram",
        recommendation="CONFIDENTIAL internal recommendation",
        authority=authority,
        classification=DecisionClassification(
            authority=authority,
            autonomous=False,
            defer_allowed=defer_allowed,
            score=0.8,
        ),
    )


def _service(tmp_path: Path, decisions: list[DecisionRecord]):
    bot = FakeBot()
    forge = FakeForge(decisions)
    store = TelegramStateStore(tmp_path / "telegram-state.json")
    codec = CallbackCodec(CALLBACK_KEY, owner_chat_id=OWNER_CHAT, owner_user_id=OWNER_USER)
    service = TelegramGovernanceService(
        bot=bot,
        forge=forge,
        state_store=store,
        codec=codec,
        owner_chat_id=OWNER_CHAT,
        owner_user_id=OWNER_USER,
        timezone="Europe/London",
        digest_hour=19,
    )
    return service, bot, forge, store, codec


def test_callback_is_short_authenticated_and_bound_to_owner() -> None:
    codec = CallbackCodec(CALLBACK_KEY, owner_chat_id=OWNER_CHAT, owner_user_id=OWNER_USER)
    value = codec.encode("x" * 128, DecisionAction.MORE_INFO)
    assert len(value.encode()) <= 64
    key, action = codec.decode(value)
    assert key == codec.decision_key("x" * 128)
    assert action is DecisionAction.MORE_INFO

    tampered = value[:-1] + ("A" if value[-1] != "A" else "B")
    with pytest.raises(TelegramGovernanceError, match="authentication"):
        codec.decode(tampered)

    other_owner = CallbackCodec(
        CALLBACK_KEY,
        owner_chat_id=OWNER_CHAT + 1,
        owner_user_id=OWNER_USER,
    )
    with pytest.raises(TelegramGovernanceError, match="authentication"):
        other_owner.decode(value)


def test_trusted_notify_api_requires_transport_auth_and_safe_summary(tmp_path: Path) -> None:
    decision = _decision()
    service, bot, _, _, _ = _service(tmp_path, [decision])
    client = TestClient(TelegramNotificationApp(service, transport_key=NOTIFY_KEY).app)

    payload = {
        "decision_id": decision.decision_id,
        "mobile_safe": True,
        "mobile_safe_summary": "Approve bounded architecture change; executable evidence is current.",
    }
    assert client.post("/v1/notify", json=payload).status_code == 401
    response = client.post(
        "/v1/notify",
        json=payload,
        headers={"Authorization": f"Bearer {NOTIFY_KEY}"},
    )
    assert response.status_code == 200
    assert len(bot.messages) == 1
    text = str(bot.messages[0]["text"])
    assert payload["mobile_safe_summary"] in text
    assert decision.question not in text
    assert decision.recommendation not in text

    invalid = client.post(
        "/v1/notify",
        json={"decision_id": "other", "mobile_safe": True},
        headers={"Authorization": f"Bearer {NOTIFY_KEY}"},
    )
    assert invalid.status_code == 422


def test_mobile_safe_gate_has_four_buttons_but_l3_omits_defer(tmp_path: Path) -> None:
    l2 = _decision("decision-l2")
    l3 = _decision("decision-l3", authority=AuthorityLevel.L3, defer_allowed=False)
    service, bot, _, _, _ = _service(tmp_path, [l2, l3])
    for decision in (l2, l3):
        service.register_notification(
            MobileNotificationRequest(
                decision_id=decision.decision_id,
                mobile_safe=True,
                mobile_safe_summary=f"Safe summary for {decision.decision_id}",
            )
        )

    l2_labels = [
        button["text"]
        for row in bot.messages[0]["reply_markup"]["inline_keyboard"]
        for button in row
    ]
    assert l2_labels == ["YES", "NO", "DEFER", "MORE INFO"]
    assert all(
        len(button["callback_data"].encode()) <= 64
        for row in bot.messages[0]["reply_markup"]["inline_keyboard"]
        for button in row
    )
    l3_labels = [
        button["text"]
        for row in bot.messages[1]["reply_markup"]["inline_keyboard"]
        for button in row
    ]
    assert l3_labels == ["YES", "NO", "MORE INFO"]


def test_restricted_gate_sends_no_content_and_no_buttons(tmp_path: Path) -> None:
    decision = _decision()
    service, bot, _, _, _ = _service(tmp_path, [decision])
    service.register_notification(
        MobileNotificationRequest(decision_id=decision.decision_id, mobile_safe=False)
    )
    message = bot.messages[0]
    assert message["reply_markup"] is None
    assert "withheld" in str(message["text"]).lower()
    assert decision.question not in str(message["text"])
    assert decision.recommendation not in str(message["text"])


def test_owner_callback_applies_action_and_persists_offset(tmp_path: Path) -> None:
    decision = _decision()
    service, bot, forge, store, codec = _service(tmp_path, [decision])
    notification = service.register_notification(
        MobileNotificationRequest(
            decision_id=decision.decision_id,
            mobile_safe=True,
            mobile_safe_summary="Safe owner summary.",
        )
    )
    bot.updates = [
        {
            "update_id": 42,
            "callback_query": {
                "id": "cb-1",
                "from": {"id": OWNER_USER},
                "data": codec.encode(decision.decision_id, DecisionAction.YES),
                "message": {
                    "message_id": notification.message_id,
                    "chat": {"id": OWNER_CHAT, "type": "private"},
                },
            },
        }
    ]
    assert service.poll_once(timeout=0) == 1
    assert forge.actions == [(decision.decision_id, DecisionAction.YES)]
    assert bot.answers == [("cb-1", "Approved")]
    assert bot.cleared == [(OWNER_CHAT, notification.message_id)]
    restored = store.load()
    assert restored.update_offset == 43
    assert restored.processed_callback_ids == ["cb-1"]


def test_wrong_owner_chat_or_tampered_callback_never_reaches_forge(tmp_path: Path) -> None:
    decision = _decision()
    service, bot, forge, _, codec = _service(tmp_path, [decision])
    notification = service.register_notification(
        MobileNotificationRequest(
            decision_id=decision.decision_id,
            mobile_safe=True,
            mobile_safe_summary="Safe owner summary.",
        )
    )
    valid = codec.encode(decision.decision_id, DecisionAction.NO)
    bad = valid[:-1] + ("A" if valid[-1] != "A" else "B")
    bot.updates = [
        {
            "update_id": 1,
            "callback_query": {
                "id": "wrong-user",
                "from": {"id": OWNER_USER + 1},
                "data": valid,
                "message": {
                    "message_id": notification.message_id,
                    "chat": {"id": OWNER_CHAT, "type": "private"},
                },
            },
        },
        {
            "update_id": 2,
            "callback_query": {
                "id": "wrong-chat",
                "from": {"id": OWNER_USER},
                "data": valid,
                "message": {
                    "message_id": notification.message_id,
                    "chat": {"id": OWNER_CHAT + 1, "type": "private"},
                },
            },
        },
        {
            "update_id": 3,
            "callback_query": {
                "id": "tampered",
                "from": {"id": OWNER_USER},
                "data": bad,
                "message": {
                    "message_id": notification.message_id,
                    "chat": {"id": OWNER_CHAT, "type": "private"},
                },
            },
        },
    ]
    assert service.poll_once(timeout=0) == 3
    assert forge.actions == []
    assert store.load().update_offset == 4


def test_defer_keeps_gate_open_and_daily_digest_resurfaces_only_safe_summary(
    tmp_path: Path,
) -> None:
    decision = _decision()
    service, bot, forge, store, codec = _service(tmp_path, [decision])
    notification = service.register_notification(
        MobileNotificationRequest(
            decision_id=decision.decision_id,
            mobile_safe=True,
            mobile_safe_summary="Safe deferred summary.",
        )
    )
    bot.updates = [
        {
            "update_id": 9,
            "callback_query": {
                "id": "cb-defer",
                "from": {"id": OWNER_USER},
                "data": codec.encode(decision.decision_id, DecisionAction.DEFER),
                "message": {
                    "message_id": notification.message_id,
                    "chat": {"id": OWNER_CHAT, "type": "private"},
                },
            },
        }
    ]
    service.poll_once(timeout=0)
    assert forge.actions == [(decision.decision_id, DecisionAction.DEFER)]
    assert bot.cleared == []

    service.maybe_send_daily_digest(
        datetime(2026, 8, 16, 19, 5, tzinfo=ZoneInfo("Europe/London"))
    )
    digest = str(bot.messages[-1]["text"])
    assert "1 open gate" in digest
    assert "Safe deferred summary." in digest
    assert decision.question not in digest
    assert store.load().last_digest_date == "2026-08-16"


def test_initialize_explicitly_switches_to_long_polling(tmp_path: Path) -> None:
    service, bot, _, _, _ = _service(tmp_path, [])
    service.initialize()
    assert bot.webhook_deleted is True
