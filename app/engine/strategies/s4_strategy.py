"""
S4 策略 — 第四季度
视策略进行视镜连打或休息跳过回合
"""
from __future__ import annotations
import logging
from typing import Optional, Dict

from app.engine.registry import StrategyRegistry
from app.engine.strategy import SeasonStrategy
from app.engine.state import SeasonState, PageState
from app.engine.context import Context
from app.engine.action import Action, SequenceAction, WaitAction, WaitForStableAction
from app.engine.action_utils import (
    click_xy,
    click_audition,
    click_rest,
    click_energy_item,
    click_confirm_promise,
    click_refuse,
    click_enter_skill_learning,
    click_schedule,
    click_stat_vo,
    click_stat_da,
    click_stat_vi,
    click_stat_rai,
    click_stat_pho,
    click_skip,
    skip_story_with_multiple_clicks,
    click_training_confirm,go_back,go_forward, click_next_audition
)
from app.engine.config_models import config_manager
from app.engine.detector import TemplateDetector
from app.core import clear_cache

logger = logging.getLogger("autowing.engine.strategies.s4")
_detector = TemplateDetector()

# ── main_stat → 课程映射 ─────────────────────
_STAT_COURSE_MAP = {
    "vocal": click_stat_vo,
    "da": click_stat_da,
    "dance": click_stat_da,
    "vi": click_stat_vi,
    "visual": click_stat_vi,
    "radio": click_stat_rai,
    "photo": click_stat_pho,
}


