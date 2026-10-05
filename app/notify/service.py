"""异步通知服务。"""

from __future__ import annotations

import logging
import queue
import threading
from dataclasses import replace

from app.notify.config import NotificationConfig
from app.notify.events import NotificationEvent
from app.notify.policy import NotificationPolicy
from app.notify.sender import NotificationSender

logger = logging.getLogger("autowing.notify.service")
_STOP = object()


class NotificationService:
    def __init__(
        self,
        config: NotificationConfig,
        sender: NotificationSender | None = None,
    ) -> None:
        self._config = replace(config, urls=list(config.urls))
        self._sender = sender or NotificationSender()
        self._policy = self._make_policy(self._config)
        self._queue: queue.Queue[object] = queue.Queue(maxsize=max(1, self._config.queue_size))
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stopping = False
        self.worker_exception: BaseException | None = None

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stopping = False
            self._thread = threading.Thread(
                target=self._run,
                daemon=True,
                name="NotificationWorker",
            )
            self._thread.start()

    def publish(self, event: NotificationEvent) -> bool:
        with self._lock:
            if self._stopping or not self._config.enabled or not self._config.urls:
                return False
            if not self._policy.should_enqueue(event):
                return False
            urls = list(self._config.urls)
        try:
            self._queue.put_nowait((event, urls))
            return True
        except queue.Full:
            logger.warning("通知队列已满，丢弃事件: event=%s", event.event_type)
            return False

    def reload(self, config: NotificationConfig) -> None:
        with self._lock:
            self._config = replace(config, urls=list(config.urls))
            self._policy = self._make_policy(self._config)

    def stop(self, timeout: float = 2.0) -> None:
        with self._lock:
            thread = self._thread
            self._stopping = True
        if thread and thread.is_alive():
            try:
                self._queue.put(_STOP, timeout=max(0.0, timeout))
            except queue.Full:
                logger.warning("通知队列停止信号未入队")
            thread.join(timeout=max(0.0, timeout))
        with self._lock:
            self._thread = None

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is _STOP:
                    return
                event, urls = item
                try:
                    self._sender.send(event, urls)
                except Exception:
                    logger.exception("通知发送失败: event=%s", event.event_type)
            finally:
                self._queue.task_done()

    @staticmethod
    def _make_policy(config: NotificationConfig) -> NotificationPolicy:
        return NotificationPolicy(
            min_level=config.min_level,
            dedup_seconds=config.dedup_seconds,
            rate_limit_seconds=config.rate_limit_seconds,
        )


# Keep the configuration type available from the service module for callers.
__all__ = ["NotificationConfig", "NotificationService"]