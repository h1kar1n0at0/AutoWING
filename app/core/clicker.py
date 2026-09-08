"""
点击引擎 — CDP 优先 + Win32 PostMessage 回退

坐标约定: 所有方法以 canvas 左上角为原点 (0,0)，
基于 1600×902 参考坐标系。CDP 点击复用 canvas_vision
的后台持久连接，不回退时零额外开销。
"""
from __future__ import annotations
import logging
import random
import threading
import time
from typing import Optional

import win32api
import win32con
import win32gui

from app.core.coord import coord

logger = logging.getLogger("autowing.clicker")


class BackgroundClicker:
    """点击引擎 — CDP 优先，Win32 回退

    使用方式不变:
        clicker.click(x, y, use_logical=True)
    自动走 CDP（如果已校准且 CDP 已连接）。
    """

    def __init__(self, window_title: str = "アイドルマスター シャイニーカラーズ"):
        self.window_title = window_title
        self.hwnd: Optional[int] = None
        self.lock = threading.Lock()
        self.last_click_time = 0.0
        self.min_interval = 0.02  # 最小间隔 20ms
        self._search_cache = {"hwnd": None, "time": 0.0}

        # CDP 模式开关 (True=优先CDP, False=只用Win32)
        self.use_cdp = True

    def find_window(self) -> bool:
        """查找目标窗口"""
        now = time.time()
        # 缓存 3 秒，避免频繁枚举
        if self._search_cache["hwnd"] and now - self._search_cache["time"] < 3:
            if win32gui.IsWindow(self._search_cache["hwnd"]):
                self.hwnd = self._search_cache["hwnd"]
                return True
            self._search_cache["hwnd"] = None

        hwnds = []

        def callback(hwnd, _extra):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if self.window_title in title:
                    hwnds.append(hwnd)

        win32gui.EnumWindows(callback, None)

        if hwnds:
            self.hwnd = hwnds[0]
            self._search_cache = {"hwnd": self.hwnd, "time": now}
            logger.info(f"找到窗口: {win32gui.GetWindowText(self.hwnd)}")
            return True

        logger.warning(f"未找到窗口: {self.window_title}")
        return False

    def click(self, x: float, y: float,
              dx: int = 0, dy: int = 0,
              use_logical: bool = False) -> bool:
        """点击屏幕坐标 (CDP 优先)

        Args:
            x, y: 坐标
            dx, dy: 额外随机偏移 (叠加在 -2~2 原生抖动之上)
            use_logical: True 时参数为参考坐标 (1600×902),
                         False 时参数为屏幕绝对坐标

        Returns:
            bool: 是否成功
        """
        # ── CDP 模式 (canvas 参考坐标, 左上角为原点) ──
        if self.use_cdp and use_logical and coord.is_calibrated:
            if self._cdp_click(x + dx + random.randint(-2, 2),
                               y + dy + random.randint(-2, 2)):
                return True
            logger.debug("CDP 点击失败，回退 Win32")

        # ── Win32 回退 ──
        if not self.hwnd and not self.find_window():
            return False

        screen_x, screen_y = int(x), int(y)
        if use_logical and coord.is_calibrated:
            screen_x, screen_y = coord.logical_to_screen(screen_x, screen_y)

        tx = int(screen_x + dx + random.randint(-2, 2))
        ty = int(screen_y + dy + random.randint(-2, 2))

        try:
            client_x, client_y = win32gui.ScreenToClient(self.hwnd, (tx, ty))
            lparam = win32api.MAKELONG(client_x, client_y)
        except Exception:
            return False

        with self.lock:
            now = time.perf_counter()
            elapsed = now - self.last_click_time
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)

            win32gui.PostMessage(self.hwnd, win32con.WM_LBUTTONDOWN,
                                 win32con.MK_LBUTTON, lparam)
            win32gui.PostMessage(self.hwnd, win32con.WM_LBUTTONUP,
                                 0, lparam)
            self.last_click_time = time.perf_counter()
            return True

    def _cdp_click(self, ref_x: float, ref_y: float,
                   duration: float = 0) -> bool:
        """通过 CDP 点击 canvas 参考坐标 (左上角为原点)"""
        try:
            from app.core.canvas_interaction import click_on_canvas
            # 长按直接由 click_on_canvas 处理 (mouse.down/sleep/mouse.up)
            result = click_on_canvas(ref_x, ref_y, duration=duration)
            return result is not None
        except Exception as e:
            logger.debug(f"CDP 点击失败: {e}")
        return False

    def long_click(self, x: float, y: float,
                   duration: float = 0.5,
                   dx: int = 0, dy: int = 0,
                   use_logical: bool = False) -> bool:
        """后台长按 (CDP 优先)"""
        # ── CDP 模式 ──
        if self.use_cdp and use_logical and coord.is_calibrated:
            if self._cdp_click(x + dx + random.randint(-2, 2),
                               y + dy + random.randint(-2, 2),
                               duration=duration):
                return True
            logger.debug("CDP 长按失败，回退 Win32")

        # ── Win32 回退 ──
        if not self.hwnd and not self.find_window():
            return False

        screen_x, screen_y = int(x), int(y)
        if use_logical and coord.is_calibrated:
            screen_x, screen_y = coord.logical_to_screen(screen_x, screen_y)

        tx = int(screen_x + dx + random.randint(-2, 2))
        ty = int(screen_y + dy + random.randint(-2, 2))

        try:
            client_x, client_y = win32gui.ScreenToClient(self.hwnd, (tx, ty))
            lparam = win32api.MAKELONG(client_x, client_y)
        except Exception:
            return False

        with self.lock:
            now = time.perf_counter()
            elapsed = now - self.last_click_time
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)

            win32gui.PostMessage(self.hwnd, win32con.WM_LBUTTONDOWN,
                                 win32con.MK_LBUTTON, lparam)
            time.sleep(duration)
            win32gui.PostMessage(self.hwnd, win32con.WM_LBUTTONUP, 0, lparam)
            self.last_click_time = time.perf_counter()
            return True

    def get_window_rect(self) -> Optional[dict]:
        """获取窗口客户区屏幕坐标"""
        if not self.hwnd and not self.find_window():
            return None
        try:
            rect = win32gui.GetWindowRect(self.hwnd)
            return {"left": rect[0], "top": rect[1],
                    "right": rect[2], "bottom": rect[3],
                    "width": rect[2] - rect[0], "height": rect[3] - rect[1]}
        except Exception:
            return None


# 全局单例
clicker = BackgroundClicker()
