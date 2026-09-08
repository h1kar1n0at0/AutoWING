"""
Canvas 检测 — 定位游戏画布在屏幕上的位置和尺寸

策略:
  1. CDP — 通过 HWND 查进程 CDP 端口，注入 JS 获取精确位置
  2. 浏览器启动器 — 手动调用 launch_browser() 以 CDP 模式打开浏览器
"""
from __future__ import annotations
import logging
import os
import random
import re
import socket
import subprocess
import time
import winreg
from typing import Optional

import urllib.request
import win32gui
import win32process

from app.config import config

logger = logging.getLogger("autowing.canvas")

CDP_PORT_RANGE = list(range(9222, 9230))


class CanvasDetector:
    """Canvas 检测器"""

    # launch_browser 启动的 CDP 端口（供 _find_cdp_port 直接读取，避免二次扫描）
    _launched_cdp_port: Optional[int] = None

    # ── CDP 端口查找 ──────────────────────────

    @staticmethod
    def _find_cdp_port(hwnd: int = None) -> Optional[int]:
        """从窗口进程或端口扫描找 CDP 端口"""
        # ① 如果端口是 launch_browser 启动的，快速验证后返回
        if CanvasDetector._launched_cdp_port is not None:
            p = CanvasDetector._launched_cdp_port
            try:
                resp = urllib.request.urlopen(
                    f"http://127.0.0.1:{p}/json/version", timeout=0.5)
                if resp.status == 200:
                    return p
            except Exception:
                CanvasDetector._launched_cdp_port = None  # 端口已失效

        # ② 通过 HWND → PID → wmic 读命令行
        if hwnd:
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                if pid:
                    r = subprocess.run(
                        ["wmic", "process", f"where ProcessId={pid}",
                         "get", "CommandLine", "/format:value"],
                        capture_output=True, text=True, timeout=3,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                    m = re.search(r'--remote-debugging-port=(\d+)', r.stdout)
                    if m:
                        return int(m.group(1))
            except Exception:
                pass

        # ③ 扫描 CDP_PORT_RANGE (9222-9229)
        for port in CDP_PORT_RANGE:
            try:
                resp = urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/json/version", timeout=0.3)
                if resp.status == 200:
                    return port
            except Exception:
                continue

        # ④ 通过 PowerShell 扫描所有含 remote-debugging-port 的进程
        try:
            ps_cmd = (
                'Get-CimInstance Win32_Process | '
                'Where-Object { $_.CommandLine -match \"--remote-debugging-port=(\\d+)\" } | '
                'Select-Object -First 1 CommandLine'
            )
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            m = re.search(r'--remote-debugging-port=(\d+)', r.stdout)
            if m:
                port = int(m.group(1))
                resp = urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/json/version", timeout=0.5)
                if resp.status == 200:
                    return port
        except Exception:
            pass

        # ⑤ 兜底: 在 25000-35000 区间用 socket 快速扫描
        try:
            for port in range(25000, 35001, 100):  # 每 100 跳一步，缩小范围
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.05)
                    if s.connect_ex(('127.0.0.1', port)) == 0:
                        resp = urllib.request.urlopen(
                            f"http://127.0.0.1:{port}/json/version", timeout=0.3)
                        if resp.status == 200:
                            return port
        except Exception:
            pass

        return None

    @staticmethod
    def _find_free_port(start: int = 25000, end: int = 35000,
                        max_attempts: int = 50) -> int:
        """在 [start, end] 范围内随机找一个可用 TCP 端口"""
        candidates = set()
        for _ in range(max_attempts):
            port = random.randint(start, end)
            if port in candidates:
                continue
            candidates.add(port)
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.3)
                    if s.connect_ex(('127.0.0.1', port)) != 0:
                        return port
            except Exception:
                continue
        logger.warning(f"未找到可用端口(范围 {start}-{end})，回退至 9222")
        return 9222

    # ── 策略1: CDP ────────────────────────────

    def detect_via_cdp(self, hwnd: int = None) -> Optional[dict]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.warning("playwright 未安装")
            return None

        port = self._find_cdp_port(hwnd)
        if not port:
            logger.info("未发现 CDP 端口")
            return None

        with sync_playwright() as p:
            try:
                browser = p.chromium.connect_over_cdp(
                    f"http://127.0.0.1:{port}", timeout=5000)
            except Exception as e:
                logger.debug(f"CDP 连接失败: {e}")
                return None

            try:
                pages = []
                for ctx in browser.contexts:
                    pages.extend(ctx.pages)
                if not pages:
                    return None

                keywords = ["シャイニー", "idolmaster", "シャニマス",
                            "shinycolors", "imas"]
                for page in pages:
                    t = page.title()
                    if any(k in t for k in keywords):
                        r = self._get_canvas_from_page(page)
                        if r:
                            return r
                for page in reversed(pages):
                    r = self._get_canvas_from_page(page)
                    if r:
                        return r
            finally:
                try:
                    browser.close()
                except Exception:
                    pass
        return None

    def _get_canvas_from_page(self, page) -> Optional[dict]:
        try:
            result = page.evaluate("""() => {
                const c = document.querySelector('canvas');
                if (!c) return null;
                const r = c.getBoundingClientRect();
                return {
                    left: Math.round(r.left + window.screenX),
                    top: Math.round(r.top + window.screenY),
                    width: Math.round(r.width),
                    height: Math.round(r.height),
                    logicalWidth: c.width,
                    logicalHeight: c.height,
                };
            }""")
            if result and result.get("width", 0) > 50:
                logger.info(f"CDP Canvas: {result['width']}x{result['height']}")
            return result
        except Exception as e:
            logger.debug(f"CDP 取 canvas 失败: {e}")
            return None

    # ── 策略2: 浏览器启动器 ───────────────────

    @staticmethod
    def find_browser() -> Optional[str]:
        """找已安装的 Chromium 浏览器路径（优先使用配置中的路径）"""
        from app.engine.config_models import config_manager
        
        # 1. 优先使用配置中的 browser_path
        user_path = config_manager.config.browser_path
        if user_path and os.path.exists(user_path):
            logger.info(f"使用配置中的浏览器路径: {user_path}")
            return user_path
        candidates = [
            # Vivaldi
            r"C:\Program Files\Vivaldi\Application\vivaldi.exe",
            r"C:\Program Files (x86)\Vivaldi\Application\vivaldi.exe",
            r"~\AppData\Local\Vivaldi\Application\vivaldi.exe",
            # thorium
            r"C:\Program Files\Thorium\Application\thorium.exe",
            r"C:\Program Files (x86)\Thorium\Application\thorium.exe",
            r"~\AppData\Local\Thorium\Application\thorium.exe",
        ]
        # 先查注册表
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\vivaldi.exe") as k:
                path = winreg.QueryValue(k, None)
                if path and os.path.exists(path):
                    return path
        except OSError:
            pass
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\thorium.exe") as k:
                path = winreg.QueryValue(k, None)
                if path and os.path.exists(path):
                    return path
        except OSError:
            pass

        for path in candidates:
            expanded = os.path.expanduser(path)
            if os.path.exists(expanded):
                return expanded
        return None

    @staticmethod
    def launch_browser(game_url: str = None,
                       close_first: bool = True) -> Optional[dict]:
        """重启浏览器并开启 CDP 端口"""
        browser_path = CanvasDetector.find_browser()
        if not browser_path:
            raise RuntimeError("未找到已安装的 Chromium 浏览器")

        if not game_url:
            game_url = "https://shinycolors.enza.fun/"

        port = CanvasDetector._find_free_port()
        CanvasDetector._launched_cdp_port = port  # 供 _find_cdp_port 直接取用
        browser_exe = os.path.basename(browser_path)

        # 关闭已有进程（如果有）
        if close_first:
            logger.info(f"关闭已有 {browser_exe}...")
            try:
                subprocess.run(
                    ["taskkill", "/f", "/im", browser_exe],
                    capture_output=True, timeout=5)
                time.sleep(1.5)
            except subprocess.TimeoutExpired:
                pass
            except Exception:
                pass

        try:
            subprocess.Popen([
                browser_path,
                f"--remote-debugging-port={port}",
                "--restore-last-session",
                "--new-window",
                game_url,
                # 反检测标志
                "--disable-blink-features=AutomationControlled",
                "--excludeSwitches=enable-automation",
                "--disable-infobars",
                "--no-first-run",
                "--no-service-autorun",
            ], creationflags=subprocess.CREATE_NO_WINDOW)
            logger.info(f"已启动 {browser_exe} (CDP:{port})")

            # 等待 CDP 端口就绪
            import urllib.request
            for i in range(20):
                time.sleep(1)
                try:
                    resp = urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/json/version",
                        timeout=1)
                    if resp.status == 200:
                        logger.info(f"CDP 端口 {port} 就绪")
                        return {"port": port, "path": browser_path}
                except Exception:
                    continue

            logger.warning("CDP 端口未就绪")
            return {"port": port, "path": browser_path}
        except Exception as e:
            raise RuntimeError(f"启动失败: {e}")
        
    # ── 统一入口 ───────────────────────────────

    def detect(self, hwnd: int = None,
               force_method: str = None) -> Optional[dict]:
        methods = [force_method] if force_method else ["cdp"]

        for method in methods:
            if method == "cdp":
                result = self.detect_via_cdp(hwnd)
            else:
                continue
            if result and result.get("width", 0) > 50:
                return result
        return None
