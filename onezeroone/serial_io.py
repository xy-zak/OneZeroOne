"""Serial port discovery, connection, and framed reading.

The reader runs in a background ``threading.Thread`` and never touches ``bpy``.
Parsed ``(address, value)`` pairs are pushed to a callback (the ValueStore).

Framing modes:
  - "text":  newline-delimited ``<address> <value>`` lines (the ESP32 default)
  - "slip":  SLIP-framed OSC packets (RFC 1055), decoded as OSC messages
  - "newline": newline-delimited ASCII OSC packets (``#address,f value``)
"""

from __future__ import annotations

import struct
import threading
from typing import Callable, Optional

# pyserial is bundled as a wheel and listed in blender_manifest.toml.
import serial
import serial.tools.list_ports

# VID/PID pairs and description keywords for common microcontroller USB-UART
# bridges. Used only to flag "likely microcontroller" in the port list; all
# ports are still shown so the user can pick manually.
_MICROCONTROLLER_VIDS = {
    0x10C4,  # Silicon Labs CP210x
    0x1A86,  # QinHeng CH340/CH341
    0x0403,  # FTDI FT232
    0x2E8A,  # Raspberry Pi Pico
    0x239A,  # Adafruit
    0x2341,  # Arduino
    0x2A03,  # Arduino LLC
    0x0483,  # STMicroelectronics (STM32 CDC)
}
_MICROCONTROLLER_KEYWORDS = (
    "arduino",
    "esp32",
    "esp8266",
    "pico",
    "stm32",
    "ch340",
    "ch341",
    "cp210",
    "ft232",
    "pro micro",
    "teensy",
)

# SLIP control bytes.
_SLIP_END = 0xC0
_SLIP_ESC = 0xDB
_SLIP_ESC_END = 0xDC
_SLIP_ESC_ESC = 0xDD

# pyserial's read(n) waits until *n* bytes arrive or ``timeout`` expires,
# whichever comes first. A 200 ms timeout with read(256) therefore batches
# ~20-byte OSC lines into ~5 Hz chunks. 1 ms is well under a 60 fps frame
# and lets us drain whatever has arrived without spinning a core.
_READ_TIMEOUT = 0.001
# Drop oldest bytes if a device stops sending frame delimiters.
_BUF_CAP = 64 * 1024


def _read_available(ser: serial.Serial) -> bytes:
    """Return every buffered byte, waiting at most ``ser.timeout`` for the first.

    Draining ``in_waiting`` after a 1-byte wait means a complete packet is
    returned as soon as the UART has it, instead of stalling for a large
    ``read(n)`` to fill.
    """
    waiting = ser.in_waiting
    if waiting:
        return ser.read(waiting)
    first = ser.read(1)
    if not first:
        return b""
    waiting = ser.in_waiting
    if waiting:
        return first + ser.read(waiting)
    return first


def list_ports() -> list[dict]:
    """Return serial ports with metadata. ``is_microcontroller`` is a hint."""
    ports = []
    for p in serial.tools.list_ports.comports():
        # Skip non-physical / legacy ttyS* ports that pyserial reports as "n/a".
        if (p.vid is None) and ((p.hwid or "") in ("n/a", p.device)):
            continue
        vid = p.vid or 0
        pid = p.pid or 0
        desc = (p.description or "").lower()
        prod = (p.product or "").lower()
        is_mcu = (
            vid in _MICROCONTROLLER_VIDS
            or any(k in desc for k in _MICROCONTROLLER_KEYWORDS)
            or any(k in prod for k in _MICROCONTROLLER_KEYWORDS)
        )
        ports.append(
            {
                "device": p.device,
                "description": p.description or p.device,
                "vid": vid,
                "pid": pid,
                "manufacturer": p.manufacturer or "",
                "product": p.product or "",
                "is_microcontroller": is_mcu,
            }
        )
    # Microcontrollers first, then by device name.
    ports.sort(key=lambda d: (not d["is_microcontroller"], d["device"]))
    return ports


