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
from app.engine.flows.base import Flow, StopSignal
from app.engine.context import Context
from app.engine.detector import TemplateDetector
from app.engine.state import SeasonState
from app.core import find, Hit, get_game_data

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


def _skill_total_damage(card: dict) -> int:
    """技能卡总伤害 = premeasuredDamages 的 damage 之和。"""
    return sum(int(d.get("damage", 0) or 0) for d in card.get("premeasuredDamages") or [])


def _pick_skill_from_api(cards: list, main_stat_buff: int) -> Optional[tuple]:
    """
    按 API 数据选技能。

    Args:
        cards: skillCards() 返回的 cards 列表（已含 isAll / premeasuredDamages）
        main_stat_buff: 主属性 buff 总量

    Returns:
        (slot, card, total_damage) 或 None
        slot: 该卡在 cards 里的位置（0-based），用于算 Hit 坐标
    """
    # 只考虑 matched 且有预测伤害的卡
    valid = [
        (i, c, _skill_total_damage(c))
        for i, c in enumerate(cards)
        if c.get("matched") and _skill_total_damage(c) > 0
    ]
    if not valid:
        return None

    if main_stat_buff < 100:
        logger.info(f"buff值为 {main_stat_buff}，选用小技能")
        # 伤害最小且非 0
        non_all = [x for x in valid if not x[1].get("isAll")]
        pool = non_all if non_all else valid   # 没单体可用时兜底回全体
        slot, card, dmg = min(pool, key=lambda x: x[2])
        return slot, card, dmg
    else:
        logger.info(f"buff值为 {main_stat_buff}，选用大技能与全体")
        # 伤害最高，优先全体
        # 排序键：isAll 优先（True 在前），再按伤害降序
        slot, card, dmg = max(
            valid,
            key=lambda x: (1 if x[1].get("isAll") else 0, x[2])
        )
        return slot, card, dmg


def _judge_id_sort_key(jid):
    s = str(jid)
    try:
        return (0, int(s))
    except (TypeError, ValueError):
        return (1, s)


def _pick_target_from_api(pds: list) -> Optional[dict]:
    """
    从 premeasuredDamages 选目标。

    规则：
      - 存活评委 = pctOfCurrentHp is not None
      - 存在 80 <= pct <= 130 → 选 pct 最接近 100 的（并列按 id 升序）
      - 否则 → 选 pct 最小的（并列按 id 升序）
      - 无存活评委 → None
    """
    alive = [d for d in pds if d.get("pctOfCurrentHp") is not None]
    if not alive:
        return None

    in_range = [d for d in alive if 80 <= d["pctOfCurrentHp"] <= 130]
    if in_range:
        in_range.sort(key=lambda d: (
            abs(d["pctOfCurrentHp"] - 100),
            _judge_id_sort_key(d.get("targetJudgeId")),
        ))
        return in_range[0]
    

    alive.sort(key=lambda d: (
        d["pctOfCurrentHp"],
        _judge_id_sort_key(d.get("targetJudgeId")),
    ))
    return alive[0]


def _resolve_target_hit(
    target_judge_id: str,
    all_pds: list,
    alive_enemies: dict,
) -> Optional[Hit]:
    """
    targetJudgeId 在全体评委 id（来自 pds）里的 rank → 视觉按 y 升序的第 rank 个。
    """
    # 视觉：按 y 升序（只含存活敌人）
    visual = sorted(alive_enemies.items(), key=lambda kv: kv[1].y)
    if not visual:
        return None

    # API：全体评委 id 升序（含死亡，rank 才和视觉顺序一致）
    sorted_ids = sorted(
        (str(d.get("targetJudgeId")) for d in all_pds),
        key=_judge_id_sort_key,
    )
    tid = str(target_judge_id)
    if tid not in sorted_ids:
        return None
    
    alive_ids = sorted(
        (str(d.get("targetJudgeId")) for d in all_pds
         if d.get("pctOfCurrentHp") is not None),
        key=_judge_id_sort_key,
    )
    if tid not in alive_ids:
        return None
    alive_rank = alive_ids.index(tid)

    if alive_rank >= len(visual):
        return None
    return visual[alive_rank][1]



