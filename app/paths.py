"""
路径工具 — 统一资源定位，兼容 PyInstaller 打包
"""
from __future__ import annotations
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    APP_ROOT = Path(sys._MEIPASS)
else:
    APP_ROOT = Path(__file__).resolve().parent.parent

ASSETS_DIR = APP_ROOT / "assets"


def asset(rel: str) -> str:
    """将 'assets/xxx.png'（或 'xxx.png'）解析为基于资源目录的绝对路径"""
    rel = rel.replace("\\", "/")
    if rel.startswith("assets/"):
        rel = rel[len("assets/"):]
    return str((ASSETS_DIR / rel).resolve())
