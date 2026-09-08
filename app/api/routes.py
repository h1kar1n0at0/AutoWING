"""
Flask REST API — 控制面板的后端接口
"""
from __future__ import annotations
import json
import logging
import threading
import time
from typing import Optional

from flask import Blueprint, jsonify, request, Response, render_template

import win32gui

from app.core import coord, clicker, CanvasDetector
from app.config import config
from app.api.log_handler import get_log_handler
from app.paths import ASSETS_DIR

logger = logging.getLogger("autowing.api")

bp = Blueprint("api", __name__)

# ── 运行时状态 ──────────────────────────────
_current_task = None
_task_lock = threading.Lock()
_task_thread: Optional[threading.Thread] = None


def _log_callback(level: str, message: str):
    get_log_handler().add_log(level, message)


# ── 状态 ────────────────────────────────────

@bp.route("/api/status")
def api_status():
    """获取当前系统状态"""
    from app.tasks.base import TaskState

    task_info = {}
    with _task_lock:
        if _current_task:
            task_info = {
                "name": _current_task.name,
                "state": _current_task.state.value,
            }
        else:
            task_info = {"name": None, "state": TaskState.IDLE.value}

    # 如果当前任务是新引擎的 Orchestrator，附带 ctx snapshot
    ctx_snapshot = None
    if _current_task and hasattr(_current_task, "get_snapshot"):
        try:
            ctx_snapshot = _current_task.get_snapshot()
        except Exception:
            pass

    return jsonify({
        "task": task_info,
        "calibrated": coord.is_calibrated,
        "canvas": {
            "left": coord.canvas_left,
            "top": coord.canvas_top,
            "width": coord.canvas_width,
            "height": coord.canvas_height,
            "logical_w": coord.logical_w,
            "logical_h": coord.logical_h,
            "scale_x": round(coord.scale_x, 4),
            "scale_y": round(coord.scale_y, 4),
        },
        "config": {
            "window_title": config.window_title,
        },
        "engine": ctx_snapshot,
    })


# ── 日历/绑定 ───────────────────────────────

@bp.route("/api/detect-canvas", methods=["POST"])
def api_detect_canvas():
    """检测 Canvas 位置"""
    data = request.get_json(silent=True) or {}
    detector = CanvasDetector()

    result = detector.detect(
        hwnd=clicker.hwnd,
        force_method=data.get("method"),
    )

    if result:
        coord.calibrate_from_canvas_element(
            left=result["left"], top=result["top"],
            width=result["width"], height=result["height"],
        )
        clicker.find_window()
        return jsonify({
            "success": True,
            "canvas": {
                "left": result["left"], "top": result["top"],
                "width": result["width"], "height": result["height"],
                "logicalWidth": result.get("logicalWidth", 1136),
                "logicalHeight": result.get("logicalHeight", 640),
            },
            "description": coord.description(),
        })
    return jsonify({"success": False, "error": "CDP 无法连接。浏览器未开启调试端口"}), 400


@bp.route("/api/launch-browser", methods=["POST"])
def api_launch_browser():
    """重启浏览器 + CDP 调试端口"""
    data = request.get_json(silent=True) or {}
    try:
        result = CanvasDetector.launch_browser(
            game_url=data.get("url", "https://shinycolors.enza.fun/produceReady"),
            close_first=data.get("close_first", True),
        )
        return jsonify({"success": True, "browser": result})
    except RuntimeError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/api/bind-window", methods=["POST"])
def api_bind_window():
    """绑定浏览器窗口"""
    data = request.get_json(silent=True) or {}
    title = data.get("window_title", config.window_title)

    clicker.window_title = title
    if clicker.find_window():
        rect = clicker.get_window_rect()
        return jsonify({
            "success": True,
            "window": rect,
            "title": win32gui.GetWindowText(clicker.hwnd) if clicker.hwnd else title,
        })

    return jsonify({"success": False, "error": f"未找到窗口: {title}"}), 400


