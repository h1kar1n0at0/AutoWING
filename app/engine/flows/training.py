"""
TRAINING Flow — 育成主循环

核心设计哲学（事件/响应驱动）：
1. 常态（STORY_SKIP）：主基调是高速点击跳过，同时检测剧情选项（如有则策略选择）。
2. 路标触发（MAIN_PAGE）：仅在检测到 MAIN 画面稳定标志时切入，进行“一站式检查（季度/技能）与决策”。
3. 视镜子流程（AUDITION）：由策略行动或视镜标志触发，交给视镜 Flow 闭环处理。
"""
from __future__ import annotations
import logging
import time
from typing import Optional

from app.engine.action import Action, WaitAction, SequenceAction
from app.engine.action_utils import (
    click_xy, click_skip, skip_story_with_multiple_clicks, refresh_page, click_end_training,go_to_produce_ready,go_back,go_forward,click_enter_skill_learning
)
from app.engine.flows.base import Flow, StopSignal, SwitchFlowSignal
from app.engine.flows.audition import AuditionFightFlow, AuditionResultFlow
from app.engine.flows.skill_learn import SkillLearnFlow
from app.engine.context import Context
from app.engine.detector import TemplateDetector
from app.engine.registry import StrategyRegistry
from app.engine.state import GlobalState, SeasonState, PageState
from app.engine.config_models import config_manager
from app.engine.strategy import SeasonStrategy
from app.core import clear_cache

logger = logging.getLogger("autowing.engine.flows.training")

