"""Learning Panel — PyQt5 port of LearningDesk, integrated into hermes-pet."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLineEdit, QPushButton, QLabel, QScrollArea, QFrame, QCheckBox,
    QTextEdit, QDateEdit, QApplication, QInputDialog, QAbstractScrollArea,
)
from PyQt5.QtCore import Qt, pyqtSignal, QDate, QThread, QPoint
from PyQt5.QtGui import QFont, QCursor

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
QTabBar { background: transparent; }
QTabBar::tab { background: #22262e; color: #8890a0; padding: 10px 8px;
    border: 1px solid #2e3340; border-bottom: none;
    border-top-left-radius: 6px; border-top-right-radius: 6px;
    margin-right: 2px; font-size: 13px; }
QTabBar::tab:selected { background: #1a1d24; color: #648cff; border-bottom: 2px solid #648cff; }
QTabBar::tab:hover { background: #2a2e38; color: #c0c8e0; }
"""


# ── Scrollable tab widget ────────────────────────────────────────────

class _ScrollTabWidget(QTabWidget):
    """QTabWidget that scrolls tabs with mouse wheel."""

    def wheelEvent(self, event):
        bar = self.tabBar()
        if bar.count() == 0:
            return
        delta = event.angleDelta().y()
        if delta > 0:
            bar.setCurrentIndex(max(0, bar.currentIndex() - 1))
        elif delta < 0:
            bar.setCurrentIndex(min(bar.count() - 1, bar.currentIndex() + 1))
        event.accept()


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


