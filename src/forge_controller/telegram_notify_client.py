from __future__ import annotations

from pathlib import Path

import httpx

from .telegram_governance import MobileNotificationRequest, NotificationState


class TelegramNotificationClientError(RuntimeError):
    pass


class TelegramNotificationClient:
    """Brain-side client for the credentialed local Telegram notification boundary."""

    def __init__(
        self,
        *,
        socket_path: str | Path,
        transport_key: str,
        client: httpx.Client | None = None,
    ) -> None:
        if len(transport_key) < 32:
            raise ValueError("Telegram notification transport key must be at least 32 characters")
        self.socket_path = Path(socket_path)
        self.transport_key = transport_key
        self._owns_client = client is None
        self.client = client or httpx.Client(
            transport=httpx.HTTPTransport(uds=str(self.socket_path)),
            timeout=10.0,
        )

    def notify(self, payload: MobileNotificationRequest) -> NotificationState:
        try:
            response = self.client.post(
                "http://forge-telegram/v1/notify",
                headers={"Authorization": f"Bearer {self.transport_key}"},
                json=payload.model_dump(mode="json"),
            )
        except httpx.HTTPError as exc:
            raise TelegramNotificationClientError("Telegram notification transport failed") from exc
        if response.status_code >= 400:
            raise TelegramNotificationClientError(
                f"Telegram notification adapter rejected request with HTTP {response.status_code}"
            )
        try:
            return NotificationState.model_validate(response.json())
        except (ValueError, TypeError) as exc:
            raise TelegramNotificationClientError(
                "Telegram notification adapter returned an invalid response"
            ) from exc

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> TelegramNotificationClient:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
