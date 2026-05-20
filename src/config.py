import os
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, 'assets')
ICONS_DIR = os.path.join(ASSETS_DIR, 'icons')

# 窗口配置
PET_SIZE = 80
CHAT_WIDTH = 420
CHAT_HEIGHT = 550

# 学习面板
LEARNING_PANEL_WIDTH = 560
LEARNING_PANEL_HEIGHT = 640

# LearningDesk 数据库路径：优先环境变量，其次默认位置
_default_db = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "LearningDesk" / "learning_desk.db"
LEARNING_DESK_DB = os.environ.get("LEARNING_DESK_DB", str(_default_db))
