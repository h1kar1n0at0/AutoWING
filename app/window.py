"""
原生窗口 — 使用 pywebview 将 Flask UI 包裹为桌面窗口

这样用户看到的是原生 Windows 窗口，而非浏览器标签页。
打包成 EXE 后看起来就是一个完整的桌面应用。
"""
from __future__ import annotations
import logging
import threading
import time
from typing import Optional

logger = logging.getLogger("autowing.window")


class DesktopWindow:
    """pywebview 原生窗口管理器"""

    def __init__(self, url: str, title: str = "AutoWING",
                 width: int = 860, height: int = 600,
                 min_width: int = 580, min_height: int = 420,
                 resizable: bool = True):
        self.url = url
        self.title = title
        self.width = width
        self.height = height
        self.min_width = min_width
        self.min_height = min_height
        self.resizable = resizable
        self._window = None

    def _on_close(self):
        """窗口关闭时的回调 — 清理 CDP 后台线程"""
        logger.info("窗口正在关闭，清理资源...")
        try:
            from app.core import stop_bg_worker
            stop_bg_worker()
        except Exception as e:
            logger.debug(f"清理资源时出错: {e}")
        return True  # 允许窗口关闭

    def open(self):
        """打开原生窗口 (阻塞，直到窗口关闭)"""
        try:
            import webview
            
            # 创建窗口时绑定关闭回调
            self._window = webview.create_window(
                title=self.title,
                url=self.url,
                width=self.width,
                height=self.height,
                min_size=(self.min_width, self.min_height),
                resizable=self.resizable,
                text_select=True,
                on_top=False,
            )
            
            # 注册关闭事件
            self._window.events.closed += self._on_close
            
            webview.start(debug=False, http_server=False)
            
        except ImportError:
            logger.warning("pywebview 未安装，将在浏览器中打开")
            self._open_browser()
        except Exception as e:
            logger.error(f"WebView 启动失败: {e}")
            self._open_browser()

    def _open_browser(self):
        """回退: 在系统浏览器中打开"""
        import webbrowser
        webbrowser.open(self.url)
        logger.info(f"已在浏览器打开: {self.url}")

        # 保持进程存活
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass