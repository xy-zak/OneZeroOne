# OneZeroOne

OSC-over-serial and UDP input remapper for **Blender 5.0+**. Values from a USB microcontroller (ESP32, Arduino, Pico, …) or a network OSC sender are remapped per target and written live to Blender properties.

## Install

1. Copy the `onezeroone` folder into Blender’s extensions directory, or install it as a local extension from Blender’s **Get Extensions / Install from Disk** flow (folder must contain `blender_manifest.toml` and the wheels).
2. Enable **OneZeroOne**. pyserial and python-osc are bundled as wheels in `onezeroone/wheels/` — no extra pip step.
3. Open a 3D Viewport, press `N`, and use the **OneZeroOne** tab.

Minimum Blender version: 5.0.

## Connect

The **Input** box is serial or UDP. While connected, that box is locked — disconnect before switching transport.

**Serial**

- Pick a port (starred entries are likely microcontrollers). Refresh if you just plugged in.
- Baud: **115200** is the default and is what you want for ~60 fps text OSC. 9600 cannot carry that rate.

**Network**

- Bind IP (`0.0.0.0` = all interfaces) and UDP port (default `9001`).

**Session** (both transports)

- **Message Type** — how packets are encoded (serial and UDP):
  - **Text** — `/address value` lines
  - **SLIP / binary OSC** — SLIP-framed OSC on serial; on UDP, SLIP or a raw binary OSC datagram
  - **Newline (ASCII OSC)** — newline-delimited ASCII OSC packets
- **Update Rate** — how often bound properties are written, 1–60 Hz. Incoming data faster than this keeps the latest sample; slower data only writes when a new sample arrives.
- **Connect** / **Disconnect**

## Bind a property

1. In Blender, right-click a property → **Copy Full Data Path** (e.g. `bpy.data.objects["Cube"].location[0]`).
2. Add the OSC address (`/inputx`) or click **Discover** while connected. Rename it in the list; use the arrows to reorder; trash unused (no bindings) addresses. `/recordframes` and `/renderimage` are never auto-discovered.
3. Select the address, paste the path into the field (or leave it empty to use the clipboard), then **Bind**. The status bar reports the bound path.
4. Open the binding’s remap triangle to set **In Min / In Max** to the range your device sends, and **Out Min / Out Max** to the Blender range you want. Clamp is on by default. **Rec** on the binding row chooses whether that target is keyed while recording.

Several targets can share one address with independent output ranges. Hover a binding name for the full data path (click to copy it).

## Recording

The **Recording** panel is its own section in the tab (not mixed with addresses).

- Start/Stop, or send OSC `/recordframes 1` to toggle.
- Keyframe rate cannot exceed the session **Update Rate**.
- Playback runs while recording; optional auto-stop at the scene end frame.
- Per-target **Rec** on each binding row chooses what gets keyed.
- After stop, optional jitter removal, interpolation, and smoothing.

Disconnect before playing a take back, or live updates will override the animation.

## OSC commands

| Address | Value | Effect |
|---|---|---|
| `/recordframes` | `1` | Toggle recording |
| `/renderimage` | `1` | Disconnect, render, reconnect |

## Debug

The **Debug** panel (own section) shows the last received address/value and an optional dump of all current values. Opening the panel is enough — there is no extra visibility toggle.

## Motion stuck around 5 fps?

- Baud is 115200 (or high enough for your packet size × 60).
- Framing matches what the device actually sends.
- You are **Connected** (Session box).
- Update Rate is 60.
- The bound data path is a live RNA property (location, custom prop, etc.), not a driver you expected to evaluate every frame — this add-on writes properties directly.

## More

Developers: see [docs/DEVELOPER.md](docs/DEVELOPER.md).
