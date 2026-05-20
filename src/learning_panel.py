"""Learning Panel — PyQt5 port of LearningDesk, integrated into hermes-pet."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLineEdit, QPushButton, QLabel, QScrollArea, QFrame, QCheckBox,
    QTextEdit, QDateEdit, QApplication, QInputDialog, QAbstractScrollArea,
)
from PyQt5.QtCore import Qt, pyqtSignal, QDate, QThread
from PyQt5.QtGui import QFont

import config
from db import Database, TaskRow
from llm_client import LLMError, build_suggestion_prompt, chat_completion
from summaries import (
    build_ai_week_summary, build_ai_half_month_summary,
    build_ai_month_summary, build_week_summary,
)
from config_store import load_settings

# ── Colors (match chat_window.py dark theme) ──────────────────────────

DARK_BG = "#1a1d24"
DARK_SURFACE = "#22262e"
DARK_BORDER = "#2e3340"
ACCENT = "#648cff"
ACCENT_DIM = "#3a4a7a"
TEXT_PRIMARY = "#e0e0e0"
TEXT_SECONDARY = "#8890a0"
INPUT_BG = "#2a2e38"
GREEN = "#4caf50"
RED = "#ff5555"

SCROLLBAR_STYLE = """
QScrollBar:vertical { background: #1e2128; width: 6px; margin: 0; border-radius: 3px; }
QScrollBar::handle:vertical { background: #3a3f4d; min-height: 30px; border-radius: 3px; }
QScrollBar::handle:vertical:hover { background: #3a4a7a; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
"""

TAB_STYLE = """
QTabWidget::pane { border: 1px solid #2e3340; background: #1a1d24; border-radius: 8px; }
QTabBar::tab { background: #22262e; color: #8890a0; padding: 8px 16px;
    border: 1px solid #2e3340; border-bottom: none;
    border-top-left-radius: 6px; border-top-right-radius: 6px; }
QTabBar::tab:selected { background: #1a1d24; color: #648cff; border-bottom: 2px solid #648cff; }
"""


# ── AI Worker Thread ───────────────────────────────────────────────────

class AIWorkerThread(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            result = self._fn()
            self.finished.emit(result)
        except LLMError as e:
            self.error.emit(str(e))
        except Exception as e:
            self.error.emit(f"Unexpected error: {e}")


# ── Helper: styled button ─────────────────────────────────────────────

def _btn(text, accent=False):
    btn = QPushButton(text)
    bg = ACCENT if accent else INPUT_BG
    hover = "#7a9eff" if accent else "#363b48"
    btn.setCursor(Qt.PointingHandCursor)
    btn.setStyleSheet(
        f"QPushButton {{ background: {bg}; color: white; border: 1px solid {DARK_BORDER};"
        f"border-radius: 6px; padding: 6px 14px; font-size: 14px; }}"
        f"QPushButton:hover {{ background: {hover}; }}"
    )
    return btn


def _label(text, color=TEXT_PRIMARY, size=14, bold=False):
    lbl = QLabel(text)
    weight = "600" if bold else "400"
    lbl.setStyleSheet(f"color: {color}; font-size: {size}px; font-weight: {weight}; background: transparent;")
    return lbl


def _text_edit(placeholder=""):
    te = QTextEdit()
    te.setPlaceholderText(placeholder)
    te.setLineWrapMode(QTextEdit.WidgetWidth)
    te.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    te.setSizeAdjustPolicy(QAbstractScrollArea.AdjustIgnored)
    te.setStyleSheet(f"background:{INPUT_BG}; color:{TEXT_PRIMARY}; border:1px solid {DARK_BORDER}; border-radius:8px; padding:8px; font-size:14px;")
    return te


# ── Learning Panel ─────────────────────────────────────────────────────

class LearningPanel(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pet_window = None
        self.db = Database(Path(config.LEARNING_DESK_DB))
        self._selected_task_id = None
        self._last_summary_kind = None
        self._last_period_key = None
        self._worker = None
        self._init_ui()

    def set_pet_window(self, pw):
        self.pet_window = pw

    # ── UI ─────────────────────────────────────────────────────────────

    def _init_ui(self):
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(config.LEARNING_PANEL_WIDTH, config.LEARNING_PANEL_HEIGHT)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        container = QFrame()
        container.setStyleSheet(f"""
            QFrame {{ background: {DARK_BG}; border: 1px solid {DARK_BORDER}; border-radius: 16px; }}
        """)
        cl = QVBoxLayout(container)
        cl.setContentsMargins(16, 12, 16, 14)
        cl.setSpacing(0)

        # title bar
        tb = QHBoxLayout()
        tb.setContentsMargins(0, 0, 0, 8)
        tb.addWidget(_label("学习面板", ACCENT, 13, True))
        tb.addStretch()
        close = _btn("✕")
        close.setFixedSize(26, 26)
        close.setStyleSheet(f"QPushButton {{ background:transparent; border:none; color:{TEXT_SECONDARY}; font-size:15px; }}"
                            f"QPushButton:hover {{ color:{RED}; }}")
        close.clicked.connect(self.hide)
        tb.addWidget(close)
        cl.addLayout(tb)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:{DARK_BORDER};")
        cl.addWidget(sep)
        cl.addSpacing(8)

        # tabs
        tabs = QTabWidget()
        tabs.setStyleSheet(TAB_STYLE)
        tabs.addTab(self._build_plan_tab(), "今日计划")
        tabs.addTab(self._build_note_tab(), "睡前记录")
        tabs.addTab(self._build_summary_tab(), "周期总结")
        tabs.addTab(self._build_advice_tab(), "学习建议")
        tabs.addTab(self._build_history_tab(), "历史回顾")
        cl.addWidget(tabs)

        outer.addWidget(container)

    # ── Tab 1: Plan ────────────────────────────────────────────────────

    def _build_plan_tab(self):
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        v = QVBoxLayout(page)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)

        # date row
        dr = QHBoxLayout()
        self.plan_date = QDateEdit()
        self.plan_date.setCalendarPopup(True)
        self.plan_date.setDisplayFormat("yyyy-MM-dd")
        self.plan_date.setDate(QDate.currentDate())
        self.plan_date.setStyleSheet(f"background:{INPUT_BG}; color:{TEXT_PRIMARY}; border:1px solid {DARK_BORDER}; border-radius:6px; padding:4px 8px;")
        self.plan_date.dateChanged.connect(self._refresh_plan)
        dr.addWidget(self.plan_date)
        for txt, delta in [("昨天", -1), ("今天", 0), ("明天", 1)]:
            b = _btn(txt)
            b.setFixedWidth(60)
            b.clicked.connect(lambda _, d=delta: self.plan_date.setDate(
                QDate.currentDate().addDays(d) if d else QDate.currentDate()))
            dr.addWidget(b)
        dr.addStretch()
        v.addLayout(dr)

        # task input row
        ir = QHBoxLayout()
        self.task_entry = QLineEdit()
        self.task_entry.setPlaceholderText("输入任务...")
        self.task_entry.setStyleSheet(f"background:{INPUT_BG}; color:{TEXT_PRIMARY}; border:1px solid {DARK_BORDER}; border-radius:6px; padding:6px 10px;")
        self.task_entry.returnPressed.connect(self._add_task)
        ir.addWidget(self.task_entry)
        add_b = _btn("添加", True)
        add_b.setFixedWidth(70)
        add_b.clicked.connect(self._add_task)
        ir.addWidget(add_b)
        v.addLayout(ir)

        # scrollable task list
        self.task_scroll = QScrollArea()
        self.task_scroll.setWidgetResizable(True)
        self.task_scroll.setFrameShape(QFrame.NoFrame)
        self.task_scroll.setStyleSheet("background:transparent; border:none;")
        self.task_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.task_scroll.verticalScrollBar().setStyleSheet(SCROLLBAR_STYLE)
        self.task_list_widget = QWidget()
        self.task_list_widget.setStyleSheet("background:transparent;")
        self.task_list_layout = QVBoxLayout(self.task_list_widget)
        self.task_list_layout.setAlignment(Qt.AlignTop)
        self.task_list_layout.setSpacing(4)
        self.task_scroll.setWidget(self.task_list_widget)
        v.addWidget(self.task_scroll)

        # bottom buttons
        br = QHBoxLayout()
        edit_b = _btn("编辑标题")
        edit_b.clicked.connect(self._edit_task)
        br.addWidget(edit_b)
        del_b = _btn("删除")
        del_b.setStyleSheet(del_b.styleSheet().replace(ACCENT, RED).replace("#7a9eff", "#ff7777"))
        del_b.clicked.connect(self._delete_task)
        br.addWidget(del_b)
        br.addStretch()
        v.addLayout(br)

        self._refresh_plan()
        return page

    def _current_date(self) -> str:
        return self.plan_date.date().toPyDate().isoformat()

    def _refresh_plan(self):
        # clear
        while self.task_list_layout.count():
            w = self.task_list_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        self._selected_task_id = None

        tasks = self.db.list_tasks(self._current_date())
        for t in tasks:
            row = QFrame()
            row.setStyleSheet(f"QFrame {{ background:{DARK_SURFACE}; border:1px solid {DARK_BORDER}; border-radius:6px; }}")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(6, 4, 6, 4)
            rl.setSpacing(6)

            sel = _btn("选")
            sel.setFixedSize(44, 30)
            sel.clicked.connect(lambda _, tid=t.id: self._select_task(tid))
            rl.addWidget(sel)

            cb = QCheckBox()
            cb.setChecked(t.done)
            cb.setStyleSheet(f"background:transparent;")
            rl.addWidget(cb)

            title_lbl = QLabel(t.title)
            title_lbl.setWordWrap(True)
            title_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            strike = "text-decoration: line-through;" if t.done else ""
            title_lbl.setStyleSheet(f"color:{TEXT_PRIMARY}; background:transparent; font-size:14px; {strike}")
            rl.addWidget(title_lbl, 1)

            def _on_toggle(state, tid=t.id, lbl=title_lbl):
                self.db.set_task_done(tid, state == Qt.Checked)
                s = "text-decoration: line-through;" if state == Qt.Checked else ""
                lbl.setStyleSheet(f"color:{TEXT_PRIMARY}; background:transparent; font-size:14px; {s}")
            cb.stateChanged.connect(_on_toggle)

            self.task_list_layout.addWidget(row)

    def _select_task(self, tid):
        self._selected_task_id = tid

    def _add_task(self):
        text = self.task_entry.text().strip()
        if not text:
            return
        self.db.add_task(self._current_date(), text)
        self.task_entry.clear()
        self._refresh_plan()

    def _edit_task(self):
        if not self._selected_task_id:
            return
        tasks = self.db.list_tasks(self._current_date())
        current = next((t for t in tasks if t.id == self._selected_task_id), None)
        if not current:
            return
        text, ok = QInputDialog.getText(self, "编辑任务", "任务标题：", QLineEdit.Normal, current.title)
        if ok and text.strip():
            self.db.update_task_title(self._selected_task_id, text.strip())
            self._refresh_plan()

    def _delete_task(self):
        if not self._selected_task_id:
            return
        self.db.delete_task(self._selected_task_id)
        self._selected_task_id = None
        self._refresh_plan()

    # ── Tab 2: Notes ──────────────────────────────────────────────────

    def _build_note_tab(self):
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        v = QVBoxLayout(page)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)

        dr = QHBoxLayout()
        self.note_date = QDateEdit()
        self.note_date.setCalendarPopup(True)
        self.note_date.setDisplayFormat("yyyy-MM-dd")
        self.note_date.setDate(QDate.currentDate())
        self.note_date.setStyleSheet(f"background:{INPUT_BG}; color:{TEXT_PRIMARY}; border:1px solid {DARK_BORDER}; border-radius:6px; padding:4px 8px;")
        dr.addWidget(self.note_date)
        load_b = _btn("载入")
        load_b.setFixedWidth(70)
        load_b.clicked.connect(self._load_note)
        dr.addWidget(load_b)
        dr.addStretch()
        v.addLayout(dr)

        self.note_text = _text_edit("写下今天的学习心得...")
        v.addWidget(self.note_text)

        save_b = _btn("保存今日学习记录", True)
        save_b.clicked.connect(self._save_note)
        v.addWidget(save_b)

        self.note_status = _label("", GREEN, 11)
        v.addWidget(self.note_status)

        self._load_note()
        return page

    def _note_date_str(self) -> str:
        return self.note_date.date().toPyDate().isoformat()

    def _load_note(self):
        content = self.db.get_note(self._note_date_str())
        self.note_text.setPlainText(content)
        self.note_status.setText("")

    def _save_note(self):
        self.db.upsert_note(self._note_date_str(), self.note_text.toPlainText())
        self.note_status.setText("✓ 已保存")

    # ── Tab 3: Summary ────────────────────────────────────────────────

    def _build_summary_tab(self):
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        v = QVBoxLayout(page)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)

        br = QHBoxLayout()
        for label, kind in [("本周总结", "week"), ("半月总结", "half_month"), ("本月总结", "month")]:
            b = _btn(label, True)
            b.clicked.connect(lambda _, k=kind: self._gen_summary(k))
            br.addWidget(b)
        v.addLayout(br)

        self.summary_status = _label("", TEXT_SECONDARY, 11)
        v.addWidget(self.summary_status)

        self.summary_text = _text_edit()
        self.summary_text.setReadOnly(True)
        v.addWidget(self.summary_text)

        cache_b = _btn("读取上次生成的总结")
        cache_b.clicked.connect(self._load_cached_summary)
        v.addWidget(cache_b)

        return page

    def _gen_summary(self, kind):
        settings = load_settings()
        base = settings.get("api_base_url", "")
        key = settings.get("api_key", "")
        model = settings.get("model", "")
        if not base:
            self.summary_status.setText("请先配置 API（编辑 settings.json）")
            return
        if self._worker and self._worker.isRunning():
            return

        self.summary_status.setText("请求中...")
        self.summary_text.clear()

        fn_map = {
            "week": lambda: build_ai_week_summary(self.db, base, key, model),
            "half_month": lambda: build_ai_half_month_summary(self.db, base, key, model),
            "month": lambda: build_ai_month_summary(self.db, base, key, model),
        }
        fn = fn_map[kind]

        def run():
            pk, text = fn()
            self._last_summary_kind = kind
            self._last_period_key = pk
            self.db.save_summary_cache(kind, pk, text)
            return text

        self._worker = AIWorkerThread(run, self)
        self._worker.finished.connect(self._on_summary_result)
        self._worker.error.connect(self._on_summary_error)
        self._worker.start()

    def _on_summary_result(self, text):
        self.summary_status.setText("✓ 完成")
        self.summary_text.setPlainText(text)

    def _on_summary_error(self, err):
        self.summary_status.setText(f"错误: {err[:100]}")

    def _load_cached_summary(self):
        if not self._last_summary_kind or not self._last_period_key:
            self.summary_status.setText("暂无缓存，请先生成一次")
            return
        body = self.db.get_cached_summary(self._last_summary_kind, self._last_period_key)
        if body:
            self.summary_text.setPlainText(body)
            self.summary_status.setText("已加载缓存")
        else:
            self.summary_status.setText("未找到缓存")

    # ── Tab 4: Advice ─────────────────────────────────────────────────

    def _build_advice_tab(self):
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        v = QVBoxLayout(page)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)

        v.addWidget(_label("基于近 7 天的学习数据，AI 为你生成个性化学习建议。", TEXT_SECONDARY, 11))

        self.advice_status = _label("", TEXT_SECONDARY, 11)
        v.addWidget(self.advice_status)

        gen_b = _btn("生成学习建议", True)
        gen_b.clicked.connect(self._gen_advice)
        v.addWidget(gen_b)

        self.advice_text = _text_edit()
        self.advice_text.setReadOnly(True)
        v.addWidget(self.advice_text)

        return page

    def _gen_advice(self):
        settings = load_settings()
        base = settings.get("api_base_url", "")
        key = settings.get("api_key", "")
        model = settings.get("model", "")
        if not base:
            self.advice_status.setText("请先配置 API（编辑 settings.json）")
            return
        if self._worker and self._worker.isRunning():
            return

        self.advice_status.setText("请求中...")
        self.advice_text.clear()

        def run():
            _, weekly_text = build_week_summary(self.db)
            today = date.today()
            parts = []
            for d in range(7):
                day = today - timedelta(days=6 - d)
                tasks = self.db.list_tasks(day.isoformat())
                note = self.db.get_note(day.isoformat())
                lines = [f"【{day.isoformat()}】"]
                for t in tasks:
                    mark = "✓" if t.done else "○"
                    lines.append(f"  {mark} {t.title}")
                if note.strip():
                    lines.append(f"  记录：{note.strip()}")
                parts.append("\n".join(lines))
            recent = "\n".join(parts)
            messages = build_suggestion_prompt(weekly_text, recent)
            return chat_completion(base, key, model, messages)

        self._worker = AIWorkerThread(run, self)
        self._worker.finished.connect(self._on_advice_result)
        self._worker.error.connect(self._on_advice_error)
        self._worker.start()

    def _on_advice_result(self, text):
        self.advice_status.setText("✓ 完成")
        self.advice_text.setPlainText(text)

    def _on_advice_error(self, err):
        self.advice_status.setText(f"错误: {err[:100]}")

    # ── Tab 5: History ────────────────────────────────────────────────

    def _build_history_tab(self):
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        v = QVBoxLayout(page)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)

        # top bar
        top = QHBoxLayout()
        self.history_count = _label("", TEXT_SECONDARY, 11)
        top.addWidget(self.history_count)
        top.addStretch()
        refresh_b = _btn("刷新列表")
        refresh_b.clicked.connect(self._refresh_history)
        top.addWidget(refresh_b)
        v.addLayout(top)

        # split: left date list, right detail
        split = QHBoxLayout()
        split.setSpacing(8)

        # left: date list
        left_scroll = QScrollArea()
        left_scroll.setFixedWidth(140)
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_scroll.setStyleSheet("background:transparent; border:none;")
        left_scroll.verticalScrollBar().setStyleSheet(SCROLLBAR_STYLE)
        self.history_list_widget = QWidget()
        self.history_list_widget.setStyleSheet("background:transparent;")
        self.history_list_layout = QVBoxLayout(self.history_list_widget)
        self.history_list_layout.setAlignment(Qt.AlignTop)
        self.history_list_layout.setSpacing(2)
        left_scroll.setWidget(self.history_list_widget)
        split.addWidget(left_scroll)

        # right: detail area
        right = QVBoxLayout()
        right.setSpacing(6)

        self.history_date_label = _label("选择左侧日期查看", TEXT_SECONDARY, 12, True)
        right.addWidget(self.history_date_label)

        self.history_tasks_label = _label("", TEXT_PRIMARY, 11)
        self.history_tasks_label.setWordWrap(True)
        right.addWidget(self.history_tasks_label)

        self.history_note_text = _text_edit()
        self.history_note_text.setReadOnly(True)
        right.addWidget(self.history_note_text)

        split.addLayout(right, 1)
        v.addLayout(split)

        self._refresh_history()
        return page

    def _refresh_history(self):
        # clear date list
        while self.history_list_layout.count():
            w = self.history_list_layout.takeAt(0).widget()
            if w:
                w.deleteLater()

        dates = self.db.list_dates_with_activity()
        self.history_count.setText(f"共 {len(dates)} 条记录")

        for d in dates:
            btn = _btn(d)
            btn.setFixedWidth(130)
            btn.setStyleSheet(
                f"QPushButton {{ background:{INPUT_BG}; color:{TEXT_PRIMARY}; border:1px solid {DARK_BORDER};"
                f"border-radius:4px; padding:4px 6px; font-size:13px; text-align:left; }}"
                f"QPushButton:hover {{ background:{ACCENT_DIM}; }}"
            )
            btn.clicked.connect(lambda _, iso=d: self._show_history_day(iso))
            self.history_list_layout.addWidget(btn)

        # clear detail
        self.history_date_label.setText("选择左侧日期查看")
        self.history_tasks_label.setText("")
        self.history_note_text.clear()

    def _show_history_day(self, iso: str):
        self.history_date_label.setText(iso)
        tasks = self.db.list_tasks(iso)
        if tasks:
            lines = []
            for t in tasks:
                mark = "✓" if t.done else "○"
                lines.append(f"{mark} {t.title}")
            self.history_tasks_label.setText("\n".join(lines))
        else:
            self.history_tasks_label.setText("（无任务）")

        note = self.db.get_note(iso)
        self.history_note_text.setPlainText(note if note.strip() else "（无学习记录）")

    # ── Positioning ───────────────────────────────────────────────────

    def show_and_position(self):
        if self.pet_window:
            pet_pos = self.pet_window.pos()
            x = pet_pos.x() - config.LEARNING_PANEL_WIDTH - 10
            y = pet_pos.y() - config.LEARNING_PANEL_HEIGHT + config.PET_SIZE
            self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
