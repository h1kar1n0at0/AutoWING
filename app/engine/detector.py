"""
页面检测器 — 通过模板匹配确定当前游戏状态

所有检测区域为原始屏幕坐标 (2560×1600)，直接传给 mss 不做缩放。
由 find() 内部 DPR 处理设备像素映射。
  ref_x = (screen_x - 81) × 0.677  (0.645×211/201)
  ref_y = (screen_y - 168) × 0.677
"""
from __future__ import annotations
import logging
from typing import Optional
import time

from app.engine.state import GlobalState, SeasonState, PageState
from app.engine.templates import Templates
from app.core import Hit, find, REF_W, clear_cache

logger = logging.getLogger("autowing.engine.detector")

CONF_HIGH = 0.97
CONF_MED = 0.90
CONF_LOW = 0.80
CONF_SEASON = 0.995

# ── Bonus 分组检测配置 ────────────────────────────
BONUS_TENSION = [("tension_down", CONF_LOW), ("tension_up", CONF_LOW)]
BONUS_PROMISE = [("confirm_promise", CONF_MED), ("refuse_promise", CONF_MED)]
BONUS_VODAVI  = [("da", CONF_LOW), ("vi", CONF_LOW), ("vo", CONF_LOW),
                 ("normal", CONF_LOW), ("perfect", CONF_LOW)]

BONUS_GROUPS: dict[str, list[tuple[str, float]]] = {
    "tension": BONUS_TENSION,
    "promise": BONUS_PROMISE,
    "vodavi":  BONUS_VODAVI,
    "regular": BONUS_VODAVI + BONUS_PROMISE,
}

COLOR_GROUPS: dict[str, tuple[int,int,int]] = {
    "vocal": (255, 219, 245),
    "dance": (187, 220, 255),
    "visual": (255, 214, 174),
    "radio": (248, 223, 255),
    "photo": (214, 255, 214),
}

# 主 ROI (LEFT/MID/RIGHT) 内遍历的组合
BONUS_MAIN = BONUS_VODAVI


class GameStateDetector:
    def detect_global(self) -> GlobalState: ...
    def detect_season(self) -> Optional[SeasonState]: ...
    def detect_page(self) -> PageState: ...


