#!/usr/bin/env python3
"""
AutoWING — アイドルマスター シャイニーカラーズ 自动化工具

启动方式:
    python run.py            # 桌面窗口模式 (推荐, 需 pywebview)
    python run.py --browser  # 浏览器模式
    python run.py --headless # 无界面模式 (纯后端)

依赖安装:
    pip install -r requirements.txt
    playwright install chromium  (可选, 用于 Canvas 自动检测)
"""
from __future__ import annotations
import argparse
import logging
import sys
import os

# 确保项目根目录在 path 中 (PyInstaller 打包后补充 _MEIPASS)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if getattr(sys, "frozen", False):
    sys.path.insert(0, sys._MEIPASS)

import ctypes

from app.server import FlaskServer
from app.window import DesktopWindow
from app.core import coord
from version import WINDOW_TITLE

# ── 日志格式 ──────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    stream=sys.stdout,
)

# 静默 Flask 开发服务器的 HTTP 请求日志
logging.getLogger("werkzeug").setLevel(logging.WARNING)


def setup_dpi():
    """启用 DPI 感知"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

import atexit

def cleanup():
    from app.core import stop_bg_worker
    stop_bg_worker()


atexit.register(cleanup)


def main():
    parser = argparse.ArgumentParser(description=f"{WINDOW_TITLE} 控制面板")
    parser.add_argument("--browser", action="store_true",
                        help="在浏览器中打开控制面板")
    parser.add_argument("--headless", action="store_true",
                        help="无界面模式 (仅启动后端)")
    parser.add_argument("--port", type=int, default=5000,
                        help="监听端口 (默认 5000)")
    parser.add_argument("--debug", action="store_true",
                        help="Flask 调试模式")
    args = parser.parse_args()

    setup_dpi()

    # ── 恢复上次校准 ──
    coord.load_calibration()

    # ── 启动 Flask ──
    server = FlaskServer(port=args.port)
    server.start(debug=args.debug)

    print(f"\n✨ AutoWING 已启动")
    print(f"   {server.url}")
    print()

    # ── 窗口模式 ──
    if args.headless:
        print("无界面模式运行中... 按 Ctrl+C 停止")
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n再见！")
    elif args.browser:
        import webbrowser
        webbrowser.open(server.url)
        print("按 Ctrl+C 停止服务器")
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n再见！")
    else:
        # 默认: 原生桌面窗口
        win = DesktopWindow(url=server.url, title=WINDOW_TITLE)
        win.open()


if __name__ == "__main__":
    main()
