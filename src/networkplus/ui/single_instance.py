"""Tek kopya: tepside calisan uygulama varken ikinci acilis yeni pencere acmaz,
calisan kopyaya 'goster' der ve cikar.

Yonetici (gorevle baslamis) kopya ile yetkisiz ikinci acilis ayni kullanicidadir;
yuksek butunluklu surecin borusuna yetkisiz surec erisebilsin diye WorldAccess.
"""

from __future__ import annotations

import getpass
import time

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtNetwork import QLocalServer, QLocalSocket


def server_name() -> str:
    try:
        user = getpass.getuser()
    except Exception:           # noqa: BLE001
        user = "user"
    return f"networkplus-{user}"


def send_to_running(message: str = "show", timeout_ms: int = 500) -> bool:
    sock = QLocalSocket()
    sock.connectToServer(server_name())
    if not sock.waitForConnected(timeout_ms):
        return False
    sock.write(message.encode("utf-8"))
    sock.waitForBytesWritten(timeout_ms)
    sock.disconnectFromServer()
    return True


def wait_and_send(message: str, total_ms: int = 15000) -> bool:
    """Yeni baslatilan (ör. gorevle) kopya hazir olana dek dene."""
    end = time.monotonic() + total_ms / 1000
    while time.monotonic() < end:
        if send_to_running(message, 300):
            return True
        time.sleep(0.3)
    return False


class SingleInstanceServer(QObject):
    messageReceived = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.WorldAccessOption)
        self.server.newConnection.connect(self._on_connection)

    def listen(self) -> bool:
        name = server_name()
        if self.server.listen(name):
            return True
        QLocalServer.removeServer(name)     # onceki cokmeden kalan artik
        return self.server.listen(name)

    def _on_connection(self):
        sock = self.server.nextPendingConnection()
        if sock is None:
            return
        sock.waitForReadyRead(500)
        msg = bytes(sock.readAll()).decode("utf-8", "replace").strip() or "show"
        sock.close()
        self.messageReceived.emit(msg)
