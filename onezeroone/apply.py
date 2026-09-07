"""Main-thread apply pump: remap store values onto bound RNA at up to 60 fps.

Incoming packets only write the ValueStore (latest value per address).  This
module copies the latest remapped values onto bound properties at
``onezeroone_update_rate`` Hz, never faster than 60 fps.

``bpy.app.timers`` alone does not wake Blender when the UI is idle (~5 Hz on
Wayland).  A WindowManager event timer *does* (it is a GHOST timer), so we
add one for the wake and keep the app timer as the apply callback.
"""

from __future__ import annotations

import time

import bpy

from . import datapath, recording, runtime
from .properties import alloc_entry_id
from .store import store

# OSC command addresses — never auto-discovered into the mapping list.
_COMMAND_ADDRESSES = frozenset({"/recordframes", "/renderimage"})

_APPLY_RATE_CAP = 60
_HOUSEKEEPING_INTERVAL = 0.5

_last_applied_generation: int = 0
_last_discover_time: float = 0.0
_wake_interval: float = 0.0


def apply_interval(wm=None) -> float:
    """Seconds between apply ticks, honoring the UI rate and the 60 fps cap."""
    rate = _APPLY_RATE_CAP
    if wm is None:
        try:
            wm = bpy.context.window_manager
        except Exception:  # noqa: BLE001
            wm = None
    if wm is not None:
        try:
            rate = int(wm.onezeroone_update_rate)
        except Exception:  # noqa: BLE001
            rate = _APPLY_RATE_CAP
    rate = max(1, min(rate, _APPLY_RATE_CAP))
    return 1.0 / rate


def sync_remap_to_store(wm) -> None:
    """Push per-binding remap config from the UI into the ValueStore."""
    for entry in wm.onezeroone_addresses:
        if not entry.address:
            continue
        for binding in entry.bindings:
            store.set_remap_for_binding(
                binding.binding_id,
                entry.address,
                binding.in_min,
                binding.in_max,
                binding.out_min,
                binding.out_max,
                binding.clamp,
            )


def auto_discover_addresses(wm) -> None:
    """Add any wire-seen address that isn't already in the list."""
    existing = {e.address for e in wm.onezeroone_addresses}
    for addr in store.addresses():
        if addr in existing or addr in _COMMAND_ADDRESSES:
            continue
        entry = wm.onezeroone_addresses.add()
        entry.address = addr
        entry.entry_id = alloc_entry_id()
        existing.add(addr)


def apply_values(wm) -> None:
    """Apply the latest remapped values directly to bound properties."""
    for entry in wm.onezeroone_addresses:
        if not entry.address:
            continue
        for binding in entry.bindings:
            if not binding.data_path:
                continue
            id_block, data_path, index = datapath.parse_full_data_path(binding.data_path)
            if id_block is None:
                continue
            value = store.get_remapped_for_binding(binding.binding_id)
            datapath.set_property_value(id_block, data_path, index, value)


def _tag_view3d_redraw(wm) -> None:
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                for region in area.regions:
                    if region.type in ("UI", "WINDOW"):
                        region.tag_redraw()


def _apply_frame(wm) -> None:
    """Apply new store data, tick recording, and periodically auto-discover."""
    global _last_applied_generation, _last_discover_time
    gen = store.generation()
    if gen > _last_applied_generation:
        _last_applied_generation = gen
        sync_remap_to_store(wm)
        apply_values(wm)
        _tag_view3d_redraw(wm)
    recording.tick_recording()
    now = time.monotonic()
    if now - _last_discover_time >= _HOUSEKEEPING_INTERVAL:
        _last_discover_time = now
        auto_discover_addresses(wm)


def _pump_is_connected() -> bool:
    return runtime.connection is not None and runtime.connection.is_connected


def _remove_wake_timer() -> None:
    global _wake_interval
    if runtime.apply_timer is None:
        return
    try:
        bpy.context.window_manager.event_timer_remove(runtime.apply_timer)
    except Exception:  # noqa: BLE001
        pass
    runtime.apply_timer = None
    _wake_interval = 0.0


def _ensure_wake_timer(wm) -> None:
    """Keep a GHOST timer ticking so the idle event loop runs at the apply rate."""
    global _wake_interval
    interval = apply_interval(wm)
    window = getattr(bpy.context, "window", None)
    if window is None:
        return
    if runtime.apply_timer is not None and abs(_wake_interval - interval) < 1e-6:
        return
    _remove_wake_timer()
    runtime.apply_timer = wm.event_timer_add(interval, window=window)
    _wake_interval = interval


def _apply_tick():
    """Main-thread pump: wake-timer maintenance + apply latest store values."""
    if not runtime._timer_running or not _pump_is_connected():
        runtime._timer_running = False
        _remove_wake_timer()
        return None
    try:
        wm = bpy.context.window_manager
    except Exception:  # noqa: BLE001 - context may be invalid on shutdown
        return apply_interval()
    _ensure_wake_timer(wm)
    _apply_frame(wm)
    return apply_interval()


def start_timer() -> None:
    global _last_applied_generation, _last_discover_time
    if runtime._timer_running:
        return
    runtime._timer_running = True
    _last_applied_generation = store.generation()
    _last_discover_time = 0.0
    try:
        _ensure_wake_timer(bpy.context.window_manager)
    except Exception:  # noqa: BLE001 - no window yet; _apply_tick will retry
        pass
    if not bpy.app.timers.is_registered(_apply_tick):
        bpy.app.timers.register(_apply_tick, first_interval=0.0, persistent=True)


def stop_timer() -> None:
    runtime._timer_running = False
    _remove_wake_timer()
    try:
        bpy.app.timers.unregister(_apply_tick)
    except Exception:  # noqa: BLE001 - not registered
        pass
