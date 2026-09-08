"""
模板路径集中管理 — 所有模板路径在此定义

命名约定:
  assets/
    pages/          页面标识模板 (用于 detector)
    hud/            HUD 元素 (体力条、辅助角色槽)
    season/         季度标识和完成状态
    global/         全局状态 (育成前/后)
    pre_training/   育成前配置界面
    skills_learning/ 技能学习页面
    audition/       视镜/战斗界面
    skills/         技能图标 (用户自定义)
    buttons/        通用按钮
    bonuses/        育成事件选项/结果
    digits/         数字 0-9
"""
from __future__ import annotations

from app.engine.state import SeasonState


class Templates:
    """模板路径注册表 — 所有图片路径集中在这里"""

    # ── 育成中页面标识 (assets/pages/) ─────────────
    # 检测区域: (77, 187, 504, 107)
    PAGES = {
        "main":              "assets/pages/main.png",
        "skill_unlock":      "assets/pages/skill_unlock.png",
        "schedule_select":   "assets/pages/schedule_select.png",
        "pre_audition":      "assets/pages/pre_audition.png",
        "post_audition":     "assets/pages/post_audition.png",
        "in_audition":       "assets/pages/in_audition.png",
    }

    # ── 全局状态入口 (assets/global/) ────────────
    GLOBAL = {
        "pre_training":      "assets/global/pre_training.png",
        "pre_training_item": "assets/global/pre_training_item.png",
        "pre_training_formation": "assets/global/pre_training_formation.png", 
        "training_start":    "assets/global/training_start.png",
        "post_training":     "assets/global/post_training.png",
    }

    # ── 季度 (assets/season/) ────────────────
    # 季度标识 region: (825, 179, 123, 70)
    # 完成/未完成 region: (1565, 189, 211, 57)
    SEASONS = {
        SeasonState.S1: "assets/season/s1.png",
        SeasonState.S2: "assets/season/s2.png",
        SeasonState.S3: "assets/season/s3.png",
        SeasonState.S4: "assets/season/s4.png",
        SeasonState.S5: "assets/season/s5.png",
    }

    WEEK_DIGITS = {str(i): f"assets/season/{i}.png" for i in range(1, 9)}

    SEASON_FLAGS = {
        "incomplete": "assets/season/incompleted.png",
        "completed":  "assets/season/completed.png",
    }
    SEASON_WEEK_DIGITS = {str(i): f"assets/season/{i}.png" for i in range(1, 10)}
    SEASON_START = "assets/season/start.png"

    # ── 育成前配置 (assets/pre_training/) ────
    PRE_TRAINING = {
        "mem_selected":     "assets/pre_training/mem_selected.png",
        "mem_unselected":   "assets/pre_training/mem_unselected.png",
        "start":            "assets/pre_training/start.png",
        "energy_item":      "assets/pre_training/soda.png"
    }

    # ── HUD (assets/hud/) ────────────────────
    # 辅助角色槽: vocal_empty(603,1248,290,69) / dance_empty(912,1245,293,69)
    #            visual_empty(1223,1244,291,76) / radio_empty(1536,1245,281,72)
    #            photo_empty(2151,1245,285,69)
    # 体力: stamina_empty(1854,187,611,68) / stamina_half(1854,187,611,68)
    HUD = {
        "vocal_empty":      "assets/hud/vocal_empty.png",
        "dance_empty":      "assets/hud/dance_empty.png",
        "visual_empty":     "assets/hud/visual_empty.png",
        "radio_empty":      "assets/hud/radio_empty.png",
        "photo_empty":      "assets/hud/photo_empty.png",
        "stamina_empty":    "assets/hud/stamina_empty.png",
        "stamina_half":     "assets/hud/stamina_half.png",
    }

    # ── 技能学习 (assets/skills_learning/) ───
    # region: (2068, 1331, 420, 187) — 注意此坐标可能超出 1600，需按实际截图缩放
    SKILLS_LEARNING = {
        "learnable":            "assets/skills_learning/learnable.png",
        "learned":              "assets/skills_learning/learned.png",
        "learning_idle":        "assets/skills_learning/learning_idle.png",
        "pause_skill_learning": "assets/skills_learning/pause_skill_learning.png",
    }

    # ── 视镜/战斗 (assets/audition/) ─────────
    # 敌人 region: (63, 292, 190, 819)
    # turn_start region: (66, 1376, 147, 146)
    # skill_bar_empty region: (90, 1262, 546, 127)
    AUDITION = {
        "enemy_type_1":  "assets/audition/enemy_type_1.png",
        "enemy_type_2":  "assets/audition/enemy_type_2.png",
        "enemy_type_3":  "assets/audition/enemy_type_3.png",
        "turn_start":    "assets/audition/turn_start.png",
        "skill_bar_empty": "assets/audition/skill_bar_empty.png",
    }

    # ── 育成事件相关 (assets/bonuses/) ───────────
    # region: (111, 181, 2340, 699)
    BONUSES = {
        # 约定/事件选项
        "confirm_promise": "assets/bonuses/confirm_promise.png",
        "refuse_promise":  "assets/bonuses/refuse_promise.png",
        "refuse_interview":  "assets/bonuses/refuse_interview.png",
        "bonus_tag":       "assets/bonuses/bonus_tag.png",
        # 事件结果
        "tension_down":    "assets/bonuses/tension_down.png",
        "tension_up":      "assets/bonuses/tension_up.png",
        "da":              "assets/bonuses/da.png",
        "vi":              "assets/bonuses/vi.png",
        "vo":              "assets/bonuses/vo.png",
        "normal":          "assets/bonuses/normal.png",
        "perfect":         "assets/bonuses/perfect.png",
        # 日程约定标记
        "promise_schedule":"assets/bonuses/promise_schedule.png",
    }

    # ── 技能图标 (assets/skills/) ────────────
    SKILLS = {
    }

    # ── 报错图标 (assets/errors/) ────────────
    ERRORS ={
        "errors_1":        "assets/errors/errors_1.png",
        "errors_2": "assets/errors/errors_2.png",
    }

    # ── 便捷访问 ─────────────────────────────

    @classmethod
    def page(cls, key: str) -> str:
        return cls.PAGES[key]

    @classmethod
    def global_(cls, key: str) -> str:
        return cls.GLOBAL[key]

    @classmethod
    def season(cls, s: SeasonState) -> str:
        return cls.SEASONS[s]

    @classmethod
    def season_flag(cls, key: str) -> str:
        return cls.SEASON_FLAGS[key]

    @classmethod
    def bonus_all(cls, key: str) -> str:
        return cls.BONUSES[key]

    @classmethod
    def pre_training(cls, key: str) -> str:
        return cls.PRE_TRAINING[key]

    @classmethod
    def hud(cls, key: str) -> str:
        return cls.HUD[key]

    @classmethod
    def skills_learning(cls, key: str) -> str:
        return cls.SKILLS_LEARNING[key]

    @classmethod
    def audition(cls, key: str) -> str:
        return cls.AUDITION[key]

    @classmethod
    def bonus(cls, key: str) -> str:
        return cls.BONUSES[key]

    @classmethod
    def button(cls, key: str) -> str:
        return cls.BUTTONS[key]

    @classmethod
    def skill(cls, key: str) -> str:
        return cls.SKILLS[key]

    @classmethod
    def week_digit(cls, digit: int) -> str:
        return cls.WEEK_DIGITS[str(digit)]