# ── 任务控制 ────────────────────────────────

@bp.route("/api/start", methods=["POST"])
def api_start():
    """启动自动化 (新引擎)"""
    from app.engine import Orchestrator

    global _current_task, _task_thread

    with _task_lock:
        if _current_task and _current_task.state.value == "running":
            return jsonify({"success": False, "error": "任务已在运行"}), 409

        if not coord.is_calibrated:
            return jsonify({"success": False, "error": "请先检测 Canvas"}), 400

        task = Orchestrator()
        task.set_log_callback(_log_callback)
        task.start()
        _current_task = task

        return jsonify({"success": True, "task": {"name": task.name, "state": "running"}})


@bp.route("/api/stop", methods=["POST"])
def api_stop():
    """停止自动化"""
    global _current_task
    with _task_lock:
        if _current_task:
            _current_task.stop()
            _current_task = None
            return jsonify({"success": True})
    return jsonify({"success": False, "error": "没有运行中的任务"}), 400


@bp.route("/api/detect-season", methods=["POST"])
def api_detect_season():
    """检测当前季度"""
    season = _detect_season()
    return jsonify({"success": True, "season": season})


def _detect_season() -> Optional[str]:
    """检测游戏当前季度 (兼容旧 API)"""
    from app.engine.detector import TemplateDetector
    detector = TemplateDetector()
    season = detector.detect_season()
    if season is not None:
        logger.info(f"检测到季度: {season.name}")
        return season.to_string()
    return None


# ── 配置 ────────────────────────────────────

@bp.route("/api/config", methods=["GET", "POST"])
def api_config():
    if request.method == "GET":
        return jsonify({
            "window_title": config.window_title,
        })

    data = request.get_json(silent=True) or {}
    if "window_title" in data:
        config.set("window_title", data["window_title"])
    return jsonify({"success": True})


# ── 策略配置 ────────────────────────────────

@bp.route("/api/strategy-config", methods=["GET", "POST"])
def api_strategy_config():
    """读写策略配置"""
    from app.engine.config_models import config_manager
    if request.method == "GET":
        return jsonify({"success": True, "config": config_manager.config.to_dict()})
    data = request.get_json(silent=True) or {}
    updated = config_manager.update(data.get("config", data))
    get_log_handler().add_log("info", "💾 策略配置已保存")
    return jsonify({"success": True, "config": updated.to_dict()})


@bp.route("/api/strategy-config/reset", methods=["POST"])
def api_strategy_config_reset():
    from app.engine.config_models import StrategyConfig, config_manager
    config_manager._config = StrategyConfig()
    config_manager.save()
    get_log_handler().add_log("info", "↺ 策略配置已重置")
    return jsonify({"success": True})


@bp.route("/api/strategy-config/skills", methods=["GET"])
def api_list_skill_templates():
    """列出 assets/skills/ 下可用技能图标 (含中文名)"""
    import os, json
    sd = str(ASSETS_DIR / "skills")
    files = sorted(f for f in os.listdir(sd) if f.lower().endswith((".png", ".jpg"))) if os.path.isdir(sd) else []
    # 加载翻译
    tpath = os.path.join(sd, "translate.json")
    translations = {}
    if os.path.isfile(tpath):
        try:
            with open(tpath, "r", encoding="utf-8") as f:
                translations = json.load(f)
        except: pass
    skills = [{"file": f, "name": translations.get(f, f)} for f in files]
    return jsonify({"success": True, "skills": skills})