# ── Resize constants ────────────────────────────────────────────────
_RESIZE_MARGIN = 8
_MIN_W = 380
_MIN_H = 320

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
        self._resize_edge = None
        self._resize_start_pos = None
        self._resize_start_geo = None
        self._init_ui()

    def set_pet_window(self, pw):
        self.pet_window = pw

    # ── Resize (edge drag) ──────────────────────────────────────────

    def _edge_at(self, pos):
        """Return set of edges the cursor is near: 'right', 'bottom', 'left', 'top'."""
        r = self.rect()
        edges = set()
        if pos.x() >= r.width() - _RESIZE_MARGIN:
            edges.add("right")
        elif pos.x() <= _RESIZE_MARGIN:
            edges.add("left")
        if pos.y() >= r.height() - _RESIZE_MARGIN:
            edges.add("bottom")
        elif pos.y() <= _RESIZE_MARGIN:
            edges.add("top")
        return edges

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            edges = self._edge_at(event.pos())
            if edges:
                self._resize_edge = edges
                self._resize_start_pos = event.globalPos()
                self._resize_start_geo = self.geometry()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resize_edge and event.buttons() & Qt.LeftButton:
            delta = event.globalPos() - self._resize_start_pos
            geo = self._resize_start_geo
            x, y, w, h = geo.x(), geo.y(), geo.width(), geo.height()
            if "right" in self._resize_edge:
                w = max(_MIN_W, geo.width() + delta.x())
            if "bottom" in self._resize_edge:
                h = max(_MIN_H, geo.height() + delta.y())
            if "left" in self._resize_edge:
                new_w = max(_MIN_W, geo.width() - delta.x())
                x = x + (geo.width() - new_w)
                w = new_w
            if "top" in self._resize_edge:
                new_h = max(_MIN_H, geo.height() - delta.y())
                y = y + (geo.height() - new_h)
                h = new_h
            self.setGeometry(x, y, w, h)
            event.accept()
            return
        # Update cursor when hovering near edges
        edges = self._edge_at(event.pos())
        if "right" in edges and "bottom" in edges:
            self.setCursor(Qt.SizeFDiagCursor)
        elif "left" in edges and "top" in edges:
            self.setCursor(Qt.SizeFDiagCursor)
        elif "right" in edges and "top" in edges:
            self.setCursor(Qt.SizeBDiagCursor)
        elif "left" in edges and "bottom" in edges:
            self.setCursor(Qt.SizeBDiagCursor)
        elif "right" in edges or "left" in edges:
            self.setCursor(Qt.SizeHorCursor)
        elif "bottom" in edges or "top" in edges:
            self.setCursor(Qt.SizeVerCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._resize_edge = None
        super().mouseReleaseEvent(event)

    # ── UI ─────────────────────────────────────────────────────────────

    def _init_ui(self):
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(_MIN_W, _MIN_H)
        self.resize(config.LEARNING_PANEL_WIDTH, config.LEARNING_PANEL_HEIGHT)

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
        tabs = _ScrollTabWidget()
        tabs.setStyleSheet(TAB_STYLE)
        tabs.tabBar().setExpanding(True)
        tabs.tabBar().setUsesScrollButtons(False)
        tabs.addTab(self._build_plan_tab(), "今日计划")
        tabs.addTab(self._build_period_tab(), "周期计划")
        tabs.addTab(self._build_note_tab(), "睡前记录")
        tabs.addTab(self._build_summary_tab(), "周期总结")
        tabs.addTab(self._build_advice_tab(), "学习建议")
        tabs.addTab(self._build_history_tab(), "历史回顾")
        cl.addWidget(tabs, 1)

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

    # ── Tab: Period Plan (left-right layout) ────────────────────────────

    def _build_period_tab(self):
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        v = QVBoxLayout(page)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)

        # top action row
        top = QHBoxLayout()
        new_b = _btn("新建计划", True)
        new_b.clicked.connect(self._new_plan)
        top.addWidget(new_b)
        del_plan_b = _btn("删除计划")
        del_plan_b.setStyleSheet(del_plan_b.styleSheet().replace(ACCENT, RED).replace("#7a9eff", "#ff7777"))
        del_plan_b.clicked.connect(self._delete_plan)
        top.addWidget(del_plan_b)
        top.addStretch()
        self.plan_info = _label("", TEXT_SECONDARY, 11)
        top.addWidget(self.plan_info)
        v.addLayout(top)

        # main split: left plan list, right detail
        split = QHBoxLayout()
        split.setSpacing(8)

        # ── left: plan list ──
        left = QVBoxLayout()
        left.addWidget(_label("计划列表", ACCENT, 12, True))
        left_scroll = QScrollArea()
        left_scroll.setMinimumWidth(120)
        left_scroll.setMaximumWidth(240)
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setStyleSheet("background:transparent; border:none;")
        left_scroll.verticalScrollBar().setStyleSheet(SCROLLBAR_STYLE)
        self.period_plan_list_widget = QWidget()
        self.period_plan_list_widget.setStyleSheet("background:transparent;")
        self.period_plan_list_layout = QVBoxLayout(self.period_plan_list_widget)
        self.period_plan_list_layout.setAlignment(Qt.AlignTop)
        self.period_plan_list_layout.setSpacing(3)
        left_scroll.setWidget(self.period_plan_list_widget)
        left.addWidget(left_scroll, 1)
        split.addLayout(left)

        # ── right: detail (add form + items) ──
        right = QVBoxLayout()
        right.setSpacing(6)

        # add item row
        add_row = QHBoxLayout()
        self.item_date = QDateEdit()
        self.item_date.setCalendarPopup(True)
        self.item_date.setDisplayFormat("yyyy-MM-dd")
        self.item_date.setDate(QDate.currentDate())
        self.item_date.setStyleSheet(f"background:{INPUT_BG}; color:{TEXT_PRIMARY}; border:1px solid {DARK_BORDER}; border-radius:6px; padding:4px 6px; font-size:12px;")
        add_row.addWidget(self.item_date)

        self.item_subject = QLineEdit()
        self.item_subject.setPlaceholderText("科目")
        self.item_subject.setMaximumWidth(90)
        self.item_subject.setStyleSheet(f"background:{INPUT_BG}; color:{TEXT_PRIMARY}; border:1px solid {DARK_BORDER}; border-radius:6px; padding:5px 8px; font-size:12px;")
        add_row.addWidget(self.item_subject)

        self.item_time = QLineEdit()
        self.item_time.setPlaceholderText("时段")
        self.item_time.setMaximumWidth(110)
        self.item_time.setStyleSheet(f"background:{INPUT_BG}; color:{TEXT_PRIMARY}; border:1px solid {DARK_BORDER}; border-radius:6px; padding:5px 8px; font-size:12px;")
        add_row.addWidget(self.item_time)

        self.item_content = QLineEdit()
        self.item_content.setPlaceholderText("具体内容...")
        self.item_content.setStyleSheet(f"background:{INPUT_BG}; color:{TEXT_PRIMARY}; border:1px solid {DARK_BORDER}; border-radius:6px; padding:5px 8px; font-size:12px;")
        self.item_content.returnPressed.connect(self._add_plan_item)
        add_row.addWidget(self.item_content, 1)

        add_item_b = _btn("添加", True)
        add_item_b.setFixedWidth(60)
        add_item_b.clicked.connect(self._add_plan_item)
        add_row.addWidget(add_item_b)
        right.addLayout(add_row)

        # scrollable item list
        self.period_scroll = QScrollArea()
        self.period_scroll.setWidgetResizable(True)
        self.period_scroll.setFrameShape(QFrame.NoFrame)
        self.period_scroll.setStyleSheet("background:transparent; border:none;")
        self.period_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.period_scroll.verticalScrollBar().setStyleSheet(SCROLLBAR_STYLE)
        self.period_list_widget = QWidget()
        self.period_list_widget.setStyleSheet("background:transparent;")
        self.period_list_layout = QVBoxLayout(self.period_list_widget)
        self.period_list_layout.setAlignment(Qt.AlignTop)
        self.period_list_layout.setSpacing(2)
        self.period_scroll.setWidget(self.period_list_widget)
        right.addWidget(self.period_scroll, 1)

        # delete item button
        bot = QHBoxLayout()
        del_item_b = _btn("删除选中条目")
        del_item_b.setStyleSheet(del_item_b.styleSheet().replace(ACCENT, RED).replace("#7a9eff", "#ff7777"))
        del_item_b.clicked.connect(self._delete_plan_item)
        bot.addWidget(del_item_b)
        bot.addStretch()
        right.addLayout(bot)

        split.addLayout(right, 1)
        v.addLayout(split, 1)

        self._active_plan_id = None
        self._selected_plan_item_id = None
        self._refresh_plan_list()
        return page

    # ── Period plan helpers ──────────────────────────────────────────

    def _refresh_plan_list(self):
        while self.period_plan_list_layout.count():
            w = self.period_plan_list_layout.takeAt(0)
            if w.widget():
                w.widget().deleteLater()

        plans = self.db.list_plans()
        if not plans:
            self._active_plan_id = None
            self.plan_info.setText("暂无计划，点击「新建计划」创建")
            self._refresh_plan_items()
            return

        for p in plans:
            btn = QPushButton(f"{p.name}\n{p.start_date} ~ {p.end_date}")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                f"QPushButton {{ background:{DARK_SURFACE}; color:{TEXT_PRIMARY}; border:1px solid {DARK_BORDER};"
                f"border-radius:6px; padding:8px 10px; font-size:12px; text-align:left; }}"
                f"QPushButton:hover {{ background:{ACCENT_DIM}; }}"
                f"QPushButton:checked {{ background:{ACCENT_DIM}; border-color:{ACCENT}; color:white; }}"
            )
            btn.setCheckable(True)
            btn.clicked.connect(lambda _, pid=p.id: self._select_plan(pid))
            self.period_plan_list_layout.addWidget(btn)

        # auto-select first plan
        if not self._active_plan_id or self._active_plan_id not in [p.id for p in plans]:
            self._active_plan_id = plans[0].id
        self._highlight_active_plan()
        self._refresh_plan_items()

    def _select_plan(self, plan_id):
        self._active_plan_id = plan_id
        self._highlight_active_plan()
        self._refresh_plan_items()

    def _highlight_active_plan(self):
        for i in range(self.period_plan_list_layout.count()):
            w = self.period_plan_list_layout.itemAt(i).widget()
            if isinstance(w, QPushButton):
                w.setChecked(False)
        # find and check the active one
        plans = self.db.list_plans()
        active_idx = next((i for i, p in enumerate(plans) if p.id == self._active_plan_id), -1)
        if 0 <= active_idx < self.period_plan_list_layout.count():
            btn = self.period_plan_list_layout.itemAt(active_idx).widget()
            if isinstance(btn, QPushButton):
                btn.setChecked(True)

    def _refresh_plan_items(self):
        while self.period_list_layout.count():
            w = self.period_list_layout.takeAt(0)
            if w.widget():
                w.widget().deleteLater()
        self._selected_plan_item_id = None

        if not self._active_plan_id:
            self.plan_info.setText("")
            return

        plan = next((p for p in self.db.list_plans() if p.id == self._active_plan_id), None)
        if plan:
            self.plan_info.setText(f"{plan.name}  {plan.start_date} ~ {plan.end_date}")

        items = self.db.list_plan_items(self._active_plan_id)
        from collections import OrderedDict
        grouped: dict[str, list] = OrderedDict()
        for it in items:
            grouped.setdefault(it.plan_date, []).append(it)

        if not grouped:
            self.period_list_layout.addWidget(_label("暂无条目，在上方添加", TEXT_SECONDARY, 12))
            return

        for day, day_items in grouped.items():
            date_lbl = _label(f"  {day}", ACCENT, 12, True)
            self.period_list_layout.addWidget(date_lbl)
            for it in day_items:
                row = QFrame()
                row.setStyleSheet(f"QFrame {{ background:{DARK_SURFACE}; border:1px solid {DARK_BORDER}; border-radius:6px; }}")
                rl = QHBoxLayout(row)
                rl.setContentsMargins(6, 4, 6, 4)
                rl.setSpacing(6)

                sel = _btn("选")
                sel.setFixedSize(36, 26)
                sel.clicked.connect(lambda _, iid=it.id: self._select_plan_item(iid))
                rl.addWidget(sel)

                cb = QCheckBox()
                cb.setChecked(it.done)
                cb.setStyleSheet("background:transparent;")
                rl.addWidget(cb)

                parts = []
                if it.subject:
                    parts.append(f"[{it.subject}]")
                if it.time_slot:
                    parts.append(it.time_slot)
                if it.content:
                    parts.append(it.content)
                info = "  ".join(parts)
                info_lbl = QLabel(info)
                info_lbl.setWordWrap(True)
                info_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
                strike = "text-decoration: line-through;" if it.done else ""
                info_lbl.setStyleSheet(f"color:{TEXT_PRIMARY}; background:transparent; font-size:13px; {strike}")
                rl.addWidget(info_lbl, 1)

                def _on_toggle(state, iid=it.id, lbl=info_lbl):
                    self.db.set_plan_item_done(iid, state == Qt.Checked)
                    s = "text-decoration: line-through;" if state == Qt.Checked else ""
                    lbl.setStyleSheet(f"color:{TEXT_PRIMARY}; background:transparent; font-size:13px; {s}")
                cb.stateChanged.connect(_on_toggle)

                self.period_list_layout.addWidget(row)

    def _select_plan_item(self, item_id):
        self._selected_plan_item_id = item_id

    def _new_plan(self):
        from PyQt5.QtWidgets import QInputDialog as QI
        name, ok1 = QI.getText(self, "新建周期计划", "计划名称（如：期末复习）：")
        if not ok1 or not name.strip():
            return
        start, ok2 = QI.getText(self, "新建周期计划", "开始日期（YYYY-MM-DD）：", QLineEdit.Normal, date.today().isoformat())
        if not ok2:
            return
        end, ok3 = QI.getText(self, "新建周期计划", "结束日期（YYYY-MM-DD）：", QLineEdit.Normal,
                              (date.today() + timedelta(days=14)).isoformat())
        if not ok3:
            return
        pid = self.db.add_plan(name.strip(), start.strip(), end.strip())
        self._active_plan_id = pid
        self._refresh_plan_list()

    def _delete_plan(self):
        if not self._active_plan_id:
            return
        self.db.delete_plan(self._active_plan_id)
        self._active_plan_id = None
        self._refresh_plan_list()

    def _add_plan_item(self):
        if not self._active_plan_id:
            self.plan_info.setText("请先新建一个计划")
            return
        plan_date = self.item_date.date().toPyDate().isoformat()
        subject = self.item_subject.text().strip()
        time_slot = self.item_time.text().strip()
        content = self.item_content.text().strip()
        if not content and not subject:
            return
        self.db.add_plan_item(self._active_plan_id, plan_date, subject, time_slot, content)
        self.item_subject.clear()
        self.item_time.clear()
        self.item_content.clear()
        self._on_plan_changed()

    def _delete_plan_item(self):
        if not self._selected_plan_item_id:
            return
        self.db.delete_plan_item(self._selected_plan_item_id)
        self._selected_plan_item_id = None
        self._on_plan_changed()

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

    # ── Tab 3: Summary (left-right layout) ─────────────────────────────

    KIND_LABEL = {"week": "周总结", "half_month": "半月总结", "month": "月总结"}

    @staticmethod
    def _summary_label(kind: str, period_key: str) -> str:
        kind_cn = LearningPanel.KIND_LABEL.get(kind, kind)
        try:
            end = period_key.split("_")[1]
            dt = date.fromisoformat(end)
            return f"{dt.month}月{dt.day}日 {kind_cn}"
        except Exception:
            return f"{period_key} {kind_cn}"

    def _build_summary_tab(self):
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        v = QVBoxLayout(page)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)

        # top: date picker + generate buttons
        top = QHBoxLayout()
        top.setSpacing(6)
        top.addWidget(_label("锚定日期:", TEXT_PRIMARY, 12))
        self.summary_ref_date = QDateEdit()
        self.summary_ref_date.setCalendarPopup(True)
        self.summary_ref_date.setDisplayFormat("yyyy-MM-dd")
        self.summary_ref_date.setDate(QDate.currentDate())
        self.summary_ref_date.setStyleSheet(f"background:{INPUT_BG}; color:{TEXT_PRIMARY}; border:1px solid {DARK_BORDER}; border-radius:6px; padding:4px 8px;")
        top.addWidget(self.summary_ref_date)
        for label, kind in [("周总结(往前7天)", "week"), ("半月总结(往前15天)", "half_month"), ("月总结(往前30天)", "month")]:
            b = _btn(label, True)
            b.clicked.connect(lambda _, k=kind: self._gen_summary(k))
            top.addWidget(b)
        v.addLayout(top)

        self.summary_status = _label("", TEXT_SECONDARY, 11)
        v.addWidget(self.summary_status)

        # split: left history, right content
        split = QHBoxLayout()
        split.setSpacing(8)

        left = QVBoxLayout()
        left.addWidget(_label("历史总结（勾选后操作）", ACCENT, 12, True))

        left_scroll = QScrollArea()
        left_scroll.setMinimumWidth(120)
        left_scroll.setMaximumWidth(240)
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setStyleSheet("background:transparent; border:none;")
        left_scroll.verticalScrollBar().setStyleSheet(SCROLLBAR_STYLE)
        self.summary_list_widget = QWidget()
        self.summary_list_widget.setStyleSheet("background:transparent;")
        self.summary_list_layout = QVBoxLayout(self.summary_list_widget)
        self.summary_list_layout.setAlignment(Qt.AlignTop)
        self.summary_list_layout.setSpacing(3)
        left_scroll.setWidget(self.summary_list_widget)
        left.addWidget(left_scroll, 1)

        # action buttons under list
        act = QHBoxLayout()
        del_b = _btn("删除选中")
        del_b.setStyleSheet(del_b.styleSheet().replace(ACCENT, RED).replace("#7a9eff", "#ff7777"))
        del_b.clicked.connect(self._delete_selected_summaries)
        act.addWidget(del_b)
        review_b = _btn("总结复盘", True)
        review_b.clicked.connect(self._review_summaries)
        act.addWidget(review_b)
        left.addLayout(act)
        split.addLayout(left)

        right = QVBoxLayout()
        self.summary_text = _text_edit()
        self.summary_text.setReadOnly(True)
        right.addWidget(self.summary_text, 1)
        split.addLayout(right, 1)

        v.addLayout(split, 1)

        self._summary_checks = []  # list of (QCheckBox, kind, period_key)
        self._refresh_summary_list()
        return page

    def _refresh_summary_list(self):
        while self.summary_list_layout.count():
            w = self.summary_list_layout.takeAt(0)
            if w.widget():
                w.widget().deleteLater()
        self._summary_checks.clear()

        items = self.db.list_all_summaries()

        if not items:
            self.summary_list_layout.addWidget(_label("该时段暂无总结", TEXT_SECONDARY, 11))
            return

        for it in items:
            label = self._summary_label(it["kind"], it["period_key"])
            gen_time = it.get("generated_at", "")[:10]

            row = QFrame()
            row.setStyleSheet(f"QFrame {{ background:{DARK_SURFACE}; border:1px solid {DARK_BORDER}; border-radius:6px; }}")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(6, 4, 6, 4)
            rl.setSpacing(6)

            cb = QCheckBox()
            cb.setStyleSheet("background:transparent;")
            rl.addWidget(cb)

            txt = f"{label}\n{gen_time}" if gen_time else label
            lbl = QLabel(txt)
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color:{TEXT_PRIMARY}; background:transparent; font-size:12px;")
            rl.addWidget(lbl, 1)

            self._summary_checks.append((cb, it["kind"], it["period_key"]))

            body = it["body"]
            row.setCursor(Qt.PointingHandCursor)
            row.mousePressEvent = lambda e, b=body, lb=label: self._show_summary(b, lb)
            self.summary_list_layout.addWidget(row)

    def _show_summary(self, body: str, label: str):
        self.summary_text.setPlainText(body)
        self.summary_status.setText(f"查看: {label}")

    def _delete_selected_summaries(self):
        deleted = 0
        for cb, kind, pk in self._summary_checks:
            if cb.isChecked():
                self.db.delete_summary(kind, pk)
                deleted += 1
        if deleted:
            self.summary_status.setText(f"已删除 {deleted} 条总结")
            self._refresh_summary_list()
        else:
            self.summary_status.setText("请先勾选要删除的总结")

    def _review_summaries(self):
        selected = [(cb, kind, pk) for cb, kind, pk in self._summary_checks if cb.isChecked()]
        if len(selected) < 2:
            self.summary_status.setText("请勾选至少 2 条总结进行复盘")
            return

        settings = load_settings()
        base = settings.get("api_base_url", "")
        key = settings.get("api_key", "")
        model = settings.get("model", "")
        if not base:
            self.summary_status.setText("请先配置 API（编辑 settings.json）")
            return
        if self._worker and self._worker.isRunning():
            return

        # Collect selected summary bodies with labels
        parts = []
        for cb, kind, pk in selected:
            body = self.db.get_cached_summary(kind, pk)
            label = self._summary_label(kind, pk)
            if body:
                parts.append(f"=== {label} ===\n{body}")
        raw = "\n\n".join(parts)

        self.summary_status.setText("正在生成总结复盘...")
        self.summary_text.clear()

        system_prompt = (
            "你是一名学习复盘分析师。用户提供了多份不同时间段的学习总结。"
            "请对比分析这些总结，找出学习者的变化与趋势，包含：\n"
            "① 学习状态的变化趋势（进步/退步/波动）\n"
            "② 做得好的、持续保持的亮点\n"
            "③ 反复出现的问题或需要改进的地方\n"
            "④ 基于趋势的具体建议\n\n"
            "控制在 800 字以内，用中文，分点清晰，客观但有建设性。"
        )

        def run():
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": raw},
            ]
            return chat_completion(base, key, model, messages)

        self._worker = AIWorkerThread(run, self)
        self._worker.finished.connect(lambda text: self._on_review_result(text, len(selected)))
        self._worker.error.connect(self._on_summary_error)
        self._worker.start()

    def _on_review_result(self, text, count):
        self.summary_status.setText(f"✓ 复盘完成（基于 {count} 份总结）")
        self.summary_text.setPlainText(text)

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

        ref = self.summary_ref_date.date().toPyDate()
        kind_cn = self.KIND_LABEL.get(kind, kind)
        self.summary_status.setText(f"正在生成{kind_cn}（{ref.isoformat()} 往前）...")
        self.summary_text.clear()

        fn_map = {
            "week": lambda: build_ai_week_summary(self.db, base, key, model, end=ref),
            "half_month": lambda: build_ai_half_month_summary(self.db, base, key, model, end=ref),
            "month": lambda: build_ai_month_summary(self.db, base, key, model, ref=ref),
        }
        fn = fn_map[kind]

        def run():
            pk, text = fn()
            self.db.save_summary_cache(kind, pk, text)
            return text

        self._worker = AIWorkerThread(run, self)
        self._worker.finished.connect(self._on_summary_result)
        self._worker.error.connect(self._on_summary_error)
        self._worker.start()

    def _on_summary_result(self, text):
        self.summary_status.setText("✓ 生成完成，已保存到历史")
        self.summary_text.setPlainText(text)
        # Force DB commit visible, then refresh
        self.db._conn.commit()
        self._refresh_summary_list()
        # Scroll to top of the list to show the new item
        if self.summary_list_layout.count():
            w = self.summary_list_layout.itemAt(0).widget()
            if w:
                w.setFocus()

    def _on_summary_error(self, err):
        self.summary_status.setText(f"错误: {err[:100]}")

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
        left_scroll.setMinimumWidth(100)
        left_scroll.setMaximumWidth(220)
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
            x = pet_pos.x() - self.width() - 10
            y = pet_pos.y() - self.height() + config.PET_SIZE
            self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