def _parse_text_line(line: str) -> Optional[tuple[str, float]]:
    """Parse ``<address> <value>`` from one text line. Returns None if invalid."""
    line = line.strip()
    if not line or not line.startswith("/"):
        return None
    # Split on first whitespace.
    parts = line.split(None, 1)
    if len(parts) != 2:
        return None
    address, raw = parts[0], parts[1].strip()
    try:
        value = float(raw)
    except ValueError:
        return None
    return address, value


def _decode_osc(packet: bytes) -> list[tuple[str, float]]:
    """Decode a single OSC packet bytes into a list of (address, first-float-arg).

    Minimal OSC 1.0 decoder: address pattern (null-padded) + type-tag string
    starting with ',' + arguments. Only int32, int64, float32, double, and
    string args are understood; the first numeric arg is used as the value.
    """
    results = []
    if not packet or packet[0:1] != b"/":
        return results
    try:
        # Address: null-terminated, 4-byte aligned.
        nul = packet.index(b"\x00")
        address = packet[:nul].decode("ascii", "replace")
        i = nul + 1
        while i % 4 != 0:
            if i >= len(packet) or packet[i] != 0:
                break
            i += 1
        i += 0
        # Type tag string starts with ','.
        if i >= len(packet) or packet[i:i + 1] != b",":
            return results
        tag_start = i
        tag_nul = packet.index(b"\x00", tag_start)
        tags = packet[tag_start + 1:tag_nul].decode("ascii", "replace")
        i = tag_nul + 1
        while i % 4 != 0:
            i += 1
        # Parse args.
        value = None
        for t in tags:
            if t == "i":  # int32
                value = int.from_bytes(packet[i:i + 4], "big", signed=True)
                i += 4
            elif t == "f":  # float32
                value = struct.unpack(">f", packet[i:i + 4])[0]
                i += 4
            elif t == "h":  # int64
                value = int.from_bytes(packet[i:i + 8], "big", signed=True)
                i += 8
            elif t == "d":  # float64
                value = struct.unpack(">d", packet[i:i + 8])[0]
                i += 8
            elif t == "s":  # string
                snul = packet.index(b"\x00", i)
                i = snul + 1
                while i % 4 != 0:
                    i += 1
            elif t == "T":
                value = 1.0
            elif t == "F":
                value = 0.0
            else:
                # Skip unsupported (b, m, r, c, N, I, t, [...]).
                break
            if i > len(packet):
                return results
        if value is not None:
            results.append((address, float(value)))
    except (ValueError, IndexError, struct.error):
        pass
    return results


def _append_capped(buf: bytearray, chunk: bytes, cap: int = _BUF_CAP) -> None:
    """Extend ``buf`` and drop the oldest bytes if it exceeds ``cap``."""
    buf.extend(chunk)
    overflow = len(buf) - cap
    if overflow > 0:
        del buf[:overflow]


def _slip_feed(
    data: bytes,
    packet: bytearray,
    escaped: bool,
    cap: int = _BUF_CAP,
) -> tuple[list[bytes], bytearray, bool]:
    """Consume SLIP bytes. Returns (completed packets, remainder, escaped flag).

    A dedicated ``escaped`` flag is used instead of stuffing 0xFF into the
    packet, so a literal 0xFF data byte is not mistaken for an escape marker.
    """
    completed: list[bytes] = []
    for b in data:
        if escaped:
            escaped = False
            if b == _SLIP_ESC_END:
                packet.append(_SLIP_END)
            elif b == _SLIP_ESC_ESC:
                packet.append(_SLIP_ESC)
            else:
                packet.append(b)
            if len(packet) > cap:
                packet.clear()
            continue
        if b == _SLIP_END:
            if packet:
                completed.append(bytes(packet))
                packet.clear()
        elif b == _SLIP_ESC:
            escaped = True
        else:
            packet.append(b)
            if len(packet) > cap:
                packet.clear()
    return completed, packet, escaped


