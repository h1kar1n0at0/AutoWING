"""通知事件领域模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


class NotificationLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class NotificationEvent:
    event_type: str
    level: NotificationLevel
    title: str
    body: str
    dedup_key: str
    bypass_level_filter: bool = False
    metadata: Mapping[str, str] = field(default_factory=dict)