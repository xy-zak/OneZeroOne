"""OSC recording: keyframe insertion for bound properties.

The apply pump calls :func:`tick_recording` at the session update rate.
Keyframes are inserted for every binding with ``record=True``, throttled to
the configured keyframe rate (cannot exceed the session update rate).  The
timeline plays during recording so ``frame_current`` advances; recording
auto-stops at ``frame_end`` when ``auto_stop_at_end`` is set.

Properties are mutated directly (not via drivers), so keyframes capture the
current value set by the live apply pump.  Disconnect before playing back a
recorded take to stop live updates from overriding the animation.
"""

from __future__ import annotations

import time

import bpy

from . import datapath

is_recording: bool = False
_last_keyframe_time: float = 0.0


def _record_settings():
    return bpy.context.window_manager.onezeroone_record_settings


def insert_keyframes() -> None:
    """Insert keyframes at the current frame for every record-enabled binding."""
    wm = bpy.context.window_manager
    frame = bpy.context.scene.frame_current
    for entry in wm.onezeroone_addresses:
        if not entry.address:
            continue
        for binding in entry.bindings:
            if not binding.record or not binding.data_path:
                continue
            id_block, data_path, index = datapath.parse_full_data_path(binding.data_path)
            if id_block is None:
                continue
            try:
                if index is not None:
                    id_block.keyframe_insert(data_path, index=index, frame=frame)
                else:
                    id_block.keyframe_insert(data_path, frame=frame)
            except Exception:  # noqa: BLE001 - skip un-keyframable properties
                pass


def tick_recording() -> None:
    """Insert a keyframe sample if recording is active and the rate elapsed.

    Called from the apply pump on the main thread.  No-op when not recording.
    """
    global _last_keyframe_time
    if not is_recording:
        return

    settings = _record_settings()
    if settings.auto_stop_at_end:
        if bpy.context.scene.frame_current >= bpy.context.scene.frame_end:
            bpy.app.timers.register(stop_recording)
            return

    try:
        fps = int(settings.keyframe_rate)
    except (TypeError, ValueError):
        fps = 30
    fps = max(1, fps)
    now = time.monotonic()
    if _last_keyframe_time == 0.0 or (now - _last_keyframe_time) >= (1.0 / fps):
        insert_keyframes()
        _last_keyframe_time = now


def start_recording() -> None:
    """Start recording: play the timeline. Keyframes come from the apply pump."""
    global is_recording, _last_keyframe_time
    if is_recording:
        return
    is_recording = True
    _last_keyframe_time = 0.0

    if not bpy.context.screen.is_animation_playing:
        try:
            bpy.ops.screen.animation_play()
        except Exception:  # noqa: BLE001 - context may not allow it
            pass


def stop_recording() -> None:
    """Stop recording: stop playback, run post-processing."""
    global is_recording, _last_keyframe_time
    is_recording = False
    _last_keyframe_time = 0.0

    if bpy.context.screen.is_animation_playing:
        try:
            bpy.ops.screen.animation_play()
        except Exception:  # noqa: BLE001
            pass

    settings = _record_settings()
    try:
        if settings.remove_jitter:
            bpy.ops.onezeroone.remove_jitter()
    except Exception:  # noqa: BLE001
        pass
    try:
        if settings.interpolate_keyframes:
            bpy.ops.onezeroone.interpolate_keyframes()
    except Exception:  # noqa: BLE001
        pass
    try:
        if settings.post_smooth_keyframes:
            bpy.ops.onezeroone.smooth_keyframes()
    except Exception:  # noqa: BLE001
        pass


def toggle_recording() -> None:
    """Toggle recording state (used by the /recordframes OSC command)."""
    if is_recording:
        stop_recording()
    else:
        start_recording()


def shutdown() -> None:
    """Stop recording if active (called on extension unregister)."""
    if is_recording:
        stop_recording()
