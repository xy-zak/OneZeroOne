"""Property groups and WindowManager registration for the address list.

Remap configuration lives per-target (per binding), not per-address, so that
two targets driven by the same OSC input can have independent output ranges.
"""

from __future__ import annotations

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import PropertyGroup

# Monotonic ID counters.  These reset when the module is reloaded, which is
# fine because WindowManager properties (and thus all entries/bindings) also
# reset on reload.
_next_entry_id: int = 0
_next_binding_id: int = 0


def alloc_entry_id() -> int:
    global _next_entry_id
    _next_entry_id += 1
    return _next_entry_id


def alloc_binding_id() -> int:
    global _next_binding_id
    _next_binding_id += 1
    return _next_binding_id


class OneZeroOneBinding(PropertyGroup):
    """A single target property that an OSC address drives.

    Each binding carries its own remap configuration so that multiple targets
    on the same input can map to different output ranges.
    """

    data_path: StringProperty(
        name="Data Path",
        description='Full data path, e.g. bpy.data.objects["Cube"].location[0]',
        default="",
    )
    binding_id: IntProperty(
        name="Binding ID",
        description="Unique stable ID used by the value store for remap lookup",
        default=0,
    )
    in_min: FloatProperty(name="In Min", default=0.0)
    in_max: FloatProperty(name="In Max", default=1.0)
    out_min: FloatProperty(name="Out Min", default=0.0)
    out_max: FloatProperty(name="Out Max", default=1.0)
    clamp: BoolProperty(
        name="Clamp",
        description="Clamp the remapped value to the output range",
        default=True,
    )
    record: BoolProperty(
        name="Record",
        description="Insert keyframes for this target while recording is active",
        default=True,
    )
    show_remap: BoolProperty(
        name="Remap",
        description="Show in/out range controls for this target",
        default=False,
    )


class OneZeroOneAddressEntry(PropertyGroup):
    """One monitored OSC address with its target bindings."""

    address: StringProperty(
        name="Address",
        description="OSC address, e.g. /inputx",
        default="",
    )
    entry_id: IntProperty(
        name="Entry ID",
        description="Unique stable ID used by operators to identify this address",
        default=0,
    )
    bindings: CollectionProperty(type=OneZeroOneBinding)


# ---------------------------------------------------------------------------
# Recording settings
# ---------------------------------------------------------------------------

_RECORD_RATE_ITEMS = [
    ("12", "12 fps", "Record at 12 frames per second"),
    ("15", "15 fps", "Record at 15 frames per second"),
    ("24", "24 fps", "Record at 24 frames per second"),
    ("30", "30 fps", "Record at 30 frames per second"),
    ("48", "48 fps", "Record at 48 frames per second"),
    ("60", "60 fps", "Record at 60 frames per second"),
]


class OneZeroOneRecordSettings(PropertyGroup):
    """Recording and post-processing options."""

    keyframe_rate: EnumProperty(
        name="Keyframe Rate",
        description="Rate at which to record keyframes",
        items=_RECORD_RATE_ITEMS,
        default="30",
    )
    auto_stop_at_end: BoolProperty(
        name="Auto-Stop at End Frame",
        description="Automatically stop recording when reaching the end of the frame range",
        default=True,
    )
    remove_jitter: BoolProperty(
        name="Remove Rogue Keyframes",
        description="Remove keyframes that appear to be jitter outliers after recording",
        default=False,
    )
    jitter_threshold: FloatProperty(
        name="Jitter Threshold",
        description="How much a keyframe must deviate to be considered jitter (smaller = more aggressive)",
        default=0.05,
        min=0.001,
        max=0.5,
        precision=3,
    )
    interpolate_keyframes: BoolProperty(
        name="Interpolate Missing Frames",
        description="Fill in missing frames using bezier interpolation after recording",
        default=False,
    )
    interpolation_gap_threshold: IntProperty(
        name="Max Frame Gap",
        description="Maximum gap between frames to interpolate (in frames)",
        default=5,
        min=2,
        max=20,
    )
    post_smooth_keyframes: BoolProperty(
        name="Apply Gaussian Smoothing",
        description="Apply smoothing to keyframes after recording stops",
        default=False,
    )
    post_smooth_factor: FloatProperty(
        name="Smoothing Factor",
        description="Strength of the post-recording smoothing (1.0 = standard)",
        default=1.0,
        min=0.1,
        max=5.0,
        precision=1,
    )


# ---------------------------------------------------------------------------
# Debug settings
# ---------------------------------------------------------------------------


class OneZeroOneDebugSettings(PropertyGroup):
    """Debug panel options."""

    show_all_values: BoolProperty(
        name="Show All OSC Values",
        description="Dump every listed address and its remapped outputs",
        default=False,
    )


def register() -> None:
    bpy.utils.register_class(OneZeroOneBinding)
    bpy.utils.register_class(OneZeroOneAddressEntry)
    bpy.utils.register_class(OneZeroOneRecordSettings)
    bpy.utils.register_class(OneZeroOneDebugSettings)
    bpy.types.WindowManager.onezeroone_addresses = CollectionProperty(
        type=OneZeroOneAddressEntry
    )
    bpy.types.WindowManager.onezeroone_new_address = StringProperty(
        name="Address",
        description="OSC address to add, e.g. /inputx",
        default="",
    )
    bpy.types.WindowManager.onezeroone_address_index = IntProperty(
        name="Active Address",
        description="Selected OSC address in the list",
        default=0,
        min=0,
    )
    bpy.types.WindowManager.onezeroone_new_path = StringProperty(
        name="Data Path",
        description="Full data path to bind (or leave empty to use the clipboard)",
        default="",
    )
    bpy.types.WindowManager.onezeroone_record_settings = PointerProperty(
        type=OneZeroOneRecordSettings
    )
    bpy.types.WindowManager.onezeroone_debug_settings = PointerProperty(
        type=OneZeroOneDebugSettings
    )


def unregister() -> None:
    del bpy.types.WindowManager.onezeroone_addresses
    del bpy.types.WindowManager.onezeroone_new_address
    del bpy.types.WindowManager.onezeroone_address_index
    del bpy.types.WindowManager.onezeroone_new_path
    del bpy.types.WindowManager.onezeroone_record_settings
    del bpy.types.WindowManager.onezeroone_debug_settings
    bpy.utils.unregister_class(OneZeroOneDebugSettings)
    bpy.utils.unregister_class(OneZeroOneRecordSettings)
    bpy.utils.unregister_class(OneZeroOneAddressEntry)
    bpy.utils.unregister_class(OneZeroOneBinding)
