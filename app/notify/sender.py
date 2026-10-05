"""Apprise 发送适配器。"""

from __future__ import annotations

import logging

from app.notify.events import NotificationEvent

logger = logging.getLogger("autowing.notify.sender")


class NotificationSender:
    def send(self, event: NotificationEvent, urls: list[str]) -> None:
        import apprise

        app = apprise.Apprise()
        for url in urls:
            try:
                app.add(url)
            except Exception:
                logger.exception("通知 URL 解析失败: event=%s", event.event_type)

        if len(app) == 0:
            return
        app.notify(title=event.title, body=event.body)