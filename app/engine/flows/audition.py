"""
AUDITION Flow — 视镜战斗（Flow 类）

每 tick 由 TrainingFlow 调用, 返回 Action 给 Orchestrator 执行。
"""
from __future__ import annotations
import logging
from typing import Optional
import time

from app.engine.action import Action, WaitAction, SequenceAction
from app.engine.action_utils import click_xy, click_xy_qte, refresh_page, long_click_xy
from app.engine.config_models import config_manager
from app.engine.flows.base import Flow
from app.engine.context import Context
from app.engine.detector import TemplateDetector
from app.engine.state import SeasonState
from app.core import find, Hit

logger = logging.getLogger("autowing.engine.flows.audition")

_ACTIVE_SKILL_ROI = TemplateDetector.ACTIVE_SKILL_ROI


# ─── 内部查询 (纯函数, 无状态) ──────────────

def _find_available_skills() -> dict:
    """查找当前可用的技能"""
    priority = config_manager.config.skill_priority
    found = {}
    for fname in priority:
        path = f"assets/skills_cropped/{fname}"
        hit = find(path, region=_ACTIVE_SKILL_ROI, conf=0.92, use_alpha=False)
        if hit:
            found[fname] = hit
    return found


def _pick_skill(available: dict, buff_count: int) -> Optional[tuple]:
    """
    根据 BUFF 数量选择技能
    
    策略:
    - BUFF = 0: 从优先级列表末尾选择（小技能/单体）
    - BUFF > 0: 从优先级列表开头选择（大技能/AOE）
    """
    if not available:
        return None
    
    priority = config_manager.config.skill_priority
    ordered = [f for f in priority if f in available]
    
    if buff_count == 0:
        ordered = list(reversed(ordered))  # BUFF 为 0 时反向选择
    
    if not ordered:
        return None
    
    skill_name = ordered[0]
    return skill_name, available[skill_name]


def _get_enemy_priority(is_s5: bool) -> tuple:
    """
    根据赛季返回敌人优先级顺序
    
    S5 赛季: type_1 > type_2 > type_3
    非 S5 赛季: type_2 > type_3 > type_1
    """
    if is_s5:
        return ("type_1", "type_2", "type_3")
    return ("type_2", "type_3", "type_1")


def _pick_target(alive_enemies: dict, is_s5: bool) -> Optional[tuple]:
    """
    从存活敌人中选择目标
    
    Args:
        alive_enemies: { "type_1": Hit对象, "type_2": Hit对象, ... }
        is_s5: 是否为 S5 赛季
    
    Returns:
        (敌人类型, Hit对象) 或 None
    """
    if not alive_enemies:
        return None
    
    priority_order = _get_enemy_priority(is_s5)
    
    # 按优先级选择第一个存活的敌人
    for enemy_type in priority_order:
        if enemy_type in alive_enemies:
            return enemy_type, alive_enemies[enemy_type]
    
    # 理论不会到这里，但以防万一
    first_type = next(iter(alive_enemies))
    return first_type, alive_enemies[first_type]


# ═══════════════════════════════════════════════
# 视镜战斗 Flow
# ═══════════════════════════════════════════════

