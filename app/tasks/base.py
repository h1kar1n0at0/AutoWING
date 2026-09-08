"""
任务基类 — 所有自动化任务的公共接口
"""
from __future__ import annotations
import logging
import threading
from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional

logger = logging.getLogger("autowing.tasks")


class TaskState(Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class Task(ABC):
    """任务基类"""

    def __init__(self, name: str = "Task"):
        self.name = name
        self.state = TaskState.IDLE
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._on_log = None  # 日志回调

    def set_log_callback(self, callback):
        """设置日志回调 (UI 使用)"""
        self._on_log = callback

    def log(self, message: str, level: str = "info"):
        """输出日志"""
        if self._on_log:
            self._on_log(level, f"[{self.name}] {message}")
        else:
            getattr(logger, level, logger.info)(f"[{self.name}] {message}")

    @abstractmethod
    def execute(self):
        """任务主逻辑 — 子类实现"""
        ...

    def start(self):
        """在后台线程启动任务"""
        if self.state == TaskState.RUNNING:
            self.log("任务已在运行", "warning")
            return

        self._stop_event.clear()
        self.state = TaskState.RUNNING
        self._thread = threading.Thread(target=self._run_wrapper,
                                        name=self.name, daemon=True)
        self._thread.start()
        self.log("任务已启动")

    def _run_wrapper(self):
        try:
            self.execute()
        except Exception as e:
            self.log(f"任务异常: {e}", "error")
            self.state = TaskState.ERROR
            raise
        else:
            if not self._stop_event.is_set():
                self.state = TaskState.IDLE
                self.log("任务正常结束")

    def stop(self):
        """请求停止任务"""
        self._stop_event.set()
        self.state = TaskState.STOPPED
        self.log("任务已停止")

    @property
    def should_stop(self) -> bool:
        return self._stop_event.is_set()

    def wait(self, seconds: float):
        """可中断的等待"""
        if self._stop_event.wait(seconds):
            raise InterruptedError("任务被中断")
