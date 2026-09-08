"""AutoWING 自动化引擎 — 状态机 + 策略模式"""
from app.engine.orchestrator import Orchestrator
from app.engine.state import GlobalState, SeasonState, PageState
from app.engine.context import Context
from app.engine.detector import TemplateDetector
from app.engine.registry import StrategyRegistry