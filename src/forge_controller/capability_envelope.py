from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field

from .capabilities import CapabilityDenied, CapabilityGrant

_MIN_HMAC_KEY_BYTES = 32


class CapabilityGrantEnvelope(BaseModel):
    """Worker-portable grant plus an issuer MAC; no signing key is serialized."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = 1
    key_id: str = Field(min_length=1, max_length=128)
    grant: CapabilityGrant
    mac_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def seal_grant(grant: CapabilityGrant, *, key_id: str, key: bytes) -> CapabilityGrantEnvelope:
    _validate_key(key)
    if not key_id:
        raise ValueError("key_id is required")
    mac = hmac.new(key, _canonical_payload(1, key_id, grant), hashlib.sha256).hexdigest()
    return CapabilityGrantEnvelope(version=1, key_id=key_id, grant=grant, mac_sha256=mac)


def open_grant(
    envelope: CapabilityGrantEnvelope,
    *,
    keyring: Mapping[str, bytes],
    revoked_grant_ids: set[str] | frozenset[str] = frozenset(),
) -> CapabilityGrant:
    if envelope.version != 1:
        raise CapabilityDenied("unsupported capability envelope version")
    key = keyring.get(envelope.key_id)
    if key is None:
        raise CapabilityDenied("unknown capability signing key")
    _validate_key(key)
    expected = hmac.new(
        key,
        _canonical_payload(envelope.version, envelope.key_id, envelope.grant),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, envelope.mac_sha256):
        raise CapabilityDenied("capability grant envelope failed authentication")
    if envelope.grant.grant_id in revoked_grant_ids:
        raise CapabilityDenied("capability grant is revoked")
    return envelope.grant


def _canonical_payload(version: int, key_id: str, grant: CapabilityGrant) -> bytes:
    payload = {
        "grant": grant.model_dump(mode="json"),
        "key_id": key_id,
        "version": version,
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _validate_key(key: bytes) -> None:
    if len(key) < _MIN_HMAC_KEY_BYTES:
        raise ValueError(f"capability signing keys must be at least {_MIN_HMAC_KEY_BYTES} bytes")
