"""
Canvas 视觉 — 模板匹配与颜色分析 (纯算法，无 CDP/线程)

输入图像统一来自 canvas_capture._get_cached_canvas (后台线程快照,
DPR 归一化到 2400×1353)，坐标输出统一为 1600×902 参考坐标系。
"""
from __future__ import annotations

import logging
from typing import Optional

import cv2
import numpy as np

from app.core.canvas_capture import _get_cached_canvas, clear_cache
from app.core.coord import REF_H, REF_W
from app.paths import asset

logger = logging.getLogger("autowing.canvas_vision")


class _Hit:
    def __init__(self, x, y, conf):
        self.x = x
        self.y = y
        self.conf = conf
    def __bool__(self):
        return True


# 公开别名 (业务代码统一使用 Hit)
Hit = _Hit

# Patch _Hit to support _used_roi
_Hit._used_roi = True


# ── 模板匹配 (全 canvas) ──────────────────
def find(template_path: str, conf: float = 0.8,
         region: tuple = None, hwnd: int = None,
         use_alpha: bool = False) -> Optional[_Hit]:
    """
    在截图中查找模板

    Args:
        template_path: 模板路径
        conf: 置信度阈值
        region: ROI 区域
        hwnd: 窗口句柄
        use_alpha: 是否使用 Alpha 通道作为掩膜（默认 False）
    """
    if isinstance(template_path, str) and template_path.startswith("assets/"):
        template_path = asset(template_path)

    canvas_img = _get_cached_canvas(hwnd)
    if canvas_img is None:
        return None

    ch, cw = canvas_img.shape[:2]
    scale_x = cw / REF_W
    scale_y = ch / REF_H

    ox = oy = 0
    if region is not None:
        rx, ry, rw, rh = region
        x1 = max(0, int(rx * scale_x))
        y1 = max(0, int(ry * scale_y))
        x2 = min(cw, int((rx + rw) * scale_x))
        y2 = min(ch, int((ry + rh) * scale_y))
        canvas_img = canvas_img[y1:y2, x1:x2]
        ox, oy = x1, y1

    # 根据 use_alpha 决定读取方式
    if use_alpha:
        template = cv2.imread(template_path, cv2.IMREAD_UNCHANGED)
    else:
        template = cv2.imread(template_path)

    if template is None:
        return None

    mask = None
    if use_alpha and len(template.shape) == 3 and template.shape[2] == 4:
        mask = template[:, :, 3]
        template = template[:, :, :3]

    th, tw = template.shape[:2]
    if canvas_img.shape[0] < th or canvas_img.shape[1] < tw:
        return None

    if mask is not None:
        res = cv2.matchTemplate(canvas_img, template, cv2.TM_CCORR_NORMED, mask=mask)
    else:
        res = cv2.matchTemplate(canvas_img, template, cv2.TM_CCOEFF_NORMED)

    _, max_val, _, max_loc = cv2.minMaxLoc(res)

    if max_val >= conf:
        px = max_loc[0] + tw // 2 + ox
        py = max_loc[1] + th // 2 + oy
        return _Hit(px / scale_x, py / scale_y, max_val)

    return None


def find_with_fallback(template_path: str, conf: float = 0.8,
                       region: tuple = None,
                       hwnd: int = None) -> Optional[_Hit]:
    """先用 ROI 找, 找不到再全 canvas 找"""
    hit = find(template_path, conf=conf, region=region, hwnd=hwnd)
    if hit is not None:
        hit._used_roi = True
        return hit
    hit = find(template_path, conf=conf, region=None, hwnd=hwnd)
    if hit is not None:
        hit._used_roi = False
    return hit