# ═══════════════════════════════════════════════
# 视镜战斗 Flow
# ═══════════════════════════════════════════════

class AuditionFightFlow(Flow):
    """视镜战斗回合循环"""

    def __init__(self):
        self._detector = TemplateDetector()
        self._step = "idle"          # idle / evaluate / click_skill / wait_turn
        self._skill_hit = None       # 选中的技能 Hit 对象
        self._target_hit = None      # 选中的目标 Hit 对象
        self._buff = 0               # 当前 BUFF 数量（视觉）
        self._buff_value = 0         # 当前主属性 BUFF 量（API）
        self._turn_count = 0         # 回合计数器
        self._just_entered_wait_turn = True  # 标记是否刚进入 wait_turn 状态
        self._guards: dict[str, tuple] = {}   # key -> (count, first_time)
        self.main_stat = config_manager.config.main_stat  # 主要属性

        # ── 游戏数据 API 状态 ──
        # None = 尚未检测；True/False = 检测结果
        self._api_checked = False       # 是否已检测过
        self._api_ready = False         # installed && ready，可用 game data
        self._api_last_error = None     # 最近一次检测的 error（调试用）

    def guard(self, key: str, max_count: int = 3, window: float = 100) -> bool:
        """
        返回 True = 允许继续；False = 超限，应停止
        window 内累计超过 max_count 次即超限
        """
        now = time.time()
        count, first = self._guards.get(key, (0, now))
        if now - first > window:
            count, first = 0, now
        count += 1
        self._guards[key] = (count, first)
        return count <= max_count

    def clear_guard(self, key: str = None):
        if key:
            self._guards.pop(key, None)
        else:
            self._guards.clear()


    def step(self, ctx: Context) -> Optional[Action]:
        # ─── 空闲等待 ──────────────────────────
        if self._step == "idle":
            # 超时检测：如果等待超过35秒仍未检测到回合开始，则强制重试
            if not hasattr(self, '_wait_start_time') or self._just_entered_wait_turn:
                self._wait_start_time = time.time()
                self._just_entered_wait_turn = False
            
            elapsed = time.time() - self._wait_start_time
            if elapsed > 35:  # 35秒超时
                if not self.guard("audition_recover", max_count=3, window=60):
                    logger.error("视镜流程超时，退出")
                    ctx.signal = StopSignal("视镜流程超时")
                    return WaitAction(seconds=0.05)
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
                if not self._api_checked:
                    self._check_game_api()

                self._step = "evaluate"
                self._turn_count += 1
                self.clear_guard("audition_recover")
                logger.info(f"第 {self._turn_count} 回合开始")
                return SequenceAction(actions=(click_xy(818, 444),WaitAction(seconds=0.05),click_xy(818, 444),WaitAction(seconds=0.05),click_xy(818, 444),WaitAction(seconds=0.05),click_xy(818, 444),WaitAction(seconds=0.05),click_xy(818, 444),WaitAction(seconds=0.05),click_xy(818, 444),WaitAction(seconds=0.05),click_xy(818, 444),WaitAction(seconds=0.05),click_xy(818, 444),WaitAction(seconds=0.05)))
            return SequenceAction(actions=(click_xy(818, 444),WaitAction(seconds=0.05),click_xy(818, 444),WaitAction(seconds=0.05),click_xy(818, 444),WaitAction(seconds=0.05)))

        # ─── 等待下一回合 ──────────────────────
        if self._step == "wait_turn":
            # 超时检测：如果等待超过35秒仍未检测到回合开始，则强制重试
            if not hasattr(self, '_wait_start_time') or self._just_entered_wait_turn:
                self._wait_start_time = time.time()
                self._just_entered_wait_turn = False
            
            elapsed = time.time() - self._wait_start_time
            if elapsed > 35:  # 35秒超时
                if not self.guard("audition_recover", max_count=3, window=60):
                    logger.error("视镜流程超时，退出")
                    ctx.signal = StopSignal("视镜流程超时")
                    return WaitAction(seconds=0.05)
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
                self.clear_guard("audition_recover")
                logger.info(f"第 {self._turn_count} 回合开始")
                self._just_entered_wait_turn = True  # 重置标记
                return SequenceAction(actions=(click_xy(818, 444),WaitAction(seconds=0.15),click_xy(818, 444),WaitAction(seconds=0.15),click_xy(818, 444),WaitAction(seconds=0.15),click_xy(818, 444),WaitAction(seconds=0.15),click_xy(818, 444),WaitAction(seconds=0.15)))
            elif self._detector._is_post_audition():
                logger.info("视镜战斗结束")
                ctx.season_data["in_multi_step_decision"] = False
                return None
            
            return SequenceAction(actions=(click_xy(818, 444),WaitAction(seconds=0.05),click_xy(818, 444),WaitAction(seconds=0.05),click_xy(818, 444),WaitAction(seconds=0.05)))
        
        # ─── 评估并决策 ──────────────────────
        if self._step == "evaluate":
            # ── BUFF 检测：API 优先，降级视觉 ──
            api_data = None
            picked_card = None
            if self._api_ready:
                api_data = get_game_data()

            if self._api_ready and api_data and api_data.get("connected"):
                passive = api_data.get("passive") or {}
                total = passive.get("total") or {}
                self._buff_value = int(total.get(self.main_stat, 0) or 0)
            else:
                # 降级：视觉估计 buff（原逻辑）
                self._buff = self._detector.estimate_buff_count()

            # ── 技能选择 ──
            skill_name = None
            if self._api_ready and api_data and api_data.get("connected"):
                cards = (api_data.get("skills") or {}).get("cards") or []
                picked = _pick_skill_from_api(cards, self._buff_value)
                if picked:
                    slot, card, dmg = picked
                    picked_card = card
                    self._skill_hit = Hit(x=542 + 300 * slot, y=829, conf=1)
                    skill_name = card.get("skillName") or f"slot_{slot}"
                    logger.info(
                        f"[API] 主属性 {self.main_stat} buff={self._buff_value} → "
                        f"选技能 slot={slot} {skill_name} "
                        f"isAll={card.get('isAll')} 伤害={dmg}"
                    )
                else:
                    # API 就绪但没拿到可用技能 → 降级到旧逻辑
                    logger.info("[API] 无可用技能卡，降级视觉选择")
                    self._buff = self._detector.estimate_buff_count()
                    available = _find_available_skills()
                    skill_result = _pick_skill(available, self._buff)
                    if not skill_result:
                        skill_name = "key_skill_1"
                        self._skill_hit = Hit(x=542, y=829, conf=1)
                    else:
                        skill_name, self._skill_hit = skill_result
            else:
                # 降级：原逻辑
                available = _find_available_skills()
                skill_result = _pick_skill(available, self._buff)
                if not skill_result:
                    logger.info("无可用高优先级技能，固定使用第一个技能")
                    skill_name = "key_skill_1"
                    self._skill_hit = Hit(x=542, y=829, conf=1)
                else:
                    skill_name, self._skill_hit = skill_result

            # ── 目标选择 ──
            alive_enemies = self._detector.detect_alive_enemies()
            if (self._api_ready and picked_card
                    and picked_card.get("premeasuredDamages") and config_manager.config.strategy_selection == "230"):
                pds = picked_card["premeasuredDamages"]
                picked_target = _pick_target_from_api(pds)
                if picked_target:
                    hit = _resolve_target_hit(
                        picked_target["targetJudgeId"], pds, alive_enemies
                    )
                    if hit:
                        self._target_hit = hit
                        logger.info(
                            f"[API] 目标 judge={picked_target['targetJudgeId']} "
                            f"pct={picked_target['pctOfCurrentHp']:.1f}% "
                            f"→ Hit({hit.x:.0f},{hit.y:.0f})"
                        )
                    else:
                        logger.info("[API] 目标映射失败，降级视觉")
            else:
                # ── 目标选择：原逻辑（视觉）──
                is_s5 = ctx.season == SeasonState.S5
                target_result = _pick_target(alive_enemies, is_s5)

                if target_result:
                    target_type, self._target_hit = target_result
                    logger.info(f"目标: {target_type}")
                else:
                    self._target_hit = None
                    logger.info("无存活敌人")

                logger.info(f"✨ BUFF: {self._buff} | 技能: {skill_name} @ ({self._skill_hit.x:.0f}, {self._skill_hit.y:.0f})")

            self._step = "click_skill"
            return SequenceAction(actions=(click_xy(818, 444),WaitAction(seconds=0.05),click_xy(818, 444),WaitAction(seconds=0.05)))

        # ─── 点击技能 ──────────────────────────
        if self._step == "click_skill":
            action_1 = None
            action_2 = None
            if self._skill_hit:
                self._step = "wait_turn"
                action_1 = click_xy(self._skill_hit.x, self._skill_hit.y, desc="选择技能")

            if self._api_ready:
                if self._buff_value < 100 and config_manager.config.strategy_selection == "230":
                    if self._target_hit:
                        logger.info(f"攻击目标 @ ({self._target_hit.x:.0f}, {self._target_hit.y:.0f})")
                        action_2 = SequenceAction(actions=(
                            click_xy(self._target_hit.x, self._target_hit.y),
                            WaitAction(0.2),
                            click_xy(self._target_hit.x, self._target_hit.y),
                            WaitAction(0.2),
                            click_xy(self._target_hit.x, self._target_hit.y),
                        ))
                    if action_1 and action_2:
                        action_3 = WaitAction(seconds=1.5)
                    else:
                        logger.warning("未找到技能或目标，跳过本回合")
                        self._step = "wait_turn"
                        return WaitAction(seconds=0.05)
                else:
                    if self._target_hit:
                        logger.info(f"攻击目标 @ ({self._target_hit.x:.0f}, {self._target_hit.y:.0f})")
                        action_2 = click_xy_qte(self._target_hit.x, self._target_hit.y, desc="选择目标")
                    if action_1 and action_2:
                        action_3 =  WaitAction(seconds=1.5)
                    else:
                        logger.warning("未找到技能或目标，跳过本回合")
                        self._step = "wait_turn"
                        return WaitAction(seconds=0.05)
                return SequenceAction(actions=(action_1, WaitAction(seconds=0.25), action_2, WaitAction(0.15), action_3, WaitAction(0.2)))

            # ── 降级：原视觉逻辑 ──
            if self._target_hit:
                logger.info(f"攻击目标 @ ({self._target_hit.x:.0f}, {self._target_hit.y:.0f})")
                if self._buff < 1 and config_manager.config.strategy_selection == "230":
                    action_2 = SequenceAction(actions=(
                        click_xy(self._target_hit.x, self._target_hit.y),
                        WaitAction(0.2),
                        click_xy(self._target_hit.x, self._target_hit.y),
                        WaitAction(0.2),
                        click_xy(self._target_hit.x, self._target_hit.y),
                    ))
                else:
                    action_2 = click_xy_qte(self._target_hit.x, self._target_hit.y, desc="选择目标")

            if action_1 and action_2:
                if self._buff > 0:
                    action_3 = ctx.step_produce_page_limited()
                else:
                    action_3 = WaitAction(seconds=1.5)
                return SequenceAction(actions=(action_1, WaitAction(seconds=0.25), action_2, WaitAction(0.15), action_3, WaitAction(0.2)))
            else:
                logger.warning("未找到技能或目标，跳过本回合")
                self._step = "wait_turn"
                return WaitAction(seconds=0.05)

        return WaitAction(seconds=0.05)

    def _check_game_api(self):
        """第一回合检测游戏数据 API，结果缓存到实例变量，供后续降级判断。"""
        self._api_checked = True
        try:
            data = get_game_data()
        except Exception as e:  # get_game_data 理论上不抛，兜底
            self._api_ready = False
            self._api_last_error = f"{type(e).__name__}: {e}"
            logger.warning(f"游戏数据 API 检测异常，降级视觉: {self._api_last_error}")
            return

        connected = bool(data.get("connected"))
        installed = bool(data.get("installed"))
        ready = bool(data.get("ready"))
        self._api_ready = connected and installed and ready
        self._api_last_error = data.get("error")

        if self._api_ready:
            logger.info("游戏数据 API 就绪（将使用 API 数据辅助决策）")
        else:
            logger.info(
                f"游戏数据 API 不可用，降级视觉检测 "
                f"(connected={connected}, installed={installed}, ready={ready}, "
                f"error={self._api_last_error})"
            )


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