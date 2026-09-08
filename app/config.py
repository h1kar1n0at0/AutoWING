"""AutoWING 配置管理"""
import json
import os
from pathlib import Path


CONFIG_FILE = Path(__file__).parent.parent / "config.json"

DEFAULT_CONFIG = {
    # 窗口绑定
    "window_title": "アイドルマスター シャイニーカラーズ",
    "browser_type": "chrome",

    # Canvas 逻辑分辨率（游戏固定值）
    "canvas_logical_width": 1136,
    "canvas_logical_height": 640,

    # 参考校准数据
    "calibration": {
        "canvas_left": 0,
        "canvas_top": 0,
        "canvas_width": 1600,
        "canvas_height": 902,
    },

}


class Config:
    """JSON 持久化配置"""

    def __init__(self):
        self._data = dict(DEFAULT_CONFIG)
        self.load()

    @property
    def canvas_logical_size(self):
        return (self._data["canvas_logical_width"], self._data["canvas_logical_height"])

    @property
    def calibration(self):
        return self._data["calibration"]

    @calibration.setter
    def calibration(self, value):
        self._data["calibration"] = value
        self.save()

    @property
    def window_title(self):
        return self._data["window_title"]

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value
        self.save()

    def load(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self._data.update(loaded)
            except (json.JSONDecodeError, IOError):
                pass

    def save(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except IOError as e:
            print(f"[配置] 保存失败: {e}")


# 全局单例
config = Config()
