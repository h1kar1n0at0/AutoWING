"""
原子操作工厂 — Strategy 到 Action 的适配层

将"决策"（做什么）转换为"具体指令"（怎么做）。

职责：
  1. 封装固定坐标/参数的点击动作，避免策略层硬编码坐标 坐标系: 以 canvas 左上角为原点 (0,0)，基于 1600×902 参考系。
  2. 提供语义化的函数名（如 click_skill_single()），提高策略可读性
  3. 作为配置驱动的桥梁：读取 config_manager 配置，决定具体点击位置
  4. 集中管理动作参数，方便日后调整坐标和阈值

使用规范：
  - 所有原子操作返回 Action 对象（ClickAction / AccelClickAction / SequenceAction 等）
  - 策略层只调用原子操作函数，不直接构造 Action
  - 坐标使用逻辑坐标系（1600×902 基准），由 Action 内部的 use_logical=True 处理换算
  - 如需新增原子操作，先确认是否已有类似函数，避免重复

分层关系：
  策略层 (strategies/*.py)     → 调用原子操作，决定"做什么"
  原子操作层 (action_utils.py)  → 封装参数，生成"具体指令"
  动作定义层 (action.py)        → 定义 Action 数据结构
  执行层 (orchestrator.py)      → 执行 Action，实际操作游戏
"""

from app.engine.action import (ClickAction, AccelClickAction, SequenceAction, 
                               WaitForTemplateAction, RefreshAction, NavigateAction, 
                               ForwardAction, QteClickAction, BackAction, WaitAction, 
                               ScrollAction, ContinuousScrollAction, LongClickAction)
from app.engine.detector import TemplateDetector
from app.engine.templates import Templates
from app.engine.config_models import config_manager


# ─── 固定位置点击（原子操作）────────────────────────────

# —————— 育成外操作 ——————————————————————————————————————

def click_xy(x: float, y: float, desc: str = "点击") -> ClickAction:
    """点击指定坐标（动态，由调用方传入）"""
    return ClickAction(x=x, y=y, description=desc)

def long_click_xy(x: float, y: float, duration: float = 1.0, desc: str = "长按") -> ClickAction:
    """长按指定坐标（动态，由调用方传入）"""
    return LongClickAction(x=x, y=y, duration=duration, description=desc)

def click_xy_qte(x: float, y: float, desc: str = "点击") -> ClickAction:
    """点击指定坐标 用于视镜qte（动态，由调用方传入）"""
    return QteClickAction(
        x=x,
        y=y,
        total_clicks=2,
        interval=1.305+config_manager.config.qte_interval_offset,
        description=f"QTE 点击 2 次，间隔 1.305 s"
    )



def click_switch_training_tab() -> ClickAction:
    """切换育成选择页面"""
    return ClickAction(
        x=1137, y=124,
        description="切换育成选择页面"
    )


def click_training_difficulty_normal() -> ClickAction:
    """切换育成难度为普通"""
    return ClickAction(
        x=1089, y=475,
        description="切换育成难度为普通"
    )


def click_training_difficulty_hard() -> ClickAction:
    """切换育成难度为困难"""
    return ClickAction(
        x=1299, y=475,
        description="切换育成难度为困难"
    )

def click_produce_idol() -> ClickAction:
    """编成页面点击育成偶像"""
    return ClickAction(
        x=560, y=390,
        description="点击育成偶像"
    )

def select_te_mission_incomplete() -> SequenceAction:
    """筛选te任务未完成的育成偶像"""
    return SequenceAction(actions=(
        ClickAction(x=1060, y=160, description="开启筛选栏"),
        WaitAction(seconds=0.05),
        continuous_scroll(x=800, y=650, total_delta_y=-1500, steps=6, interval=0.05, description="滚动筛选栏到底部"),
        WaitAction(seconds=0.05),
        ClickAction(x=480, y=138, description="筛选te任务未完成"),
        WaitAction(seconds=0.05),
        ClickAction(x=1023, y=781, description="确认筛选适用"),
        WaitAction(seconds=0.05),
    ))

def select_1st_produce_idol() -> ClickAction:
    """育成偶像编成页面选择第一个育成偶像"""
    return ClickAction(
        x=377, y=300,
        description="选择第一个育成偶像"
    )

