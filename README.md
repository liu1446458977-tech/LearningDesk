# Hermes Pet — 超级悬浮学习助手

桌面悬浮 AI 助手 + 学习计划管理一体化工具。基于 PyQt5，暗色主题。

## 功能总览

### 悬浮球（Pet Orb）

- 右下角常驻，带呼吸光晕动画
- 左键拖拽移动，短按打开 AI 聊天
- 右键菜单：打开聊天 / 学习面板 / 退出
- 收到消息时闪绿色，思考中变黄色

### AI 聊天（Chat Window）

- 通过 Hermes CLI 交互，支持连续对话记忆（自动 resume session）
- Ctrl+V 粘贴图片，拖拽图片到窗口
- 错误消息红色高亮显示
- ANSI 转义码自动清除，输出干净

### 学习面板（Learning Panel）

5 个标签页，直接读取 LearningDesk 数据库：

| 标签页   | 功能                                                         |
| -------- | ------------------------------------------------------------ |
| 今日计划 | 日期选择（昨天/今天/明天）+ 任务增删改查 + 勾选完成（带删除线） |
| 睡前记录 | 按日期载入/保存每日学习心得                                  |
| 周期总结 | AI 生成本周 / 半月 / 本月学习总结，支持缓存读取              |
| 学习建议 | 基于近 7 天数据，AI 生成个性化学习建议                       |
| 历史回顾 | 左侧日期列表 + 右侧任务/记录详情，只读浏览                   |

### API 兼容性

- 自动识别 Anthropic 格式（`/v1/messages`）和 OpenAI 格式（`/v1/chat/completions`）
- 模型名大小写自动适配（400 时自动转小写重试）
- 通过 `settings.json` 配置 API 端点

### 其他

- 全局暗色主题，字体统一 +2px
- 所有文本区域自动换行，无水平滚动条
- LearningDesk 数据库完全兼容，历史数据不丢失
- `sync_learning_record.py` — 学习记录同步脚本
- PyInstaller 打包支持

## 安装

```bash
# 安装依赖
pip install -r requirements.txt

# 运行
cd src
python main.py
```

或双击 `Hermes.bat`。

## 环境变量

| 变量                | 说明                    | 默认值                                         |
| ------------------- | ----------------------- | ---------------------------------------------- |
| `HERMES_HOME`       | Hermes 配置目录         | `~/.hermes`                                    |
| `HERMES_BIN`        | hermes 可执行文件路径   | 自动检测 PATH                                  |
| `HERMES_AGENT_ROOT` | hermes agent 包路径     | 自动检测                                       |
| `LEARNING_DESK_DB`  | LearningDesk 数据库路径 | `%LOCALAPPDATA%\LearningDesk\learning_desk.db` |

在 `Hermes.bat` / `run.bat` 或系统环境变量中设置。

## AI 功能配置

周期总结和学习建议需要 API 配置。如果已安装 LearningDesk，自动从 `%LOCALAPPDATA%\LearningDesk\settings.json` 读取。

手动创建 `data/settings.json`：

```json
{
  "api_base_url": "https://your-api-endpoint",
  "api_key": "your-api-key",
  "model": "your-model-name"
}
```

支持 OpenAI 兼容端点和 Anthropic 兼容端点（URL 含 `anthropic` 自动切换格式）。

## 项目结构

```
hermes-pet/
├── src/
│   ├── main.py             # 入口，暗色调色板，信号接线
│   ├── pet_window.py       # 悬浮球（可拖拽，右键菜单）
│   ├── chat_window.py      # AI 聊天界面（图片粘贴/拖拽）
│   ├── api_client.py       # Hermes CLI 桥接（会话记忆）
│   ├── hermes_chat.py      # Hermes 包装脚本（修复 prompt_toolkit）
│   ├── learning_panel.py   # 学习面板（5 标签页）
│   ├── config.py           # 窗口尺寸、路径配置
│   ├── config_store.py     # settings.json 加载器
│   ├── db.py               # SQLite 数据库层
│   ├── summaries.py        # AI 总结生成器
│   ├── llm_client.py       # HTTP 客户端（OpenAI + Anthropic）
│   └── vision_analyzer.py  # 图片 base64 编码
├── sync_learning_record.py # 学习记录同步
├── assets/icons/           # 图标（预留）
├── Hermes.bat              # 快速启动
├── run.bat                 # 带状态输出的启动器
├── install.bat             # 依赖安装
├── build.bat               # PyInstaller 打包
├── hermespet.spec          # PyInstaller 配置
├── requirements.txt
└── README.md
```

## 打包

```bash
pip install pyinstaller
pyinstaller --clean hermespet.spec
```

输出：`dist/HermesPet.exe`

## License

MIT
