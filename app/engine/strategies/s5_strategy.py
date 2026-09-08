"""
S5 策略 — WING半决赛及决赛: 参加WING半决赛/决赛或直接结算
"""
from __future__ import annotations
from typing import Optional

import logging
from app.engine.registry import StrategyRegistry
from app.engine.strategy import SeasonStrategy
from app.engine.state import SeasonState, PageState
from app.engine.context import Context
from app.engine.action import Action, SequenceAction, WaitAction, LongClickAction
from app.engine.action_utils import (
    click_audition,
    click_rest,
    click_energy_item,
    click_enter_skill_learning,
    click_schedule,
    click_training_confirm,
    skip_story_with_multiple_clicks,
    skip_story_with_multiple_clicks_final,click_xy,
)
from app.engine.config_models import config_manager
from app.engine.strategies.s1_strategy import _handle_promise, _handle_forced_action

logger = logging.getLogger("autowing.engine.strategies.s5")

@StrategyRegistry.register(SeasonState.S5)
class S5Strategy(SeasonStrategy):
    """S5 — WING半决赛及决赛: 参加WING半决赛/决赛或直接结算"""

    season = SeasonState.S5

    def get_action(self, page: PageState, ctx: Context) -> Optional[Action]:
        # ── MAIN ──────────────────────────
        strategy = config_manager.config.strategy_selection
        if strategy == "230":
            logger.info("策略选择为 230，结束育成")
            ctx.season_data["signal"]="event_skip_final"
            return SequenceAction(actions=(
                click_xy(1503,176),
                WaitAction(seconds=0.05),
                LongClickAction(x=1018, y=589, duration=3.5, description="退出育成"))
            )
        else:
            logger.info("进行决赛/半决赛视镜")
            ctx.season_data["signal"]="audition_fight"
            return  SequenceAction(actions=(click_schedule(), WaitAction(seconds=2.5)))