def click_training_confirm() -> ClickAction:
    """通用确定键"""
    return ClickAction(
        x=1466, y=829,
        description="通用确定键"
    )


def click_training_star() -> ClickAction:
    """星标键（切换展示）"""
    return ClickAction(
        x=848, y=187,
        description="星标键"
    )


def click_training_x3_stamina() -> ClickAction:
    """切换为3倍体力消耗"""
    return ClickAction(
        x=1294, y=841,
        description="切换为3倍体力消耗"
    )



def click_energy_item() -> SequenceAction:
    """使用体力道具"""
    return SequenceAction(actions=(
            ClickAction(x=1111, y=600, description="使用体力道具"),
            WaitAction(seconds=0.15),
            ClickAction(x=923, y=746, description="确认"),
            WaitAction(seconds=0.15),
            ClickAction(x=794, y=627, description="关闭"),
            WaitAction(seconds=0.15),
            click_training_confirm(),
        ))

# —————— 育成操作 ——————————————————————————————————————

def click_enter_skill_learning() -> SequenceAction:
    """进入技能学习页面"""
    return SequenceAction(actions=(
            ClickAction(x=1066, y=832, description="进入技能学习页面"),
            WaitAction(seconds=2.35),
            ClickAction(x=1535, y=579, description="缩放"),
            WaitAction(seconds=0.06),
            ClickAction(x=1535, y=579, description="缩放"),
            WaitAction(seconds=0.06),
            ClickAction(x=1535, y=579, description="缩放"),
        ))

def click_skill_learning() -> SequenceAction:
    """技能学习"""
    return SequenceAction(actions=(
            ClickAction(x=1449, y=805, description="确认"),
            WaitAction(seconds=0.05),
            ClickAction(x=875, y=723, description="二次确认"),
            WaitAction(seconds=0.05),
            ClickAction(x=875, y=651, description="二次确认"),
            WaitAction(seconds=0.05),
            ClickAction(x=1092, y=166, description="选择"),
            WaitAction(seconds=0.05),
            ClickAction(x=930, y=801, description="三次确认"),
            WaitAction(seconds=0.5),
        ))


def click_back() -> ClickAction:
    """进入日程页面"""
    return ClickAction(x=69, y=827, description="退出到上一页面")

def click_schedule() -> ClickAction:
    """进入日程页面"""
    return ClickAction(x=190, y=698, description="进入日程页面")

def click_stat_vo() -> ClickAction:
    """选择 Vo 课程"""
    return ClickAction(x=446, y=648, description="选择Vo课程")

def click_stat_da() -> ClickAction:
    """选择 Da 课程"""
    return ClickAction(x=637, y=651, description="选择Da课程")

def click_stat_vi() -> ClickAction:
    """选择 Vi 课程"""
    return ClickAction(x=852, y=651, description="选择Vi课程")

def click_stat_rai() -> ClickAction:
    """选择广播"""
    return ClickAction(x=1051, y=655, description="选择广播工作")

def click_stat_pho() -> ClickAction:
    """选择杂志摄影"""
    return ClickAction(x=1470, y=674, description="选择摄影工作")

def click_skip() -> ClickAction:
    """单点跳过"""
    return ClickAction(x=1523, y=68, description="单点跳过")

def click_confirm_promise() -> ClickAction:
    """同意约定"""
    return ClickAction(x=311, y=313, description="同意约定")

def click_refuse() -> ClickAction:
    """拒绝"""
    return ClickAction(x=1283, y=313, description="拒绝")

def click_rest() -> ClickAction:
    """休息"""
    return ClickAction(x=483, y=764, description="休息")

def click_audition() -> ClickAction:
    """进入视镜选择页面"""
    return ClickAction(x=165, y=593, description="进入视镜选择页面")

def click_next_audition() -> ClickAction:
    """切换到下一个视镜"""
    return ClickAction(x=1445, y=414, description="切换到下一个视镜")


def skip_story_with_multiple_clicks() -> SequenceAction:
    """跳过剧情"""
    return SequenceAction(actions=(
        ClickAction(
            x=1523, y=68,
            description="跳过剧情"
        ),
        ClickAction(
                    x=1414, y=823,
                    description="跳过剧情"
        ),
        ClickAction(
                    x=1523, y=68,
                    description="跳过剧情"
                ),
    ))


