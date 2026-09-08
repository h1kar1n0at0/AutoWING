"""AutoWING 核心引擎 — 公共 API 门面

业务代码统一从这里导入，避免直接依赖具体内部模块。
"""
from app.core.canvas import CanvasDetector
from app.core.canvas_capture import (
    capture_canvas,
    clear_cache,
    wait_for_stable,
)
from app.core.canvas_interaction import (
    click_on_canvas,
    execute_qte_sequence,
    get_canvas_rect,
    get_page,
    page_go_back,
    page_go_forward,
    page_goto,
    page_reload,
    preview_coords,
    continuous_scroll,
    scroll_on_canvas,
)
from app.core.canvas_session import set_bg_capture_interval, stop_bg_worker
from app.core.canvas_vision import (
    Hit,
    analyze_pixel_color,
    analyze_region_color,
    check_pixel_color,
    check_region_color,
    check_region_color_cached,
    find,
    find_all,
    find_with_fallback,
)
from app.core.clicker import BackgroundClicker, clicker
from app.core.coord import REF_H, REF_W, CoordSystem, coord

__all__ = [
    "REF_H",
    "REF_W",
    "BackgroundClicker",
    # canvas
    "CanvasDetector",
    "CoordSystem",
    "Hit",
    "analyze_pixel_color",
    "analyze_region_color",
    "capture_canvas",
    "check_pixel_color",
    "check_region_color",
    "check_region_color_cached",
    # canvas_capture
    "clear_cache",
    # canvas_interaction
    "click_on_canvas",
    "get_canvas_rect",
    "get_page",
    "page_go_back",
    "page_go_forward",
    "page_goto",
    "page_reload",
    "preview_coords",
    "set_bg_capture_interval",
    "continuous_scroll",
    "scroll_on_canvas",
    # clicker
    "clicker",
    # coord
    "coord",
    "execute_qte_sequence",
    # canvas_vision
    "find",
    "find_all",
    "find_with_fallback",
    # canvas_session
    "stop_bg_worker",
    "wait_for_stable",
]
