"""
游戏数据 API（被动 buff / 技能伤害）

同步公开 API，内部调度到 canvas_session 的后台事件循环。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from app.core.canvas_session import (
    _ensure_bg,
    _is_bg_loop_alive,
    _run_on_bg_loop,
    get_page,
)

logger = logging.getLogger("autowing.canvas_game_api")

_EVAL_TIMEOUT = 3.0

_GAME_DATA_JS = """() => {
    const api = window.__ENZA_OVERLAY_API__;
    if (!api) return { installed: false, ready: false };
    let ready = false;
    try { ready = !!api.ready(); } catch (e) {}
    if (!ready) return { installed: true, ready: false };
    let passive = null, skills = null, err = null;
    try { passive = api.passiveBuff(); } catch (e) { err = 'passiveBuff: ' + e; }
    try { skills = api.skillCards(); } catch (e) { err = (err ? err + '; ' : '') + 'skillCards: ' + e; }
    return { installed: true, ready: true, passive, skills, error: err };
}"""


async def _async_get_game_data():
    page = get_page()
    if not page:
        return {"connected": False, "error": "no page for window"}
    try:
        data = await asyncio.wait_for(page.evaluate(_GAME_DATA_JS), timeout=_EVAL_TIMEOUT)
        data["connected"] = True
        return data
    except asyncio.TimeoutError:
        return {"connected": False, "error": "evaluate timeout"}
    except Exception as e:
        return {"connected": False, "error": f"{type(e).__name__}: {e}"}


def get_game_data() -> dict:
    _ensure_bg()
    if not _is_bg_loop_alive():
        return {"connected": False, "error": "bg loop not alive"}
    result = _run_on_bg_loop(_async_get_game_data())
    return result if result is not None else {"connected": False, "error": "evaluate failed"}

def get_passive_buff() -> dict:
    d = get_game_data()
    return d.get("passive") or {"ready": False, "error": d.get("error", "unavailable")}


def get_skill_cards() -> dict:
    d = get_game_data()
    return d.get("skills") or {"ready": False, "cards": [], "error": d.get("error", "unavailable")}