class TrainingFlow(Flow):
    """育成主循环 — 基于事件与路标切入的状态机"""

    def __init__(self, sub_state: str = "event_skip"):
        self._detector = TemplateDetector()
        self._strategy: Optional[SeasonStrategy] = None
        
        # 核心模式: "event_skip" (默认常态) / "main_page" / "audition_fight" / "audition_result" / "skill_learn"
        self._sub_state = sub_state

        # 统计与记录
        self._turn_count = 0
        self._last_detail_tick = 0
        self._consecutive_unknowns = 0
        self._event_skip_entered_at: float = time.monotonic()
        self._event_skip_min_duration: float = 0.5  # 秒

        # 约定标记
        self._has_active_promise = False

        # 动作冷却与标记
        self._action_cooldown = 0
        self._skill_learned_flag = False  # 技能学习检查标记
        self._main_page_warmed = False

        # ── 子状态 Flow 实例 ──
        self._audition_fight: Optional[AuditionFightFlow] = None
        self._audition_result: Optional[AuditionResultFlow] = None
        self._skill_learn: Optional[SkillLearnFlow] = None

        self._last_season: Optional[SeasonState] = None

    # ═══════════════════════════════════════════
    # 主入口 (Flow 执行锁保护中)
    # ═══════════════════════════════════════════

    def step(self, ctx: Context) -> Optional[Action]:
        """
        每 tick 调用一次
        """

        clear_cache()
        # 1. 常态：剧情跳过模式
        if self._sub_state == "event_skip":
            return self._step_event_skip(ctx)

        # 2. 切入：主界面一站式检查与决策
        if self._sub_state == "main_page":
            return self._step_main_page(ctx)

        # 3. 视镜战斗 / 结算子 Flow
        if self._sub_state == "audition_fight":
            return self._step_audition_fight(ctx)
        if self._sub_state == "audition_result":
            return self._step_audition_result(ctx)

        # 4. 技能学习子 Flow
        if self._sub_state == "skill_learn":
            return self._step_skill_learn(ctx)

        if self._sub_state == "event_skip_final":
            return self._step_event_skip_final(ctx)

        # 防御性回退到常态
        self._enter_event_skip()
        return WaitAction(seconds=0.05)

    # ═══════════════════════════════════════════
    # 模式 1：跳过剧情 (常态主基调)
    # ═══════════════════════════════════════════

    def _step_event_skip(self, ctx: Context) -> Optional[Action]:
        # A. 检查是否有剧情分支选项（优先响应）
        option_action = self._check_and_handle_story_option(ctx)
        if option_action:
            return option_action

        # 时间闸：进入 event_skip 后至少 0.5 秒内不退出
        elapsed = time.monotonic() - self._event_skip_entered_at
        if elapsed < self._event_skip_min_duration:
            return skip_story_with_multiple_clicks()

        # B. 探查标志：是否已经稳定进入 MAIN 界面？
        if self._detector.is_main_page():  # 对应 match main template
            logger.info("【路标】到达 MAIN 界面，切入决策模式")
            self._sub_state = "main_page"
            self._consecutive_unknowns = 0
            return WaitAction(seconds=0.25)

        # C. 探查标志：是否直接触发了视镜前画面？(如视镜前剧情播放完进入战斗)
        if self._detector._is_pre_audition():
            logger.info("【路标】检测到视镜前画面，准备切入视镜战斗")
            opts = self._detector.detect_tension()
            if opts:
                logger.info("检测到视镜前剧情选项，调用策略进行选择")
                if self._strategy:
                    self._audition_fight = AuditionFightFlow()
                    self._sub_state = "audition_fight"
                    action = self._strategy.get_option_action(opts,ctx)
                    return action
            else:
                logger.info("等待视镜前剧情选项出现")
                return skip_story_with_multiple_clicks()

        if self._detector._is_in_audition():
            logger.info("【路标】检测到视镜战斗中，切入视镜战斗 Flow")
            self._audition_fight = AuditionFightFlow()
            self._sub_state = "audition_fight"
            return WaitAction(seconds=0.05)
        
        self._consecutive_unknowns += 1

        # 极罕见的死锁兜底：连续 200 tick 处于 UNKNOWN 且完全摸不到任何路标
        if self._consecutive_unknowns > 200:
            error_action = self._check_and_handle_error(ctx)
            if error_action:
                logger.warning("检测到界面异常/报错弹窗，执行恢复动作")
                # 触发了报错处理后重置计数器，等待弹窗关闭
                self._consecutive_unknowns = 0
                return error_action
            
        # 如果等待超过 2 分钟仍然没有进入 MAIN 或视镜前画面，停止flow，避免无限循环
        if self._consecutive_unknowns > 2400:
            ctx.signal = StopSignal(reason="育成流程卡死超时 (2 min unknowns)")
            return None  # 退出

        # E. 常态执行：高速连续点击 Skip
        return skip_story_with_multiple_clicks()


    def _step_event_skip_final(self, ctx: Context) -> Optional[Action]:
        # 探查标志：是否已经进入结算界面？
        if self._detector.detect_post_training():
            logger.info("【路标】到达结算界面，结算育成")
            self._sub_state = "main_page"
            self._consecutive_unknowns = 0
            ctx.signal = SwitchFlowSignal(
                                target="idle",
                                kwargs={"training_done": True},
                            )
            return SequenceAction(actions=(click_end_training(), WaitAction(seconds=0.5), go_to_produce_ready()))

        self._consecutive_unknowns += 1

        # 极罕见的死锁兜底：连续 ~30 秒 (600 tick) 处于 UNKNOWN 且完全摸不到任何路标
        if self._consecutive_unknowns > 600:
            error_action = self._check_and_handle_error(ctx)
            if error_action:
                logger.warning("检测到界面异常/报错弹窗，执行恢复动作")
                # 触发了报错处理后重置计数器，等待弹窗关闭
                self._consecutive_unknowns = 0
                return error_action
            
        # 如果等待超过 2 分钟仍然没有进入 MAIN 或视镜前画面，停止flow，避免无限循环
        if self._consecutive_unknowns > 2400:
            ctx.signal = StopSignal(reason="育成流程卡死超时 (2 min unknowns)")
            return None  # 退出

        # E. 常态执行：高速连续点击 Skip
        return skip_story_with_multiple_clicks()


    def _check_and_handle_story_option(self, ctx: Context) -> Optional[Action]:
        """检查并处理剧情分支选项"""
        opts = self._detector.detect_regular()
        if opts:
            logger.info("检测到剧情选项，调用策略进行选择")
            if self._strategy:
                action = self._strategy.get_option_action(opts,ctx)
                if action:
                    return action
        return None

    # ═══════════════════════════════════════════
    # 模式 2：MAIN 界面（一站式检查与决策）
    # ═══════════════════════════════════════════

    def _step_main_page(self, ctx: Context) -> Optional[Action]:
        if not self._main_page_warmed:
            self._main_page_warmed = True
            return WaitAction(seconds=0.05) 
        self._main_page_warmed = False
        # A. 检查/更新季度
        season = self._detector.detect_season()
        if season and season != self._last_season:
            self._last_season = season
            ctx.record_season_transition(season)
            logger.info(f"季度更新: {season.name}")
            self._load_strategy(season)

        
        week = self._detector.detect_week()
        if season!= SeasonState.S5 and week == 0:
            return WaitAction(0.05)  # 未检测到周数，等待稳定
        
        # B. 校验技能学习节点 (二季度视镜前 / 三季度刚进入)
        if self._should_trigger_skill_learn(ctx):
            logger.info("满足技能学习节点条件，进入技能学习 Flow")
            self._skill_learn = SkillLearnFlow()
            self._sub_state = "skill_learn"
            return click_enter_skill_learning()

        # C. 定期更新数值
        self._turn_count += 1
        if self._turn_count - self._last_detail_tick >= 5:
            self._last_detail_tick = self._turn_count

        # D. 执行决策链 (包含：视镜 / 休息 / 日程 / 约定)
        action = self._decision_chain(ctx)

        in_multi_step = ctx.season_data.get("in_multi_step_decision", False)

        # 只有在流程结束且“确实输出了动作”时，才切回剧情跳过模式
        if action is not None and not in_multi_step or action is None and not in_multi_step:
            logger.info("决策动作已下发，切回剧情跳过模式")
            self._enter_event_skip()
            
        if season == SeasonState.S5:
            self._sub_state = "audition_fight"

        signal = ctx.season_data.get("signal", None)
        if signal is not None:
            logger.info(f"检测到信号: {signal}, 切换模式")
            if signal == "event_skip_final":
                self._sub_state = "event_skip_final"
                logger.info("切换到最终剧情跳过模式")
            elif signal == "audition_fight":
                
                self._audition_fight = AuditionFightFlow()
                self._sub_state = "audition_fight"
                logger.info("切换到视镜战斗模式")
            ctx.season_data.pop("signal", None)
        return action

    def _should_trigger_skill_learn(self, ctx: Context) -> bool:
        """精准判断是否触发技能学习"""
        # 1. S2 视镜前 (周数=2 且未检查过)
        if ctx.season == SeasonState.S2 and not self._skill_learned_flag:
            week = self._detector.detect_week()
            logger.info(f"检测到 S2 周数={week}，技能学习标记={self._skill_learned_flag}")
            if week == 2 and self._detector.detect_season_task_completed() is False:
                self._skill_learned_flag= True
                return True

        # 2. S3 刚进入 (未检查过)
        if ctx.season == SeasonState.S3 and not self._skill_learned_flag:
            self._skill_learned_flag= True
            return True

        return False

    # ═══════════════════════════════════════════
    # MAIN 页面决策链
    # ═══════════════════════════════════════════

    def _decision_chain(self, ctx: Context) -> Optional[Action]:
        """季度任务 → 约定 → 体力 → 策略 (输出：视镜/休息/日程)"""
        page = self._detector.detect_page()

        ctx.season_data.pop("forced_action", None)
        week = self._detector.detect_week()
        ctx.remaining_weeks = week if week is not None else ctx.remaining_weeks

        if week == 0 and ctx.season!= SeasonState.S5:
            return WaitAction(seconds=0.05)  # 未检测到周数，等待稳定
        # 1. 季度任务 (S1/S2, 周数=2 且未完成)
        if ctx.season == SeasonState.S2 and config_manager.config.strategy_selection != "230":
            completed = self._detector.detect_season_task_completed()
            if completed is False:
                
                if week == 2:
                    logger.info("季度任务未完成且周数=2 → 强制选择视镜")
                    ctx.season_data["forced_action"] = "audition"
                    return self._call_strategy(page, ctx)
                ctx.season_data["season_task_due"] = True
            elif completed is True:
                ctx.season_data["season_task_done"] = True

        # 2. 约定
        if self._check_promise():
            logger.info("检测到约定待履行")
            ctx.season_data["forced_action"] = "promise"
            ctx.season_data["have_promised"] = True
            return self._call_strategy(page, ctx)

        # 3. 体力
        if (ctx.season in (SeasonState.S1, SeasonState.S2) and config_manager.config.strategy_selection != "230") or (ctx.season == SeasonState.S3 and config_manager.config.strategy_selection == "140"):
            if self._detector.detect_stamina_half():
                logger.info("体力不足一半")
                forced = "rest"
                ctx.season_data["forced_action"] = forced
                return self._call_strategy(page, ctx)

        # 4. 正常策略（决定是 Audition / Rest / Schedule）
        action = self._call_strategy(page, ctx)
        return action if action is not None else WaitAction(seconds=0.05)

    def _check_promise(self) -> bool:
        if not config_manager.config.handle_agreement:
            return False
        return (self._detector.detect_promise_rest()
                or self._detector.detect_promise_schedule())

    # ═══════════════════════════════════════════
    # 子状态: 视镜战斗与结果
    # ═══════════════════════════════════════════

    def _step_audition_fight(self, ctx: Context) -> Optional[Action]:
        if self._audition_fight is None:
            self._enter_event_skip()
            return WaitAction(seconds=0.05)

        action = self._audition_fight.step(ctx)
        if action is not None:
            return action

        # 战斗结束，切换到结算处理子 Flow
        self._audition_fight = None
        self._audition_result = AuditionResultFlow()
        self._sub_state = "audition_result"
        logger.info("战斗结束，进入视镜结果处理")
        return WaitAction(seconds=0.05)

    def _step_audition_result(self, ctx: Context) -> Optional[Action]:
        if self._audition_result is None:
            self._enter_event_skip()
            return WaitAction(seconds=0.05)

        action = self._audition_result.step(ctx)
        if action is not None:
            self._audition_result = None
            self._sub_state = "event_skip_final"
            logger.info("视镜结算完成，切回剧情跳过模式")
            return WaitAction(seconds=0.05)

        # 结果处理完毕，把控制权还给跳过模式（等待返回 MAIN 或剧情）
        else :
            self._audition_result = None
            self._enter_event_skip()
            logger.info("视镜结算完成，切回剧情跳过模式")
            return WaitAction(seconds=0.05)

    # ═══════════════════════════════════════════
    # 子状态: 技能学习
    # ═══════════════════════════════════════════

    def _step_skill_learn(self, ctx: Context) -> Optional[Action]:
        if self._skill_learn is None:
            self._sub_state = "main_page"
            return WaitAction(seconds=0.05)

        action = self._skill_learn.step(ctx)
        if action is not None:
            if ctx.season_data["in_multi_step_decision"] == False:
                self._sub_state = "main_page"
            return action

        # 技能学习完成/退出后，回到 main_page 继续做决策
        else:
            self._skill_learn = None
            self._sub_state = "main_page"
            logger.info("技能学习完成，返回主界面决策")
            return WaitAction(seconds=0.05)

    # ═══════════════════════════════════════════
    # 策略管理
    # ═══════════════════════════════════════════

    def _load_strategy(self, season: SeasonState) -> None:
        strategy = StrategyRegistry.get(season)
        if strategy is None:
            logger.warning(f"季度 {season.name} 无注册策略, 使用默认行为")
            self._strategy = None
        else:
            logger.info(f"加载策略: {type(strategy).__name__}")
            self._strategy = strategy

    def _call_strategy(self, page: PageState, ctx: Context) -> Optional[Action]:
        if self._strategy is None:
            return None
        try:
            action = self._strategy.get_action(page, ctx)
            if action is not None:
                self._action_cooldown = 3
            return action
        except Exception as e:
            logger.error(f"策略决策异常: {e}")
            return None

    def _check_and_handle_error(self, ctx: Context) -> Optional[Action]:
        """检测并处理报错/重连/确认弹窗"""
        # 示例：检测是否有“网络重连”、“确定/关闭”等异常弹窗按钮
        error_hit = self._detector.detect_error_dialog()
        if error_hit:
            return refresh_page()
        return None

    def _enter_event_skip(self) -> None:
        if self._sub_state != "event_skip":
            self._sub_state = "event_skip"
            self._event_skip_entered_at = time.monotonic()