def _get_main_stat_action(ctx):
    """根据 main_stat 返回对应的课程点击函数"""
    strategy = config_manager.config.strategy_selection.lower()
    audition_count = ctx.season_data.get("audition_count", 0)
    if strategy == "230":
        logger.info("策略选择为 230，进行视镜连打")
        if audition_count == 0:
            logger.info("进行100000粉丝视镜")
            
            return SequenceAction(actions=(
                click_audition(),
                WaitAction(seconds=0.05),
                click_next_audition(),
                WaitAction(seconds=0.05),
                click_next_audition(),
                WaitAction(seconds=0.05),
                click_next_audition(),
                WaitAction(seconds=0.05),
                click_training_confirm(),
                WaitAction(seconds=0.05),
            ))
        elif audition_count < 4:
            logger.info("进行200000粉丝视镜")
            
            return SequenceAction(actions=(
                            click_audition(),
                            WaitAction(seconds=0.05),
                            click_next_audition(),
                            WaitAction(seconds=0.05),
                            click_next_audition(),
                            WaitAction(seconds=0.05),
                            click_next_audition(),
                            WaitAction(seconds=0.05),
                            click_next_audition(),
                            WaitAction(seconds=0.05),
                            click_training_confirm(),
                            WaitAction(seconds=0.05),
                        ))
        logger.info("进行300000粉丝视镜")
        
        return SequenceAction(actions=(
                            click_audition(),
                            WaitAction(seconds=0.05),
                            click_next_audition(),
                            WaitAction(seconds=0.05),
                            click_next_audition(),
                            WaitAction(seconds=0.05),
                            click_next_audition(),
                            WaitAction(seconds=0.05),
                            click_next_audition(),
                            WaitAction(seconds=0.05),
                            click_next_audition(),
                            WaitAction(seconds=0.05),
                            click_training_confirm(),
                            WaitAction(seconds=0.05),
                        ))

    if strategy == "140":
        logger.info("策略选择为 140，进行视镜连打")
        if audition_count < 4:
            logger.info("进行100000粉丝视镜")
            
            return SequenceAction(actions=(
                click_audition(),
                WaitAction(seconds=0.05),
                click_next_audition(),
                WaitAction(seconds=0.05),
                click_next_audition(),
                WaitAction(seconds=0.05),
                click_next_audition(),
                WaitAction(seconds=0.05),
                click_training_confirm(),
                WaitAction(seconds=0.05),
            ))
        elif audition_count < 7:
            logger.info("进行200000粉丝视镜")
            
            return SequenceAction(actions=(
                            click_audition(),
                            WaitAction(seconds=0.05),
                            click_next_audition(),
                            WaitAction(seconds=0.05),
                            click_next_audition(),
                            WaitAction(seconds=0.05),
                            click_next_audition(),
                            WaitAction(seconds=0.05),
                            click_next_audition(),
                            WaitAction(seconds=0.05),
                            click_training_confirm(),
                            WaitAction(seconds=0.05),
                        ))
        logger.info("进行300000粉丝视镜")
        
        return SequenceAction(actions=(
                            click_audition(),
                            WaitAction(seconds=0.05),
                            click_next_audition(),
                            WaitAction(seconds=0.05),
                            click_next_audition(),
                            WaitAction(seconds=0.05),
                            click_next_audition(),
                            WaitAction(seconds=0.05),
                            click_next_audition(),
                            WaitAction(seconds=0.05),
                            click_next_audition(),
                            WaitAction(seconds=0.05),
                            click_training_confirm(),
                            WaitAction(seconds=0.05),
                        ))
    
    
    if audition_count < 4:
            logger.info("进行视镜")
            logger.info("进行100000粉丝视镜")
            
            return SequenceAction(actions=(
                click_audition(),
                WaitAction(seconds=0.05),
                click_next_audition(),
                WaitAction(seconds=0.05),
                click_next_audition(),
                WaitAction(seconds=0.05),
                click_next_audition(),
                WaitAction(seconds=0.05),
                click_training_confirm(),
                WaitAction(seconds=0.05),
            ))
            
    
    stat = config_manager.config.main_stat
    if stat is None:
        stat = "vocal"
        logger.warning("main_stat 未配置，使用默认值 'vocal'")
    else:
        stat = stat.lower()
    
    logger.info(f"主属性: {stat}, 检测支援卡加成...")
    support_counts = _detector.detect_support_counts(stat)
    fn = _STAT_COURSE_MAP.get(stat)
    
    if fn is None:
        logger.warning(f"未知的 main_stat: {stat}, 回退到 VO 课程")
        fn = click_stat_vo
    
    if support_counts is not None and support_counts > 0:
        logger.info(f"检测到 {support_counts} 张 {stat} 支援卡加成，选择对应课程")
        ctx.season_data["action_source"] = "schedule"
        return fn()
    
    logger.info(f"未检测到 {stat} 支援卡加成，回退到广播录制")
    ctx.season_data["action_source"] = "schedule"
    return click_stat_rai()


# ── 约定处理 ─────────────────────────────────
def detect_promise_type() -> Optional[str]:
    """检测约定类型 (vo/da/vi/rai/pho)"""
    clear_cache()
    if _detector.detect_promise_rest():
        logger.info("检测到休息约定")
        return "rest"
    if _detector.detect_promise_schedule():
        logger.info("检测到日程约定")
        return "schedule"
    return None


def _handle_promise(ctx: Context) -> Optional[Action]:
    """检测约定并返回处理动作"""
    if not ctx.season_data.get("have_promised"):
        logger.info("没有待履行的约定，跳过")
        return None

    logger.info("检测到待履行的约定，开始处理...")
    promise_type = detect_promise_type()
    
    if promise_type is None:
        logger.warning("无法识别约定类型，跳过处理")
        return None
    
    if promise_type == "rest":
        logger.info("处理休息约定")
        ctx.season_data["in_multi_step_decision"] = False
        return SequenceAction(actions=(
                    click_rest(),
                    WaitAction(seconds=0.05),
                    click_rest(),
                    WaitAction(seconds=0.05),
                    ctx.step_produce_page(),
                    WaitAction(seconds=0.15),
                ))
    
    if promise_type == "schedule":
        logger.info("处理日程约定")
        return SequenceAction(actions=(
            click_schedule(),
            WaitForStableAction((0,705,264,624)),  # 等待日程页面稳定
            WaitAction(seconds=0.05),
        ))
    
    logger.warning(f"未识别的约定类型: {promise_type}")
    return None


