"""通知服务配置。"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


@dataclass
class NotificationConfig:
    enabled: bool = False
    urls: list[str] = field(default_factory=list)
    min_level: str = "warning"
    dedup_seconds: float = 60.0
    rate_limit_seconds: float = 30.0
    queue_size: int = 100


def mask_notification_url(url: str) -> str:
    """Mask credentials and token-like query values without logging secrets."""
    if not isinstance(url, str) or not url.strip():
        return "***"
    try:
        parts = urlsplit(url.strip())
        if not parts.scheme:
            return "***"

        # 只替换 userinfo，保留 host/port/IPv6 方括号
        if parts.username is not None or parts.password is not None:
            hostname = parts.hostname or ""
            if ":" in hostname and not hostname.startswith("["):
                hostname = f"[{hostname}]"
            host_part = f"{hostname}:{parts.port}" if parts.port else hostname
            netloc = f"***:***@{host_part}"
        else:
            netloc = parts.netloc

        path = parts.path
        if parts.scheme in {"bark", "barks"} and path:
            segments = path.split("/")
            if len(segments) >= 2:
                segments[-1] = "***"
                path = "/".join(segments)

        query = []
        secret_names = {"token", "password", "pass", "key", "auth", "apikey", "api_key"}
        for key, value in parse_qsl(parts.query, keep_blank_values=True):
            query.append((key, "***" if key.lower() in secret_names else value))

        return urlunsplit((parts.scheme, netloc, path, urlencode(query), ""))
    except ValueError:
        return "***"


def merge_notification_urls(existing: list[str], submitted: list[str]) -> list[str]:
    """Keep full URLs when the UI posts their unchanged masked counterparts."""
    merged: list[str] = []
    for index, value in enumerate(submitted):
        if not isinstance(value, str) or not value.strip():
            continue
        value = value.strip()
        if index < len(existing) and value == mask_notification_url(existing[index]):
            merged.append(existing[index])
        else:
            merged.append(value)
    return merged


def mask_notification_urls(urls: list[str]) -> list[str]:
    return [mask_notification_url(url) for url in urls]