"""
Canvas 截图与稳定性 — 取图、缓存、等待画面稳定

取图有两套管线:
  1. _get_cached_canvas() — 后台线程快照 + TTL 缓存 + DPR 归一化 (2400×1353)，供视觉算法统一取图
  2. capture_canvas() — 每次实时 CDP 原生截图 + 内存裁剪 canvas，返回 PNG bytes

坐标约定: 均为 1600×902 参考坐标系 (REF_W/REF_H)。
"""
from __future__ import annotations

import base64
import logging
import time
from typing import Optional

import cv2
import numpy as np

from app.core.canvas_interaction import _async_get_canvas_rect, click_on_canvas
from app.core.canvas_session import (
    _ensure_bg,
    _get_canvas_image,
    _is_bg_loop_alive,
    _run_on_bg_loop,
    get_page,
)
from app.core.coord import REF_H, REF_W

logger = logging.getLogger("autowing.canvas_capture")


# ── 缓存 ──────────────────────────────────

_canvas_cache: Optional[np.ndarray] = None
_canvas_cache_time = 0.0
_CACHE_TTL = 0.1


def _get_cached_canvas(hwnd=None):
    global _canvas_cache, _canvas_cache_time
    now = time.time()
    if _canvas_cache is not None and now - _canvas_cache_time < _CACHE_TTL:
        return _canvas_cache
    img = _get_canvas_image(hwnd)
    if img is not None:
        # 统一缩放到 DPR 1.5 (2400×1353)，使模板匹配不受屏幕 DPR 影响
        h, w = img.shape[:2]
        if (w, h) != (2400, 1353):
            img = cv2.resize(img, (2400, 1353), interpolation=cv2.INTER_CUBIC)
        _canvas_cache = img
        _canvas_cache_time = now
    return img


def clear_cache():
    global _canvas_cache, _canvas_cache_time
    _canvas_cache = None
    _canvas_cache_time = 0.0


def capture_canvas(quality: int = 92) -> Optional[bytes]:
    """从缓存获取 canvas 截图，返回 JPEG bytes
    
    用于 API 外部调用，与视觉算法共用同一数据源。
    """
    img = _get_cached_canvas()
    if img is None:
        return None
    
    success, encoded_img = cv2.imencode('.jpg', img, 
                                        [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not success:
        return None
    
    return encoded_img.tobytes()


# ── 等待稳定 ──────────────────────────────

def wait_for_stable(
    roi: tuple = (0, 0, 100, 100),
    diff_threshold: float = 5.0,
    min_stable_frames: int = 7,
    timeout: float = 30.0,
    accelerate: bool = True,
) -> bool:
    """等待画面 ROI 区域稳定

    基于 CDP canvas 截图 (_get_cached_canvas)，
    坐标统一为 1600×902 参考系，不再支持 use_logical_coords。

    Args:
        roi:               (x, y, w, h) 基于 1600×902 基准
        diff_threshold:    帧差阈值，低于此值算一帧稳定
        min_stable_frames: 连续稳定帧数
        timeout:           超时秒数
        accelerate:        期间隔点 ROI 中心加速推进

    Returns:
        True  — 区域已稳定
        False — 超时未稳定
    """
    deadline = time.time() + timeout
    stable_count = 0
    last_img = None
    tick = 0

    while time.time() < deadline:
        if stable_count % 3 == 0:
            clear_cache()
        canvas_img = _get_cached_canvas()
        if canvas_img is None:
            time.sleep(0.05)
            continue

        ch, cw = canvas_img.shape[:2]
        sx = cw / REF_W
        sy = ch / REF_H
        rx, ry, rw, rh = roi
        x1 = max(0, int(rx * sx))
        y1 = max(0, int(ry * sy))
        x2 = min(cw, int((rx + rw) * sx))
        y2 = min(ch, int((ry + rh) * sy))
        if x1 >= x2 or y1 >= y2:
            time.sleep(0.05)
            tick += 1
            continue
        frame = canvas_img[y1:y2, x1:x2]

        # 加速：每帧点一次屏幕中心
        if accelerate:
            click_on_canvas(818, 289)

        # 帧差检测
        if last_img is not None:
            diff = cv2.absdiff(frame, last_img)
            mean_diff = float(np.mean(diff))
            if mean_diff <= diff_threshold:
                stable_count += 1
            else:
                stable_count = 0
            if stable_count >= min_stable_frames:
                clear_cache()
                return True

        last_img = frame
        tick += 1
        time.sleep(0.05)

    return False