def _handle_forced_action(action_type: str, ctx: Context) -> Optional[Action]:
    """处理 orchestrator 下发的强制动作

    Args:
        action_type: "audition" / "rest" / "energy" / "promise"
    """
    logger.info(f"处理强制动作: {action_type}")
    
    if action_type == "audition":
        logger.info("强制动作: 进入视镜")
        ctx.season_data["in_multi_step_decision"] = False
        return SequenceAction(actions=(
            click_schedule(),
            WaitForStableAction((0,705,264,624)),
            click_audition(),
            WaitAction(seconds=0.05),
            click_training_confirm(),
            WaitAction(seconds=0.05),
        ))
    
    if action_type == "rest":
        logger.info("强制动作: 休息")
        ctx.season_data["have_promised"] = False
        ctx.season_data["in_multi_step_decision"] = False
        return SequenceAction(actions=(
                    click_rest(),
                    WaitAction(seconds=0.05),
                    click_rest(),
                    WaitAction(seconds=0.05),
                    ctx.step_produce_page(),
                    WaitAction(seconds=0.15),
                ))
    
    if action_type == "promise":
        logger.info("强制动作: 处理约定")
        if config_manager.config.handle_agreement:
            return _handle_promise(ctx)
        else:
            logger.info("约定处理已禁用，跳过")
            return None
    
    logger.warning(f"未知的强制动作类型: {action_type}")
    return None


# ═══════════════════════════════════════════════
# S4 策略
# ══════════════════════════════════════════════

