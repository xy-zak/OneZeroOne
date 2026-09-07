"""Operators: connect/disconnect, address list, bind/unbind targets."""

from __future__ import annotations

import bpy

from . import apply, datapath, network_io, recording, recording_ops, runtime, serial_io
from .preferences import get_prefs, refresh_port_cache
from .properties import alloc_binding_id, alloc_entry_id
from .store import store


def _on_value(address: str, value: float) -> None:
    """Store one incoming sample. Called from the serial/network reader thread.

    Must not touch ``bpy`` except for the rare command addresses, which are
    dispatched via a one-shot main-thread timer. Live values are applied by
    the 60 fps-capped apply pump running on the main thread.
    """
    if address == "/recordframes" and value == 1.0:
        bpy.app.timers.register(recording.toggle_recording)
        return
    if address == "/renderimage" and value == 1.0:
        bpy.app.timers.register(_start_render_image)
        return
    store.update(address, value)


def _detach_render_handlers() -> None:
    for handler, coll in (
        (_render_complete_handler, bpy.app.handlers.render_complete),
        (_render_cancel_handler, bpy.app.handlers.render_cancel),
    ):
        try:
            coll.remove(handler)
        except ValueError:
            pass


def _start_render_image() -> None:
    """Stop the connection, render, then restart it."""
    apply.stop_timer()
    if runtime.connection is not None:
        runtime.connection.disconnect()
        runtime.connection = None

    _detach_render_handlers()
    bpy.app.handlers.render_complete.append(_render_complete_handler)
    bpy.app.handlers.render_cancel.append(_render_cancel_handler)
    bpy.ops.render.render("INVOKE_DEFAULT")


def _restart_after_render() -> None:
    """Reconnect after a render completes or is cancelled."""
    bpy.ops.onezeroone.connect()


def _render_complete_handler(scene):
    _detach_render_handlers()
    bpy.app.timers.register(_restart_after_render, first_interval=0.5)


def _render_cancel_handler(scene):
    _detach_render_handlers()
    bpy.app.timers.register(_restart_after_render, first_interval=0.5)


def _find_entry(wm, entry_id: int):
    """Return (index, entry) for ``entry_id``, or (-1, None)."""
    for i, entry in enumerate(wm.onezeroone_addresses):
        if entry.entry_id == entry_id:
            return i, entry
    return -1, None


def _active_entry(wm):
    """Return (index, entry) for the selected address, or (-1, None)."""
    addrs = wm.onezeroone_addresses
    if not addrs:
        return -1, None
    idx = min(max(int(wm.onezeroone_address_index), 0), len(addrs) - 1)
    return idx, addrs[idx]


def _clamp_address_index(wm, preferred: int | None = None) -> None:
    n = len(wm.onezeroone_addresses)
    if n == 0:
        wm.onezeroone_address_index = 0
        return
    idx = preferred if preferred is not None else int(wm.onezeroone_address_index)
    wm.onezeroone_address_index = min(max(idx, 0), n - 1)


class ONEZEROONE_OT_refresh_ports(bpy.types.Operator):
    """Rescan available serial ports"""

    bl_idname = "onezeroone.refresh_ports"
    bl_label = "Refresh Ports"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        refresh_port_cache()
        return {"FINISHED"}


class ONEZEROONE_OT_connect(bpy.types.Operator):
    """Start listening for OSC values on the selected serial port or network socket"""

    bl_idname = "onezeroone.connect"
    bl_label = "Connect"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        wm = get_prefs(context)
        mode = wm.onezeroone_input_mode
        runtime.clear_error()
        if runtime.connection is not None and runtime.connection.is_connected:
            self.report({"INFO"}, "Already connected")
            return {"FINISHED"}
        if mode == "network":
            ip = wm.onezeroone_net_ip or "0.0.0.0"
            port = wm.onezeroone_net_port
            conn = network_io.NetworkConnection(
                on_value=_on_value,
                on_error=runtime.set_error,
            )
            ok = conn.connect(ip, port, wm.onezeroone_framing)
            if not ok:
                self.report({"ERROR"}, f"Could not bind {ip}:{port}: {runtime.get_error()}")
                return {"CANCELLED"}
            runtime.connection = conn
            apply.sync_remap_to_store(context.window_manager)
            apply.start_timer()
            self.report({"INFO"}, f"Listening on {ip}:{port}")
            return {"FINISHED"}
        port = wm.onezeroone_port
        if not port:
            self.report({"ERROR"}, "No serial port selected")
            return {"CANCELLED"}
        conn = serial_io.SerialConnection(
            on_value=_on_value,
            on_error=runtime.set_error,
        )
        ok = conn.connect(port, wm.onezeroone_baud, wm.onezeroone_framing)
        if not ok:
            self.report({"ERROR"}, f"Could not open {port}: {runtime.get_error()}")
            return {"CANCELLED"}
        runtime.connection = conn
        apply.sync_remap_to_store(context.window_manager)
        apply.start_timer()
        self.report({"INFO"}, f"Connected to {port} @ {wm.onezeroone_baud}")
        return {"FINISHED"}


