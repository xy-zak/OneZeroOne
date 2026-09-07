"""Runtime (non-persisted) state: the connection, apply timer, errors."""

from __future__ import annotations

import threading
from typing import Optional, Protocol


class Connection(Protocol):
    """Serial or network transport. Worker threads never touch ``bpy``."""

    @property
    def is_connected(self) -> bool: ...

    @property
    def label(self) -> str: ...

    def disconnect(self) -> None: ...


connection: Optional[Connection] = None
_timer_running: bool = False
# WM event timer that wakes Blender's idle event loop at the apply rate.
apply_timer = None
_last_error: str = ""
_error_lock = threading.Lock()


def set_error(message: str) -> None:
    global _last_error
    with _error_lock:
        _last_error = message


def get_error() -> str:
    with _error_lock:
        return _last_error


def clear_error() -> None:
    global _last_error
    with _error_lock:
        _last_error = ""
