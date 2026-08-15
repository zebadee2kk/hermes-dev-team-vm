from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import hmac
import json
import os
import stat
import threading
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .assurance import DecisionRecord, DecisionStatus
from .models import DecisionAction

_CALLBACK_VERSION = "1"
_CALLBACK_MAX_BYTES = 64
_CALLBACK_MAC_BYTES = 9
_STATE_VERSION = 1
_MAX_PROCESSED_CALLBACKS = 256
_ACTION_CODE = {
    DecisionAction.YES: "Y",
    DecisionAction.NO: "N",
    DecisionAction.DEFER: "D",
    DecisionAction.MORE_INFO: "M",
}
_CODE_ACTION = {value: key for key, value in _ACTION_CODE.items()}


class TelegramGovernanceError(RuntimeError):
    pass


class MobileNotificationRequest(BaseModel):
    """Trusted control-plane statement about what may safely leave Forge for Telegram."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_id: str = Field(min_length=1, max_length=128)
    mobile_safe: bool = False
    mobile_safe_summary: str | None = Field(default=None, max_length=600)

    @model_validator(mode="after")
    def require_summary_for_actionable_notification(self) -> MobileNotificationRequest:
        if self.mobile_safe and not (self.mobile_safe_summary or "").strip():
            raise ValueError("mobile_safe requires a non-empty mobile_safe_summary")
        if not self.mobile_safe and self.mobile_safe_summary is not None:
            raise ValueError("restricted notification must not include a mobile summary")
        return self


class NotificationState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: str
    mobile_safe: bool
    mobile_safe_summary: str | None = None
    message_id: int = Field(gt=0)


class TelegramState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = _STATE_VERSION
    update_offset: int = Field(default=0, ge=0)
    notifications: dict[str, NotificationState] = Field(default_factory=dict)
    processed_callback_ids: list[str] = Field(default_factory=list)
    last_digest_date: str | None = None


class TelegramStateStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> TelegramState:
        if not self.path.exists():
            return TelegramState()
        try:
            info = self.path.stat()
            if not stat.S_ISREG(info.st_mode):
                raise TelegramGovernanceError("Telegram state path must be a regular file")
            if info.st_mode & 0o077:
                raise TelegramGovernanceError("Telegram state file must not be group/world accessible")
            state = TelegramState.model_validate(json.loads(self.path.read_text()))
        except TelegramGovernanceError:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise TelegramGovernanceError("Telegram state file is invalid") from exc
        if state.version != _STATE_VERSION:
            raise TelegramGovernanceError("unsupported Telegram state version")
        return state

    def save(self, state: TelegramState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        data = state.model_dump_json(indent=2) + "\n"
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


class CallbackCodec:
    def __init__(self, key: bytes, *, owner_chat_id: int, owner_user_id: int) -> None:
        if len(key) < 32:
            raise ValueError("Telegram callback HMAC key must be at least 32 bytes")
        self.key = key
        self.owner_chat_id = owner_chat_id
        self.owner_user_id = owner_user_id

    @staticmethod
    def decision_key(decision_id: str) -> str:
        digest = hashlib.sha256(decision_id.encode("utf-8")).digest()[:12]
        return _b64url(digest)

    def encode(self, decision_id: str, action: DecisionAction) -> str:
        body = f"{_CALLBACK_VERSION}:{_ACTION_CODE[action]}:{self.decision_key(decision_id)}"
        mac = hmac.new(self.key, self._bound(body), hashlib.sha256).digest()[:_CALLBACK_MAC_BYTES]
        encoded = f"{body}:{_b64url(mac)}"
        if not 1 <= len(encoded.encode("utf-8")) <= _CALLBACK_MAX_BYTES:
            raise TelegramGovernanceError("Telegram callback data exceeds Bot API limit")
        return encoded

    def decode(self, value: str) -> tuple[str, DecisionAction]:
        if not 1 <= len(value.encode("utf-8")) <= _CALLBACK_MAX_BYTES:
            raise TelegramGovernanceError("invalid Telegram callback data length")
        parts = value.split(":")
        if len(parts) != 4 or parts[0] != _CALLBACK_VERSION or parts[1] not in _CODE_ACTION:
            raise TelegramGovernanceError("invalid Telegram callback data")
        body = ":".join(parts[:3])
        expected = hmac.new(self.key, self._bound(body), hashlib.sha256).digest()[:_CALLBACK_MAC_BYTES]
        try:
            supplied = _b64url_decode(parts[3])
        except ValueError as exc:
            raise TelegramGovernanceError("invalid Telegram callback signature") from exc
        if not hmac.compare_digest(expected, supplied):
            raise TelegramGovernanceError("Telegram callback failed authentication")
        return parts[2], _CODE_ACTION[parts[1]]

    def _bound(self, body: str) -> bytes:
        return f"{body}|{self.owner_chat_id}|{self.owner_user_id}".encode("utf-8")


class TelegramBotClient:
    def __init__(self, token: str, *, client: httpx.Client | None = None) -> None:
        if not token or ":" not in token:
            raise ValueError("Telegram bot token is invalid")
        self._base_url = f"https://api.telegram.org/bot{token}"
        self.client = client or httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0))

    def delete_webhook(self) -> None:
        self._call("deleteWebhook", {"drop_pending_updates": False})

    def get_updates(self, *, offset: int, timeout: int = 50) -> list[dict[str, object]]:
        result = self._call(
            "getUpdates",
            {
                "offset": offset,
                "timeout": timeout,
                "allowed_updates": ["callback_query"],
            },
        )
        if not isinstance(result, list) or not all(isinstance(item, dict) for item in result):
            raise TelegramGovernanceError("Telegram getUpdates returned an invalid result")
        return result

    def send_message(
        self,
        *,
        chat_id: int,
        text: str,
        reply_markup: dict[str, object] | None = None,
    ) -> int:
        payload: dict[str, object] = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        result = self._call("sendMessage", payload)
        if not isinstance(result, dict) or not isinstance(result.get("message_id"), int):
            raise TelegramGovernanceError("Telegram sendMessage returned no message id")
        return int(result["message_id"])

    def answer_callback_query(self, callback_query_id: str, text: str) -> None:
        self._call(
            "answerCallbackQuery",
            {"callback_query_id": callback_query_id, "text": text[:200]},
        )

    def clear_keyboard(self, *, chat_id: int, message_id: int) -> None:
        self._call(
            "editMessageReplyMarkup",
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "reply_markup": {"inline_keyboard": []},
            },
        )

    def _call(self, method: str, payload: dict[str, object]) -> object:
        try:
            response = self.client.post(f"{self._base_url}/{method}", json=payload)
        except httpx.HTTPError as exc:
            raise TelegramGovernanceError(f"Telegram {method} transport failed") from exc
        if response.status_code != 200:
            raise TelegramGovernanceError(f"Telegram {method} failed with HTTP {response.status_code}")
        try:
            body = response.json()
        except ValueError as exc:
            raise TelegramGovernanceError(f"Telegram {method} returned invalid JSON") from exc
        if not isinstance(body, dict) or body.get("ok") is not True:
            raise TelegramGovernanceError(f"Telegram {method} returned an unsuccessful result")
        return body.get("result")


class ForgeGovernanceClient:
    def __init__(
        self,
        base_url: str,
        control_key: str,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.control_key = control_key
        self.client = client or httpx.Client(timeout=15.0)

    def get_decision(self, decision_id: str) -> DecisionRecord | None:
        response = self._request(
            "GET",
            f"/v1/governance/decisions/{decision_id}",
            allow_not_found=True,
        )
        if response.status_code == 404:
            return None
        try:
            return DecisionRecord.model_validate(response.json())
        except (ValueError, TypeError) as exc:
            raise TelegramGovernanceError("Forge decision response is invalid") from exc

    def apply_action(self, decision_id: str, action: DecisionAction) -> dict[str, object]:
        response = self._request(
            "POST",
            f"/v1/governance/decisions/{decision_id}/owner-action",
            json={"action": action.value},
            allow_conflict=True,
        )
        if response.status_code == 409:
            return {"already_handled": True}
        try:
            payload = response.json()
        except ValueError as exc:
            raise TelegramGovernanceError("Forge owner action returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise TelegramGovernanceError("Forge owner action returned an invalid result")
        return payload

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, object] | None = None,
        allow_not_found: bool = False,
        allow_conflict: bool = False,
    ) -> httpx.Response:
        try:
            response = self.client.request(
                method,
                f"{self.base_url}{path}",
                headers={"Authorization": f"Bearer {self.control_key}"},
                json=json,
            )
        except httpx.HTTPError as exc:
            raise TelegramGovernanceError("Forge governance API transport failed") from exc
        if allow_not_found and response.status_code == 404:
            return response
        if allow_conflict and response.status_code == 409:
            return response
        if response.status_code >= 400:
            raise TelegramGovernanceError(
                f"Forge governance API failed with HTTP {response.status_code}"
            )
        return response


class TelegramGovernanceService:
    def __init__(
        self,
        *,
        bot: TelegramBotClient,
        forge: ForgeGovernanceClient,
        state_store: TelegramStateStore,
        codec: CallbackCodec,
        owner_chat_id: int,
        owner_user_id: int,
        timezone: str = "Europe/London",
        digest_hour: int = 19,
    ) -> None:
        if not 0 <= digest_hour <= 23:
            raise ValueError("digest_hour must be 0-23")
        self.bot = bot
        self.forge = forge
        self.state_store = state_store
        self.codec = codec
        self.owner_chat_id = owner_chat_id
        self.owner_user_id = owner_user_id
        self.timezone = ZoneInfo(timezone)
        self.digest_hour = digest_hour
        self.state = state_store.load()
        self._lock = threading.RLock()

    def initialize(self) -> None:
        self.bot.delete_webhook()

    def register_notification(self, payload: MobileNotificationRequest) -> NotificationState:
        with self._lock:
            existing = self.state.notifications.get(payload.decision_id)
            if existing is not None:
                if (
                    existing.mobile_safe != payload.mobile_safe
                    or existing.mobile_safe_summary != _clean_summary(payload.mobile_safe_summary)
                ):
                    raise TelegramGovernanceError(
                        "decision already has a different mobile-notification policy"
                    )
                return existing
            decision = self.forge.get_decision(payload.decision_id)
            if decision is None:
                raise TelegramGovernanceError("decision does not exist")
            if decision.status is not DecisionStatus.OPEN:
                raise TelegramGovernanceError("only open decisions can be notified")
            summary = _clean_summary(payload.mobile_safe_summary)
            if payload.mobile_safe:
                text = self._mobile_safe_text(decision, summary or "")
                reply_markup = {"inline_keyboard": self._keyboard(decision)}
            else:
                text = self._restricted_text(decision)
                reply_markup = None
            message_id = self.bot.send_message(
                chat_id=self.owner_chat_id,
                text=text,
                reply_markup=reply_markup,
            )
            notification = NotificationState(
                decision_id=decision.decision_id,
                mobile_safe=payload.mobile_safe,
                mobile_safe_summary=summary,
                message_id=message_id,
            )
            self.state.notifications[decision.decision_id] = notification
            self.state_store.save(self.state)
            return notification

    def maybe_send_daily_digest(self, now: datetime | None = None) -> None:
        current = (now or datetime.now(self.timezone)).astimezone(self.timezone)
        today = current.date().isoformat()
        with self._lock:
            if current.hour < self.digest_hour or self.state.last_digest_date == today:
                return
            open_notifications = self._open_notifications_and_prune()
            safe = [item for item in open_notifications if item.mobile_safe]
            restricted = len(open_notifications) - len(safe)
            lines = [f"Forge daily digest · {len(open_notifications)} open gate(s)"]
            for item in safe[:8]:
                decision = self.forge.get_decision(item.decision_id)
                if decision is None or decision.status is not DecisionStatus.OPEN:
                    continue
                summary = item.mobile_safe_summary or ""
                lines.append(
                    f"• {decision.authority.value} {self.codec.decision_key(item.decision_id)[:8]} · "
                    f"{summary[:160]}"
                )
            if len(safe) > 8:
                lines.append(f"• +{len(safe) - 8} more mobile-safe gate(s)")
            if restricted:
                lines.append(f"• {restricted} restricted gate(s) withheld from Telegram")
            if not open_notifications:
                lines.append("No owner decisions are waiting.")
            self.bot.send_message(chat_id=self.owner_chat_id, text="\n".join(lines))
            self.state.last_digest_date = today
            self.state_store.save(self.state)

    def poll_once(self, *, timeout: int = 50) -> int:
        updates = self.bot.get_updates(offset=self.state.update_offset, timeout=timeout)
        processed = 0
        for update in sorted(updates, key=lambda item: int(item.get("update_id", -1))):
            update_id = update.get("update_id")
            if not isinstance(update_id, int) or update_id < 0:
                continue
            self._handle_update(update)
            with self._lock:
                self.state.update_offset = max(self.state.update_offset, update_id + 1)
                self.state_store.save(self.state)
            processed += 1
        return processed

    def run_forever(self) -> None:
        self.initialize()
        while True:
            try:
                self.maybe_send_daily_digest()
                self.poll_once(timeout=50)
            except TelegramGovernanceError:
                time.sleep(5)

    def _keyboard(self, decision: DecisionRecord) -> list[list[dict[str, str]]]:
        actions = [DecisionAction.YES, DecisionAction.NO]
        if decision.classification is not None and decision.classification.defer_allowed:
            actions.append(DecisionAction.DEFER)
        actions.append(DecisionAction.MORE_INFO)
        labels = {
            DecisionAction.YES: "YES",
            DecisionAction.NO: "NO",
            DecisionAction.DEFER: "DEFER",
            DecisionAction.MORE_INFO: "MORE INFO",
        }
        first = [
            {"text": labels[action], "callback_data": self.codec.encode(decision.decision_id, action)}
            for action in actions[:2]
        ]
        second = [
            {"text": labels[action], "callback_data": self.codec.encode(decision.decision_id, action)}
            for action in actions[2:]
        ]
        return [row for row in (first, second) if row]

    def _handle_update(self, update: dict[str, object]) -> None:
        callback = update.get("callback_query")
        if not isinstance(callback, dict):
            return
        callback_id = callback.get("id")
        sender = callback.get("from")
        message = callback.get("message")
        data = callback.get("data")
        if not isinstance(callback_id, str):
            return
        with self._lock:
            if callback_id in self.state.processed_callback_ids:
                self.bot.answer_callback_query(callback_id, "Already processed")
                return
        if not isinstance(sender, dict) or sender.get("id") != self.owner_user_id:
            self.bot.answer_callback_query(callback_id, "Not authorised")
            self._mark_callback_processed(callback_id)
            return
        if not isinstance(message, dict) or not isinstance(message.get("chat"), dict):
            self.bot.answer_callback_query(callback_id, "Invalid message context")
            self._mark_callback_processed(callback_id)
            return
        chat = message["chat"]
        if chat.get("id") != self.owner_chat_id or chat.get("type") != "private":
            self.bot.answer_callback_query(callback_id, "Not authorised")
            self._mark_callback_processed(callback_id)
            return
        if not isinstance(data, str):
            self.bot.answer_callback_query(callback_id, "Invalid action")
            self._mark_callback_processed(callback_id)
            return
        try:
            key, action = self.codec.decode(data)
        except TelegramGovernanceError:
            self.bot.answer_callback_query(callback_id, "Invalid or expired action")
            self._mark_callback_processed(callback_id)
            return
        with self._lock:
            matches = [
                item
                for item in self.state.notifications.values()
                if self.codec.decision_key(item.decision_id) == key
            ]
        if len(matches) != 1:
            self.bot.answer_callback_query(callback_id, "Decision is no longer available")
            self._mark_callback_processed(callback_id)
            return
        notification = matches[0]
        if not notification.mobile_safe:
            self.bot.answer_callback_query(callback_id, "This decision cannot be actioned in Telegram")
            self._mark_callback_processed(callback_id)
            return
        decision = self.forge.get_decision(notification.decision_id)
        if decision is None or decision.status is not DecisionStatus.OPEN:
            self.bot.answer_callback_query(callback_id, "Decision is no longer open")
            self._mark_callback_processed(callback_id)
            return
        if action is DecisionAction.DEFER and (
            decision.classification is None or not decision.classification.defer_allowed
        ):
            self.bot.answer_callback_query(callback_id, "DEFER is not allowed for this gate")
            self._mark_callback_processed(callback_id)
            return
        result = self.forge.apply_action(decision.decision_id, action)
        if result.get("already_handled") is True:
            self.bot.answer_callback_query(callback_id, "Already handled")
        else:
            status_text = {
                DecisionAction.YES: "Approved",
                DecisionAction.NO: "Rejected",
                DecisionAction.DEFER: "Deferred",
                DecisionAction.MORE_INFO: "More information requested",
            }[action]
            self.bot.answer_callback_query(callback_id, status_text)
        if action in {DecisionAction.YES, DecisionAction.NO} or result.get("already_handled") is True:
            message_id = message.get("message_id")
            if isinstance(message_id, int):
                self.bot.clear_keyboard(chat_id=self.owner_chat_id, message_id=message_id)
        self._mark_callback_processed(callback_id)

    def _mark_callback_processed(self, callback_id: str) -> None:
        with self._lock:
            values = [*self.state.processed_callback_ids, callback_id]
            self.state.processed_callback_ids = values[-_MAX_PROCESSED_CALLBACKS:]

    def _open_notifications_and_prune(self) -> list[NotificationState]:
        open_items: list[NotificationState] = []
        changed = False
        for decision_id, item in list(self.state.notifications.items()):
            decision = self.forge.get_decision(decision_id)
            if decision is None or decision.status is not DecisionStatus.OPEN:
                self.state.notifications.pop(decision_id, None)
                changed = True
            else:
                open_items.append(item)
        if changed:
            self.state_store.save(self.state)
        return open_items

    def _mobile_safe_text(self, decision: DecisionRecord, summary: str) -> str:
        key = self.codec.decision_key(decision.decision_id)[:8]
        return f"Forge gate · {decision.authority.value} · {key}\n{summary}\n\nChoose one:"

    def _restricted_text(self, decision: DecisionRecord) -> str:
        key = self.codec.decision_key(decision.decision_id)[:8]
        return (
            f"Forge gate · {decision.authority.value} · {key}\n"
            "Details withheld from Telegram by policy. Review this gate in a trusted Forge interface."
        )


class TelegramNotificationApp:
    def __init__(self, service: TelegramGovernanceService, *, transport_key: str) -> None:
        if len(transport_key) < 32:
            raise ValueError("Telegram notification transport key must be at least 32 characters")
        self.service = service
        self.transport_key = transport_key
        self.app = FastAPI(title="Forge Telegram Notification Adapter", version="0.1.0")
        self.app.add_api_route("/healthz", self.healthz, methods=["GET"])
        self.app.add_api_route(
            "/v1/notify",
            self.notify,
            methods=["POST"],
            response_model=NotificationState,
        )

    def healthz(self) -> dict[str, str]:
        return {"status": "ok"}

    def notify(self, payload: MobileNotificationRequest, request: Request) -> NotificationState:
        authorization = request.headers.get("authorization", "")
        prefix = "Bearer "
        supplied = authorization[len(prefix) :] if authorization.startswith(prefix) else ""
        if not supplied or not hmac.compare_digest(supplied, self.transport_key):
            raise HTTPException(status_code=401, detail="invalid Telegram notification credential")
        try:
            return self.service.register_notification(payload)
        except TelegramGovernanceError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="forge-telegram-governance")
    parser.add_argument("--once", action="store_true", help="poll/digest once then exit")
    return parser


def build_production_service() -> tuple[TelegramGovernanceService, str, Path]:
    credentials_dir = os.environ.get("CREDENTIALS_DIRECTORY")
    if not credentials_dir:
        raise RuntimeError("CREDENTIALS_DIRECTORY is required; use systemd LoadCredential")
    credentials = Path(credentials_dir)
    token = _read_secret(credentials / "telegram-bot-token", min_length=20)
    control_key = _read_secret(credentials / "forge-control-key", min_length=32)
    callback_key = _read_hex_secret(credentials / "telegram-callback-hmac-key", min_bytes=32)
    notify_key = _read_secret(credentials / "telegram-notify-api-key", min_length=32)
    owner_chat_id = int(_required_env("FORGE_TELEGRAM_OWNER_CHAT_ID"))
    owner_user_id = int(_required_env("FORGE_TELEGRAM_OWNER_USER_ID"))
    state_file = Path(
        os.environ.get("FORGE_TELEGRAM_STATE_FILE", "/var/lib/forge-telegram/state.json")
    )
    socket_path = Path(
        os.environ.get("FORGE_TELEGRAM_NOTIFY_SOCKET", "/run/forge-telegram/notify.sock")
    )
    timezone = os.environ.get("FORGE_TELEGRAM_TIMEZONE", "Europe/London")
    digest_hour = int(os.environ.get("FORGE_TELEGRAM_DIGEST_HOUR", "19"))
    base_url = os.environ.get("FORGE_TELEGRAM_GOVERNANCE_URL", "http://127.0.0.1:8080")
    service = TelegramGovernanceService(
        bot=TelegramBotClient(token),
        forge=ForgeGovernanceClient(base_url, control_key),
        state_store=TelegramStateStore(state_file),
        codec=CallbackCodec(
            callback_key,
            owner_chat_id=owner_chat_id,
            owner_user_id=owner_user_id,
        ),
        owner_chat_id=owner_chat_id,
        owner_user_id=owner_user_id,
        timezone=timezone,
        digest_hour=digest_hour,
    )
    return service, notify_key, socket_path


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    service, notify_key, socket_path = build_production_service()
    service.initialize()
    if args.once:
        service.maybe_send_daily_digest()
        service.poll_once(timeout=0)
        return 0
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    app = TelegramNotificationApp(service, transport_key=notify_key).app
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            uds=str(socket_path),
            access_log=False,
            server_header=False,
            date_header=False,
            log_level="warning",
        )
    )
    thread = threading.Thread(target=server.run, name="telegram-notify-uds", daemon=True)
    thread.start()
    service.run_forever()
    return 0


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _read_secret(path: Path, *, min_length: int) -> str:
    _validate_secret(path)
    value = path.read_text().strip()
    if len(value) < min_length:
        raise RuntimeError(f"credential {path.name} is too short")
    return value


def _read_hex_secret(path: Path, *, min_bytes: int) -> bytes:
    _validate_secret(path)
    try:
        value = bytes.fromhex(path.read_text().strip())
    except ValueError as exc:
        raise RuntimeError(f"credential {path.name} must contain hexadecimal bytes") from exc
    if len(value) < min_bytes:
        raise RuntimeError(f"credential {path.name} must contain at least {min_bytes} bytes")
    return value


def _validate_secret(path: Path) -> None:
    try:
        info = path.stat()
    except FileNotFoundError as exc:
        raise RuntimeError(f"required systemd credential is missing: {path.name}") from exc
    if not stat.S_ISREG(info.st_mode):
        raise RuntimeError(f"systemd credential must be a regular file: {path.name}")
    if info.st_uid not in {0, os.geteuid()}:
        raise RuntimeError(f"systemd credential has an unexpected owner: {path.name}")
    if info.st_mode & 0o077:
        raise RuntimeError(f"systemd credential must not be group/world accessible: {path.name}")


def _clean_summary(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(value.split())


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * ((4 - len(value) % 4) % 4)
    try:
        return base64.b64decode(value + padding, altchars=b"-_", validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("invalid base64url") from exc


if __name__ == "__main__":
    raise SystemExit(main())