class ONEZEROONE_OT_disconnect(bpy.types.Operator):
    """Close the connection and stop listening"""

    bl_idname = "onezeroone.disconnect"
    bl_label = "Disconnect"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        apply.stop_timer()
        if recording.is_recording:
            recording.stop_recording()
        if runtime.connection is not None:
            runtime.connection.disconnect()
            runtime.connection = None
        self.report({"INFO"}, "Disconnected")
        return {"FINISHED"}


class ONEZEROONE_OT_add_address(bpy.types.Operator):
    """Add an OSC address to monitor"""

    bl_idname = "onezeroone.add_address"
    bl_label = "Add Address"
    bl_options = {"INTERNAL", "UNDO"}

    def execute(self, context):
        wm = context.window_manager
        addr = wm.onezeroone_new_address.strip()
        typed = bool(addr)
        if not addr:
            addr = "/new"
        if not addr.startswith("/"):
            addr = "/" + addr
        existing = {e.address for e in wm.onezeroone_addresses}
        if addr in existing:
            if typed:
                self.report({"INFO"}, "Address already listed")
                return {"CANCELLED"}
            n = 2
            while f"{addr}{n}" in existing:
                n += 1
            addr = f"{addr}{n}"
        entry = wm.onezeroone_addresses.add()
        entry.address = addr
        entry.entry_id = alloc_entry_id()
        wm.onezeroone_new_address = ""
        wm.onezeroone_address_index = len(wm.onezeroone_addresses) - 1
        apply.sync_remap_to_store(wm)
        return {"FINISHED"}