@bp.route("/api/learn-order/export", methods=["POST"])
def api_learn_order_export():
    """导出技能学习顺序为 JSON 文件 (系统另存为对话框)"""
    data = request.get_json(silent=True) or {}
    points = data.get("data")
    if not isinstance(points, list) or not points:
        return jsonify({"success": False, "error": "学习顺序为空"}), 400
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.asksaveasfilename(
            title="保存技能学习顺序",
            defaultextension=".json",
            initialfile=f"learn_order_{time.strftime('%Y-%m-%d')}.json",
            filetypes=[("JSON 文件", "*.json")],
        )
        root.destroy()
    except Exception as e:
        return jsonify({"success": False, "error": f"保存对话框失败: {e}"}), 500
    if not path:
        return jsonify({"success": False, "error": "已取消保存"})
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(points, f, indent=2, ensure_ascii=False)
        get_log_handler().add_log("info", f"📤 学习顺序已导出: {path}")
        return jsonify({"success": True, "path": path})
    except Exception as e:
        return jsonify({"success": False, "error": f"写入失败: {e}"}), 500


@bp.route("/api/learn-order/import", methods=["POST"])
def api_learn_order_import():
    """从 JSON 文件导入技能学习顺序 (系统打开对话框)"""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askopenfilename(
            title="选择技能学习顺序 JSON",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
        )
        root.destroy()
    except Exception as e:
        return jsonify({"success": False, "error": f"打开对话框失败: {e}"}), 500
    if not path:
        return jsonify({"success": False, "error": "已取消选择"})
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return jsonify({"success": False, "error": "JSON 内容不是数组"}), 400
        get_log_handler().add_log("info", f"📥 已读取学习顺序: {path} ({len(data)} 个点)")
        return jsonify({"success": True, "data": data})
    except json.JSONDecodeError:
        return jsonify({"success": False, "error": "JSON 格式错误"}), 400
    except Exception as e:
        return jsonify({"success": False, "error": f"读取失败: {e}"}), 500


# ── 日志 SSE ────────────────────────────────

@bp.route("/api/logs/stream")
def api_logs_stream():
    """SSE 实时日志流"""
    handler = get_log_handler()

    def generate():
        # 发送初始连接消息
        yield f"data: {json.dumps({'type': 'connected'})}\n\n"
        while True:
            items = handler.get_all()
            if items:
                for item in items:
                    yield f"data: {json.dumps({'type': 'log', **item})}\n\n"
            else:
                yield ": heartbeat\n\n"  # SSE 心跳
            time.sleep(0.5)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── UI 页面 ─────────────────────────────────

@bp.route("/favicon.ico")
def favicon():
    return "", 204


# ── 技能学习录制 ────────────────────────────
@bp.route("/api/capture-canvas", methods=["GET"])
def api_capture_canvas():
    """通过 CDP 截取 canvas 并返回 PNG"""
    from app.core import capture_canvas
    data = capture_canvas()
    if not data:
        return jsonify({"success": False, "error": "CDP 未连接或无 canvas"}), 400
    try:
        from flask import send_file
        import io
        return send_file(io.BytesIO(data), mimetype="image/jpeg")
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/api/browse-file", methods=["POST"])
def api_browse_file():
    """弹出系统文件选择框 (tkinter), 返回所选文件路径"""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        return jsonify({"success": False, "error": "系统缺少 tkinter, 无法打开文件选择框"}), 500

    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askopenfilename(
            title="选择浏览器可执行文件",
            filetypes=[("可执行文件", "*.exe"), ("所有文件", "*.*")],
        )
        root.destroy()
    except Exception as e:
        return jsonify({"success": False, "error": f"文件选择失败: {e}"}), 500

    if path:
        return jsonify({"success": True, "path": path})
    return jsonify({"success": False, "error": "未选择文件"})


@bp.route("/api/skill-image/<filename>")
def api_skill_image(filename):
    """返回技能缩略图 (assets/skills/)"""
    import os
    sd = str(ASSETS_DIR / "skills")
    base = os.path.abspath(sd)
    fpath = os.path.abspath(os.path.join(sd, filename))
    if os.path.commonpath([base, fpath]) != base:
        return "", 403
    if os.path.isfile(fpath):
        from flask import send_file
        return send_file(fpath, mimetype="image/png")
    return "", 404


@bp.route("/")
def index():
    return render_template("index.html")