def decode_datagram(data: bytes, framing: str) -> list[tuple[str, float]]:
    """Decode one already-framed blob (a UDP datagram, or a complete serial packet).

    ``framing`` is ``text``, ``slip``, or ``newline``.  On UDP, SLIP END bytes
    are optional: a datagram that is already a binary OSC packet is decoded
    directly (UDP supplies the frame that SLIP would provide on serial).
    """
    if not data:
        return []
    if framing == "text":
        results: list[tuple[str, float]] = []
        for line in data.decode("ascii", "replace").splitlines():
            parsed = _parse_text_line(line)
            if parsed is not None:
                results.append(parsed)
        return results
    if framing == "newline":
        results = []
        for line in data.split(b"\n"):
            line = line.strip(b"\r")
            if line:
                results.extend(_decode_osc(bytes(line)))
        return results
    # slip — UDP datagrams that start with END are SLIP-wrapped; otherwise
    # the datagram is a raw OSC packet (0xC0 may appear inside float bytes).
    if data[:1] == bytes((_SLIP_END,)):
        completed, remainder, _ = _slip_feed(data, bytearray(), False)
        out: list[tuple[str, float]] = []
        for pkt in completed:
            out.extend(_decode_osc(pkt))
        if remainder:
            out.extend(_decode_osc(bytes(remainder)))
        return out
    return _decode_osc(data)


class SerialConnection:
    """Owns a serial port and a background reader thread."""

    def __init__(
        self,
        on_value: Callable[[str, float], None],
        on_error: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._on_value = on_value
        self._on_error = on_error
        self._serial: Optional[serial.Serial] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._port = ""
        self._baud = 115200
        self._framing = "text"

    @property
    def is_connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    @property
    def port(self) -> str:
        return self._port

    @property
    def label(self) -> str:
        """Endpoint label for the UI (matches NetworkConnection.label)."""
        return self._port

    @property
    def baud(self) -> int:
        return self._baud

    @property
    def framing(self) -> str:
        return self._framing

    def connect(self, port: str, baud: int = 115200, framing: str = "text") -> bool:
        if self.is_connected:
            self.disconnect()
        try:
            self._serial = serial.Serial(port, baud, timeout=_READ_TIMEOUT)
        except Exception as exc:  # noqa: BLE001 - surface any serial error
            self._serial = None
            if self._on_error:
                self._on_error(str(exc))
            return False
        self._port = port
        self._baud = baud
        self._framing = framing
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="onezeroone-serial", daemon=True
        )
        self._thread.start()
        return True

    def disconnect(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:  # noqa: BLE001
                pass
            self._serial = None

    # -- reader loop --------------------------------------------------------

    def _run(self) -> None:
        assert self._serial is not None
        if self._framing == "text":
            self._run_text()
        elif self._framing == "slip":
            self._run_slip()
        elif self._framing == "newline":
            self._run_newline_osc()
        else:
            self._run_text()

    def _run_text(self) -> None:
        """Read lines and parse ``<address> <value>``."""
        buf = bytearray()
        while not self._stop.is_set():
            try:
                chunk = _read_available(self._serial)
            except Exception as exc:  # noqa: BLE001
                if not self._stop.is_set() and self._on_error:
                    self._on_error(str(exc))
                break
            if not chunk:
                continue
            _append_capped(buf, chunk)
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                parsed = _parse_text_line(line.decode("ascii", "replace"))
                if parsed is not None:
                    self._on_value(parsed[0], parsed[1])

    def _run_slip(self) -> None:
        """Read SLIP-framed OSC packets."""
        packet = bytearray()
        escaped = False
        while not self._stop.is_set():
            try:
                chunk = _read_available(self._serial)
            except Exception as exc:  # noqa: BLE001
                if not self._stop.is_set() and self._on_error:
                    self._on_error(str(exc))
                break
            if not chunk:
                continue
            completed, packet, escaped = _slip_feed(chunk, packet, escaped)
            for raw in completed:
                for addr, val in _decode_osc(raw):
                    self._on_value(addr, val)

    def _run_newline_osc(self) -> None:
        """Read newline-delimited ASCII OSC packets."""
        buf = bytearray()
        while not self._stop.is_set():
            try:
                chunk = _read_available(self._serial)
            except Exception as exc:  # noqa: BLE001
                if not self._stop.is_set() and self._on_error:
                    self._on_error(str(exc))
                break
            if not chunk:
                continue
            _append_capped(buf, chunk)
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                for addr, val in _decode_osc(bytes(line)):
                    self._on_value(addr, val)