class ONEZEROONE_OT_remove_address(bpy.types.Operator):
    """Remove the selected OSC address"""

    bl_idname = "onezeroone.remove_address"
    bl_label = "Remove Address"
    bl_options = {"INTERNAL", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(context.window_manager.onezeroone_addresses)

    def execute(self, context):
        wm = context.window_manager
        idx, entry = _active_entry(wm)
        if idx < 0 or entry is None:
            return {"CANCELLED"}
        for binding in entry.bindings:
            store.clear_remap_for_binding(binding.binding_id)
        wm.onezeroone_addresses.remove(idx)
        _clamp_address_index(wm, idx)
        return {"FINISHED"}


class ONEZEROONE_OT_move_address(bpy.types.Operator):
    """Move the selected address up or down"""

    bl_idname = "onezeroone.move_address"
    bl_label = "Move Address"
    bl_options = {"INTERNAL", "UNDO"}

    direction: bpy.props.EnumProperty(
        items=(
            ("UP", "Up", "Move the selected address up"),
            ("DOWN", "Down", "Move the selected address down"),
        ),
        default="UP",
    )

    @classmethod
    def poll(cls, context):
        return len(context.window_manager.onezeroone_addresses) > 1

    def execute(self, context):
        wm = context.window_manager
        idx, _entry = _active_entry(wm)
        if idx < 0:
            return {"CANCELLED"}
        new = idx - 1 if self.direction == "UP" else idx + 1
        if new < 0 or new >= len(wm.onezeroone_addresses):
            return {"CANCELLED"}
        wm.onezeroone_addresses.move(idx, new)
        wm.onezeroone_address_index = new
        return {"FINISHED"}


class ONEZEROONE_OT_clear_unused_addresses(bpy.types.Operator):
    """Remove addresses that have no bindings"""

    bl_idname = "onezeroone.clear_unused_addresses"
    bl_label = "Clear Unused"
    bl_options = {"INTERNAL", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(context.window_manager.onezeroone_addresses)

    def execute(self, context):
        wm = context.window_manager
        removed = 0
        for i in range(len(wm.onezeroone_addresses) - 1, -1, -1):
            entry = wm.onezeroone_addresses[i]
            if entry.bindings:
                continue
            wm.onezeroone_addresses.remove(i)
            removed += 1
        _clamp_address_index(wm)
        self.report({"INFO"}, f"Removed {removed} unused address(es)")
        return {"FINISHED"}


class ONEZEROONE_OT_auto_discover(bpy.types.Operator):
    """Add all addresses currently seen on the wire to the list"""

    bl_idname = "onezeroone.auto_discover"
    bl_label = "Discover"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        apply.auto_discover_addresses(context.window_manager)
        apply.sync_remap_to_store(context.window_manager)
        return {"FINISHED"}


class ONEZEROONE_OT_paste_path(bpy.types.Operator):
    """Paste the clipboard into the data-path field"""

    bl_idname = "onezeroone.paste_path"
    bl_label = "Paste Path"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        clip = context.window_manager.clipboard.strip()
        if not clip:
            self.report({"WARNING"}, "Clipboard is empty")
            return {"CANCELLED"}
        context.window_manager.onezeroone_new_path = clip
        return {"FINISHED"}


class ONEZEROONE_OT_copy_path(bpy.types.Operator):
    """Copy the full data path (hover to see it)"""

    bl_idname = "onezeroone.copy_path"
    bl_label = "Copy Data Path"
    bl_options = {"INTERNAL"}

    path: bpy.props.StringProperty()

    @classmethod
    def description(cls, context, properties):
        return properties.path or "Copy full data path"

    def execute(self, context):
        context.window_manager.clipboard = self.path
        self.report({"INFO"}, self.path)
        return {"FINISHED"}


class ONEZEROONE_OT_add_target(bpy.types.Operator):
    """Bind a Blender property to the selected OSC address.

    Uses the data-path field if it is filled, otherwise the clipboard
    (right-click a property → Copy Full Data Path).
    """

    bl_idname = "onezeroone.add_target"
    bl_label = "Bind"
    bl_options = {"INTERNAL", "UNDO"}

    entry_id: bpy.props.IntProperty()

    def execute(self, context):
        wm = context.window_manager
        if self.entry_id:
            _, entry = _find_entry(wm, self.entry_id)
        else:
            _, entry = _active_entry(wm)
        if entry is None:
            self.report({"WARNING"}, "Select an address first")
            return {"CANCELLED"}
        path = wm.onezeroone_new_path.strip() or wm.clipboard.strip()
        if not path:
            self.report({"WARNING"}, "Paste a data path, or copy one first")
            return {"CANCELLED"}
        id_block, _, _ = datapath.parse_full_data_path(path)
        if id_block is None:
            self.report({"ERROR"}, "Cannot parse data path - not a valid Blender property")
            return {"CANCELLED"}
        for b in entry.bindings:
            if b.data_path == path:
                self.report({"INFO"}, "Target already bound")
                return {"CANCELLED"}
        binding = entry.bindings.add()
        binding.data_path = path
        binding.binding_id = alloc_binding_id()
        apply.sync_remap_to_store(wm)
        wm.onezeroone_new_path = ""
        short = datapath.short_data_path(path)
        self.report({"INFO"}, f"Bound {short}")
        return {"FINISHED"}


class ONEZEROONE_OT_remove_target(bpy.types.Operator):
    """Remove a target binding"""

    bl_idname = "onezeroone.remove_target"
    bl_label = "Remove Target"
    bl_options = {"INTERNAL", "UNDO"}

    entry_id: bpy.props.IntProperty()
    target_index: bpy.props.IntProperty()

    def execute(self, context):
        wm = context.window_manager
        _, entry = _find_entry(wm, self.entry_id)
        if entry is None:
            return {"CANCELLED"}
        if self.target_index < 0 or self.target_index >= len(entry.bindings):
            return {"CANCELLED"}
        binding = entry.bindings[self.target_index]
        store.clear_remap_for_binding(binding.binding_id)
        entry.bindings.remove(self.target_index)
        return {"FINISHED"}


CLASSES = (
    ONEZEROONE_OT_refresh_ports,
    ONEZEROONE_OT_connect,
    ONEZEROONE_OT_disconnect,
    ONEZEROONE_OT_add_address,
    ONEZEROONE_OT_remove_address,
    ONEZEROONE_OT_move_address,
    ONEZEROONE_OT_clear_unused_addresses,
    ONEZEROONE_OT_auto_discover,
    ONEZEROONE_OT_paste_path,
    ONEZEROONE_OT_copy_path,
    ONEZEROONE_OT_add_target,
    ONEZEROONE_OT_remove_target,
    *recording_ops.CLASSES,
)
