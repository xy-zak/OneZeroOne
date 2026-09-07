import unittest

from _load import load

store_mod = load("store")
ValueStore = store_mod.ValueStore
_MAX = store_mod._MAX_ADDRESSES


class StoreTests(unittest.TestCase):
    def test_generation_increments(self):
        s = ValueStore()
        self.assertEqual(s.generation(), 0)
        s.update("/x", 1.0)
        s.update("/y", 2.0)
        self.assertEqual(s.generation(), 2)
        self.assertEqual(s.get_raw("/x"), 1.0)
        self.assertEqual(s.last_received(), ("/y", 2.0))

    def test_remap_per_binding(self):
        s = ValueStore()
        s.update("/in", 0.5)
        s.set_remap_for_binding(1, "/in", 0.0, 1.0, 0.0, 10.0, True)
        s.set_remap_for_binding(2, "/in", 0.0, 1.0, 100.0, 200.0, True)
        self.assertEqual(s.get_remapped_for_binding(1), 5.0)
        self.assertEqual(s.get_remapped_for_binding(2), 150.0)
        s.clear_remap_for_binding(1)
        self.assertEqual(s.get_remapped_for_binding(1), 0.0)

    def test_address_cap_evicts_oldest(self):
        s = ValueStore()
        for i in range(_MAX + 5):
            s.update(f"/a{i}", float(i))
        addrs = s.addresses()
        self.assertEqual(len(addrs), _MAX)
        self.assertNotIn("/a0", addrs)
        self.assertIn(f"/a{_MAX + 4}", addrs)