class AuditionFightFlow(Flow):
    """视镜战斗回合循环"""

    def __init__(self):
        self._detector = TemplateDetector()
        self._step = "idle"          # idle / evaluate / click_skill / click_target / wait_turn
        self._skill_hit = None       # 选中的技能 Hit 对象
        self._target_hit = None      # 选中的目标 Hit 对象
        self._buff = 0               # 当前 BUFF 数量
        self._turn_count = 0         # 回合计数器
        self._just_entered_wait_turn = True  # 标记是否刚进入 wait_turn 状态

    def step(self, ctx: Context) -> Optional[Action]:
        # ─── 空闲等待 ──────────────────────────
        if self._step == "idle":
            # 超时检测：如果等待超过15秒仍未检测到回合开始，则强制重试
            if not hasattr(self, '_wait_start_time') or self._just_entered_wait_turn:
                self._wait_start_time = time.time()
                self._just_entered_wait_turn = False
            
            elapsed = time.time() - self._wait_start_time
            if elapsed > 15:  # 15秒超时
                logger.warning(f"等待回合超时 ({elapsed:.1f}s)，强制重置")
                self._wait_start_time = time.time()  # 重置计时器
                if ctx.can_jump():
                    ctx._record_jump()
                    return SequenceAction(actions=(
                                        refresh_page(),
                                        WaitAction(seconds=2.5)
                                    ))
                else:
                    logger.warning("跳转限流: 已达到跳转上限，等待中...")
                    return WaitAction(seconds=1.5)
            if self._detector.detect_turn_start():
                self._step = "evaluate"
                self._turn_count += 1
                logger.info(f"第 {self._turn_count} 回合开始")
                return SequenceAction(actions=(click_xy(818, 589),WaitAction(seconds=0.05),click_xy(818, 589),WaitAction(seconds=0.05),click_xy(818, 589),WaitAction(seconds=0.3)))
            return click_xy(x=818, y=589, desc="跳过剧情")

        # ─── 等待下一回合 ──────────────────────
        if self._step == "wait_turn":
            # 超时检测：如果等待超过15秒仍未检测到回合开始，则强制重试
            if not hasattr(self, '_wait_start_time') or self._just_entered_wait_turn:
                self._wait_start_time = time.time()
                self._just_entered_wait_turn = False
            
            elapsed = time.time() - self._wait_start_time
            if elapsed > 15:  # 15秒超时
                logger.warning(f"等待回合超时 ({elapsed:.1f}s)，强制重置")
                self._wait_start_time = time.time()  # 重置计时器
                if ctx.can_jump():
                    ctx._record_jump()
                    return SequenceAction(actions=(
                                        refresh_page(),
                                        WaitAction(seconds=2.5)
                                    ))
                else:
                    logger.warning("跳转限流: 已达到跳转上限，等待中...")
                    return WaitAction(seconds=1.5)
                
            if self._detector.detect_judge_details():
                    logger.info("检测到评委详情页面，关闭页面")
                    return SequenceAction(actions=(long_click_xy(800, 800,duration= 0.05,desc="关闭评委详情"), WaitAction(seconds=0.15)))
            
            if self._detector.detect_turn_start():
                self._step = "evaluate"
                self._turn_count += 1
                logger.info(f"第 {self._turn_count} 回合开始")
                self._just_entered_wait_turn = True  # 重置标记
                return SequenceAction(actions=(click_xy(818, 589),WaitAction(seconds=0.05),click_xy(818, 589),WaitAction(seconds=0.05),click_xy(818, 589),WaitAction(seconds=0.05),click_xy(818, 589),WaitAction(seconds=0.15),click_xy(818, 589),WaitAction(seconds=0.33)))
            elif self._detector._is_post_audition():
                logger.info("视镜战斗结束")
                ctx.season_data["in_multi_step_decision"] = False
                return None
            
            return SequenceAction(actions=(click_xy(818, 589),WaitAction(seconds=0.05),click_xy(818, 589),WaitAction(seconds=0.05),click_xy(818, 589),WaitAction(seconds=0.05)))
        
        # ─── 评估并决策 ──────────────────────
        if self._step == "evaluate":
            # 1. 检测 BUFF
            self._buff = self._detector.estimate_buff_count()
            
            # 2. 查找可用技能
            available = _find_available_skills()
            skill_result = _pick_skill(available, self._buff)
            
            if not skill_result:
                logger.info("无可用高优先级技能，固定使用第一个技能")
                skill_name = "key_skill_1"
                self._skill_hit =  Hit(x=542,y=829,conf=1)
            else:
                skill_name, self._skill_hit = skill_result
            
            # 3. 查找存活敌人并选择目标
            is_s5 = ctx.season == SeasonState.S5
            alive_enemies = self._detector.detect_alive_enemies()
            target_result = _pick_target(alive_enemies, is_s5)
            
            if target_result:
                target_type, self._target_hit = target_result
                logger.info(f"目标: {target_type}")
            else:
                self._target_hit = None
                logger.info("无存活敌人")
            
            logger.info(f"✨ BUFF: {self._buff} | 技能: {skill_name} @ ({self._skill_hit.x:.0f}, {self._skill_hit.y:.0f})")
            
            self._step = "click_skill"
            return SequenceAction(actions=(click_xy(818, 589),WaitAction(seconds=0.05),click_xy(818, 589),WaitAction(seconds=0.05)))

        # ─── 点击技能 ──────────────────────────
        if self._step == "click_skill":
            action_1 = None
            action_2 = None
            if self._skill_hit:
                self._step = "wait_turn"
                action_1 = click_xy(self._skill_hit.x, self._skill_hit.y, desc="选择技能")
            if self._target_hit:
                logger.info(f"攻击目标 @ ({self._target_hit.x:.0f}, {self._target_hit.y:.0f})")
                action_2 = click_xy_qte(self._target_hit.x, self._target_hit.y, desc="选择目标")

            
            if action_1 and action_2:
                if self._buff >0 :
                                action_3 = ctx.step_produce_page_limited()
                else:
                                action_3 = WaitAction(seconds=1.5)
                return SequenceAction(actions=(action_1,WaitAction(seconds=0.25), action_2,WaitAction(0.15),action_3))
            else:
                logger.warning("未找到技能或目标，跳过本回合")
                self._step = "wait_turn"
                return WaitAction(seconds=0.05)

        return WaitAction(seconds=0.05)

# ═══════════════════════════════════════════════
# 视镜结果处理 Flow
# ═══════════════════════════════════════════════

class AuditionResultFlow(Flow):
    """跳过视镜结果画面"""
    
    def __init__(self):
        self._detector = TemplateDetector()
        self._is_s5 = False
        self._count = 0

    def step(self, ctx: Context) -> Optional[Action]:
        # 计数
        self._count = ctx.season_data.get("audition_count", 0) + 1
        ctx.season_data["audition_count"] = self._count
        logger.info(f"季度{ctx.season}视镜计数: {self._count}")
        
        # 判断最终视镜逻辑
        is_s5 = ctx.season == SeasonState.S5
        if is_s5 and self._count >= 2:
            logger.info("季度 S5 视镜计数达到 2，跳过最终剧情")
            from app.engine.action_utils import skip_story_with_multiple_clicks_final
            return skip_story_with_multiple_clicks_final()
        
        return None