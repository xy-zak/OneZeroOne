"""Network (UDP) input using the same text / SLIP / newline parsers as serial.

Each UDP datagram is one already-framed blob.  The OSC server runs in a
background ``threading.Thread`` and never touches ``bpy``.
"""

from __future__ import annotations

import socket
import threading
from typing import Callable, Optional

from .serial_io import decode_datagram


class NetworkConnection:
    """Owns a UDP socket and a background receive thread."""

    def __init__(
        self,
        on_value: Callable[[str, float], None],
        on_error: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._on_value = on_value
        self._on_error = on_error
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._ip = ""
        self._port = 0
        self._framing = "text"

    @property
    def is_connected(self) -> bool:
        return self._sock is not None

    @property
    def ip(self) -> str:
        return self._ip

    @property
    def port(self) -> int:
        return self._port

    @property
    def framing(self) -> str:
        return self._framing

    @property
    def port_label(self) -> str:
        """Human-readable endpoint label for the UI."""
        return f"{self._ip}:{self._port}" if self._sock is not None else ""

    @property
    def label(self) -> str:
        return self.port_label

    def connect(self, ip: str, port: int = 9001, framing: str = "text") -> bool:
        if self.is_connected:
            self.disconnect()
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((ip, port))
            sock.settimeout(0.2)
        except Exception as exc:  # noqa: BLE001 - surface any bind error
            if self._on_error:
                self._on_error(str(exc))
            return False
        self._sock = sock
        self._ip = ip
        self._port = port
        self._framing = framing
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="onezeroone-network", daemon=True
        )
        self._thread.start()
        return True

    def disconnect(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:  # noqa: BLE001
                pass
            self._sock = None

    def _run(self) -> None:
        assert self._sock is not None
        while not self._stop.is_set():
            try:
                data, _addr = self._sock.recvfrom(65535)
            except socket.timeout:
                continue
            except Exception as exc:  # noqa: BLE001
                if not self._stop.is_set() and self._on_error:
                    self._on_error(str(exc))
                break
            if not data:
                continue
            for address, value in decode_datagram(data, self._framing):
                self._on_value(address, value)
