"""
坐标系统 — Canvas 感知的三层坐标映射

  参考坐标 (基于模板截图时的 canvas 尺寸, 默认 1600×902)
       ↓  × scale_factor (实际canvas尺寸 / 参考尺寸)
  Canvas 渲染像素坐标
       ↓  + canvas 屏幕偏移
  屏幕绝对坐标 (用于 find/find_all/click)

ref_w/ref_h 始终固定在 1600×902 (模板截图基准), 从不改变。
canvas_width/height 随窗口大小变化, scale 自动计算。
"""
from __future__ import annotations

import attr

from app.config import config

# 参考分辨率（模板截图基准），与 CoordSystem.ref_w/ref_h 保持一致
REF_W = 1600
REF_H = 902


@attr.s(auto_attribs=True)
class CoordSystem:
    """坐标换算核心"""

    # 模板截图时的基准分辨率（ShinyColors 游戏 Canvas 尺寸）
    ref_w: int = 1600
    ref_h: int = 902

    # 游戏内 Canvas 的逻辑像素（CSS 像素）
    logical_w: int = 1136
    logical_h: int = 640

    # Canvas 在屏幕上的位置和当前渲染尺寸
    canvas_left: int = 0
    canvas_top: int = 0
    canvas_width: int = 1600
    canvas_height: int = 902

    _calibrated: bool = False

    # ── 属性 ──────────────────────────────────

    @property
    def scale_x(self) -> float:
        """X 轴缩放比: 当前渲染尺寸 / 参考尺寸"""
        if self.ref_w == 0:
            return 1.0
        return self.canvas_width / self.ref_w

    @property
    def scale_y(self) -> float:
        if self.ref_h == 0:
            return 1.0
        return self.canvas_height / self.ref_h

    @property
    def is_calibrated(self) -> bool:
        return self._calibrated

    # ── 校准 ──────────────────────────────────

    def calibrate(self, *, canvas_left=None, canvas_top=None,
                  canvas_width=None, canvas_height=None):
        """设置实际检测到的画布位置

        ref_w/ref_h 始终维持 1600×902 不变,
        只有 canvas 的实际屏幕位置和渲染尺寸会更新。
        """
        if canvas_left is not None:
            self.canvas_left = canvas_left
        if canvas_top is not None:
            self.canvas_top = canvas_top
        if canvas_width is not None:
            self.canvas_width = canvas_width
        if canvas_height is not None:
            self.canvas_height = canvas_height

        self._calibrated = True
        config.calibration = {
            "canvas_left": self.canvas_left,
            "canvas_top": self.canvas_top,
            "canvas_width": self.canvas_width,
            "canvas_height": self.canvas_height,
        }

    def calibrate_from_canvas_element(self, left, top, width, height):
        self.calibrate(canvas_left=left, canvas_top=top,
                       canvas_width=width, canvas_height=height)

    def load_calibration(self):
        """从配置恢复校准数据 (ref_w/ref_h 保持默认 1600×902)"""
        cal = config.calibration
        self.calibrate(
            canvas_left=cal.get("canvas_left", 0),
            canvas_top=cal.get("canvas_top", 0),
            canvas_width=cal.get("canvas_width", 1600),
            canvas_height=cal.get("canvas_height", 902),
        )

    # ── 坐标换算 ──────────────────────────────

    def to_screen(self, rx: float, ry: float) -> tuple[int, int]:
        """参考坐标 → 屏幕绝对像素坐标"""
        return (
            int(self.canvas_left + rx * self.scale_x),
            int(self.canvas_top + ry * self.scale_y),
        )

    def region_to_screen(self, rx: float, ry: float,
                         rw: float, rh: float) -> tuple[int, int, int, int]:
        """参考 region → 屏幕 region"""
        return (
            int(self.canvas_left + rx * self.scale_x),
            int(self.canvas_top + ry * self.scale_y),
            int(rw * self.scale_x),
            int(rh * self.scale_y),
        )

    def screen_to_ref(self, sx: int, sy: int) -> tuple[float, float]:
        if not self._calibrated:
            return (float(sx), float(sy))
        return (
            (sx - self.canvas_left) / self.scale_x,
            (sy - self.canvas_top) / self.scale_y,
        )

    # ── 别名 ──────────────────────────────────

    def logical_to_screen(self, lx: float, ly: float) -> tuple[int, int]:
        return self.to_screen(lx, ly)

    def logical_region(self, lx: float, ly: float,
                       lw: float, lh: float) -> tuple[int, int, int, int]:
        return self.region_to_screen(lx, ly, lw, lh)

    # ── 状态描述 ──────────────────────────────

    def description(self) -> str:
        if not self._calibrated:
            return "未校准"
        return (f"Canvas: 参考 {self.ref_w}×{self.ref_h}"
                f" → {self.canvas_width}×{self.canvas_height}px"
                f" @ ({self.canvas_left},{self.canvas_top})"
                f" 缩放: X={self.scale_x:.1%} Y={self.scale_y:.1%}")


coord = CoordSystem()
