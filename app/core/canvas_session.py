"""
CDP 会话 — 后台常驻 CDP 连接线程的生命周期

后台线程用 playwright.async_api，page 对象是 async 的。
所有交互/截图函数保持同步（供 Flask / clicker 调用），内部通过
_run_on_bg_loop() 调度到后台事件循环上执行。

职责:
  保持一条常驻 CDP 连接 (thread + event loop + browser/page)
  持续截图刷新 _bg_snapshot
  启动/停止/重连
"""
from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import logging
import threading
import time
import warnings
from typing import Optional

import cv2
import numpy as np

from app.core.canvas import CanvasDetector
from app.notify.events import NotificationEvent, NotificationLevel

warnings.filterwarnings("ignore", category=ResourceWarning)
logger = logging.getLogger("autowing.canvas_session")

_stop_bg_worker = False
_bg_capture_interval = 0.05  # CDP 截图间隔（秒），可通过 set_bg_capture_interval() 调整
_SCREENSHOT_TIMEOUT = 3.0   # 单次截图 evaluate 超时，防止页面 pending navigation 卡死后台循环


# ── 后台常驻 CDP 连接 ────────────────────

_bg_browser = None   # (pw, browser, page)
_bg_hwnd = None
_bg_loop: Optional[asyncio.AbstractEventLoop] = None  # 后台线程的事件循环
_bg_lock = threading.Lock()
_bg_ready = threading.Event()


def _notify_cdp_disconnect(
    was_connected: bool,
    was_requested_to_stop: bool,
    worker_id: str,
) -> None:
    if not was_connected or was_requested_to_stop:
        return
    try:
        from app.notify.runtime import get_notification_service

        get_notification_service().publish(NotificationEvent(
            event_type="cdp_disconnected",
            level=NotificationLevel.WARNING,
            title="AutoWING：CDP 连接断开",
            body="Canvas 后台连接已意外退出，请检查浏览器和调试端口。",
            dedup_key=worker_id,
        ))
    except Exception as exc:
        logger.debug("CDP 断线通知失败: %s", type(exc).__name__)


def _run_on_bg_loop(coro) -> Optional[any]:
    """同步调用方：将协程调度到后台线程的事件循环并等待结果

    超时或协程异常时返回 None 而非抛异常 —
    后台循环被卡住或页面导航导致执行上下文销毁时, 避免异常传播到主循环。
    """
    loop = _bg_loop
    if loop is None or not loop.is_running():
        return None
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    try:
        return future.result(timeout=30)
    except (TimeoutError, asyncio.TimeoutError, concurrent.futures.TimeoutError):
        logger.warning("后台协程执行超时 (30s)，返回 None")
        future.cancel()
        try:
            # 读取结果, 避免 future 带异常完成却无人取 → "Future exception was never retrieved"
            future.result(timeout=1)
        except Exception:
            pass
        return None
    except Exception as e:
        # 协程异常 (常见: 页面导航导致 Execution context was destroyed) — 吞掉
        logger.debug(f"后台协程异常 ({type(e).__name__}): {e}")
        return None


def _is_bg_loop_alive() -> bool:
    """后台事件循环是否还在运行 (用于在创建协程前预检，避免 RuntimeWarning)"""
    return _bg_loop is not None and _bg_loop.is_running()


