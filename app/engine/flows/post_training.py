"""
POST_TRAINING Flow — 育成结束结果处理

跳过结果画面 → 等待脱离 POST_TRAINING 状态。
"""
from __future__ import annotations
import logging
from typing import Optional

from app.engine.action import Action, WaitAction
from app.engine.action_utils import click_xy
from app.engine.flows.base import Flow
from app.engine.context import Context
from app.engine.detector import TemplateDetector
from app.engine.state import GlobalState

logger = logging.getLogger("autowing.engine.flows.post_training")


class PostTrainingFlow(Flow):
    """跳过育成结果，回到育成前页面"""

    def __init__(self):
        self._detector = TemplateDetector()
        self._tick_count = 0
        self._done = False

    def step(self, ctx: Context) -> Optional[Action]:
        if self._done:
            return None

        # 检测是否已脱离 POST_TRAINING
        gs = self._detector.detect_global()
        ctx.record_global_transition(gs)
        if gs != GlobalState.POST_TRAINING:
            self._done = True
            logger.info("已脱离 POST_TRAINING")
            return None

        self._tick_count += 1

        # 隔一个 tick 点一次跳过，防止过于密集
        if self._tick_count % 3 == 0:
            return click_xy(1170, 990, desc="跳过育成结果")

        return WaitAction(seconds=0.05)
