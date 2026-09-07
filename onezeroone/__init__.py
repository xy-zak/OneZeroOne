"""OneZeroOne: OSC-over-serial/network input remapper for Blender 5+.

Listens to OSC-style values from a USB microcontroller (ESP32, Arduino, Pi
Pico, ...) or network (UDP), remaps them per-target to arbitrary ranges, and
applies them to Blender properties live via direct RNA mutation.

Extension metadata lives in ``blender_manifest.toml``.
"""

from __future__ import annotations

import bpy

from . import operators, preferences, properties, runtime, ui
from . import debug_ui, recording_ui


_CLASSES = (
    *operators.CLASSES,
    *ui.CLASSES,
    *debug_ui.CLASSES,
    *recording_ui.CLASSES,
)


def register() -> None:
    # Unregister any classes left over from a failed previous registration.
    for cls in reversed(_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:  # noqa: BLE001 - not registered, fine
            pass
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    preferences.register()
    properties.register()


def unregister() -> None:
    # Stop recording, the timer, and the connection before tearing down.
    from . import apply, recording

    recording.shutdown()
    apply.stop_timer()
    if runtime.connection is not None:
        runtime.connection.disconnect()
        runtime.connection = None
    properties.unregister()
    preferences.unregister()
    for cls in reversed(_CLASSES):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:  # noqa: BLE001 - already unregistered
            pass


if __name__ == "__main__":
    register()
