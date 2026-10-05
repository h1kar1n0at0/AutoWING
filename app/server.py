"""
Flask 服务器 — 提供 API 和 UI 页面
"""
from __future__ import annotations
import logging
import threading
from pathlib import Path
from typing import Optional

from flask import Flask

from app.api.routes import bp as api_bp
from app.notify.runtime import start_notification_service, stop_notification_service

logger = logging.getLogger("autowing.server")

# ui 目录位于 app 包内 (打包后随 _MEIPASS/app/ui 一并解包)
_UI_DIR = Path(__file__).resolve().parent / "ui"


def create_app() -> Flask:
    """创建 Flask 应用"""
    app = Flask(
        __name__,
        static_folder=str(_UI_DIR / "static"),
        template_folder=str(_UI_DIR / "templates"),
    )
    app.register_blueprint(api_bp)
    app.config["SECRET_KEY"] = "autowing-secret"
    return app


class FlaskServer:
    """Flask 服务器管理"""

    def __init__(self, host: str = "127.0.0.1", port: int = 5000):
        self.host = host
        self.port = port
        self.app = create_app()
        self._thread: Optional[threading.Thread] = None
        start_notification_service()

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self, debug: bool = False):
        """在后台线程启动 Flask"""
        self._thread = threading.Thread(
            target=self.app.run,
            kwargs={
                "host": self.host,
                "port": self.port,
                "debug": debug,
                "use_reloader": False,
            },
            daemon=True,
            name="FlaskServer",
        )
        self._thread.start()
        logger.info(f"Flask 服务器已启动: {self.url}")

    def stop(self):
        """停止服务器 (Flask 开发服务器不支持外部停止，但 daemon=True 会在主进程退出时自动结束)"""
        stop_notification_service()
        logger.info("Flask 服务器停止")
