"""
策略注册表 — 装饰器注册 + 自动发现

用法::

    @StrategyRegistry.register(SeasonState.S3)
    class S3Strategy(SeasonStrategy):
        season = SeasonState.S3
        ...

注册: 模块底部静态导入 app.engine.strategies 下各策略模块，
执行它们的顶层代码 (@register 装饰器在类定义时触发注册)。
(静态导入而非扫描/动态 import, 兼容 PyInstaller 打包)
"""
from __future__ import annotations
import logging
from typing import Optional

from app.engine.state import SeasonState
from app.engine.strategy import SeasonStrategy

logger = logging.getLogger("autowing.engine.registry")


class StrategyRegistry:
    """策略注册表"""

    _strategies: dict[SeasonState, type[SeasonStrategy]] = {}

    @classmethod
    def register(cls, season: SeasonState):
        """装饰器: 注册一个策略类"""
        def wrapper(clazz: type[SeasonStrategy]) -> type[SeasonStrategy]:
            if not issubclass(clazz, SeasonStrategy):
                raise TypeError(f"{clazz.__name__} 不是 SeasonStrategy 子类")
            cls._strategies[season] = clazz
            logger.debug(f"已注册策略: {clazz.__name__} → {season}")
            return clazz
        return wrapper

    @classmethod
    def get(cls, season: SeasonState) -> Optional[SeasonStrategy]:
        """获取季度对应的策略实例，未注册返回 None"""
        clazz = cls._strategies.get(season)
        if clazz is None:
            return None
        return clazz()

    @classmethod
    def get_all_seasons(cls) -> set[SeasonState]:
        return set(cls._strategies.keys())

    @classmethod
    def unregister_all(cls) -> None:
        cls._strategies.clear()


# ── 策略模块注册 ──────────────────────────────
# 显式静态导入策略模块:
#   1) 模块导入时 @register 装饰器即完成注册
#   2) 静态导入可被 PyInstaller 静态分析收集, 打包后策略不会缺失
#      (pkgutil.iter_modules 动态扫描在冻结后枚举不到 PYZ 内的模块;
#       importlib 字符串导入也无法被 PyInstaller 追踪)
from app.engine.strategies import s1_strategy  # noqa: F401  (同时注册 S1/S2)
from app.engine.strategies import s3_strategy  # noqa: F401
from app.engine.strategies import s4_strategy  # noqa: F401
from app.engine.strategies import s5_strategy  # noqa: F401
