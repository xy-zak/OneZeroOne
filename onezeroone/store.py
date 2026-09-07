"""Thread-safe store of the latest value per OSC address.

The serial reader thread writes here; the Blender main thread (UI panel,
value application timer) reads from here.  All access goes through a ``threading.Lock``
so no ``bpy`` RNA is touched from the worker thread.

Remap configuration is keyed by ``binding_id`` (one per target), not by
address, so that multiple targets on the same input can have independent
output ranges.
"""

from __future__ import annotations

import threading
import time

from .remap import remap

# Auto-discover can flood the dict if a device chatters unique addresses.
_MAX_ADDRESSES = 256


class ValueStore:
    """Holds the latest raw value per address plus per-binding remap config."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._raw: dict[str, float] = {}
        self._ts: dict[str, float] = {}
        # Per-binding remap: binding_id -> (address, in_min, in_max, out_min, out_max, clamp)
        self._binding_remap: dict[int, tuple[str, float, float, float, float, bool]] = {}
        # Monotonic timestamp of the most recent update() call.
        self._last_update: float = 0.0
        # Increments on every update() so the apply pump can detect new data
        # even when two packets share the same monotonic clock reading.
        self._generation: int = 0
        # Most recently received (address, value) — for the debug panel.
        self._last_address: str = ""
        self._last_value: float = 0.0

    def update(self, address: str, value: float) -> None:
        with self._lock:
            if address not in self._raw and len(self._raw) >= _MAX_ADDRESSES:
                if self._ts:
                    oldest = min(self._ts, key=self._ts.get)
                    self._raw.pop(oldest, None)
                    self._ts.pop(oldest, None)
            self._raw[address] = value
            now = time.monotonic()
            self._ts[address] = now
            self._last_update = now
            self._generation += 1
            self._last_address = address
            self._last_value = value

    def generation(self) -> int:
        """Return a monotonic counter of ``update()`` calls."""
        with self._lock:
            return self._generation

    def last_update_time(self) -> float:
        """Return the monotonic timestamp of the most recent value update."""
        with self._lock:
            return self._last_update

    def last_received(self) -> tuple[str, float]:
        """Return the most recently received (address, value)."""
        with self._lock:
            return self._last_address, self._last_value

    def get_raw(self, address: str) -> float:
        with self._lock:
            return self._raw.get(address, 0.0)

    def get_timestamp(self, address: str) -> float:
        with self._lock:
            return self._ts.get(address, 0.0)

    # -- Per-binding remap ------------------------------------------------

    def set_remap_for_binding(
        self,
        binding_id: int,
        address: str,
        in_min: float,
        in_max: float,
        out_min: float,
        out_max: float,
        clamp: bool = True,
    ) -> None:
        with self._lock:
            self._binding_remap[binding_id] = (
                address, in_min, in_max, out_min, out_max, clamp,
            )

    def get_remapped_for_binding(self, binding_id: int) -> float:
        with self._lock:
            params = self._binding_remap.get(binding_id)
            if params is None:
                return 0.0
            address, in_min, in_max, out_min, out_max, clamp = params
            raw = self._raw.get(address, 0.0)
        return remap(raw, in_min, in_max, out_min, out_max, clamp)

    def clear_remap_for_binding(self, binding_id: int) -> None:
        with self._lock:
            self._binding_remap.pop(binding_id, None)

    # -- Address discovery -------------------------------------------------

    def addresses(self) -> list[str]:
        with self._lock:
            return sorted(self._raw.keys())

    def has_address(self, address: str) -> bool:
        with self._lock:
            return address in self._raw


# Module-level singleton shared by the reader thread, UI and value application timer.
store = ValueStore()
