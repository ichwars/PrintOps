"""Actual immediate delivery and digest outcome for one notification provider."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class NotificationDelivery:
    status: Literal["delivered", "failed", "skipped"]
    digest_queued: bool = False
