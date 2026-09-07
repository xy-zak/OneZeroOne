# OneZeroOne — developer notes

Package root: `onezeroone/`. Blender 5 extension metadata is in `blender_manifest.toml`. Wheels (pyserial, python-osc) live in `onezeroone/wheels/`.

## Package map

| Module | Role |
|---|---|
| `serial_io.py` / `network_io.py` | Reader threads. Shared `decode_datagram` for text / SLIP / newline. Never touch `bpy`. |
| `store.py` | Thread-safe latest value per address + per-binding remap. |
| `apply.py` | Main-thread pump: remap → RNA, auto-discover, recording tick, GHOST wake timer. |
| `datapath.py` | Parse “Copy Full Data Path”; `short_data_path` for UI labels; `set_property_value` mutates RNA. |
| `operators.py` | Connect/disconnect, addresses, targets, OSC command dispatch. |
| `recording.py` | Recording flag, keyframe insert, post-process kickoff. |
| `runtime.py` | `Connection` protocol, current connection, last error, timer flags. |
| `ui.py` / `recording_ui.py` / `debug_ui.py` | N-panel. Addresses use a `template_list`; selected address’s bindings draw below. |
| `remap.py` | Linear range map. |

## Thread rules

- Serial and UDP handlers run off the main thread.
- They may only: parse, `store.update`, and for `/recordframes` and `/renderimage` schedule `bpy.app.timers.register(...)` (Blender documents that as thread-safe).
- All RNA writes, UI, recording, and `event_timer_add` happen on the main thread via the apply pump.

```
device → serial_io / network_io → ValueStore.update
                                      ↓
Blender main loop ← GHOST WM timer + bpy.app.timers
                                      ↓
                              apply.py apply_values
                                      ↓
                         datapath.set_property_value
                                      ↓
                         recording.tick_recording (if on)
```

## Apply pump

`bpy.app.timers` alone often sleeps at ~5 Hz when the UI is idle (especially Wayland). `WindowManager.event_timer_add` is a GHOST timer and wakes the loop. `apply.py` installs both: the WM timer for wake, the app timer for the callback.

Rate is `onezeroone_update_rate`, capped at 60 Hz. A store **generation** counter detects new packets even when two updates share a monotonic timestamp. Apply writes **all** bindings when generation advanced (latest sample wins). Recording ticks every pump tick and throttles to `keyframe_rate`.

## Store

- One raw float per OSC address; remap is keyed by `binding_id`.
- Address dict is capped at 256; oldest-by-timestamp is evicted on overflow.
- Serial/newline byte buffers and in-progress SLIP packets are capped at 64 KiB.

## Adding a transport

Implement `runtime.Connection`: `is_connected`, `label`, `disconnect()`, plus your `connect(...)`. Construct with `on_value=operators._on_value` and `on_error=runtime.set_error`. Assign to `runtime.connection` and call `apply.start_timer()`. Mirror `SerialConnection` / `NetworkConnection`.

## Adding an OSC command

In `operators._on_value`, handle the address **before** `store.update`. Schedule main-thread work with `bpy.app.timers.register`. Do not call operators or RNA directly from the reader thread.

## Tests

Parser, remap, store, and data-path split tests do not import Blender. From the repo root:

```
python -m unittest discover -s tests -v
```

`tests/_load.py` loads `onezeroone/*.py` without running package `__init__.py` (which imports `bpy`).

## Reload / unload

`unregister()` stops recording, stops the apply pump, and disconnects. Reloading the extension in one Blender session can leave a WM event timer if unload failed; Disconnect first, then disable the add-on.

## Out of scope for small PRs

Recording post-process (jitter / interpolate / smooth) is a product feature. Prefer fixing the live path over rewriting that pipeline.
