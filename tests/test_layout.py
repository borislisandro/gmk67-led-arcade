import unittest

from ledarcade.layout import DOWN, GMK67, LEFT, RIGHT, UP


class LayoutTest(unittest.TestCase):
    def test_key_count(self):
        self.assertEqual(len(GMK67.keys), 67)
        self.assertEqual(len(GMK67.led_keys), 66)          # the knob has no LED
        self.assertEqual([len(r) for r in GMK67.rows], [15, 15, 14, 14, 9])

    def test_rows_are_16u_wide(self):
        for row in GMK67.rows:
            self.assertAlmostEqual(row[-1].x2, 16.0)

    def test_evdev_codes_unique(self):
        codes = [k.evdev for k in GMK67.keys if k.evdev is not None]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertEqual(GMK67.by_evdev[30].id, "A")
        self.assertEqual(GMK67.by_evdev[103].id, "UP")

    def test_matrix_positions_unique(self):
        pos = [k.matrix for k in GMK67.keys]
        self.assertEqual(len(pos), len(set(pos)))

    def test_horizontal_steps_and_wrap(self):
        self.assertEqual(GMK67.step("A", RIGHT)[0], "S")
        self.assertEqual(GMK67.step("CAPS", LEFT)[0], "PGUP")
        self.assertIsNone(GMK67.step("CAPS", LEFT, wrap=False)[0])
        # the knob has no LED, so moving right from Backspace wraps to Esc
        self.assertEqual(GMK67.step("BSPC", RIGHT)[0], "ESC")

    def test_vertical_steps(self):
        self.assertEqual(GMK67.step("B", DOWN)[0], "SPACE")
        self.assertEqual(GMK67.step("UP", DOWN)[0], "DOWN")
        self.assertEqual(GMK67.step("DOWN", UP)[0], "UP")
        self.assertEqual(GMK67.step("ESC", UP)[0], "LCTRL")     # wraps bottom

    def test_virtual_column_prevents_drift(self):
        # Going straight up from X with a remembered column stays in one column.
        k, vx = "X", None
        path = []
        for _ in range(3):
            k, vx = GMK67.step(k, UP, vx)
            path.append(k)
        self.assertEqual(path, ["D", "E", "3"])

    def test_neighbours_symmetric(self):
        for k in GMK67.led_keys:
            for n in GMK67.neighbours(k.id):
                self.assertIn(k.id, GMK67.neighbours(n), f"{k.id} <-> {n}")

    def test_neighbours_examples(self):
        self.assertEqual(sorted(GMK67.neighbours("G")), sorted(["F", "H", "T", "Y", "B", "V"]))
        self.assertIn("SPACE", GMK67.neighbours("N"))


if __name__ == "__main__":
    unittest.main()
