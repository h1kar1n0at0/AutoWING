"""
主循环 Orchestrator — 调度器模式

每 tick:
  1. 有 _active_flow → step() → 执行 Action
  2. 无 _active_flow → detect_global() → 创建对应 Flow
"""
from __future__ import annotations
import logging
import random
import time
from typing import Optional

from app.core import (
    find, click_on_canvas, wait_for_stable,
    page_go_back, page_go_forward, page_reload, page_goto,execute_qte_sequence,
    scroll_on_canvas, continuous_scroll
)
from app.tasks.base import Task, TaskState
from app.engine.context import Context
from app.engine.state import GlobalState
from app.engine.action import (
    Action, ClickAction, LongClickAction, WaitAction,
    WaitForStableAction, WaitForTemplateAction,
    AccelClickAction, SequenceAction, RunTaskAction,
    NavigateAction, ForwardAction, BackAction, RefreshAction,QteClickAction,
    ScrollAction, ContinuousScrollAction
)
from app.engine.detector import GameStateDetector, TemplateDetector
from app.engine.config_models import config_manager
from app.engine.flows.base import Flow
from app.engine.flows.pre_training import PreTrainingFlow
from app.engine.flows.training import TrainingFlow
from app.engine.flows.post_training import PostTrainingFlow
from app.notify.events import NotificationEvent, NotificationLevel

logger = logging.getLogger("autowing.engine.orchestrator")


def get_notification_service():
    from app.notify.runtime import get_notification_service as get_service

    return get_service()


