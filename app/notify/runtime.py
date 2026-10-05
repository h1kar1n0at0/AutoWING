"""应用级通知服务生命周期。"""

from __future__ import annotations

import threading

from app.engine.config_models import config_manager
from app.notify.config import NotificationConfig
from app.notify.service import NotificationService

_lock = threading.Lock()
_service: NotificationService | None = None


def _current_config() -> NotificationConfig:
    config = config_manager.config
    return NotificationConfig(
        enabled=config.notifications_enabled,
        urls=list(config.notification_urls),
        min_level=config.notification_min_level,
        dedup_seconds=config.notification_dedup_seconds,
        rate_limit_seconds=config.notification_rate_limit_seconds,
        queue_size=config.notification_queue_size,
    )


def start_notification_service() -> NotificationService:
    global _service
    with _lock:
        if _service is None:
            _service = NotificationService(_current_config())
            _service.start()
        return _service


def get_notification_service() -> NotificationService:
    return start_notification_service()


def reload_notification_service() -> NotificationService:
    service = start_notification_service()
    service.reload(_current_config())
    return service


def stop_notification_service(timeout: float = 2.0) -> None:
    global _service
    with _lock:
        service = _service
        _service = None
    if service is not None:
        service.stop(timeout=timeout)