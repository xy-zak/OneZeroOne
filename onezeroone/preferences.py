"""Connection settings stored on the WindowManager.

Blender 5.2 extensions don't populate ``context.preferences.addons``, so
AddonPreferences is not accessible. We register port/baud/framing as
WindowManager properties instead — the same mechanism used for the address
list.
"""

from __future__ import annotations

import time

import bpy
from bpy.props import EnumProperty, IntProperty, StringProperty

from . import serial_io

FRAMING_ITEMS = [
    (
        "text",
        "Text  (/addr value)",
        "Newline-delimited '/address value' lines (ESP32 default). On UDP, one datagram may contain several lines.",
    ),
    (
        "slip",
        "SLIP / binary OSC",
        "SLIP-framed OSC on serial. On UDP, SLIP or a raw binary OSC datagram (UDP already frames packets).",
    ),
    (
        "newline",
        "Newline (ASCII OSC)",
        "Newline-delimited ASCII OSC packets",
    ),
]

INPUT_MODE_ITEMS = [
    ("serial", "Serial (USB)", "Listen on a USB serial port"),
    ("network", "Network (UDP)", "Listen for OSC over UDP (Wi-Fi / Ethernet)"),
]

# Port-list cache so the UI dropdown doesn't rescan USB on every redraw.
_port_cache: list[dict] = []
_port_cache_ts: float = 0.0


def _port_items(self, context):
    global _port_cache, _port_cache_ts
    now = time.monotonic()
    if not _port_cache or (now - _port_cache_ts) > 2.0:
        _port_cache = serial_io.list_ports()
        _port_cache_ts = now
    items = []
    for p in _port_cache:
        label = p["description"]
        if p["is_microcontroller"]:
            label = "* " + label
        items.append((p["device"], label, p["device"]))
    if not items:
        items.append(("", "No serial ports found", ""))
    return items


def refresh_port_cache() -> None:
    global _port_cache, _port_cache_ts
    _port_cache = serial_io.list_ports()
    _port_cache_ts = time.monotonic()


def register() -> None:
    bpy.types.WindowManager.onezeroone_input_mode = EnumProperty(
        name="Input Mode",
        description="Transport for incoming OSC values",
        items=INPUT_MODE_ITEMS,
        default="serial",
    )
    bpy.types.WindowManager.onezeroone_port = EnumProperty(
        name="Port",
        description="Serial port to connect to",
        items=_port_items,
    )
    bpy.types.WindowManager.onezeroone_baud = IntProperty(
        name="Baud Rate",
        description="Serial baud rate (115200 is required for ~60 fps text OSC)",
        default=115200,
        min=1,
    )
    bpy.types.WindowManager.onezeroone_framing = EnumProperty(
        name="Message Type",
        description="How incoming messages are encoded (serial and UDP)",
        items=FRAMING_ITEMS,
        default="text",
    )
    bpy.types.WindowManager.onezeroone_net_ip = StringProperty(
        name="IP Address",
        description="IP address to bind the OSC UDP server to (0.0.0.0 = all interfaces)",
        default="0.0.0.0",
    )
    bpy.types.WindowManager.onezeroone_net_port = IntProperty(
        name="Port",
        description="UDP port to listen for OSC messages",
        default=9001,
        min=1024,
        max=65535,
    )
    bpy.types.WindowManager.onezeroone_update_rate = IntProperty(
        name="Update Rate",
        description=(
            "How many times per second bound properties are written. "
            "Tracks the incoming stream and is capped at 60 fps"
        ),
        default=60,
        min=1,
        max=60,
    )


def unregister() -> None:
    del bpy.types.WindowManager.onezeroone_input_mode
    del bpy.types.WindowManager.onezeroone_port
    del bpy.types.WindowManager.onezeroone_baud
    del bpy.types.WindowManager.onezeroone_framing
    del bpy.types.WindowManager.onezeroone_net_ip
    del bpy.types.WindowManager.onezeroone_net_port
    del bpy.types.WindowManager.onezeroone_update_rate


def get_prefs(context):
    """Return the WindowManager, which holds the connection settings."""
    return context.window_manager
