import unittest

from _load import load

split = load("datapath").split_full_data_path


class DatapathSplitTests(unittest.TestCase):
    def test_location_zero_is_index_zero(self):
        self.assertEqual(
            split('bpy.data.objects["Cube"].location[0]'),
            ("objects", "Cube", "location", 0),
        )

    def test_location_two(self):
        self.assertEqual(
            split('bpy.data.objects["Cube"].location[2]'),
            ("objects", "Cube", "location", 2),
        )

    def test_scalar_has_no_index(self):
        self.assertEqual(
            split('bpy.data.objects["Cube"].hide_viewport'),
            ("objects", "Cube", "hide_viewport", None),
        )

    def test_custom_prop(self):
        self.assertEqual(
            split('bpy.data.objects["Cube"]["my_prop"]'),
            ("objects", "Cube", '["my_prop"]', None),
        )

    def test_pose_bone(self):
        self.assertEqual(
            split('bpy.data.objects["Arm"].pose.bones["Bone"].location[2]'),
            ("objects", "Arm", 'pose.bones["Bone"].location', 2),
        )

    def test_invalid(self):
        self.assertIsNone(split("not a path"))
        self.assertIsNone(split("Cube.location[0]"))


class ShortDataPathTests(unittest.TestCase):
    def test_location(self):
        short = load("datapath").short_data_path
        self.assertEqual(
            short('bpy.data.objects["Cube"].location[0]'),
            "Cube.location[0]",
        )

    def test_custom_prop(self):
        short = load("datapath").short_data_path
        self.assertEqual(
            short('bpy.data.objects["Cube"]["my_prop"]'),
            'Cube["my_prop"]',
        )

    def test_pose_bone(self):
        short = load("datapath").short_data_path
        self.assertEqual(
            short('bpy.data.objects["Arm"].pose.bones["Bone"].location[2]'),
            'Arm.pose.bones["Bone"].location[2]',
        )

    def test_unparsed_is_truncated(self):
        short = load("datapath").short_data_path
        long_path = "x" * 50
        self.assertEqual(short(long_path), "…" + long_path[-41:])
        self.assertEqual(short("short"), "short")
