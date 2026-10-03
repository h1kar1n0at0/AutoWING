"""
运行时上下文 — 专为 Flow 和 Strategy 服务的全局共享内存
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, TYPE_CHECKING
import time
from app.engine.state import GlobalState, SeasonState
from app.engine.config_models import StrategyConfig as ConfigModel, config_manager
from app.engine.action_utils import go_forward, go_back
import logging
if TYPE_CHECKING:
    from app.engine.flows.base import FlowSignal
    from app.engine.strategy import SeasonStrategy
    from app.engine.action import BaseAction
    
logger = logging.getLogger("autowing.engine.context")

@dataclass
class Context:
    """Orchestrator、Flow 和 Strategy 共享的运行时内存上下文"""

    # 当 Flow 需要通知 Orchestrator 进行“切换 Flow”或“彻底停止引擎”时设置
    signal: Optional[FlowSignal] = None

    # ═══════════════════════════════════════════
    # 1. 配置与策略持久化缓存 (免去反复读取 cfg / 重新实例化)
    # ═══════════════════════════════════════════
    config: ConfigModel = field(default_factory=lambda: config_manager.config)
    strategy: Optional[SeasonStrategy] = None  # 当前季度的策略实例，持久化在 Context

    # ═══════════════════════════════════════════
    # 2. 核心游戏状态 (仅在路标/决策点更新)
    # ═══════════════════════════════════════════
    global_state: GlobalState = GlobalState.UNKNOWN
    season: Optional[SeasonState] = None
    remaining_weeks: int = 8               # 剩余周数 (倒计时 8 -> 1)
    should_advance_page: bool = False            # 是否需要浏览器前进 (False 则后退)
    

    # ═══════════════════════════════════════════
    # 3. 策略与 Flow 跨 Tick 共享数据
    # ═══════════════════════════════════════════
    # 读写任意临时标记 (如 forced_action="audition", target_schedule="vocal")
    season_data: Dict[str, Any] = field(default_factory=dict)

    # ═══════════════════════════════════════════
    # 4. 跳转限流配置
    # ═══════════════════════════════════════════
    _JUMP_WINDOW: float = 32.0  # 窗口期 32 秒
    _JUMP_MAX_COUNT: int = 2    # 窗口期内最大跳转次数

    # ═══════════════════════════════════════════
    # 5. 状态转换与自动化缓存清理
    # ═══════════════════════════════════════════

    def record_global_transition(self, state: GlobalState) -> bool:
        """全局状态切换 (如脱离 TRAINING 进入 MAIN_MENU)"""
        changed = state != self.global_state
        if changed:
            self.season_data.clear()
            self.season = None
            self.strategy = None
            self.remaining_weeks = 8
            self.signal = None  # 状态切换时自动复位信号
            self.should_advance_page = False  # 状态切换时自动复位浏览器前进标记
        self.global_state = state
        return changed

    def record_season_transition(self, season: Optional[SeasonState]) -> bool:
        """季度切换 (S1 -> S2 -> S3...)"""
        changed = season != self.season
        if changed and season is not None:
            # 保留 jump_records，避免季度切换重置跳转限流计时
            jump_records = self.season_data.get("jump_records")
            self.season_data.clear()
            if jump_records is not None:
                self.season_data["jump_records"] = jump_records
            self.remaining_weeks = 8
            # 策略可以在此处由 StrategyRegistry 载入并直接赋值给 self.strategy
        self.season = season
        return changed

    def reload_config(self) -> None:
        """用户在 UI/Web 修改配置后，热重载配置缓存"""
        self.config = config_manager.config

    # ═══════════════════════════════════════════
    # 6. 跳转限流方法
    # ═══════════════════════════════════════════

    def _clean_jump_records(self) -> None:
        """清理超时的跳转记录（超过 32 秒）"""
        records = self.season_data.get("jump_records", [])
        now = time.time()
        cleaned = [t for t in records if now - t <= self._JUMP_WINDOW]
        if len(cleaned) != len(records):
            self.season_data["jump_records"] = cleaned

    def _get_jump_count(self) -> int:
        """获取当前窗口期内的跳转次数（自动清理超时）"""
        self._clean_jump_records()
        return len(self.season_data.get("jump_records", []))

    def _record_jump(self) -> None:
        """记录一次跳转"""
        records = self.season_data.get("jump_records", [])
        records.append(time.time())
        self.season_data["jump_records"] = records

    def can_jump(self) -> bool:
        """检查是否允许跳转（窗口期内 < 2 次）"""
        return self._get_jump_count() < self._JUMP_MAX_COUNT

    def step_produce_page(self) -> BaseAction:
        """选择触发浏览器'前进'还是'后退'（不限流）"""
        if self.should_advance_page:
            self.should_advance_page = False  
            return go_forward()
        self.should_advance_page = True
        return go_back()

    def step_produce_page_limited(self) -> BaseAction:
        """
        带限流的 step_produce_page
        
        32 秒窗口内最多允许 2 次跳转，超过则返回 WaitAction
        """
        if self.can_jump():
            self._record_jump()
            count = self._get_jump_count()
            logger.debug(f"跳转记录: {count}/{self._JUMP_MAX_COUNT} (窗口: {self._JUMP_WINDOW}s)")
            return self.step_produce_page()
        else:
            logger.debug(f"跳转限流: 已达到 {self._JUMP_MAX_COUNT} 次上限，等待中...")
            from app.engine.action import WaitAction
            return WaitAction(seconds=1.5)

    def reset_jump_records(self) -> None:
        """手动重置跳转记录（用于特殊场景）"""
        self.season_data["jump_records"] = []
        logger.debug("跳转记录已重置")