"""
Flow 基类 — 多步流程状态机

Orchestrator 每 tick 调用 flow.step(ctx) 一次，
返回 Action 则执行，返回 None 表示流程完成。

Flow 也可通过 ctx.signal 向 Orchestrator 发送控制信号
（切换流程、停止等）。
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from app.engine.action import Action
from app.engine.context import Context


@dataclass(frozen=True)
class FlowSignal:
    """流程控制信号 — Flow → Orchestrator 的元指令"""
    pass


@dataclass(frozen=True)
class StopSignal(FlowSignal):
    """停止整个自动化"""
    reason: str = ""


@dataclass(frozen=True)
class SwitchFlowSignal(FlowSignal):
    """切换到指定的 Flow 目标"""
    target: str = ""
    kwargs: dict = field(default_factory=dict)  # 传给 Flow 构造器的参数


class Flow(ABC):
    """流程基类

    子类实现 step()，在其中管理内部状态、执行检测、返回动作。
    step() 不阻塞、不直接点击，只返回 Action 或 None。

    如需向 Orchestrator 发送控制信号，设置 ctx.signal 即可。
    """

    @abstractmethod
    def step(self, ctx: Context) -> Optional[Action]:
        """执行一步流程

        Returns:
            Action — 当前 tick 要执行的动作
            None — 流程已完成，Orchestrator 会清除此 Flow
        """
        ...
