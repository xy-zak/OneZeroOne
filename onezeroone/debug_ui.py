"""Debug panel: last received, recording status, all-values dump."""

from __future__ import annotations

import bpy

from . import recording
from .store import store


class ONEZEROONE_PT_debug(bpy.types.Panel):
    bl_label = "Debug"
    bl_idname = "ONEZEROONE_PT_debug"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "OneZeroOne"
    bl_order = 20
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        debug = context.window_manager.onezeroone_debug_settings

        box = layout.box()
        col = box.column()

        addr, val = store.last_received()
        col.label(text="Last OSC Address:")
        col.label(text=addr or "None")
        col.separator()
        col.label(text="Last OSC Value:")
        col.label(text=f"{val:.4f}" if addr else "None")

        col.separator()
        if recording.is_recording:
            col.label(text="Recording Status: Active", icon="REC")
        else:
            col.label(text="Recording Status: Inactive", icon="SNAP_FACE")

        col.separator()
        col.prop(debug, "show_all_values")
        if debug.show_all_values:
            col.separator()
            col.label(text="All OSC Values:")
            addresses = store.addresses()
            if not addresses:
                col.label(text="No values received yet")
            else:
                wm = context.window_manager
                for entry in wm.onezeroone_addresses:
                    if not entry.address or entry.address not in addresses:
                        continue
                    raw = store.get_raw(entry.address)
                    vbox = col.box()
                    vbox.label(text=f"Address: {entry.address}")
                    vbox.label(text=f"Raw Value: {raw:.4f}")
                    for binding in entry.bindings:
                        remapped = store.get_remapped_for_binding(binding.binding_id)
                        vbox.label(text=f"  out: {remapped:.4f}")


CLASSES = (ONEZEROONE_PT_debug,)