class Orchestrator(Task):
    """自动化调度器

    不包含任何流程逻辑 — 全部委托给 Flow 子类。
    """

    def __init__(self, detector: Optional[GameStateDetector] = None):
        super().__init__(name="Orchestrator")
        self.detector = detector or TemplateDetector()
        self.ctx = Context()
        self._active_flow: Optional[Flow] = None

        # 错误跟踪
        self._consecutive_unknowns = 0
        self._unknown_notified = False

        # 运行计数与循环间隔
        cfg = config_manager.config
        self._run_count = 0
        self._run_target = cfg.max_runs  # 0 = 无限
        self._loop_delay = getattr(cfg, 'loop_interval', 0.05)

    def set_run_count(self, n: int) -> None:
        self._run_count = n

    # ── 主循环 ─────────────────────────────────

    def execute(self) -> None:
        self.ctx.start_time = time.time()
        self.log("Orchestrator 已启动")

        while not self.should_stop:
            try:
                self._tick()
            except InterruptedError:
                break
            except Exception as e:
                self.log(f"循环异常: {e}", "error")
                self._notify(
                    "loop_exception", NotificationLevel.ERROR,
                    "AutoWING：循环异常", str(e),
                    f"loop:{type(e).__name__}:{self._consecutive_unknowns // 5}",
                )
                self._consecutive_unknowns += 1
                if self._consecutive_unknowns > 30:
                    self.log("异常过多，自动停止", "error")
                    self._notify(
                        "excessive_errors", NotificationLevel.ERROR,
                        "AutoWING：异常过多，已停止",
                        "主循环连续异常超过 30 次，自动停止。",
                        "excessive-errors",
                    )
                    break
                time.sleep(min(2.0, 0.1 * self._consecutive_unknowns))

        self.log("Orchestrator 已停止")

    def _tick(self) -> None:
        t0 = time.perf_counter()

        # ── 1. 有活跃 Flow → 执行一步 ──
        if self._active_flow is not None:
            try:
                action = self._active_flow.step(self.ctx)
            except Exception as e:
                self.log(f"Flow 异常: {e}", "error")
                flow_name = type(self._active_flow).__name__
                self._notify(
                    "flow_exception", NotificationLevel.ERROR,
                    f"AutoWING：{flow_name} 异常", str(e),
                    f"{flow_name}:{type(e).__name__}",
                )
                self._active_flow = None
                return

            # 处理控制信号 (先执行动作, 后处理信号)
            if action is not None:
                self._execute_action(action)

            signal = self._consume_signal()
            if signal is not None:
                self._handle_signal(signal)
                return

            # Flow 自然完成
            if action is None:
                if isinstance(self._active_flow, PostTrainingFlow):
                    self._on_training_run_done()
                self._active_flow = None
            return

        # ── 2. 无 Flow → 检测全局状态 ──
        gs = self.detector.detect_global()
        is_new = self.ctx.record_global_transition(gs)

        if is_new:
            self.log(f"全局状态: {gs.name}")

        if gs == GlobalState.PRE_TRAINING:
            self._active_flow = PreTrainingFlow()
            if self.detector.detect_pre_training_item():
                self._active_flow.set_step("energy_x3")
            elif self.detector.detect_formation():
                self._active_flow.set_step("formation")
        elif gs == GlobalState.TRAINING:
            self._active_flow = TrainingFlow()
        elif gs == GlobalState.POST_TRAINING:
            self._on_training_run_done()
            self._active_flow = PostTrainingFlow()
        else:
            self._consecutive_unknowns += 1
            if self._consecutive_unknowns == 1:
                self.log(f"未知状态 (第{self._consecutive_unknowns}次)", "warning")
            if self._consecutive_unknowns >= 10 and not self._unknown_notified:
                self._unknown_notified = True
                self._notify(
                    "unknown_threshold", NotificationLevel.WARNING,
                    "AutoWING：未知状态持续过久",
                    "连续 UNKNOWN 状态已超过 10 次。",
                    "unknown-threshold",
                )
            time.sleep(0.5)

        if gs != GlobalState.UNKNOWN:
            self._unknown_notified = False

        # 3. 限速
        elapsed = time.perf_counter() - t0
        sleep_time = self._loop_delay - elapsed
        if sleep_time > 0:
            if self.should_stop:
                raise InterruptedError()
            time.sleep(max(0.001, sleep_time))

    def _consume_signal(self):
        """读取并清空 ctx.signal, 返回信号或 None"""
        sig = self.ctx.signal
        self.ctx.signal = None
        return sig

    def _handle_signal(self, signal) -> None:
        """处理 Flow 控制信号"""
        from app.engine.flows.base import StopSignal, SwitchFlowSignal

        if isinstance(signal, StopSignal):
            self.log(f"停止信号: {signal.reason}")
            self._notify(
                "stop_signal", NotificationLevel.WARNING,
                "AutoWING：收到停止信号", signal.reason,
                f"stop:{signal.reason}",
            )
            self.stop()
            return

        if signal.target is None or signal.target == "idle":
            if signal.kwargs.get("training_done"):
                self._on_training_run_done()

            self._active_flow = None
            self.log("已切换到 idle 状态")
            return

        elif isinstance(signal, SwitchFlowSignal):
            self.log(f"切换 Flow: {signal.target}")
            
            mapping = {
                "pre_training": PreTrainingFlow,
                "training": TrainingFlow,
                "post_training": PostTrainingFlow,
            }
            cls = mapping.get(signal.target)
            if cls is not None:
                self._active_flow = cls(**signal.kwargs)
            else:
                self.log(f"未知 Flow 目标: {signal.target}", "warning")
                self._active_flow = None
            if signal.target == "pre_training":
                self._on_training_run_done()

    def _on_training_run_done(self) -> None:
        """一次育成运行完成时的处理"""
        self._run_count += 1
        self.log(f"育成完成, 已执行 {self._run_count} 次")
        self._notify(
            "training_done", NotificationLevel.INFO,
            "AutoWING：育成完成",
            f"已完成第 {self._run_count} 次育成。",
            f"run:{self._run_count}",
        )
        if self._run_target > 0 and self._run_count >= self._run_target:
            self.log(f"达到执行次数 {self._run_target}, 停止")
            self._notify(
                "run_target_reached", NotificationLevel.WARNING,
                "AutoWING：达到目标次数，已停止",
                f"已达到目标次数 {self._run_target}。",
                f"target:{self._run_target}",
            )
            self.stop()

    def _notify(
        self,
        event_type: str,
        level: NotificationLevel,
        title: str,
        body: str,
        dedup_key: str,
        bypass_level_filter: bool = False,
    ) -> None:
        try:
            get_notification_service().publish(NotificationEvent(
                event_type=event_type,
                level=level,
                title=title,
                body=body[:1000],
                dedup_key=dedup_key,
                bypass_level_filter=bypass_level_filter,
            ))
        except Exception as exc:
            logger.debug("通知入队失败: event=%s error=%s", event_type, type(exc).__name__)

    # ── 动作执行 ──────────────────────────────

    def _execute_action(self, action: Action) -> None:
        if isinstance(action, ClickAction):
            click_on_canvas(action.x, action.y)
            if action.wait_after > 0:
                self._interruptible_sleep(action.wait_after)

        elif isinstance(action, LongClickAction):
            click_on_canvas(action.x, action.y, duration=action.duration)

        elif isinstance(action, WaitAction):
                # 计算实际等待时间
            wait_time = action.seconds
            
            # 应用全局偏移（只对非零等待生效）
            if wait_time > 0.05:
                offset = config_manager.config.wait_offset
                wait_time = max(0, wait_time + offset)
            
            self._interruptible_sleep(wait_time)

        elif isinstance(action, WaitForStableAction):
            wait_for_stable(
                roi=action.roi, diff_threshold=action.diff_threshold,
                min_stable_frames=action.min_stable_frames,
                timeout=action.timeout,
            )

        elif isinstance(action, QteClickAction):
            self._execute_qte_click(action)


        elif isinstance(action, WaitForTemplateAction):
            self._execute_wait_for_template(action)

        elif isinstance(action, AccelClickAction):
            self._execute_accel_click(action)

        elif isinstance(action, SequenceAction):
            for sub in action.actions:
                if self.should_stop:
                    raise InterruptedError()
                self._execute_action(sub)

        elif isinstance(action, RunTaskAction):
            self._execute_sub_task(action)

        elif isinstance(action, ForwardAction):
            self.log("前进")
            page_go_forward()
            if action.wait_after > 0:
                self._interruptible_sleep(action.wait_after)

        elif isinstance(action, BackAction):
            self.log("后退")
            page_go_back()
            if action.wait_after > 0:
                self._interruptible_sleep(action.wait_after)

        elif isinstance(action, RefreshAction):
            self.log("刷新页面")
            page_reload()
            if action.wait_after > 0:
                self._interruptible_sleep(action.wait_after)

        elif isinstance(action, NavigateAction):
            self.log(f"跳转至 {action.url}")
            page_goto(action.url)
            if action.wait_after > 0:
                self._interruptible_sleep(action.wait_after)

        elif isinstance(action, ScrollAction):
            scroll_on_canvas(action.x, action.y, delta_x=action.delta_x, delta_y=action.delta_y)
            if action.wait_after > 0:
                self._interruptible_sleep(action.wait_after)

        elif isinstance(action, ContinuousScrollAction):
            continuous_scroll(action.x, action.y, total_delta_y=action.total_delta_y, steps=action.steps, interval=action.interval)
            if action.wait_after > 0:
                self._interruptible_sleep(action.wait_after)


    def _execute_accel_click(self, action: AccelClickAction) -> None:
        deadline = time.time() + action.timeout
        last_click = 0.0

        while not self.should_stop:
            now = time.perf_counter()
            if now - last_click >= action.interval:
                ax = action.x + random.randint(-action.jitter, action.jitter)
                ay = action.y + random.randint(-action.jitter, action.jitter)
                click_on_canvas(ax, ay)
                last_click = now

            if action.until_template:
                hit = find(action.until_template, region=action.until_region,
                           conf=action.until_conf)
                if hit:
                    return

            if time.time() > deadline:
                return
            if self.should_stop:
                raise InterruptedError()
            time.sleep(0.005)

    def _execute_wait_for_template(self, action: WaitForTemplateAction) -> None:
        deadline = time.time() + action.timeout
        while not self.should_stop:
            hit = find(action.template, region=action.region,
                       conf=action.conf)
            if hit:
                if action.click_on_found:
                    click_on_canvas(hit.x, hit.y)
                return
            if time.time() > deadline:
                break
            if self.should_stop:
                raise InterruptedError()
            time.sleep(0.05)

    def _execute_sub_task(self, action: RunTaskAction) -> None:
        try:
            import importlib
            mod_path, cls_name = action.task_cls_path.rsplit(".", 1)
            mod = importlib.import_module(mod_path)
            task_cls = getattr(mod, cls_name)
            task = task_cls(**action.kwargs)
            task.set_log_callback(self._on_log)
            task.start()

            while not self.should_stop:
                if task.state not in (TaskState.RUNNING,):
                    break
                time.sleep(0.5)
        except Exception as e:
            self.log(f"子任务启动失败: {e}", "error")

    def _interruptible_sleep(self, seconds: float) -> None:
        """可中断的 sleep，兼容 Windows"""
        if seconds <= 0:
            return
        
        end = time.time() + seconds
        while time.time() < end:
            if self.should_stop:
                raise InterruptedError()
            remaining = end - time.time()
            if remaining > 0.01:
                time.sleep(min(remaining, 0.01))
            else:
                # 最后 10ms 忙等待
                while time.time() < end:
                    if self.should_stop:
                        raise InterruptedError()
                
    def _execute_qte_click(self, action: QteClickAction) -> None:
        """执行 QTE 固定节奏点击 (高精度打包版)"""
        self.log(f"QTE 点击启动: {action.description} ({action.total_clicks}次, 间隔{action.interval}s)")
        
        # 将整个 QTE 过程作为整体派发，避免在 Python 主线程中逐次跨线程通信
        execute_qte_sequence(
            ref_x=action.x,
            ref_y=action.y,
            total_clicks=action.total_clicks,
            interval=action.interval,
            jitter=action.jitter
        )

    # ── 暴露给 API 的快照 ────────────────────

    def get_snapshot(self) -> dict:
        snap = self.ctx.snapshot()
        snap["flow"] = type(self._active_flow).__name__ if self._active_flow else None
        snap["run_count"] = self._run_count
        snap["run_target"] = self._run_target
        return snap