def find_all(template_path: str, conf: float = 0.8,
             region: tuple = None, min_distance: int = 10,
             hwnd: int = None) -> list[_Hit]:
    """在截图中查找模板的所有匹配点

    坐标与 find() 一致：以 1600×902 参考坐标系返回各匹配中心。
    min_distance 为参考系下的最小间距，用于过滤重叠的相邻匹配。
    """
    if isinstance(template_path, str) and template_path.startswith("assets/"):
        template_path = asset(template_path)

    canvas_img = _get_cached_canvas(hwnd)
    if canvas_img is None:
        return []

    ch, cw = canvas_img.shape[:2]
    scale_x = cw / REF_W
    scale_y = ch / REF_H

    ox = oy = 0
    if region is not None:
        rx, ry, rw, rh = region
        x1 = max(0, int(rx * scale_x))
        y1 = max(0, int(ry * scale_y))
        x2 = min(cw, int((rx + rw) * scale_x))
        y2 = min(ch, int((ry + rh) * scale_y))
        if x1 >= x2 or y1 >= y2:
            return []
        canvas_img = canvas_img[y1:y2, x1:x2]
        ox, oy = x1, y1

    template = cv2.imread(template_path)
    if template is None:
        return []
    th, tw = template.shape[:2]
    if canvas_img.shape[0] < th or canvas_img.shape[1] < tw:
        return []

    res = cv2.matchTemplate(canvas_img, template, cv2.TM_CCOEFF_NORMED)
    locations = np.where(res >= conf)
    points = list(zip(*locations[::-1]))
    if not points:
        return []

    candidates = []
    for pt in points:
        conf_val = res[pt[1], pt[0]]
        # 参照 find(): 中心点从裁剪图坐标 → 全图坐标 → 参考坐标
        cx = (pt[0] + tw // 2 + ox) / scale_x
        cy = (pt[1] + th // 2 + oy) / scale_y
        candidates.append((conf_val, cx, cy))

    candidates.sort(reverse=True)

    filtered = []
    used = set()
    for conf_val, cx, cy in candidates:
        if any(abs(cx - ux) < min_distance and abs(cy - uy) < min_distance
               for ux, uy in used):
            continue
        filtered.append(_Hit(cx, cy, conf_val))
        used.add((cx, cy))
    return filtered


def check_pixel_color(
    image,
    x: int,
    y: int,
    target_color: tuple,
    tolerance: int = 10
):
    """
    检查指定 Canvas 坐标像素颜色

    Args:
        image:
            OpenCV BGR image

        x,y:
            Canvas 坐标

        target_color:
            RGB颜色，例如 (255,220,50)

        tolerance:
            每个通道允许误差

    Returns:
        bool
    """

    if image is None:
        return False

    h, w = image.shape[:2]

    if x < 0 or y < 0 or x >= w or y >= h:
        return False

    # OpenCV 是 BGR
    b, g, r = image[y, x]

    tr, tg, tb = target_color

    return (
        abs(int(r)-tr) <= tolerance and
        abs(int(g)-tg) <= tolerance and
        abs(int(b)-tb) <= tolerance
    )


def check_region_color(
    image,
    x: int,
    y: int,
    width: int,
    height: int,
    target_color: tuple,
    tolerance: int = 20,
    threshold: float = 0.5
):
    """
    检查 Canvas 区域颜色占比

    Returns:
        bool
    """

    if image is None:
        return False

    h, w = image.shape[:2]

    x1 = max(0, x)
    y1 = max(0, y)
    x2 = min(w, x + width)
    y2 = min(h, y + height)

    if x1 >= x2 or y1 >= y2:
        return False

    roi = image[y1:y2, x1:x2]

    # BGR
    b = roi[:,:,0].astype(int)
    g = roi[:,:,1].astype(int)
    r = roi[:,:,2].astype(int)

    tr, tg, tb = target_color

    mask = (
        (abs(r-tr) <= tolerance) &
        (abs(g-tg) <= tolerance) &
        (abs(b-tb) <= tolerance)
    )

    ratio = mask.mean()

    return ratio >= threshold


def check_region_color_cached(
    x: int, y: int, w: int, h: int,
    target_color: tuple,
    tolerance: int = 20,
    threshold: float = 0.5,
    hwnd: int = None,
) -> bool:
    """在缓存快照上做区域颜色检查

    坐标 x/y/w/h 为 1600×902 参考系, 内部按缓存图像尺寸缩放。
    缓存由后台 CDP 线程每 ~0.15s 刷新, 避免每次调用都发起一次完整截图。
    """
    clear_cache()
    img = _get_cached_canvas(hwnd)
    if img is None:
        return False
    ch, cw = img.shape[:2]
    sx = cw / REF_W
    sy = ch / REF_H
    rx = int(x * sx)
    ry = int(y * sy)
    rw = int(round(w * sx))
    rh = int(round(h * sy))
    return bool(check_region_color(
        img, rx, ry, rw, rh, target_color,
        tolerance=tolerance, threshold=threshold,
    ))


def analyze_pixel_color(
    image,
    x,
    y,
    target_color=None,
    tolerance=10
):
    """
    Canvas坐标像素颜色分析

    target_color:
        RGB
    """

    h, w = image.shape[:2]

    if not (0 <= x < w and 0 <= y < h):
        return {
            "match": False,
            "error": "out_of_bounds"
        }

    # OpenCV BGR
    b, g, r = image[y, x]

    rgb = (
        int(r),
        int(g),
        int(b)
    )

    result = {
        "x": x,
        "y": y,
        "rgb": rgb
    }

    if target_color:

        tr, tg, tb = target_color

        distance = max(
            abs(rgb[0]-tr),
            abs(rgb[1]-tg),
            abs(rgb[2]-tb)
        )

        result.update({
            "target": target_color,
            "distance": distance,
            "match": distance <= tolerance
        })

    return result


def analyze_region_color(
    image,
    x,
    y,
    width,
    height,
    target_color=None,
    tolerance=20
):

    h, w = image.shape[:2]

    roi = image[
        max(0,y):min(h,y+height),
        max(0,x):min(w,x+width)
    ]

    if roi.size == 0:
        return {
            "match": False,
            "error": "empty_region"
        }

    rgb = roi[:,:,::-1].astype(int)

    result = {
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "total_pixels":
            int(rgb.shape[0]*rgb.shape[1]),
        "average_rgb":
            tuple(
                rgb.mean(axis=(0,1)).astype(int)
            )
    }

    if target_color:

        diff = abs(
            rgb -
            target_color
        )

        mask = (
            (diff[:,:,0] <= tolerance) &
            (diff[:,:,1] <= tolerance) &
            (diff[:,:,2] <= tolerance)
        )

        matched = int(mask.sum())

        result.update({
            "matched_pixels": matched,
            "ratio":
                matched /
                result["total_pixels"]
        })

    return result