def skip_story_with_multiple_clicks_final() -> SequenceAction:
    """跳过剧情(最终视镜后)"""
    return SequenceAction(actions=(
        # 先点右上角跳过
        AccelClickAction(
            x=1523, y=68,
            interval=0.05,
            until_template=Templates.GLOBAL.get("post_training"),
            until_region=TemplateDetector.PAGE_POST_TRAINING,
            until_conf=0.9,
            timeout=60.0,
            description="跳过剧情(最终视镜后)"
        ),
        # 再点中间继续
        AccelClickAction(
                    x=1414, y=823,
                    interval=0.05,
                    until_template=Templates.GLOBAL.get("post_training"),
                    until_region=TemplateDetector.PAGE_POST_TRAINING,
                    until_conf=0.9,
                    timeout=60.0,
                    description="跳过剧情(最终视镜后)"
        ),
        AccelClickAction(
                    x=1414, y=823,
                    interval=0.05,
                    until_template=Templates.GLOBAL.get("post_training"),
                    until_region=TemplateDetector.PAGE_POST_TRAINING,
                    until_conf=0.9,
                    timeout=60.0,
                    description="跳过剧情(最终视镜后)"
        ),
    ))


def complex_skill_unlock() -> SequenceAction:
    """技能解锁：先选技能 → 等待 → 确认 → 返回"""
    return SequenceAction(actions=(
        # 1. 点击单体技能
        ClickAction(x=400, y=350, description="选择单体技能"),
        # 2. 等待技能详情出现
        WaitForTemplateAction(
            template="skill_detail.png",
            region=(300, 200, 400, 300),
            timeout=3.0,
        ),
        # 3. 点击确认
        ClickAction(x=960, y=600, description="确认技能"),
        # 4. 等待返回
        WaitForTemplateAction(
            template="skill_unlock.png",
            region=(77, 187, 504, 107),
            timeout=5.0,
            click_on_found=False,
        ),
    ))

# ─── 根据配置选择属性 ─────────────────────────────

def click_end_training() -> ClickAction:
    """点击开始育成"""
    return ClickAction(x=925, y=630, description="结束育成")

# ─── 导航原子操作 ────────────────────────────────────────

def refresh_page() -> RefreshAction:
    """刷新当前页面"""
    return RefreshAction(
        wait_after=0.5,
        description="刷新页面"
    )


def go_back() -> BackAction:
    """后退到上一页"""
    return BackAction(
        wait_after=0.05,
        description="后退"
    )


def go_forward() -> ForwardAction:
    """前进到下一页"""
    return ForwardAction(
        wait_after=0.05,
        description="前进"
    )


def go_to_produce_ready() -> NavigateAction:
    """跳转到育成准备页"""
    return NavigateAction(
        action="goto",
        url="https://shinycolors.enza.fun/produceReady",
        wait_after=1.25,
        description="跳转到育成准备页"
    )


def go_to_produce1() -> NavigateAction:
    """跳转到育成页1"""
    return NavigateAction(
        action="goto",
        url="https://shinycolors.enza.fun/produce/?a=",
        wait_after=0.15,
        description="跳转到育成页1"
    )

def go_to_produce2() -> NavigateAction:
    """跳转到育成页2"""
    return NavigateAction(
        action="goto",
        url="https://shinycolors.enza.fun/produce/?a=#",
        wait_after=1.5,
        description="跳转到育成页2"
    )

# ── 滚动动作 ─────────────────────────────────
def continuous_scroll(x: float, y: float, total_delta_y: float = -1000, steps: int = 5, interval: float = 0.05, description: str = "连续滚动") -> ContinuousScrollAction:
    """连续滚动（模拟滚轮连续多次滚动）"""
    return ContinuousScrollAction(
        x=800,  # 默认滚动位置为 canvas 中心
        y=600,
        total_delta_y=total_delta_y,
        steps=steps,
        interval=interval,
        wait_after=0.2,
        description=description
    )

def scroll_on_xy(delta_x: float = 0, delta_y: float = -300) -> ScrollAction:
    """在指定位置滚动"""
    return ScrollAction(
        x=800,  # 默认滚动位置为 canvas 中心
        y=600,
        delta_x=delta_x,
        delta_y=delta_y,
        wait_after=0.2,
        description="滚动"
    )