import os
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                             QLineEdit, QPushButton, QLabel,
                             QScrollArea, QFrame, QApplication)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QDragEnterEvent, QDropEvent, QImage, QPixmap, QKeyEvent
import config
from vision_analyzer import VisionAnalyzer
from api_client import HermesAPIClient


class InputBox(QLineEdit):
    """支持 Ctrl+V 粘贴图片的输入框"""
    image_pasted = pyqtSignal(str)  # 发射临时文件路径

    def __init__(self, parent=None):
        super().__init__(parent)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_V and event.modifiers() & Qt.ControlModifier:
            clipboard = QApplication.clipboard()
            mimedata = clipboard.mimeData()
            if mimedata.hasImage():
                image = QImage(mimedata.imageData())
                temp_dir = os.path.join(os.path.expanduser("~"), ".hermes_pet_temp")
                os.makedirs(temp_dir, exist_ok=True)
                temp_path = os.path.join(temp_dir, f"clipboard_{os.urandom(4).hex()}.png")
                image.save(temp_path, "PNG")
                self.image_pasted.emit(temp_path)
                return
        super().keyPressEvent(event)

DARK_BG = "#1a1d24"
DARK_SURFACE = "#22262e"
DARK_BORDER = "#2e3340"
ACCENT = "#648cff"
ACCENT_DIM = "#3a4a7a"
TEXT_PRIMARY = "#e0e0e0"
TEXT_SECONDARY = "#8890a0"
INPUT_BG = "#2a2e38"
SCROLLBAR_BG = "#1e2128"
SCROLLBAR_HANDLE = "#3a3f4d"

SCROLLBAR_STYLE = f"""
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollBar:vertical {{
    background: {SCROLLBAR_BG};
    width: 6px;
    margin: 0;
    border-radius: 3px;
}}
QScrollBar::handle:vertical {{
    background: {SCROLLBAR_HANDLE};
    min-height: 30px;
    border-radius: 3px;
}}
QScrollBar::handle:vertical:hover {{
    background: {ACCENT_DIM};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}
"""


