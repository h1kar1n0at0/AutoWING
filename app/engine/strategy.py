"""
策略抽象基类 — 每种季度玩法实现一个子类
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional

from app.engine.state import GlobalState, SeasonState, PageState
from app.engine.context import Context
from app.engine.action import Action


class SeasonStrategy(ABC):
    """季度策略基类

    子类只需：
      1. 设置 season 属性
      2. 实现 get_action() — 当前页面下该做什么
      3. 可选覆写 on_enter_xxx hooks

    get_action() 返回 None 表示 "没需要做的事，继续检测"。
    """

    @property
    @abstractmethod
    def season(self) -> SeasonState:
        """此策略处理哪个季度"""
        ...

    # ── 生命周期 hooks ──────────────────────

    def on_enter_global(self, state: GlobalState, ctx: Context) -> None:
        """进入全局状态时"""
        pass

    def on_exit_global(self, state: GlobalState, ctx: Context) -> None:
        """离开全局状态时"""
        pass

    def on_enter_page(self, page: PageState, ctx: Context) -> None:
        """进入子页面时"""
        pass

    def on_exit_page(self, page: PageState, ctx: Context) -> None:
        """离开子页面时"""
        pass

    # ── 决策 ─────────────────────────────────

    @abstractmethod
    def get_action(self, page: PageState, ctx: Context) -> Optional[Action]:
        """根据当前页面状态返回要执行的动作

        返回 None = 此 tick 不需要动作，Orchestrator 会继续循环检测。
        不要在 get_action 里阻塞或 sleep — 由 Orchestrator 处理。
        """
        ...

    # ── 错误恢复 ─────────────────────────────

    def on_error(self, page: PageState, ctx: Context,
                 error: Exception) -> Optional[Action]:
        """动作执行出错时的恢复

        返回恢复动作，或 None 让 Orchestrator 走默认错误处理。
        """
        return None
