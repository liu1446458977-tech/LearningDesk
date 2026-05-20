import sys
import os
import traceback

# 确保 src 目录在模块搜索路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 全局异常钩子 — 让所有未捕获异常都打印出来而不是静默崩溃
def excepthook(exc_type, exc_value, exc_tb):
    traceback.print_exception(exc_type, exc_value, exc_tb)
    try:
        input("\n发生错误，按回车退出...")
    except EOFError:
        pass

sys.excepthook = excepthook

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPalette, QColor, QFont
from PyQt5.QtCore import Qt


def apply_dark_palette(app):
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#1a1d24"))
    palette.setColor(QPalette.WindowText, QColor("#e0e0e0"))
    palette.setColor(QPalette.Base, QColor("#22262e"))
    palette.setColor(QPalette.AlternateBase, QColor("#2a2e38"))
    palette.setColor(QPalette.Text, QColor("#e0e0e0"))
    palette.setColor(QPalette.Button, QColor("#2a2e38"))
    palette.setColor(QPalette.ButtonText, QColor("#e0e0e0"))
    palette.setColor(QPalette.Highlight, QColor("#648cff"))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ToolTipBase, QColor("#2a2e38"))
    palette.setColor(QPalette.ToolTipText, QColor("#e0e0e0"))
    app.setPalette(palette)

    font = QFont("Segoe UI", 12)
    font.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(font)


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    apply_dark_palette(app)

    from pet_window import PetWindow
    from chat_window import ChatWindow
    from learning_panel import LearningPanel

    pet_window = PetWindow()
    chat_window = ChatWindow()
    learning_panel = LearningPanel()

    chat_window.set_pet_window(pet_window)
    learning_panel.set_pet_window(pet_window)

    pet_window.open_chat.connect(chat_window.show_and_position)
    pet_window.open_learning_plan.connect(learning_panel.show_and_position)
    chat_window.send_message.connect(pet_window.on_message_received)

    pet_window.show()
    chat_window.api_client.warmup()
    print("Hermes 已启动，悬浮球在右下角")

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
