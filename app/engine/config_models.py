"""
策略配置数据模型 — 用户的所有设置项

对应文档第 9 条:
  - 策略/难度/执行次数/体力道具/主要属性/mem/技能学习顺序/技能优先级
"""
from __future__ import annotations
import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

# 配置文件路径
CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "configs"
CONFIG_FILE = CONFIG_DIR / "strategy.json"


@dataclass
class StrategyConfig:
    """策略配置 — 全部可设置项"""

    # ── 基础设置 ──
    difficulty: str = "medium"           # 难度 (medium/hard)
    max_runs: int = 0                    # 执行次数 (0=无限)
    use_energy_item: bool = False        # 自动使用体力道具
    energy_multiplier: int = 1           # 体力倍率 (1/3)
    main_stat: str = "vocal"             # 主要属性
    strategy_selection: str = "TE"       # 策略选择 (TE/140/230)
    handle_agreement: bool = False       # 是否处理约定

    # ── mem ──
    use_mem: bool = False                # 使用 mem 道具

    # ── 高级设置 ──
    browser_path: str = ""               # 浏览器可执行文件路径
    wait_offset: float = 0.0             # 全局等待偏移量 (秒, 0-10)
    pre_wait_offset: float = 0.0         # 育成前额外等待偏移量 (秒, 0-10)
    qte_interval_offset: float = 0.0     # QTE间隔时长偏移量 (秒, -1 到 1)
    loop_interval: float = 0.05          # 循环间隔 (秒, 0.05-1)

    # ── 技能学习顺序 ──
    # 由用户录制一系列点击位置，位置基于 1600×902 参考坐标
    skill_learn_order: list[dict] = field(default_factory=list)
    # 每条格式: {"x": 100, "y": 200, "wait": 0.5, "label": "技能A"}
    # 可以通过 UI 录制、导出、导入

    # ── 主动技能优先级 ──
    # 用户从 assets/skills/ 中选取，按优先级排列
    skill_priority: list[str] = field(default_factory=list)
    # 格式: ["big_base.png", "high_dmg1.png", ...]

    # ── 其他功能 ──
    auto_continuous_mining: bool = False          # 是否启用自动连续挖矿

    # ── 通知 ──
    notifications_enabled: bool = False
    notification_urls: list[str] = field(default_factory=list)
    notification_min_level: str = "warning"
    notification_dedup_seconds: float = 60.0
    notification_rate_limit_seconds: float = 30.0
    notification_queue_size: int = 100

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> "StrategyConfig":
        valid_keys = cls.__dataclass_fields__
        filtered = {k: v for k, v in d.items() if k in valid_keys}
        return cls(**filtered)


class ConfigManager:
    """配置持久化管理"""

    def __init__(self):
        self._config = StrategyConfig()

    @property
    def config(self) -> StrategyConfig:
        return self._config

    def load(self) -> StrategyConfig:
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._config = StrategyConfig.from_dict(data)
            except (json.JSONDecodeError, IOError) as e:
                print(f"[配置] 加载失败: {e}")
        return self._config

    def save(self) -> bool:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self._config.to_dict(), f,
                          indent=2, ensure_ascii=False)
            return True
        except IOError as e:
            print(f"[配置] 保存失败: {e}")
            return False

    def update(self, data: dict) -> StrategyConfig:
        self._config = StrategyConfig.from_dict(data)
        self.save()
        return self._config

    def export_learn_order(self) -> str:
        return json.dumps(self._config.skill_learn_order,
                          indent=2, ensure_ascii=False)

    def import_learn_order(self, json_str: str) -> bool:
        try:
            data = json.loads(json_str)
            if isinstance(data, list):
                self._config.skill_learn_order = data
                self.save()
                return True
        except (json.JSONDecodeError, TypeError):
            pass
        return False


# 全局单例
config_manager = ConfigManager()
config_manager.load()

# 兼容别名 (Context 中引用)
ConfigModel = StrategyConfig