def _bg_worker(hwnd):
    """后台线程: 保持 CDP 连接, 持续截图到 _bg_snapshot"""
    global _bg_browser, _bg_loop, _bg_snapshot, _stop_bg_worker
    was_connected = False

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # 后台线程内的任务异常 (页面导航/断线等, 如 "Future exception was never retrieved")
    # 统一降级为 debug, 避免 asyncio 默认处理器以 ERROR 级别刷日志
    def _bg_loop_exception_handler(_loop, context):
        exc = context.get("exception")
        if exc is not None:
            logger.debug(f"后台事件循环异常: {context.get('message')} ({type(exc).__name__}: {exc})")
        else:
            logger.debug(f"后台事件循环异常: {context.get('message')}")

    loop.set_exception_handler(_bg_loop_exception_handler)
    _bg_loop = loop

    async def run():
        nonlocal was_connected
        global _bg_browser, _bg_snapshot, _stop_bg_worker
        port = CanvasDetector._find_cdp_port(hwnd)
        if not port:
            logger.debug(f"未找到 CDP 端口 (hwnd={hwnd})")
            return
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("playwright 未安装")
            return

        try:
            async with async_playwright() as pw:
                try:
                    browser = await pw.chromium.connect_over_cdp(
                        f"http://127.0.0.1:{port}", timeout=8000)
                except Exception as e:
                    logger.debug(f"CDP 连接失败: {e}")
                    return

                try:
                    pages = [pg for ctx in browser.contexts for pg in ctx.pages]
                    if not pages:
                        logger.debug("未找到页面")
                        return

                    pg = None
                    for p_ in pages:
                        try:
                            t = await p_.title()
                            if any(k in t for k in ["シャイニー", "idolmaster", "imas"]):
                                pg = p_
                                break
                        except Exception:
                            continue

                    if not pg:
                        pg = pages[-1]

                    try:
                        await pg.wait_for_selector("canvas", timeout=5000)
                    except Exception:
                        logger.debug("等待 canvas 超时")
                        return

                    # 反检测: 覆盖 navigator.webdriver
                    try:
                        await pg.add_init_script("""\
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined,
});""")
                        logger.debug("已注入 navigator.webdriver 反检测脚本")
                    except Exception as e:
                        logger.debug(f"注入反检测脚本失败: {e}")

                    _bg_browser = (pw, browser, pg)
                    was_connected = True
                    _bg_ready.set()
                    logger.info("CDP 后台线程就绪")

                    # 持续截图
                    consecutive_errors = 0
                    while not _stop_bg_worker:  # ← 检查停止标志
                        try:
                            data_url = await asyncio.wait_for(
                                pg.evaluate("""() => {
                                    const c = document.querySelector('canvas');
                                    if (!c) return null;
                                    return c.toDataURL('image/jpeg', 0.92);
                                }"""),
                                timeout=_SCREENSHOT_TIMEOUT,
                            )
                            if data_url:
                                header, encoded = data_url.split(',', 1)
                                data = base64.b64decode(encoded)
                                img = cv2.imdecode(
                                    np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
                                with _bg_lock:
                                    _bg_snapshot = img
                                consecutive_errors = 0
                            else:
                                # canvas 元素不在了，退出循环
                                logger.debug("canvas 元素已消失，退出截图循环")
                                break
                        except Exception as exc:
                            consecutive_errors += 1
                            logger.debug(f"截图失败 ({type(exc).__name__}): {exc}")
                            if consecutive_errors >= 5:
                                await asyncio.sleep(10)
                                consecutive_errors = 0
                                continue
                        await asyncio.sleep(_bg_capture_interval)

                    logger.debug("CDP 截图循环退出")

                finally:
                    try:
                        await browser.close()
                    except Exception:
                        pass
        except (RuntimeError, ValueError) as e:
            # 在 run() 内部捕获事件循环关闭错误
            if "Event loop is closed" in str(e) or "closed pipe" in str(e):
                logger.debug(f"CDP 清理时忽略: {e}")
            else:
                raise

    try:
        loop.run_until_complete(run())
    except (RuntimeError, ValueError) as e:
        if "Event loop is closed" in str(e) or "closed pipe" in str(e):
            logger.debug(f"CDP 后台线程清理时忽略: {e}")
        else:
            logger.error(f"CDP 后台线程异常退出: {e}")
    except Exception as e:
        logger.error(f"CDP 后台线程异常退出: {e}")
    finally:
        _notify_cdp_disconnect(
            was_connected=was_connected,
            was_requested_to_stop=_stop_bg_worker,
            worker_id=str(hwnd),
        )
        _bg_ready.set()
        _bg_loop = None
        _bg_browser = None
        logger.debug("CDP 后台线程已清理")

_bg_snapshot: Optional[np.ndarray] = None
_bg_thread: Optional[threading.Thread] = None

# 重连冷却：避免 CDP 断线后高频重连导致窗口抖动
_bg_last_attempt = 0.0
_BG_RETRY_INTERVAL = 5.0  # 两次重连最小间隔（秒）


def _ensure_bg(hwnd=None):
    """确保后台 CDP 线程运行"""
    # 惰性导入 clicker 避免循环 import (clicker → canvas_interaction → canvas_session)
    from app.core.clicker import clicker as _ck
    if hwnd is None:
        hwnd = _ck.hwnd
    global _bg_thread, _bg_hwnd, _bg_last_attempt

    # 如果已有线程在跑且 HWND 没变，直接返回
    if _bg_thread and _bg_thread.is_alive() and _bg_hwnd == hwnd:
        return

    now = time.time()

    # 冷却期内不重连（避免死循环抖动）
    if now - _bg_last_attempt < _BG_RETRY_INTERVAL:
        logger.debug("CDP 重连冷却中，跳过")
        return

    _bg_last_attempt = now
    _bg_ready.clear()
    _bg_hwnd = hwnd
    _bg_thread = threading.Thread(target=_bg_worker, args=(hwnd,), daemon=True)
    _bg_thread.start()
    # 等后台线程就绪 (连接完成或失败)
    _bg_ready.wait(timeout=15)
    # 如果线程已退出说明连接失败，不继续等截图
    if not _bg_thread.is_alive():
        logger.debug("CDP 后台线程已退出，连接失败")
        return
    # 再等第一帧截图就绪
    for _ in range(30):
        with _bg_lock:
            if _bg_snapshot is not None:
                return
        time.sleep(0.2)


def _get_canvas_image(hwnd=None):
    """从后台线程获取最新 canvas 截图 (~50ms)"""
    _ensure_bg(hwnd)
    with _bg_lock:
        return _bg_snapshot


def _disconnect():
    global _bg_thread, _bg_browser, _bg_snapshot, _bg_loop, _bg_last_attempt
    _bg_thread = None
    _bg_browser = None
    _bg_snapshot = None
    _bg_loop = None
    _bg_last_attempt = 0.0


def get_page():
    """获取后台 CDP 连接的 page 对象 (async Page, 仅供内部使用)"""
    _ensure_bg()
    with _bg_lock:
        if _bg_browser:
            return _bg_browser[2]  # (pw, browser, pg)
    return None


def stop_bg_worker():
    """停止后台 CDP 工作线程

    优先让截图循环自然退出 (检查停止标志 → playwright 优雅关闭);
    超时兜底才强制停止事件循环, 避免遗留未完成任务导致
    "Task was destroyed" / "Event loop stopped before Future completed" 噪音。
    """
    global _stop_bg_worker, _bg_thread, _bg_browser, _bg_loop

    _stop_bg_worker = True

    # 1. 优雅退出: 截图循环每轮最长约 3s (截图超时), 给足时间自然结束
    if _bg_thread and _bg_thread.is_alive():
        _bg_thread.join(timeout=4.0)

    # 2. 兜底: 仍存活则强制停止事件循环
    if _bg_thread and _bg_thread.is_alive():
        if _bg_loop and _bg_loop.is_running():
            try:
                _bg_loop.call_soon_threadsafe(_bg_loop.stop)
            except Exception:
                pass
        _bg_thread.join(timeout=1.0)

    _disconnect()
    _stop_bg_worker = False  # 重置标志


def set_bg_capture_interval(seconds: float = 0.5) -> None:
    """调整后台 CDP 截图间隔

    默认 0.5s，最低 0.1s（CPU 负载随间隔缩短显著上升）。
    仅在 _bg_worker 循环生效，不会触发截图。
    """
    global _bg_capture_interval
    _bg_capture_interval = max(0.1, seconds)