class TemplateDetector(GameStateDetector):
    """模板匹配检测器 (所有区域已换算到 1600×902 基准)"""

    # ── 页面标识 ──────────────────────────────
    # main / skill_unlock / schedule_select
    PAGE_TOP_ROI = (-3, 5, 355, 90)
    # pre_audition / post_audition
    PAGE_BOTTOM_LEFT_ROI = (-1, 432, 147, 197)
    # in_audition
    PAGE_SMALL_TOP_ROI = (0, 1, 150, 63)
    # post_training
    PAGE_POST_TRAINING = (803,571,250,130)

    # ── 季度 / 周数 ──────────────────────────
    SEASON_BADGE_ROI = (490, 0, 96, 60)          # s1~s5 标识
    SEASON_TASK_ROI = (990, 13, 143, 40)         # 完成/未完成
    WEEK_ROI = (591, 10, 104, 97)                 # 周数 OCR

    # ── 育成前配置 ────────────────────────────
    MEM_SLOT_ROI = (752, 235, 827, 482)          # mem 选择
    START_BUTTON_ROI = (813, 662, 239, 113)       # 开始按钮
    PAGE_SODA_ROI=(987,293,250,220)
    PAGE_TRAINING_START=(807,557,260, 250)

    # ── HUD ───────────────────────────────────
    STAMINA_ROI = (1184, 11, 410, 47)            # 体力条
    SUPPORT_VOCAL_ROI = (347, 720, 195, 48)      # vocal 辅助槽
    SUPPORT_DANCE_ROI = (554, 718, 197, 48)      # dance
    SUPPORT_VISUAL_ROI = (762, 718, 196, 52)     # visual
    SUPPORT_RADIO_ROI = (971, 718, 189, 50)      # radio
    SUPPORT_PHOTO_ROI = (1382, 718, 192, 48)     # photo

    # ── 技能学习 ──────────────────────────────
    SKILL_LEARN_ROI = (1306, 755, 304, 158)      # 学习按钮区域

    # ── 视镜/战斗 ────────────────────────────
    ENEMY_ROI = (-14, 80, 130, 551)              # 敌人栏
    TURN_START_ROI = (-11, 806, 100, 99)          # 回合开始
    SKILL_BAR_ROI = (4, 729, 368, 88)            # 技能栏(buff估算)
    ACTIVE_SKILL_ROI = (518, 751, 745, 147)      # 主动技能栏

    # ── 育成事件 ──────────────────────────────
    BONUS_TAG_ROI = (1395, 345, 120, 100)               # 事件选项区域    
    BONUS_ROI_LEFT = (270,125,265,120)
    BONUS_ROI_RIGHT = (1280,125,265,120)
    BONUS_ROI_MID = (800,0,265,120)
    REFUSE_ROI = (1130,230,315,150)
    SCHEDULE_PROMISE_ROI = (338,493,550,250)      # 日程约定区域
    ERROR_ROI = (480,462,620,320)                # 报错检查

    # ═══════════════════════════════════════════
    # 全局状态
    # ═══════════════════════════════════════════

    def detect_global(self) -> GlobalState:
        if find(Templates.global_("post_training"),
                conf=CONF_MED,region=self.PAGE_POST_TRAINING):
            return GlobalState.POST_TRAINING
        if find(Templates.global_("pre_training"),
                conf=CONF_MED,region=self.PAGE_TOP_ROI) or find(Templates.global_("pre_training_item"),
                conf=CONF_MED,region=self.PAGE_TOP_ROI) or find(Templates.global_("pre_training_formation"),
                conf=CONF_MED,region=self.PAGE_TOP_ROI):
            return GlobalState.PRE_TRAINING
        if self.detect_season() is not None:
            return GlobalState.TRAINING
        return GlobalState.UNKNOWN

    def detect_post_training(self) -> bool:
        return find(Templates.global_("post_training"),
                    conf=CONF_MED,region=self.PAGE_POST_TRAINING) is not None

    def detect_formation(self) -> bool:
        return find(Templates.global_("pre_training_formation"),
                    conf=CONF_MED,region=self.PAGE_TOP_ROI) is not None

    
    def detect_pre_training_item(self) -> bool:
        return find(Templates.global_("pre_training_item"),
                    conf=CONF_MED,region=self.PAGE_TOP_ROI) is not None

    # ═══════════════════════════════════════════
    # 季度
    # ═══════════════════════════════════════════

    def detect_season(self) -> Optional[SeasonState]:
        for s in SeasonState:
            if find(Templates.season(s), conf=CONF_SEASON,region=self.SEASON_BADGE_ROI):
                return s
        return None

    def detect_season_task_completed(self) -> Optional[bool]:
        if find(Templates.season_flag("completed"),
                conf=CONF_LOW,region=self.SEASON_TASK_ROI):
            return True
        if find(Templates.season_flag("incomplete"),
                conf=CONF_LOW,region=self.SEASON_TASK_ROI):
            return False
        return None

    def detect_week(self) -> int:
        for i in range(1, 9):
            if find(Templates.week_digit(i), conf=0.95, region=self.WEEK_ROI):
                return i
        return 0  # 或 raise Exception("未检测到周数")

    # ═══════════════════════════════════════════
    # 页面
    # ═══════════════════════════════════════════

    def detect_page(self) -> PageState:
        # 最高优先级: in_audition
        if find(Templates.page("in_audition"),
                conf=CONF_HIGH,region=self.PAGE_SMALL_TOP_ROI):
            return PageState.IN_AUDITION
        # pre / post audition
        if find(Templates.page("pre_audition"),
                conf=CONF_MED,region=self.PAGE_BOTTOM_LEFT_ROI):
            return PageState.PRE_AUDITION
        if find(Templates.page("post_audition"),
                conf=CONF_MED,region=self.PAGE_BOTTOM_LEFT_ROI):
            return PageState.POST_AUDITION
        # skill_unlock
        if find(Templates.page("skill_unlock"),
                conf=CONF_MED,region=self.PAGE_TOP_ROI):
            return PageState.SKILL_UNLOCK
        # schedule_select
        if find(Templates.page("schedule_select"),
                conf=CONF_MED,region=self.PAGE_TOP_ROI):
            return PageState.SCHEDULE_SELECT
        # main (最后检查, 最通用)
        if find(Templates.page("main"),
                conf=CONF_MED,region=self.PAGE_TOP_ROI):
            return PageState.MAIN
        return PageState.UNKNOWN

    def _is_in_audition(self) -> bool:
        """检测是否在试镜中（最高优先级）"""
        return find(
        Templates.page("in_audition"),
        conf=CONF_HIGH,
        region=self.PAGE_SMALL_TOP_ROI
        ) is not None

    def _is_pre_audition(self) -> bool:
        """检测是否在试镜前页面"""
        return find(
            Templates.page("pre_audition"),
            conf=CONF_MED,
            region=self.PAGE_BOTTOM_LEFT_ROI
        ) is not None

    def _is_post_audition(self) -> bool:
        """检测是否在试镜后页面"""
        return find(
            Templates.page("post_audition"),
            conf=CONF_MED,
            region=self.PAGE_BOTTOM_LEFT_ROI
        ) is not None

    def _is_skill_unlock(self) -> bool:
        """检测是否在技能解锁页面"""
        return find(
            Templates.page("skill_unlock"),
            conf=CONF_MED,
            region=self.PAGE_TOP_ROI
        ) is not None

    def _is_schedule_select(self) -> bool:
        """检测是否在日程选择页面"""
        return find(
            Templates.page("schedule_select"),
            conf=CONF_MED,
            region=self.PAGE_TOP_ROI
        ) is not None

    def is_main_page(self) -> bool:
        """检测是否在主页面（最通用，最后检查）"""
        return find(
            Templates.page("main"),
            conf=CONF_MED,
            region=self.PAGE_TOP_ROI
        ) is not None

    def detect_error_dialog(self) -> bool:
        """检测报错对话框"""
        for e in Templates.ERRORS.values():
            if find(e, conf=CONF_MED, region=self.ERROR_ROI):
                return True
        return False

    # ═══════════════════════════════════════════
    # 视镜/战斗
    # ═══════════════════════════════════════════

    def detect_turn_start(self) -> bool:
        if find(Templates.audition("turn_start"),
                    conf=CONF_MED,
                    region=self.TURN_START_ROI) is not None and self.detect_alive_enemies() is not None:
            return True
        return False

    def detect_alive_enemies(self) -> dict[str, Hit]:
        enemies = {}
        for t in (1, 2, 3):
            hit = find(Templates.audition(f"enemy_type_{t}"), 
                    conf=CONF_MED, 
                    region=self.ENEMY_ROI)
            if hit:
                enemies[f"type_{t}"] = hit
        return enemies

    def estimate_buff_count(self) -> int:
        hit = find(Templates.audition("skill_bar_empty"),
                   conf=0.0,
                   region=self.SKILL_BAR_ROI)
        if hit is None:
            return 0
        if hit.conf >= 0.90:
            return 0
        elif hit.conf >= 0.70:
            return 1
        elif hit.conf >= 0.50:
            return 2
        return 3

    # ═══════════════════════════════════════════
    # 技能学习
    # ═══════════════════════════════════════════

    def detect_skill_learning_state(self) -> Optional[str]:
        for state, key in [
            ("learnable", "learnable"),
            ("learned", "learned"),
            ("idle", "learning_idle"),
            ("paused", "pause_skill_learning"),
        ]:
            if find(Templates.skills_learning(key),
                    conf=CONF_MED,region=self.SKILL_LEARN_ROI):
                return state
        return None

    # ═══════════════════════════════════════════
    # 育成前
    # ═══════════════════════════════════════════

    def detect_mem_unselected(self) -> Optional[Hit]:
        """检测未选择的 mem 所在槽位，返回匹配结果"""
        return find(Templates.pre_training("mem_unselected"), conf=CONF_LOW,region=self.MEM_SLOT_ROI)

    def detect_start_ready(self) -> Optional[Hit]:
        """检测开始按钮是否就绪，返回匹配结果"""
        return find(Templates.pre_training("start"), conf=CONF_MED,region=self.PAGE_TRAINING_START)

    def detect_energy_item(self) -> bool:
        return find(Templates.pre_training("energy_item"),
                    conf=CONF_MED,region=self.PAGE_SODA_ROI) is not None


    # ═══════════════════════════════════════════
    # 育成中
    # ═══════════════════════════════════════════
    def detect_support_counts(self,stat:str) -> int:
        """ 检测 具体 stat 的辅助角色数量 """
        clear_cache()
        if stat == "vocal":
            region = self.SUPPORT_VOCAL_ROI
            color = COLOR_GROUPS["vocal"]
        elif stat == "dance":
            region = self.SUPPORT_DANCE_ROI
            color = COLOR_GROUPS["dance"]
        elif stat == "visual":
            region = self.SUPPORT_VISUAL_ROI
            color = COLOR_GROUPS["visual"]
        elif stat == "radio":
            region = self.SUPPORT_RADIO_ROI
            color = COLOR_GROUPS["radio"]
        elif stat == "photo":
            region = self.SUPPORT_PHOTO_ROI
            color = COLOR_GROUPS["photo"]
        else:
            logger.warning("未知的 stat: %s", stat)
            return 0
        return 0 if self._check_region_color(
            region[0], region[1], region[2], region[3], color, threshold=0.9, tolerance=10) else 1



    # ═══════════════════════════════════════════
    # 育成事件
    # ═══════════════════════════════════════════

    def _is_bonus_showing(self) -> bool:
        """预检: 事件选项标签 (bonus_tag) 是否出现"""
        return find(Templates.bonus("bonus_tag"), conf=CONF_LOW,
                    region=self.BONUS_TAG_ROI) is not None

    def _scan_main_bonus(self, groups: list) -> dict[str, Hit]:
        """在 3 个主 ROI 内遍历模板, 每个 key 只保留首个命中"""
        result: dict[str, Hit] = {}
        for region in (self.BONUS_ROI_LEFT, self.BONUS_ROI_MID, self.BONUS_ROI_RIGHT):
            for key, conf in groups:
                if key in result:
                    continue
                hit = find(Templates.bonus(key), conf=conf, region=region)
                if hit:
                    result[key] = hit
        return result

    def _scan_refuse(self) -> dict[str, Hit]:
        """REFUSE_ROI 检测 refuse_promise / refuse_interview

        refuse_promise 命中时, 在其对称位置合成 confirm_promise (不做模板匹配)。
        """
        result: dict[str, Hit] = {}
        refuse = find(Templates.bonus("refuse_promise"),
                      conf=CONF_MED, region=self.REFUSE_ROI)
        if refuse:
            result["refuse_promise"] = refuse
            result["confirm_promise"] = Hit(
                REF_W - refuse.x, refuse.y, refuse.conf)
        interview = find(Templates.bonus("refuse_interview"),
                         conf=CONF_MED, region=self.REFUSE_ROI)
        if interview:
            result["refuse_interview"] = interview
        return result

    def detect_event_options(self, region: Optional[tuple] = None) -> dict[str, Hit]:
        """检测事件选项，返回所有匹配选项的字典 {bonus_key: Hit}"""
        return self.detect_tension(region=region)

    def detect_bonus_group(self, group: str, region: Optional[tuple] = None) -> dict[str, Hit]:
        """通用分组检测: 在给定 ROI (或 3 个主 ROI) 内遍历组内模板"""
        items = BONUS_GROUPS.get(group)
        if items is None:
            logger.warning("未知的 bonus 组: %s", group)
            return {}
        regions = ((region,) if region is not None
                   else (self.BONUS_ROI_LEFT, self.BONUS_ROI_MID, self.BONUS_ROI_RIGHT))
        result: dict[str, Hit] = {}
        for roi in regions:
            for key, conf in items:
                if key in result:
                    continue
                hit = find(Templates.bonus(key), conf=conf, region=roi)
                if hit:
                    result[key] = hit
        return result

    def detect_tension(self, region: Optional[tuple] = None) -> dict[str, Hit]:
        """检测 Tension 组 (tension_down/tension_up)"""
        if region is not None:
            return self.detect_bonus_group("tension", region=region)
        return self._scan_main_bonus(BONUS_TENSION)

    def detect_regular(self, region: Optional[tuple] = None) -> dict[str, Hit]:
        """检测常规育成事件选项 (VODAVI + Promise)

        bonus_tag 预检 → 3 主 ROI 检测 TENSION+VODAVI → REFUSE_ROI 检测 promise。
        confirm_promise 由 refuse_promise 对称镜像合成, 不直接匹配。
        """
        if not self._is_bonus_showing():
            return {}
        clear_cache()  # 等待选项渲染完成
        result = self._scan_main_bonus(BONUS_MAIN)
        result.update(self._scan_refuse())
        return result

    def detect_promise_schedule_bonus(self, region: Optional[tuple] = None) -> Optional[Hit]:
        """检测日程约定标记 (模板匹配)，使用 CONF_MED"""
        region = region or self.SCHEDULE_PROMISE_ROI
        return find(Templates.bonus("promise_schedule"), conf=CONF_MED, region=region)

    # ═══════════════════════════════════════════
    # 色彩检测 — 约定 / 体力 (基于 canvas_vision)
    # ═══════════════════════════════════════════

    def _check_region_color(
        self, x: int, y: int, w: int, h: int,
        color: tuple, threshold: float = 0.8, tolerance: int = 20
    ) -> bool:
        """通用: 检查 canvas 区域颜色占比是否达标

        复用缓存快照 (与 find() 同源), 不再每次触发实时截图。
        """
        from app.core import check_region_color_cached, clear_cache
        clear_cache()
        return check_region_color_cached(
            x, y, w, h, color,
            tolerance=tolerance, threshold=threshold,
        )

    def detect_promise_rest(self) -> bool:
        """检测是否处于休息约定待履行状态 (色彩)"""
        return self._check_region_color(
            526, 741, 20, 20, (16, 186, 24), threshold=0.8)

    def detect_promise_schedule(self) -> bool:
        """检测是否处于日程约定待履行状态 (色彩)"""
        return self._check_region_color(
            63, 648, 20, 20, (16, 186, 24), threshold=0.8)

    def detect_stamina_half(self) -> bool:
        """检测体力是否不足一半 (色彩)"""
        return self._check_region_color(
            1418, 31, 10, 2, (80, 70, 84), threshold=0.8)
