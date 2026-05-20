# Hermes Pet - Super Floating Learning Assistant

桌面悬浮 AI 助手 + 学习计划管理一体化工具。基于 PyQt5，暗色主题。

## Features

- **AI 聊天** — 悬浮球左键打开，通过 Hermes CLI 交互，支持图片粘贴/拖拽
- **学习面板** — 悬浮球右键打开，5 个标签页：
  - 今日计划 — 任务增删改查 + 完成勾选
  - 睡前记录 — 每日学习心得
  - 周期总结 — AI 生成周/半月/月总结
  - 学习建议 — AI 个性化学习建议
  - 历史回顾 — 查看所有历史记录
- **LearningDesk 兼容** — 直接读取 LearningDesk 数据库，历史数据不丢失

## Prerequisites

- Windows 10/11
- Python 3.10+
- [Hermes Agent](https://github.com/NousResearch/hermes-agent) installed (for AI chat)
- (Optional) [LearningDesk](https://github.com/) installed (for existing task data)

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run
cd src
python main.py
```

Or double-click `Hermes.bat`.

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `HERMES_HOME` | Hermes config directory | `~/.hermes` |
| `HERMES_BIN` | Path to hermes executable | Auto-detect from PATH |
| `HERMES_AGENT_ROOT` | Hermes agent package root | Auto-detect |
| `LEARNING_DESK_DB` | LearningDesk database path | `%LOCALAPPDATA%\LearningDesk\learning_desk.db` |

Set these in `Hermes.bat` / `run.bat` or as system environment variables.

### AI Summary & Advice

AI features (周期总结, 学习建议) require a `settings.json` with API credentials.
If LearningDesk is installed, settings are auto-detected from `%LOCALAPPDATA%\LearningDesk\settings.json`.

Otherwise, create `data/settings.json` in the project directory:
```json
{
  "api_base_url": "https://your-api-endpoint/v1",
  "api_key": "your-api-key",
  "model": "your-model-name"
}
```

## Project Structure

```
hermes-pet/
├── src/
│   ├── main.py            # App entry, dark palette, signal wiring
│   ├── pet_window.py      # Floating orb (draggable, context menu)
│   ├── chat_window.py     # AI chat UI (image paste, drag-drop)
│   ├── api_client.py      # Hermes CLI subprocess bridge
│   ├── learning_panel.py  # Learning panel (5 tabs, PyQt5)
│   ├── config.py          # Window sizes, paths
│   ├── config_store.py    # Settings loader
│   ├── db.py              # SQLite database (from LearningDesk)
│   ├── summaries.py       # AI summary generators
│   ├── llm_client.py      # OpenAI-compatible HTTP client
│   └── vision_analyzer.py # Image base64 encoder
├── assets/icons/          # (reserved)
├── Hermes.bat             # Quick launcher
├── run.bat                # Launcher with status output
├── install.bat            # Dependency installer
├── build.bat              # PyInstaller packaging
├── hermespet.spec         # PyInstaller spec
├── requirements.txt
└── README.md
```

## Build

```bash
pip install pyinstaller
pyinstaller --clean hermespet.spec
```

Output: `dist/HermesPet.exe`

## License

MIT
