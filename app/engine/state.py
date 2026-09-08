"""
游戏状态枚举 — 三层状态体系

检测优先级:
  GlobalState > SeasonState > PageState

由 TemplateDetector 按从高到低优先级匹配模板来判定。
"""
from __future__ import annotations
from enum import Enum, auto


class GlobalState(Enum):
    """全局状态: 游戏的大阶段"""
    UNKNOWN = auto()
    PRE_TRAINING = auto()      # 育成前 (大厅、偶像选择等)
    TRAINING = auto()           # 育成中
    POST_TRAINING = auto()      # 育成结束 (结果画面)


class SeasonState(Enum):
    """季度状态: 育成中的周目"""
    S1 = auto()
    S2 = auto()
    S3 = auto()
    S4 = auto()
    S5 = auto()

    @classmethod
    def from_string(cls, s: str) -> "SeasonState":
        mapping = {f"s{i}": cls(f"S{i}") for i in range(1, 6)}
        return mapping[s.lower()]

    def to_string(self) -> str:
        return self.name.lower()


class PageState(Enum):
    """页面状态: 当前所处子页面"""
    UNKNOWN = auto()
    MAIN = auto()               # 主页面
    SKILL_UNLOCK = auto()       # 技能解锁页面
    SCHEDULE_SELECT = auto()    # 课程&工作&视镜选择页面
    PRE_AUDITION = auto()       # 视镜前 (队伍编成等)
    IN_AUDITION = auto()        # 视镜中 (战斗中)
    POST_AUDITION = auto()      # 视镜结束 (结果)
    STORY = auto()              # 剧情/事件中
