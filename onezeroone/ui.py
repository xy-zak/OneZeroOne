"""N-sidebar panel: transport, session, and a template_list of OSC addresses.

The selected address shows its bindings below the list. Bindings use a short
path label (full path on hover), a Record checkbox, and optional remap rows.
"""

from __future__ import annotations

import bpy

from . import datapath, runtime
from .preferences import get_prefs
from .store import store


def _active_entry(wm):
    """Return (index, entry) for the selected address, or (-1, None)."""
    addrs = wm.onezeroone_addresses
    if not addrs:
        return -1, None
    idx = min(max(int(wm.onezeroone_address_index), 0), len(addrs) - 1)
    return idx, addrs[idx]


def _draw_factor_bar(layout, t: float) -> None:
    """Tiny filled bar for how far the raw value sits in the input range."""
    t = min(1.0, max(0.0, t))
    row = layout.row(align=True)
    row.scale_y = 0.4
    split = row.split(factor=max(0.02, t), align=True)
    filled = split.row()
    filled.alert = True
    filled.label(text="")
    split.label(text="")


def _draw_binding(layout, entry, index: int, binding) -> None:
    box = layout.box()
    short = datapath.short_data_path(binding.data_path)

    header = box.row(align=True)
    path_op = header.operator("onezeroone.copy_path", text=short, icon="DRIVER", emboss=False)
    path_op.path = binding.data_path
    header.prop(binding, "record", text="Rec")
    icon = "TRIA_DOWN" if binding.show_remap else "TRIA_RIGHT"
    header.prop(binding, "show_remap", text="", icon=icon, emboss=False)
    rem = header.row(align=True)
    rem.alert = True
    op = rem.operator("onezeroone.remove_target", text="", icon="X")
    op.entry_id = entry.entry_id
    op.target_index = index

    raw = store.get_raw(entry.address)
    remapped = store.get_remapped_for_binding(binding.binding_id)
    live = box.row(align=True)
    live.label(text=f"raw {raw:.3f}")
    live.label(text=f"out {remapped:.3f}")
    span = binding.in_max - binding.in_min
    t = 0.0 if abs(span) < 1e-12 else (raw - binding.in_min) / span
    _draw_factor_bar(box, t)

    if not binding.show_remap:
        return
    row = box.row(align=True)
    row.prop(binding, "in_min", text="In Min")
    row.label(text="\u2192")
    row.prop(binding, "out_min", text="Out Min")
    row = box.row(align=True)
    row.prop(binding, "in_max", text="In Max")
    row.label(text="\u2192")
    row.prop(binding, "out_max", text="Out Max")
    box.prop(binding, "clamp", text="Clamp")


class ONEZEROONE_UL_addresses(bpy.types.UIList):
    """Address list: editable OSC path, live raw value, binding count."""

    bl_idname = "ONEZEROONE_UL_addresses"

    def draw_item(
        self,
        context,
        layout,
        data,
        item,
        icon,
        active_data,
        active_property,
        index,
        flt_flag,
    ):
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            layout.prop(item, "address", text="", emboss=False)
            layout.label(text=f"{store.get_raw(item.address):.2f}")
            n = len(item.bindings)
            layout.label(text=str(n) if n else "")
        elif self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=item.address)


class ONEZEROONE_PT_main(bpy.types.Panel):
    bl_label = "OneZeroOne"
    bl_idname = "ONEZEROONE_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "OneZeroOne"
    bl_order = 0

    def draw(self, context):
        layout = self.layout
        wm = get_prefs(context)
        connected = runtime.connection is not None and runtime.connection.is_connected

        box = layout.box()
        box.label(text="Input", icon="PLUGIN")
        col = box.column()
        col.enabled = not connected
        col.prop(wm, "onezeroone_input_mode")
        if wm.onezeroone_input_mode == "network":
            col.prop(wm, "onezeroone_net_ip")
            col.prop(wm, "onezeroone_net_port")
        else:
            row = col.row(align=True)
            row.prop(wm, "onezeroone_port", text="")
            row.operator("onezeroone.refresh_ports", text="", icon="FILE_REFRESH")
            col.prop(wm, "onezeroone_baud")

        box = layout.box()
        box.label(text="Session", icon="PLAY")
        frame_row = box.row()
        frame_row.enabled = not connected
        frame_row.prop(wm, "onezeroone_framing")
        box.prop(wm, "onezeroone_update_rate")
        err = runtime.get_error()
        if err:
            box.label(text=err, icon="ERROR")
        if connected:
            box.label(text=f"Connected: {runtime.connection.label}", icon="CHECKMARK")
            dis = box.row()
            dis.alert = True
            dis.operator("onezeroone.disconnect", text="Disconnect", icon="X")
        else:
            box.operator("onezeroone.connect", text="Connect", icon="PLAY")

        box = layout.box()
        n_addrs = len(wm.onezeroone_addresses)
        box.label(text=f"Addresses : {n_addrs}", icon="DRIVER")
        row = box.row(align=True)
        row.prop(wm, "onezeroone_new_address", text="", placeholder="/inputx")
        row.operator("onezeroone.add_address", text="", icon="ADD")
        if connected:
            row.operator("onezeroone.auto_discover", text="Discover", icon="VIEWZOOM")

        list_row = box.row()
        list_row.template_list(
            "ONEZEROONE_UL_addresses",
            "",
            wm,
            "onezeroone_addresses",
            wm,
            "onezeroone_address_index",
            rows=4,
        )
        buttons = list_row.column(align=True)
        buttons.operator("onezeroone.add_address", text="", icon="ADD")
        buttons.operator("onezeroone.remove_address", text="", icon="REMOVE")
        buttons.separator()
        up = buttons.operator("onezeroone.move_address", text="", icon="TRIA_UP")
        up.direction = "UP"
        down = buttons.operator("onezeroone.move_address", text="", icon="TRIA_DOWN")
        down.direction = "DOWN"
        buttons.separator()
        buttons.operator("onezeroone.clear_unused_addresses", text="", icon="TRASH")

        if not wm.onezeroone_addresses:
            box.label(text="No addresses yet", icon="INFO")
            return

        _idx, entry = _active_entry(wm)
        if entry is None:
            return

        raw = store.get_raw(entry.address)
        sel = box.column(align=True)
        sel.label(text=f"{entry.address}   raw {raw:.3f}")

        if entry.bindings:
            for j, binding in enumerate(entry.bindings):
                _draw_binding(sel, entry, j, binding)
        else:
            sel.label(text="No bindings", icon="INFO")

        path_row = sel.row(align=True)
        path_row.prop(wm, "onezeroone_new_path", text="", placeholder="Full data path")
        path_row.operator("onezeroone.paste_path", text="", icon="PASTEDOWN")
        bind = path_row.operator("onezeroone.add_target", text="Bind", icon="DRIVER")
        bind.entry_id = entry.entry_id


CLASSES = (
    ONEZEROONE_UL_addresses,
    ONEZEROONE_PT_main,
)
