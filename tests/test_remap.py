import unittest

from _load import load

remap = load("remap").remap


class RemapTests(unittest.TestCase):
    def test_identity_range(self):
        self.assertEqual(remap(0.5, 0.0, 1.0, 0.0, 1.0), 0.5)

    def test_scale_and_offset(self):
        self.assertEqual(remap(0.5, 0.0, 1.0, 10.0, 20.0), 15.0)

    def test_inverted_output(self):
        self.assertEqual(remap(0.0, 0.0, 1.0, 1.0, 0.0), 1.0)
        self.assertEqual(remap(1.0, 0.0, 1.0, 1.0, 0.0), 0.0)

    def test_clamp(self):
        self.assertEqual(remap(2.0, 0.0, 1.0, 0.0, 10.0, clamp=True), 10.0)
        self.assertEqual(remap(-1.0, 0.0, 1.0, 0.0, 10.0, clamp=True), 0.0)

    def test_no_clamp(self):
        self.assertEqual(remap(2.0, 0.0, 1.0, 0.0, 10.0, clamp=False), 20.0)

    def test_degenerate_input(self):
        self.assertEqual(remap(5.0, 3.0, 3.0, 7.0, 9.0), 7.0)
