"""
PRE_TRAINING Flow — 育成前设置（状态机模式）

每 tick 由 Orchestrator 调用，返回 Action 给执行层执行。
"""
from __future__ import annotations
import logging
from typing import Optional

from app.engine.action import Action, ClickAction, WaitAction, SequenceAction, WaitForTemplateAction
from app.engine.action_utils import (
    click_switch_training_tab,
    click_training_confirm,
    click_training_difficulty_normal,
    click_training_difficulty_hard,
    click_produce_idol,
    select_te_mission_incomplete,
    select_1st_produce_idol,
    click_training_x3_stamina,
    click_training_star,
    click_energy_item,
    click_xy,
    go_to_produce1,
    go_to_produce2,
    refresh_page,
    continuous_scroll,
)
from app.engine.config_models import config_manager
from app.engine.flows.base import Flow, SwitchFlowSignal
from app.engine.context import Context
from app.engine.detector import TemplateDetector
from app.engine.state import GlobalState
from app.core import clear_cache

logger = logging.getLogger("autowing.engine.flows.pre_training")


class PreTrainingStep:
    IDLE = "idle"
    SWITCH_TAB = "switch_tab"
    DIFFICULTY = "difficulty"
    FORMATION = "formation"
    ENERGY_X3 = "energy_x3"
    MEM = "mem"
    ENERGY_ITEM = "energy_item"
    WAIT_START = "wait_start"
    DONE = "done"


