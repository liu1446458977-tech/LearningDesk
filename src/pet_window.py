from PyQt5.QtWidgets import QWidget, QLabel, QMenu, QAction, QApplication
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QPainter, QColor, QPen, QFont
import config


class PetWindow(QWidget):
    open_chat = pyqtSignal()
    open_learning_plan = pyqtSignal()
    send_message = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.drag_position = None
        self.is_thinking = False
        self._pulse_alpha = 40
        self._pulse_dir = 1
        self.init_ui()
        self.init_animations()

    def init_ui(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(config.PET_SIZE, config.PET_SIZE)

        self.pet_label = QLabel(self)
        self.pet_label.setAlignment(Qt.AlignCenter)
        self.pet_label.setGeometry(0, 0, config.PET_SIZE, config.PET_SIZE)
        self.pet_label.setText("H")
        self.pet_label.setFont(QFont("Consolas", 24, QFont.Bold))
        self.pet_label.setStyleSheet("color: #e0e0e0; background: transparent;")

        self.move_to_corner()

    def init_animations(self):
        self.blink_timer = QTimer(self)
        self.blink_timer.timeout.connect(self._pulse)
        self.blink_timer.start(80)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 外圈光晕
        painter.setBrush(QColor(100, 140, 255, int(self._pulse_alpha)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(4, 4, config.PET_SIZE - 8, config.PET_SIZE - 8)

        # 主圆
        painter.setBrush(QColor(35, 40, 52))
        painter.setPen(QPen(QColor(80, 100, 160, 120), 1.5))
        painter.drawEllipse(8, 8, config.PET_SIZE - 16, config.PET_SIZE - 16)

        painter.end()

    def _pulse(self):
        self._pulse_alpha += self._pulse_dir * 1.5
        if self._pulse_alpha >= 60:
            self._pulse_dir = -1
        elif self._pulse_alpha <= 25:
            self._pulse_dir = 1
        self.update()

    def move_to_corner(self):
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.width() - config.PET_SIZE - 20
        y = screen.height() - config.PET_SIZE - 20
        self.move(x, y)

    def on_message_received(self, text):
        self.is_thinking = False
        self.pet_label.setStyleSheet("color: #80ff80; background: transparent;")
        QTimer.singleShot(1200, lambda: self.pet_label.setStyleSheet("color: #e0e0e0; background: transparent;"))

    def set_thinking(self, thinking):
        self.is_thinking = thinking
        if thinking:
            self.pet_label.setStyleSheet("color: #ffcc00; background: transparent;")
        else:
            self.pet_label.setStyleSheet("color: #e0e0e0; background: transparent;")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_start_pos = event.globalPos()
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.drag_position:
            self.move(event.globalPos() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if hasattr(self, "drag_start_pos"):
                delta = (event.globalPos() - self.drag_start_pos).manhattanLength()
                if delta < 15:
                    self.open_chat.emit()
            self.drag_position = None
            if hasattr(self, "drag_start_pos"):
                del self.drag_start_pos

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #22262e;
                border: 1px solid #2e3340;
                border-radius: 8px;
                padding: 4px 0;
                color: #e0e0e0;
                font-size: 15px;
            }
            QMenu::item {
                padding: 6px 24px;
            }
            QMenu::item:selected {
                background-color: #3a4a7a;
            }
            QMenu::separator {
                height: 1px;
                background: #2e3340;
                margin: 4px 12px;
            }
        """)
        open_chat_action = QAction("Open Chat", self)
        open_chat_action.triggered.connect(self._on_open_chat_triggered)
        menu.addAction(open_chat_action)

        learning_plan_action = QAction("学习面板", self)
        learning_plan_action.triggered.connect(self.open_learning_plan.emit)
        menu.addAction(learning_plan_action)

        menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(quit_action)

        menu.exec_(event.globalPos())

    def _on_open_chat_triggered(self):
        self.open_chat.emit()
