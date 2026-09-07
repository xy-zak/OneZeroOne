import struct
import unittest

from _load import load

serial_io = load("serial_io")
parse = serial_io._parse_text_line
decode = serial_io._decode_osc
slip_feed = serial_io._slip_feed
append_capped = serial_io._append_capped
END = serial_io._SLIP_END
ESC = serial_io._SLIP_ESC
ESC_END = serial_io._SLIP_ESC_END
ESC_ESC = serial_io._SLIP_ESC_ESC


def _pad4(data: bytes) -> bytes:
    data += b"\x00"
    while len(data) % 4:
        data += b"\x00"
    return data


def _osc_float(address: str, value: float) -> bytes:
    return _pad4(address.encode("ascii")) + _pad4(b",f") + struct.pack(">f", value)


class SerialParseTests(unittest.TestCase):
    def test_parse_text_line(self):
        self.assertEqual(parse("/inputx 0.5"), ("/inputx", 0.5))
        self.assertEqual(parse("  /a -1.25\n"), ("/a", -1.25))
        self.assertIsNone(parse("nope"))
        self.assertIsNone(parse("/only"))
        self.assertIsNone(parse(""))

    def test_decode_osc_float32(self):
        packet = _osc_float("/foo", 1.5)
        got = decode(packet)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0][0], "/foo")
        self.assertAlmostEqual(got[0][1], 1.5, places=5)

    def test_slip_end_and_esc_end(self):
        payload = bytes([END, 0x01])
        data = bytes([ESC, ESC_END, 0x01, END])
        completed, rest, escaped = slip_feed(data, bytearray(), False)
        self.assertFalse(escaped)
        self.assertEqual(rest, bytearray())
        self.assertEqual(completed, [payload])

    def test_slip_literal_0xff_is_data(self):
        data = bytes([0xFF, 0x02, END])
        completed, rest, escaped = slip_feed(data, bytearray(), False)
        self.assertFalse(escaped)
        self.assertEqual(completed, [bytes([0xFF, 0x02])])
        self.assertEqual(rest, bytearray())

    def test_slip_esc_esc(self):
        data = bytes([ESC, ESC_ESC, END])
        completed, _, _ = slip_feed(data, bytearray(), False)
        self.assertEqual(completed, [bytes([ESC])])

    def test_append_capped_drops_oldest(self):
        buf = bytearray(b"abcdef")
        append_capped(buf, b"ghij", cap=8)
        self.assertEqual(buf, bytearray(b"cdefghij"))
        self.assertEqual(len(buf), 8)

    def test_decode_datagram_text(self):
        decode_datagram = serial_io.decode_datagram
        self.assertEqual(
            decode_datagram(b"/x 1.5\n/y 2\n", "text"),
            [("/x", 1.5), ("/y", 2.0)],
        )

    def test_decode_datagram_slip_raw_osc(self):
        decode_datagram = serial_io.decode_datagram
        packet = _osc_float("/foo", 1.5)
        got = decode_datagram(packet, "slip")
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0][0], "/foo")
        self.assertAlmostEqual(got[0][1], 1.5, places=5)

    def test_decode_datagram_slip_framed(self):
        decode_datagram = serial_io.decode_datagram
        inner = _osc_float("/bar", 3.0)
        framed = bytes([END]) + inner + bytes([END])
        got = decode_datagram(framed, "slip")
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0][0], "/bar")
        self.assertAlmostEqual(got[0][1], 3.0, places=5)
