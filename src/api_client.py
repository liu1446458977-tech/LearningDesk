import os
import shutil
import subprocess
import threading
from PyQt5.QtCore import QObject, pyqtSignal

# Auto-detect hermes executable: env var > PATH > common locations
def _find_hermes():
    exe = os.environ.get("HERMES_BIN", "")
    if exe and os.path.isfile(exe):
        return exe
    found = shutil.which("hermes")
    if found:
        return found
    common = os.path.join(os.environ.get("APPDATA", ""), "Python", "Python314", "Scripts", "hermes.exe")
    return common if os.path.isfile(common) else "hermes"

HERMES_EXE = _find_hermes()
HERMES_ENV = {
    **os.environ,
    "HERMES_HOME": os.environ.get("HERMES_HOME", os.path.join(os.path.expanduser("~"), ".hermes")),
    "HERMES_BIN": HERMES_EXE,
    "HERMES_AGENT_ROOT": os.environ.get("HERMES_AGENT_ROOT", ""),
}


class HermesAPIClient(QObject):
    message_received = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.message_callback = None
        self._connected = False
        self._session_id = None
        self._ready_event = threading.Event()
        self._ready_event.set()  # CLI 模式无需预热，立即就绪

    def set_message_callback(self, callback):
        self.message_callback = callback
        self.message_received.connect(callback)

    def warmup(self):
        self._connected = True
        print("[hermes-pet] CLI 模式就绪")

    def send_message(self, text, image=None, image_path=None):
        img_path = image_path or image
        thread = threading.Thread(
            target=self._send_in_background,
            args=(text, img_path),
            daemon=True,
        )
        thread.start()

    def _send_in_background(self, text, image_path=None):
        self._ready_event.wait(timeout=5)

        try:
            self._send_via_cli(text, image_path)
        except Exception as e:
            self.error_occurred.emit(f"请求异常: {e}")

    def _send_via_cli(self, text, image_path=None):
        hermes_cmd = self._build_hermes_cmd(text, image_path)

        result = subprocess.run(
            hermes_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120,
            env=HERMES_ENV,
        )

        stdout = result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
        stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""

        if result.returncode != 0:
            err = stderr.strip()
            self.error_occurred.emit(f"Hermes 错误: {err[:200]}" if err else "Hermes 未返回结果")
            return

        self._extract_session_id(stdout)

        answer = self._parse_output(stdout)
        if answer:
            self.message_received.emit(answer)
        else:
            self.error_occurred.emit("Hermes 返回为空")

    def _build_hermes_cmd(self, text, image_path=None):
        cmd = [HERMES_EXE, "chat", "-q", text, "-Q"]

        if self._session_id:
            cmd += ["--resume", self._session_id]

        if image_path and os.path.exists(image_path):
            cmd += ["--image", image_path]
        return cmd

    def _extract_session_id(self, stdout):
        for line in stdout.split("\n"):
            if line.startswith("session_id:"):
                self._session_id = line.split(":", 1)[1].strip()
                return

    def _parse_output(self, stdout):
        lines = stdout.strip().split("\n")
        result_lines = []
        for line in lines:
            if line.startswith("session_id:"):
                continue
            if line.startswith("⚠"):
                continue
            if line.startswith("warning:"):
                continue
            result_lines.append(line)
        return "\n".join(result_lines).strip()
