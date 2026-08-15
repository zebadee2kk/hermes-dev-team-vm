from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256


def deterministic_jitter_seconds(key: str, max_seconds: float) -> float:
    """Stable jitter avoids restart-induced probe stampedes while remaining testable."""
    if max_seconds <= 0:
        return 0.0
    digest = sha256(key.encode("utf-8")).digest()
    fraction = int.from_bytes(digest[:8], "big") / ((1 << 64) - 1)
    return fraction * max_seconds


def probe_after_reset(
    deployment_id: str,
    retry_at: datetime,
    *,
    max_jitter_seconds: float = 30.0,
) -> datetime:
    """Schedule a probe at or after provider truth; never mutate the provider reset itself."""
    return retry_at + timedelta(
        seconds=deterministic_jitter_seconds(deployment_id, max_jitter_seconds)
    )


def exponential_probe_delay(
    deployment_id: str,
    attempt: int,
    *,
    base_seconds: float = 1.0,
    cap_seconds: float = 60.0,
    jitter_fraction: float = 0.25,
) -> timedelta:
    if attempt < 1:
        raise ValueError("attempt must be >= 1")
    raw = min(cap_seconds, base_seconds * (2 ** (attempt - 1)))
    jitter = deterministic_jitter_seconds(
        f"{deployment_id}:{attempt}", raw * max(0.0, jitter_fraction)
    )
    return timedelta(seconds=min(cap_seconds, raw + jitter))
