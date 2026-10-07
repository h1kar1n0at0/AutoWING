"""
CDP 交互 — 在已连接的 Canvas 上执行点击 / 坐标预览 / QTE / 页面导航

依赖 canvas_session 的后台持久连接；所有公开函数保持同步，
内部通过 _run_on_bg_loop() 调度到后台事件循环上执行。

坐标约定: 以 canvas 左上角为原点，基于 1600×902 参考坐标系 (REF_W/REF_H)。
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Optional

from app.core.canvas_session import (
    _ensure_bg,
    _is_bg_loop_alive,
    _run_on_bg_loop,
    get_page,
)
from app.core.coord import REF_H, REF_W

logger = logging.getLogger("autowing.canvas_interaction")


# ── 异步内核 (在后台事件循环上执行) ────────

async def _async_get_canvas_rect(page=None):
    """async: 获取 canvas 在视口中的位置和尺寸 (CSS 像素)"""
    if page is None:
        page = get_page()
    if not page:
        return None
    try:
        return await page.evaluate("""() => {
            const c = document.querySelector('canvas');
            if (!c) return null;
            const r = c.getBoundingClientRect();
            return {
                left: r.left, top: r.top,
                width: r.width, height: r.height,
                logicalW: c.width, logicalH: c.height,
            };
        }""")
    except Exception as e:
        logger.debug(f"取 canvas rect 失败: {e}")
        return None


async def _async_mouse_click(page, px, py, button, duration):
    """async: 执行鼠标点击 (普通或长按)"""
    if duration > 0:
        await page.mouse.move(px, py)
        await page.mouse.down(button=button)
        await asyncio.sleep(duration)
        await page.mouse.up(button=button)
    else:
        await page.mouse.click(px, py, button=button)


async def _async_click_on_canvas(ref_x, ref_y, button="left", duration=0, page=None):
    """async: 在 canvas 上点击，坐标以 canvas 左上角为原点 (适配各种缩放)"""
    if page is None:
        page = get_page()
    if not page:
        return None

    # 复用 _async_get_canvas_rect
    rect = await _async_get_canvas_rect(page)
    if not rect:
        return None

    # 计算基准坐标 (REF_W x REF_H) 映射到当前 Canvas CSS 渲染尺寸的缩放比
    s = rect["width"] / REF_W
    sx = sy = s

    # 计算目标点在 Page Viewport 中的绝对坐标
    px = rect["left"] + ref_x * sx
    py = rect["top"] + ref_y * sy

    await _async_mouse_click(page, px, py, button, duration)

    return {
        "ref": {"x": ref_x, "y": ref_y},
        "page": {"x": round(px, 2), "y": round(py, 2)},
        "canvas_rect": rect,
        "scale": {"x": round(sx, 4), "y": round(sy, 4)},
    }


async def _async_preview_coords(ref_x, ref_y, page=None):
    """async: 计算点击坐标但不执行点击 (预览/调试用)"""
    if page is None:
        page = get_page()
    if not page:
        return None

    # 复用 _async_get_canvas_rect
    rect = await _async_get_canvas_rect(page)
    if not rect:
        return None

    s = rect["width"] / REF_W
    sx = sy = s
    px = rect["left"] + ref_x * sx
    py = rect["top"] + ref_y * sy

    return {
        "ref": {"x": ref_x, "y": ref_y},
        "page": {"x": round(px, 2), "y": round(py, 2)},
        "canvas_rect": rect,
        "scale": {"x": round(sx, 4), "y": round(sy, 4)},
        "screen": None,
    }


async def _async_execute_qte_sequence(ref_x: float, ref_y: float, total_clicks: int, interval: float, jitter: int = 0, page=None):
    if page is None:
        page = get_page()
    if not page:
        return

    # 1. 仅在开始前查询一次 Canvas 坐标 (不再每次点击都查 DOM)
    rect = await _async_get_canvas_rect(page)
    if not rect:
        return

    s = rect["width"] / REF_W
    sx = sy = s

    # 2. 使用 time.perf_counter() 获得最高精度的单调时钟
    start_time = time.perf_counter()

    for i in range(total_clicks):
        # 计算加了 jitter 的绝对点
        jx = random.randint(-jitter, jitter) if jitter > 0 else 0
        jy = random.randint(-jitter, jitter) if jitter > 0 else 0
        px = rect["left"] + (ref_x + jx) * sx
        py = rect["top"] + (ref_y + jy) * sy

        # 直接发送 mouse click (不重新查 rect)
        await page.mouse.click(px, py)

        # 如果是最后一次点击，无需等待
        if i == total_clicks - 1:
            break

        # 3. 绝对时间对齐点算法（消除累积误差）
        target_time = start_time + (i + 1) * interval
        while True:
            now = time.perf_counter()
            remaining = target_time - now
            if remaining <= 0:
                break
            if remaining > 0.012:
                # 剩余时间较长时 sleep，让出 CPU
                await asyncio.sleep(remaining - 0.005)
            else:
                # 最后 5ms 使用微秒级忙等待 (Busy-Wait) 锁定极佳精度
                pass


# ── 滚轮操作 (CDP) ─────────────────────────

async def _async_scroll_on_canvas(
    ref_x: float, 
    ref_y: float, 
    delta_x: float = 0, 
    delta_y: float = -300,  # 负数向上滚（鼠标向下拖），正数向下滚（鼠标向上拖）
    page=None
):
    """async: 通过拖拽模拟滚轮，坐标以 canvas 左上角为原点"""
    if page is None:
        page = get_page()
    if not page:
        return None

    rect = await _async_get_canvas_rect(page)
    if not rect:
        return None

    s = rect["width"] / REF_W
    sx = sy = s

    # 计算目标点在 Page Viewport 中的绝对坐标
    px = rect["left"] + ref_x * sx
    py = rect["top"] + ref_y * sy

    # 边界验证：确保点击点在 Canvas 范围内
    canvas_left = rect["left"]
    canvas_right = rect["left"] + rect["width"]
    canvas_top = rect["top"]
    canvas_bottom = rect["top"] + rect["height"]
    
    if not (canvas_left <= px <= canvas_right and canvas_top <= py <= canvas_bottom):
        logger.warning(f"滚动点超出 Canvas 范围: ({px:.2f}, {py:.2f})，Canvas rect: {rect}")
        return None

    try:
        # 拖拽滚动：按下 → 移动 → 释放
        await page.mouse.move(px, py)
        await asyncio.sleep(0.03)
        await page.mouse.down(button="left")
        await asyncio.sleep(0.03)
        
        # 计算终点（delta_y 负值 = 向上拖 = 页面向下滚）
        end_px = px + delta_x
        end_py = py + delta_y
        
        # 分步移动，模拟真实拖拽（更容易触发滚动）
        steps = 8
        for i in range(steps):
            t = (i + 1) / steps
            current_x = px + (end_px - px) * t
            current_y = py + (end_py - py) * t
            await page.mouse.move(current_x, current_y)
            await asyncio.sleep(0.015)
        
        await asyncio.sleep(0.03)
        await page.mouse.up(button="left")
        
        return {
            "ref": {"x": ref_x, "y": ref_y},
            "page": {"x": round(px, 2), "y": round(py, 2)},
            "delta": {"x": delta_x, "y": delta_y},
            "canvas_rect": rect,
            "scale": {"x": round(sx, 4), "y": round(sy, 4)},
        }
    except Exception as e:
        logger.debug(f"拖拽滚动失败: {e}")
        return None


async def _async_continuous_scroll(
    ref_x: float,
    ref_y: float,
    total_delta_y: float = -1000,
    steps: int = 5,
    interval: float = 0.3,
    page=None
):
    """async: 连续拖拽滚动（模拟手指慢慢滑）"""
    if page is None:
        page = get_page()
    if not page:
        return False

    rect = await _async_get_canvas_rect(page)
    if not rect:
        return False

    s = rect["width"] / REF_W
    sx = sy = s
    base_px = rect["left"] + ref_x * sx
    base_py = rect["top"] + ref_y * sy

    # 边界验证
    canvas_left = rect["left"]
    canvas_right = rect["left"] + rect["width"]
    canvas_top = rect["top"]
    canvas_bottom = rect["top"] + rect["height"]
    
    if not (canvas_left <= base_px <= canvas_right and canvas_top <= base_py <= canvas_bottom):
        logger.warning(f"滚动起点超出 Canvas 范围: ({base_px:.2f}, {base_py:.2f})")
        return False

    # 每次拖拽的距离
    step_delta = total_delta_y / steps
    
    for i in range(steps):
        try:
            # 每次从稍微不同的位置开始（更自然）
            start_x = base_px + random.randint(-3, 3)
            start_y = base_py + random.randint(-3, 3)
            
            # 确保起点仍在 Canvas 内
            start_y = max(canvas_top + 10, min(canvas_bottom - 10, start_y))
            
            end_x = start_x + random.randint(-2, 2)
            end_y = start_y + step_delta + random.randint(-3, 3)
            
            # 确保终点不超出 Canvas 太远（避免拖出界）
            end_y = max(canvas_top + 10, min(canvas_bottom - 10, end_y))
            
            # 执行拖拽
            await page.mouse.move(start_x, start_y)
            await asyncio.sleep(0.03)
            await page.mouse.down(button="left")
            await asyncio.sleep(0.03)
            
            await page.mouse.move(end_x, end_y)
            
            await asyncio.sleep(0.03)
            await page.mouse.up(button="left")
            
            if i < steps - 1:
                await asyncio.sleep(interval)
                
        except Exception as e:
            logger.debug(f"连续拖拽滚动第 {i+1} 步失败: {e}")
            return False
    
    return True

# ── 同步公开 API (调度到后台 loop) ─────────


def execute_qte_sequence(ref_x: float, ref_y: float, total_clicks: int, interval: float, jitter: int = 0):
    """同步公开 API"""
    _ensure_bg()
    if not _is_bg_loop_alive():
        return None
    return _run_on_bg_loop(_async_execute_qte_sequence(ref_x, ref_y, total_clicks, interval, jitter))


def get_canvas_rect(page=None) -> Optional[dict]:
    """同步: 获取 canvas 在视口中的位置和尺寸"""
    _ensure_bg()
    if not _is_bg_loop_alive():
        return None
    return _run_on_bg_loop(_async_get_canvas_rect(page))


def click_on_canvas(ref_x: float, ref_y: float,
                    button: str = "left",
                    duration: float = 0,
                    page=None) -> Optional[dict]:
    """同步: 在 canvas 上点击，坐标以 canvas 左上角为原点"""
    _ensure_bg()
    if not _is_bg_loop_alive():
        return None
    return _run_on_bg_loop(
        _async_click_on_canvas(ref_x, ref_y, button, duration, page))


def preview_coords(ref_x: float, ref_y: float,
                   page=None) -> Optional[dict]:
    """同步: 计算点击坐标但不执行"""
    _ensure_bg()
    if not _is_bg_loop_alive():
        return None
    return _run_on_bg_loop(_async_preview_coords(ref_x, ref_y, page))


def scroll_on_canvas(
    ref_x: float, 
    ref_y: float, 
    delta_x: float = 0, 
    delta_y: float = -300
) -> Optional[dict]:
    """
    在 canvas 指定位置滚动
    
    Args:
        ref_x: 参考坐标系 X (0~1600)
        ref_y: 参考坐标系 Y (0~902)
        delta_x: 水平滚动量（正=右）
        delta_y: 垂直滚动量（正=下，负=上）
    
    Returns:
        滚动信息字典，失败返回 None
    """
    _ensure_bg()
    if not _is_bg_loop_alive():
        return None
    return _run_on_bg_loop(
        _async_scroll_on_canvas(ref_x, ref_y, delta_x, delta_y)
    )


def continuous_scroll(
    ref_x: float,
    ref_y: float,
    total_delta_y: float = -1000,
    steps: int = 5,
    interval: float = 0.3
) -> bool:
    """
    连续滚动（模拟多次拖拽滚动）
    
    Args:
        ref_x: 参考坐标系 X
        ref_y: 参考坐标系 Y
        total_delta_y: 总滚动量
        steps: 分几步滚完
        interval: 每步间隔（秒）
    """
    _ensure_bg()
    if not _is_bg_loop_alive():
        return False
    return _run_on_bg_loop(
        _async_continuous_scroll(ref_x, ref_y, total_delta_y, steps, interval)
    ) or False

# ── 页面导航 (CDP) ─────────────────────────

async def _async_page_go_back(page=None):
    if page is None:
        page = get_page()
    if not page:
        return False
    try:
        await page.go_back()
        return True
    except Exception as e:
        logger.debug(f"go_back 失败: {e}")
        return False


async def _async_page_go_forward(page=None):
    if page is None:
        page = get_page()
    if not page:
        return False
    try:
        await page.go_forward()
        return True
    except Exception as e:
        logger.debug(f"go_forward 失败: {e}")
        return False


async def _async_page_reload(page=None):
    if page is None:
        page = get_page()
    if not page:
        return False
    try:
        await page.reload()
        return True
    except Exception as e:
        logger.debug(f"reload 失败: {e}")
        return False


async def _async_page_goto(url: str, page=None):
    if page is None:
        page = get_page()
    if not page:
        return False
    try:
        await page.goto(url, wait_until="domcontentloaded")
        # 等页面加载完成, 避免后续 evaluate/click 卡在 pending navigation
        try:
            await page.wait_for_load_state("load", timeout=10.0)
        except Exception:
            logger.debug(f"goto 后等待 load 超时: {url}")
        return True
    except Exception as e:
        logger.debug(f"goto {url} 失败: {e}")
        return False


def page_go_back() -> bool:
    _ensure_bg()
    if not _is_bg_loop_alive():
        return False
    return _run_on_bg_loop(_async_page_go_back()) or False


def page_go_forward() -> bool:
    _ensure_bg()
    if not _is_bg_loop_alive():
        return False
    return _run_on_bg_loop(_async_page_go_forward()) or False


def page_reload() -> bool:
    _ensure_bg()
    if not _is_bg_loop_alive():
        return False
    return _run_on_bg_loop(_async_page_reload()) or False


def page_goto(url: str) -> bool:
    _ensure_bg()
    if not _is_bg_loop_alive():
        return False
    return _run_on_bg_loop(_async_page_goto(url)) or False