class ChatWindow(QWidget):
    send_message = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.vision = VisionAnalyzer()
        self.api_client = HermesAPIClient()
        self.api_client.set_message_callback(self.on_hermes_response)
        self.api_client.error_occurred.connect(self.on_hermes_error)
        self.pending_image = None
        self.pet_window = None
        self.init_ui()

    def set_pet_window(self, pet_window):
        self.pet_window = pet_window

    def init_ui(self):
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("Hermes")
        self.setFixedSize(config.CHAT_WIDTH, config.CHAT_HEIGHT)
        self.setAcceptDrops(True)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        container = QFrame()
        container.setStyleSheet(f"""
            QFrame {{
                background-color: {DARK_BG};
                border: 1px solid {DARK_BORDER};
                border-radius: 16px;
            }}
        """)

        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(16, 12, 16, 14)
        container_layout.setSpacing(0)

        # 标题栏
        title_bar = QHBoxLayout()
        title_bar.setContentsMargins(0, 0, 0, 8)
        title_label = QLabel("HERMES")
        title_label.setFont(QApplication.font())
        title_label.setStyleSheet(f"font-weight: 600; font-size: 15px; color: {ACCENT}; letter-spacing: 2px; background: transparent;")
        title_bar.addWidget(title_label)
        title_bar.addStretch()

        status_dot = QLabel("●")
        status_dot.setStyleSheet(f"color: #4caf50; font-size: 10px; background: transparent; margin-right: 8px;")
        title_bar.addWidget(status_dot)

        close_btn = QPushButton("✕")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                font-size: 15px;
                border: none;
                color: {TEXT_SECONDARY};
                background: transparent;
                padding: 2px 6px;
            }}
            QPushButton:hover {{
                color: #ff5555;
            }}
        """)
        close_btn.setFixedSize(26, 26)
        close_btn.clicked.connect(self.hide)
        title_bar.addWidget(close_btn)
        container_layout.addLayout(title_bar)

        # 分割线
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {DARK_BORDER};")
        container_layout.addWidget(sep)
        container_layout.addSpacing(8)

        # 消息历史区
        self.history_scroll = QScrollArea()
        self.history_scroll.setWidgetResizable(True)
        self.history_scroll.setFrameShape(QFrame.NoFrame)
        self.history_scroll.setStyleSheet("background: transparent; border: none;")
        self.history_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.history_scroll.verticalScrollBar().setStyleSheet(SCROLLBAR_STYLE)

        self.history_widget = QWidget()
        self.history_widget.setStyleSheet("background: transparent;")
        self.history_layout = QVBoxLayout()
        self.history_layout.setAlignment(Qt.AlignTop)
        self.history_layout.setSpacing(6)
        self.history_widget.setLayout(self.history_layout)
        self.history_scroll.setWidget(self.history_widget)
        container_layout.addWidget(self.history_scroll)

        # 图片预览区（带删除按钮）
        self.preview_container = QFrame()
        self.preview_container.setStyleSheet(f"""
            QFrame {{
                background-color: {DARK_SURFACE};
                border: 1px solid {ACCENT_DIM};
                border-radius: 8px;
            }}
        """)
        preview_layout = QHBoxLayout(self.preview_container)
        preview_layout.setContentsMargins(8, 6, 8, 6)
        preview_layout.setSpacing(6)

        self.image_preview = QLabel()
        self.image_preview.setFixedHeight(80)
        self.image_preview.setAlignment(Qt.AlignCenter)
        self.image_preview.setStyleSheet("background: transparent; border: none;")
        preview_layout.addWidget(self.image_preview)

        self.remove_img_btn = QPushButton("✕")
        self.remove_img_btn.setCursor(Qt.PointingHandCursor)
        self.remove_img_btn.setFixedSize(24, 24)
        self.remove_img_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {DARK_BORDER};
                color: {TEXT_SECONDARY};
                border: none;
                border-radius: 10px;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: #ff5555;
                color: white;
            }}
        """)
        self.remove_img_btn.clicked.connect(self.clear_pending_image)
        preview_layout.addWidget(self.remove_img_btn, alignment=Qt.AlignTop)

        self.preview_container.hide()
        container_layout.addWidget(self.preview_container)

        container_layout.addSpacing(8)

        # 输入区
        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)

        self.input_box = InputBox()
        self.input_box.setPlaceholderText("输入消息... (Ctrl+V 粘贴图片)")
        self.input_box.setStyleSheet(f"""
            QLineEdit {{
                border: 1px solid {DARK_BORDER};
                border-radius: 10px;
                padding: 10px 14px;
                background-color: {INPUT_BG};
                color: {TEXT_PRIMARY};
                font-size: 15px;
            }}
            QLineEdit:focus {{
                border: 1px solid {ACCENT};
            }}
        """)
        self.input_box.returnPressed.connect(self.send_text_message)
        self.input_box.image_pasted.connect(self.load_image)
        input_layout.addWidget(self.input_box)

        self.send_btn = QPushButton("➤")
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {ACCENT};
                color: white;
                border: none;
                border-radius: 10px;
                padding: 10px 14px;
                font-size: 17px;
            }}
            QPushButton:hover {{
                background-color: #7a9eff;
            }}
            QPushButton:pressed {{
                background-color: #5070cc;
            }}
        """)
        self.send_btn.clicked.connect(self.send_text_message)
        input_layout.addWidget(self.send_btn)

        container_layout.addLayout(input_layout)

        main_layout.addWidget(container)
        self.setLayout(main_layout)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.load_image(url.toLocalFile())

    def load_image(self, file_path):
        self.pending_image = file_path
        pixmap = QPixmap(file_path).scaled(
            200, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.image_preview.setPixmap(pixmap)
        self.preview_container.show()

    def clear_pending_image(self):
        self.pending_image = None
        self.image_preview.clear()
        self.preview_container.hide()

    def send_text_message(self):
        text = self.input_box.text().strip()
        if text or self.pending_image:
            self.add_message("You", text, is_user=True, image=self.pending_image)
            self.input_box.clear()
            image_to_send = self.pending_image
            self.pending_image = None
            self.image_preview.clear()
            self.preview_container.hide()
            self.send_message.emit(text)
            self.api_client.send_message(text, image=image_to_send)

    def on_hermes_response(self, text):
        self.add_message("Hermes", text, is_user=False)

    def on_hermes_error(self, text):
        self.add_message("Error", text, is_user=False)

    def add_message(self, sender, text, is_user=False, image=None):
        msg_widget = QFrame()
        msg_widget.setStyleSheet(f"""
            QFrame {{
                background-color: {DARK_SURFACE};
                border: 1px solid {DARK_BORDER};
                border-radius: 10px;
                padding: 0px;
            }}
        """)

        msg_layout = QVBoxLayout(msg_widget)
        msg_layout.setContentsMargins(12, 8, 12, 10)
        msg_layout.setSpacing(4)

        # 发送者标签
        sender_label = QLabel(sender)
        if is_user:
            sender_label.setStyleSheet(f"color: {ACCENT}; font-size: 13px; font-weight: 600; background: transparent; border: none; letter-spacing: 1px;")
        elif sender == "Error":
            sender_label.setStyleSheet(f"color: #ff5555; font-size: 13px; font-weight: 600; background: transparent; border: none; letter-spacing: 1px;")
        else:
            sender_label.setStyleSheet(f"color: #4caf50; font-size: 13px; font-weight: 600; background: transparent; border: none; letter-spacing: 1px;")
        msg_layout.addWidget(sender_label)

        # 消息内容
        if text:
            text_label = QLabel(text)
            text_label.setWordWrap(True)
            text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            text_label.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 15px; line-height: 1.5; background: transparent; border: none;")
            msg_layout.addWidget(text_label)

        # 图片
        if image:
            img_label = QLabel()
            img_label.setStyleSheet("background: transparent; border: none;")
            pixmap = QPixmap(image).scaled(260, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            img_label.setPixmap(pixmap)
            msg_layout.addWidget(img_label)

        self.history_layout.addWidget(msg_widget)
        scrollbar = self.history_scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def show_and_position(self):
        if self.pet_window:
            pet_pos = self.pet_window.pos()
            x = pet_pos.x() - config.CHAT_WIDTH - 10
            y = pet_pos.y() - config.CHAT_HEIGHT + config.PET_SIZE
            self.move(x, y)
        else:
            screen = QApplication.primaryScreen().availableGeometry()
            x = (screen.width() - config.CHAT_WIDTH) // 2
            y = (screen.height() - config.CHAT_HEIGHT) // 2
            self.move(x, y)

        self.show()
        self.raise_()
        self.activateWindow()
