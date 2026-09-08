"""
动作系统 — Strategy 输出给 Orchestrator 执行的指令

所有 Action 都是 frozen dataclass (不可变)，确保 Strategy
不会通过修改 Action 来间接共享状态。
"""
from __future__ import annotations
from abc import ABC
from dataclasses import dataclass, field
from typing import Optional


class Action(ABC):
    """动作基类 (标记接口)"""
    pass


@dataclass(frozen=True)
class ClickAction(Action):
    """点击指定位置"""
    x: float
    y: float
    wait_after: float = 0
    jitter: int = 5
    description: str = ""


@dataclass(frozen=True)
class LongClickAction(Action):
    """长按"""
    x: float
    y: float
    duration: float = 0.5
    jitter: int = 5
    description: str = ""


@dataclass(frozen=True)
class WaitAction(Action):
    """等待固定时长"""
    seconds: float


@dataclass(frozen=True)
class WaitForStableAction(Action):
    """等待画面区域静止"""
    roi: tuple = (0, 0, 100, 100)       # 逻辑坐标
    timeout: float = 10.0
    diff_threshold: float = 5.0
    min_stable_frames: int = 7


@dataclass(frozen=True)
class WaitForTemplateAction(Action):
    """等待模板出现，可选点击它"""
    template: str
    region: tuple = (0, 0, 1600, 902)
    conf: float = 0.8
    timeout: float = 10.0
    click_on_found: bool = False


@dataclass(frozen=True)
class AccelClickAction(Action):
    """连点加速 + 等待模板退出条件

    替代原 _wait_finish_accel 模式：
    在指定位置持续点击，直到某个模板出现或超时。
    """
    x: float
    y: float
    interval: float = 0.05
    jitter: int = 12
    until_template: Optional[str] = None
    until_region: tuple = (0, 0, 1600, 902)
    until_conf: float = 0.9
    timeout: float = 30.0
    description: str = ""


@dataclass(frozen=True)
class SequenceAction(Action):
    """顺序执行多个动作"""
    actions: tuple = ()  # tuple 保证可哈希 (frozen 要求)

@dataclass(frozen=True)
class QteClickAction(Action):
    """QTE 固定节奏点击
    
    按固定时间间隔点击指定位置，不检测退出条件。
    用于 QTE 节奏点击场景。
    """
    x: float
    y: float
    total_clicks: int = 2        # 总点击次数
    interval: float = 0.5         # 每次点击间隔（秒）
    jitter: int = 0               # 随机抖动（一般 QTE 不需要）
    description: str = "QTE 点击"

@dataclass(frozen=True)
class ScrollAction(Action):
    """在指定位置滚动
    
    对应 scroll_on_canvas()
    """
    x: float                          # 滚动位置 X (参考坐标系)
    y: float                          # 滚动位置 Y (参考坐标系)
    delta_x: float = 0                # 水平滚动量（正=右）
    delta_y: float = -300             # 垂直滚动量（正=下，负=上）
    wait_after: float = 0.2           # 滚动后等待时间
    description: str = "滚动"

@dataclass(frozen=True)
class ContinuousScrollAction(Action):
    """连续滚动（模拟多次拖拽滚动）
    
    对应 continuous_scroll()
    """
    x: float                          # 滚动位置 X (参考坐标系)
    y: float                          # 滚动位置 Y (参考坐标系)
    total_delta_y: float = -1000      # 总滚动量
    steps: int = 5                    # 分几步滚完
    interval: float = 0.3             # 每步间隔（秒）
    wait_after: float = 0.2           # 滚动完成后等待时间
    description: str = "连续滚动"

@dataclass(frozen=True)
class RunTaskAction(Action):
    """启动子任务"""
    task_cls_path: str = ""
    kwargs: dict = field(default_factory=dict)

@dataclass(frozen=True)
class NavigateAction(Action):
    """页面导航动作"""
    action: str  # "refresh" | "back" | "forward" | "goto"
    url: Optional[str] = None  # goto 时使用
    wait_after: float = 2.0  # 导航后等待时间
    description: str = ""  # 可选描述信息


@dataclass(frozen=True)
class RefreshAction(Action):
    """刷新当前页面（语义化封装）"""
    wait_after: float = 2.0
    description: str = ""  # 可选描述信息


@dataclass(frozen=True)
class BackAction(Action):
    """后退到上一页"""
    wait_after: float = 2.0
    description: str = ""  # 可选描述信息


@dataclass(frozen=True)
class ForwardAction(Action):
    """前进到下一页"""
    wait_after: float = 2.0
    description: str = ""  # 可选描述信息