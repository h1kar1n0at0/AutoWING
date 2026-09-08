"""
SKILL_LEARN Flow — 技能学习

每 tick 由 TrainingFlow 调用, 返回 Action 给 Orchestrator 执行。
"""
from __future__ import annotations
import logging
from typing import Optional
import time

from app.engine.action import Action, WaitAction, SequenceAction
from app.engine.action_utils import click_xy, click_skill_learning, click_back, click_enter_skill_learning
from app.engine.config_models import config_manager
from app.engine.flows.base import Flow
from app.engine.context import Context
from app.engine.detector import TemplateDetector,PageState

logger = logging.getLogger("autowing.engine.flows.skill_learn")


class SkillLearnFlow(Flow):
    """技能学习: 遍历 skill_learn_order 坐标数组"""

    def __init__(self):
        self._detector = TemplateDetector()
        self._step = "wait_idle"   # wait_idle / click_position / check_result / confirm
        self._idx = 0
        self._retry = 0
        self._learned: set[int] = set()
        self._max_retry = 3
        self._state_wait_start = 0.0
        self._state_wait_timeout = 10.0  # 10 秒超时
        logger.info("🔧 SkillLearnFlow 初始化完成")

    # ── 内部 ──────────────────────────────────

    def _next_unlearned(self) -> Optional[int]:
        order = config_manager.config.skill_learn_order
        logger.info(f"🔍 _next_unlearned: order={order}, _idx={self._idx}, _learned={self._learned}")
        while self._idx < len(order) and self._idx in self._learned:
            logger.info(f"   跳过已学习的 #{self._idx}")
            self._idx += 1
        result = self._idx if self._idx < len(order) else None
        logger.info(f"   _next_unlearned 返回: {result}")
        return result

    def is_all_learned(self) -> bool:
        order = config_manager.config.skill_learn_order
        if not order:
            logger.info("🔍 is_all_learned: order 为空，返回 True")
            return True
        result = len(self._learned) >= len(order)
        logger.info(f"🔍 is_all_learned: learned={len(self._learned)}/{len(order)}, result={result}")
        return result

    def reset(self) -> None:
        logger.info("🔄 SkillLearnFlow.reset() 被调用")
        self._step = "wait_idle"
        self._idx = 0
        self._retry = 0
        self._learned = set()

    # ── 主入口 ────────────────────────────────

    def step(self, ctx: Context) -> Optional[Action]:
        
        ctx.season_data["in_multi_step_decision"] = True
        
        order = config_manager.config.skill_learn_order
        if not order:
            logger.warning("⚠️ skill_learn_order 为空，技能学习 Flow 退出")
            ctx.season_data["in_multi_step_decision"] = False
            return SequenceAction(actions=(WaitAction(seconds=0.05),click_back(),WaitAction(seconds=0.05)))
            
        if self.is_all_learned():
            logger.info("✅ 所有技能已学习完成，退出")
            ctx.season_data["in_multi_step_decision"] = False
            return SequenceAction(actions=(WaitAction(seconds=0.05),click_back(),WaitAction(seconds=0.05)))

        # WAIT_IDLE: 等待 learning_idle
        if self._step == "wait_idle":
            logger.info("⏳ wait_idle: 检测技能学习状态...")
            state = self._detector.detect_skill_learning_state()
            logger.info(f"   检测到 state = {state}")
            
            if state == "paused":
                logger.info("⏸️ 检测到 pause_skill_learning, 终止")
                ctx.season_data["in_multi_step_decision"] = False
                return SequenceAction(actions=(WaitAction(seconds=0.05),click_back(),WaitAction(seconds=0.05)))
            
            if state != "idle":
                logger.info(f"   状态不是 idle ({state})，等待中...")
                now = time.time()
                if self._state_wait_start == 0.0:
                    self._state_wait_start = now
                elif now - self._state_wait_start >= self._state_wait_timeout:
                    logger.warning(f" 等待状态超时 ({self._state_wait_timeout}s)，检查页面状态...")
                    # 检查是否还在技能学习页面
                    page = self._detector.detect_page()
                    if page != PageState.SKILL_UNLOCK:
                        logger.info(f"   当前页面不是 SKILL_UNLOCK ({page})，尝试重新进入 SKILL_UNLOCK 页面")
                        # 这里你可以自定义返回逻辑
                        return SequenceAction(actions=(
                                    click_back(),
                                    WaitAction(seconds=0.3),
                                    click_enter_skill_learning(),
                                ))
                    else:
                        logger.info("   仍在 SKILL_UNLOCK 页面，继续等待...")
                        # 重置超时计时器，继续等待
                        self._state_wait_start = now
                        return click_xy(759, 439)
                return click_xy(759,439)

            logger.info("   状态是 idle，准备学习下一个技能")
            next_idx = self._next_unlearned()
            if next_idx is None:
                logger.info("   没有未学习的技能了")
                ctx.season_data["in_multi_step_decision"] = False
                return SequenceAction(actions=(WaitAction(seconds=0.05),click_back(),WaitAction(seconds=0.05)))

            self._step = "click_position"
            self._retry = 0
            logger.info(f" 准备学习技能 #{next_idx}")
            return WaitAction(seconds=0.3)

        # CLICK_POSITION: 点击技能位置
        if self._step == "click_position":
            logger.info(f" click_position: _idx={self._idx}, order len={len(order)}")
            if self._idx < len(order):
                entry = order[self._idx]
                x, y = entry["x"], entry["y"]
                label = entry.get("label", f"技能#{self._idx}")
                logger.info(f"   点击技能: {label} 坐标=({x:.0f},{y:.0f})")
                self._step = "check_result"
                return SequenceAction(actions=(
                    click_xy(x, y, desc=f"选择{label}"),
                    WaitAction(seconds=0.3)
                ))
            else:
                logger.warning(f"   _idx ({self._idx}) 超出 order 长度 ({len(order)})")
                ctx.season_data["in_multi_step_decision"] = False
                return SequenceAction(actions=(WaitAction(seconds=0.05),click_back(),WaitAction(seconds=0.05)))

        # CHECK_RESULT: 检测结果
        if self._step == "check_result":
            logger.info(" check_result: 检测点击结果...")
            state = self._detector.detect_skill_learning_state()
            logger.info(f"   点击后状态: {state}")

            if state == "learned":
                logger.info(f" 技能 #{self._idx} 已学会！")
                self._learned.add(self._idx)
                self._idx += 1
                self._step = "wait_idle"
                logger.info(f"   当前已学习: {self._learned}, 下一个索引: {self._idx}")
                return WaitAction(seconds=0.3)

            if state == "learnable":
                logger.info(f" 技能 #{self._idx} 可学习，进入确认")
                self._step = "confirm"
                return WaitAction(seconds=0.3)

            if state == "paused":
                logger.info("⏸ 检测到终止状态，退出技能学习")
                ctx.season_data["in_multi_step_decision"] = False
                return SequenceAction(actions=(WaitAction(seconds=0.05),click_back(),WaitAction(seconds=0.05)))

            # 无反应 → 重试
            self._retry += 1
            logger.info(f"   无响应或未知状态 ({state})，重试 {self._retry}/{self._max_retry}")
            if self._retry < self._max_retry:
                logger.info(f"    第 {self._retry} 次重试")
                self._step = "click_position"
                return WaitAction(seconds=0.5)
            
            logger.warning(f" 技能 #{self._idx} 重试 {self._max_retry} 次仍失败，跳过")
            self._learned.add(self._idx)
            self._idx += 1
            self._step = "wait_idle"
            logger.info(f"   已跳过，当前已学习: {self._learned}, 下一个索引: {self._idx}")
            return WaitAction(seconds=0.3)

        # CONFIRM: 确认学习
        if self._step == "confirm":
            logger.info(f" confirm: 确认学习技能 #{self._idx}")
            self._learned.add(self._idx)
            self._idx += 1
            self._step = "wait_idle"
            logger.info(f"   已学习: {self._learned}, 下一个索引: {self._idx}")
            logger.info("确认学习完成")
            return click_skill_learning()

        logger.warning(f" 未知的 _step: {self._step}，重置到 wait_idle")
        self._step = "wait_idle"
        ctx.season_data["in_multi_step_decision"] = False
        return SequenceAction(actions=(WaitAction(seconds=0.05),click_back(),WaitAction(seconds=0.05)))