class PreTrainingFlow(Flow):
    """育成前设置：切换 tab → 难度 → 体力倍率 → mem → 道具 → 开始"""

    def __init__(self):
        self._detector = TemplateDetector()
        self._step = PreTrainingStep.IDLE
        self._wait_start_frame_count = 0
        self._done = False
        
        self._off_set=config_manager.config.pre_wait_offset

    # ── 内部检测 ──────────────────────────────

    def _is_training_started(self) -> bool:
        return self._detector.detect_global() == GlobalState.TRAINING

    # ── 主入口 ──────────────────────────────────

    def step(self, ctx: Context) -> Optional[Action]:
        if self._done:
            return None

        # 已经开始育成 → 流程完成
        if self._is_training_started():
            self._done = True
            return None

        return self._route_step(ctx)

    def _route_step(self, ctx: Context) -> Optional[Action]:
        config = config_manager.config

        # ─── IDLE: 首次进入 ──────────────────
        if self._step == PreTrainingStep.IDLE:
            global_state = self._detector.detect_global()
            if global_state != GlobalState.PRE_TRAINING:
                return WaitAction(seconds=0.5)
            logger.info("开始育成前设置...")
            self._step = PreTrainingStep.SWITCH_TAB
            return click_switch_training_tab()

        # ─── SWITCH_TAB: 切换育成 tab ─────────
        if self._step == PreTrainingStep.SWITCH_TAB:
            self._step = PreTrainingStep.DIFFICULTY
            return WaitAction(seconds=0.05)

        # ─── DIFFICULTY: 选择难度 ─────────────
        if self._step == PreTrainingStep.DIFFICULTY:
            self._step = PreTrainingStep.FORMATION
            logger.info("进入育成编队页面")
            self._wait_start_frame_count = 0
            diff = click_training_difficulty_hard() if config.difficulty == "hard" else click_training_difficulty_normal()
            return SequenceAction(actions=(
                diff,
                WaitAction(seconds=0.03),
                click_training_confirm(),                
                WaitAction(seconds=2.5+self._off_set),
            ))

        # ─── FORMATION: 编成 ──────────────
        if self._step == PreTrainingStep.FORMATION:
            if not self._detector.detect_formation():
                if self._wait_start_frame_count > 600:
                    logger.warning("编成页面未就绪，重置流程")
                    self._step = PreTrainingStep.IDLE
                    self._wait_start_frame_count = 0
                    return SequenceAction(actions=(
                        refresh_page(),
                        WaitAction(seconds=15.55),
                    ))
                logger.info("编成页面未就绪，等待...")

                self._wait_start_frame_count += 1
                return WaitAction(seconds=0.15)
            if config.strategy_selection == "TE" and config.auto_continuous_mining:
                logger.info("启用自动连续挖矿，修改育成偶像")
                self._step = PreTrainingStep.ENERGY_X3
                return SequenceAction(actions=(
                    click_produce_idol(),
                    WaitAction(seconds=1.8+self._off_set),
                    select_te_mission_incomplete(),
                    WaitAction(seconds=2+self._off_set),
                    select_1st_produce_idol(),
                    WaitAction(seconds=2+self._off_set),
                    click_training_confirm(),
                    WaitAction(seconds=1.5+self._off_set),
                ))
            self._step = PreTrainingStep.ENERGY_X3
            logger.info("完成育成前编成")
            return SequenceAction(actions=(
                click_training_confirm(),
                WaitAction(seconds=1.5+self._off_set),
            ))

        # ─── ENERGY_X3: 体力倍率 ──────────────
        if self._step == PreTrainingStep.ENERGY_X3:
            self._wait_start_frame_count = 0
            self._step = PreTrainingStep.MEM
            logger.info("配置体力倍率")
            if config.energy_multiplier == 3:
                return SequenceAction(actions=(
                    click_training_x3_stamina(),
                    WaitAction(seconds=0.05),
                    click_training_star(),
                    WaitAction(seconds=0.8)
                    ))
            return SequenceAction(actions=(
                click_training_star(),
                WaitAction(seconds=0.8),))

        # ─── MEM: 选择 mem 道具 ──────────────
        if self._step == PreTrainingStep.MEM:
            self._step = PreTrainingStep.ENERGY_ITEM
            logger.info("配置育成道具")
            if config.use_mem:
                clear_cache()
                mem_hit = self._detector.detect_mem_unselected()
                if mem_hit:
                    logger.info("找到 mem 槽位")
                    return SequenceAction(actions=(
                        click_xy(mem_hit.x, mem_hit.y, desc="选择mem"),
                        WaitAction(seconds=0.05),
                        click_training_confirm(),
                        WaitAction(seconds=0.07)
                    ))
                logger.info("mem 未检测到，终止执行")
                return None
            return SequenceAction(actions=(click_training_confirm(),
                                           WaitAction(0.07),))

        # ─── ENERGY_ITEM: 体力道具 ───────────
        if self._step == PreTrainingStep.ENERGY_ITEM:
            self._step = PreTrainingStep.WAIT_START
            clear_cache()
            self._wait_start_frame_count = 0
            need_item = self._detector.detect_energy_item()
            if need_item:
                if config.use_energy_item:
                    logger.info("使用体力道具")
                    return click_energy_item()
                logger.warning("体力不足但未启用自动使用，停止执行")
                self._done = True
                return None
            return WaitAction(seconds=0.05)

        # ─── WAIT_START: 等待开始按钮 ────────
        if self._step == PreTrainingStep.WAIT_START:
            start_hit = self._detector.detect_start_ready()
            if start_hit:
                logger.info("开始按钮就绪，准备进入育成")

                # 1. 刷新 Context 状态：记录全局状态切换为 TRAINING
                # 这一步会自动把 ctx.global_state 设为 GlobalState.TRAINING，并清空旧的 season_data 脏数据！
                ctx.record_global_transition(GlobalState.TRAINING)

                # 2. 发送信号通知 Orchestrator 切换到 TrainingFlow
                ctx.signal = SwitchFlowSignal(
                    target="training",
                    kwargs={"sub_state": "event_skip"},
                )

                # 3. 返回执行点击开始按钮的组合动作
                return SequenceAction(actions=(
                    click_xy(start_hit.x, start_hit.y, desc="开始育成"),
                    WaitAction(seconds=0.5),
                    go_to_produce1(),
                    WaitAction(seconds=0.15),
                    go_to_produce2(),               
                ))
            
            self._wait_start_frame_count += 1
            if self._wait_start_frame_count == 5:
                clear_cache()
                need_item = self._detector.detect_energy_item()
                if need_item:
                    if config.use_energy_item:
                        logger.info("使用体力道具")
                        return click_energy_item()
                    logger.warning("体力不足但未启用自动使用，停止执行")
                    self._done = True
                    return None
            if self._wait_start_frame_count > 600:
                logger.warning("等待开始按钮超时，重置流程")
                self._step = PreTrainingStep.IDLE
                self._wait_start_frame_count = 0
                return SequenceAction(actions=(
                    refresh_page(),
                    WaitAction(seconds=15.55),
                ))

        return WaitAction(seconds=0.05)

    def set_step(self, step: str) -> None:
        """外部切换当前步骤"""
        # 安全获取所有字符串类型的值（跳过私有属性和非字符串）
        valid_steps = [
            v for v in vars(PreTrainingStep).values() 
            if isinstance(v, str) and not v.startswith("_")
        ]
        
        if step in valid_steps:
            self._step = step
            self._done = False
            self._wait_start_frame_count = 0  # 建议同时重置计时器
            logger.info(f"PreTrainingFlow step 切换到: {step}")
        else:
            raise ValueError(f"无效的 step: {step}，可选值: {valid_steps}")