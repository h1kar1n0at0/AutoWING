"""
日志捕获 + SSE (Server-Sent Events) 实时推送 + 文件持久化
"""
from __future__ import annotations
import logging
import os
import queue
import time
from datetime import datetime
from pathlib import Path

# 日志目录
LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"


class LogHandler(logging.Handler):
    """捕获日志: SSE 队列 + 文件持久化"""

    def __init__(self, level=logging.INFO):
        super().__init__(level)
        self._queue: queue.Queue = queue.Queue(maxsize=1000)

        # ── 文件日志 ──
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now().strftime("%Y%m%d")
        self._log_file = LOG_DIR / f"autowing_{date_str}.log"
        self._file = open(self._log_file, "a", encoding="utf-8")
        self._file.write(
            f"\n{'='*60}\n"
            f"AutoWING 启动 @ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"{'='*60}\n"
        )
        self._file.flush()

        # 自动清理 30 天前的旧日志
        self._clean_old_logs()

    def _clean_old_logs(self, days=30):
        """删除过期日志文件"""
        cutoff = time.time() - days * 86400
        for f in LOG_DIR.glob("autowing_*.log"):
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
            except OSError:
                pass

    def emit(self, record):
        ts = time.strftime("%H:%M:%S")
        msg = self.format(record)
        entry = {
            "time": ts,
            "level": record.levelname.lower(),
            "message": msg,
        }

        # 写文件
        try:
            self._file.write(
                f"[{ts}] {record.levelname:<7} {msg}\n"
            )
            self._file.flush()
        except OSError:
            pass

        # 入 SSE 队列
        try:
            self._queue.put_nowait(entry)
        except queue.Full:
            try:
                self._queue.get_nowait()
                self._queue.put_nowait({
                    "time": time.strftime("%H:%M:%S"),
                    "level": "warning",
                    "message": "... (日志队列满，丢弃历史) ...",
                })
            except queue.Empty:
                pass

    def get_all(self):
        items = []
        while not self._queue.empty():
            try:
                items.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return items

    def add_log(self, level: str, message: str):
        """从非 logging 路径添加日志（如任务回调）"""
        entry = {
            "time": time.strftime("%H:%M:%S"),
            "level": level,
            "message": message,
        }
        try:
            self._file.write(f"[{entry['time']}] {level.upper():<7} {message}\n")
            self._file.flush()
        except OSError:
            pass
        try:
            self._queue.put_nowait(entry)
        except queue.Full:
            pass

    def close(self):
        try:
            self._file.close()
        except OSError:
            pass
        super().close()


# 全局日志处理器
_log_handler = LogHandler()
_log_handler.setFormatter(logging.Formatter("%(message)s"))

# 只添加到 root logger，让所有日志从这里输出（只输出一次）
_root_logger = logging.getLogger()
_root_logger.addHandler(_log_handler)
_root_logger.setLevel(logging.DEBUG)



def get_log_handler() -> LogHandler:
    return _log_handler


def get_log_dir() -> Path:
    return LOG_DIR