@StrategyRegistry.register(SeasonState.S4)
class S4Strategy(SeasonStrategy):
    """S4 — 第四季度: 以视镜和休息为主"""

    season = SeasonState.S4

    def __init__(self):
        logger.info("S4Strategy 初始化")
        super().__init__()

    def get_action(self, page: PageState, ctx: Context) -> Optional[Action]:
        logger.info(f"S4Strategy.get_action 被调用: page={page.name}")
        ctx.season_data["in_multi_step_decision"] = True
        
        if page == PageState.MAIN:
            logger.info("页面: MAIN, 进入决策主入口")
            return self._decide_main(ctx)

        if page == PageState.SCHEDULE_SELECT:
            logger.info("页面: SCHEDULE_SELECT, 进入日程选择")
            return self._decide_schedule(ctx)

        logger.info(f"页面 {page.name} 暂不处理")
        return WaitAction(seconds=0.05)

    def get_option_action(self, opts: Dict, ctx: Context) -> Optional[Action]:
        """剧情选项决策"""
        logger.info(f"处理剧情选项，共 {len(opts)} 个选项")
        strategy = config_manager.config.strategy_selection.lower()
        audition_count = ctx.season_data.get("audition_count", 0)
        remaining_weeks = ctx.remaining_weeks
        if opts.get("confirm_promise"):
            logger.info("检测到确认约定选项")
            if config_manager.config.handle_agreement and strategy == "TE" and audition_count + remaining_weeks >= 5:
                ctx.season_data["have_promised"] = True
                logger.info("同意约定")
                return click_confirm_promise()
            logger.info("拒绝约定")
            return click_refuse()
        
        stat = config_manager.config.main_stat
        if stat is None:
            stat = "vo"
            logger.warning("main_stat 未配置，使用默认 'vo'")
        else:
            stat = stat.lower()[:2]  # 取前两个字符
        
        
        if opts.get(stat):
            logger.info(f"选择 {stat} 选项")
            return click_xy(opts[stat].x-150, opts[stat].y+60)
        
        if opts.get("tension_down"):
            logger.info("选择 tension_down 选项")
            return click_xy(opts["tension_down"].x-150, opts["tension_down"].y+60)
        
        if opts.get("perfect") and config_manager.config.strategy_selection.lower() != "230":
            logger.info("选择 perfect 选项")
            return click_xy(opts["perfect"].x-150, opts["perfect"].y+60)
        
        if opts.get("normal"):
            logger.info("选择 normal 选项")
            return click_xy(opts["normal"].x-150, opts["normal"].y+60)
        
        # 默认选第一个选项
        first_key = next(iter(opts.keys()))
        first_opt = opts[first_key]
        logger.info(f"没有匹配的选项，默认选择第一个: {first_key}")
        return click_xy(first_opt.x-150, first_opt.y+60)

    def _decide_main(self, ctx: Context) -> Optional[Action]:
        """MAIN 页面上的决策链

        优先处理 Flow 的 forced_action 标记,
        无标记时走自有决策逻辑。
        """
        logger.info("执行 MAIN 页面决策链...")
        
        # ── 0. 检查 Flow 的强制动作 ──
        forced = ctx.season_data.pop("forced_action", None)
        if forced:
            logger.info(f"检测到强制动作: {forced}")
            ctx.season_data["action_source"] = f"forced_{forced}"
            result = _handle_forced_action(forced, ctx)
            if result:
                logger.info(f"强制动作 {forced} 处理完成")
            else:
                logger.warning(f"强制动作 {forced} 处理失败，返回 None")
            return result

        # ── 1. 默认: 按 main_stat 选课程 ──
        logger.info("无特殊决策，执行默认日程选择")
        audition_count = ctx.season_data.get("audition_count", 0)
        strategy = config_manager.config.strategy_selection.lower()
        logger.info(f"策略选择: {strategy}, 当前视镜次数: {audition_count}")
        if strategy == "te" and audition_count == 4:
            logger.info("策略为 TE 且季度内视镜达标，选择休息跳过")
            ctx.season_data["action_source"] = "rest"
            ctx.season_data["in_multi_step_decision"] = False
            return SequenceAction(actions=(
                        click_rest(),
                        WaitAction(seconds=0.05),
                        click_rest(),
                        WaitAction(seconds=0.05),
                        ctx.step_produce_page(),
                        WaitAction(seconds=0.15),
                    ))
        ctx.season_data["action_source"] = "schedule"
        return SequenceAction(actions=(
            click_schedule(),
            WaitForStableAction((0,705,264,624)),
        ))

    def _decide_schedule(self, ctx: Context) -> Optional[Action]:
        """SCHEDULE_SELECT 页面: 选课程/工作"""
        logger.info("执行日程选择决策...")
        ctx.season_data["in_multi_step_decision"] = False
        
        # 如果有日程约定待履行 → 选择相应课程
        if ctx.season_data.get("have_promised"):
            logger.info("检测到待履行的日程约定")
            hit = _detector.detect_promise_schedule_bonus()
            if hit is not None:
                logger.info(f"检测到约定课程: x={hit.x}, y={hit.y}")
                ctx.season_data["in_multi_step_decision"] = False
                ctx.season_data["have_promised"] = False
                return SequenceAction(actions=(
                    click_xy(hit.x+10, hit.y+10),
                    WaitAction(seconds=0.05),
                    click_xy(hit.x+10, hit.y+10),
                    WaitAction(seconds=0.05),
                    ctx.step_produce_page()
                ))
            else:
                logger.info("未检测到约定课程，继续默认选择")

        logger.info("进行日程选择")
        ctx.season_data["in_multi_step_decision"] = False
        ctx.season_data["action_source"] = None
        action = _get_main_stat_action(ctx)
        if ctx.season_data.get("action_source") == "schedule":
            return SequenceAction(actions=(
                action,
                WaitAction(seconds=0.05),
                action,
                WaitAction(seconds=0.15),
                ctx.step_produce_page()
            ))
        else:
            return action

