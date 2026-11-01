import random
import unittest

from ledarcade.backends.openrgb import led_name_to_key, parse_controller
from ledarcade.backends.terminal import TerminalBackend
from ledarcade.backends.via_ambient import mood
from ledarcade.engine import playable_keys
from ledarcade.games import GAMES
from ledarcade.games.lightsout import LightsOut
from ledarcade.games.minesweeper import Minesweeper
from ledarcade.games.snake import Snake
from ledarcade.input import KeyEvent, decode_terminal_bytes
from ledarcade.layout import GMK67

ALL = {k.id for k in GMK67.keys if k.evdev is not None}


def make(cls, seed=1):
    g = cls(GMK67, random.Random(seed), ALL)
    g.reset(0.0)
    return g


def tap(g, key, t, hold=0.05, shifted=False):
    g.on_key(KeyEvent(key, True, shifted), t)
    g.on_key(KeyEvent(key, False, shifted), t + hold)


class SnakeTest(unittest.TestCase):
    def test_moves_right_and_eats(self):
        s = make(Snake)
        s.apple, s.golden = "H", False
        s.update(s.next_step)
        self.assertEqual(s.body, ["H", "G", "F", "D"])
        self.assertEqual(s.score, 1)
        self.assertEqual(s.drain_events(), ["eat"])

    def test_cannot_reverse(self):
        s = make(Snake)
        s.on_key(KeyEvent("LEFT", True), 0)
        self.assertEqual(s.queue, [])

    def test_self_collision_kills(self):
        s = make(Snake)
        s.body = ["G", "F", "R", "T", "Y", "H"]
        s.direction = "up"
        s.apple = "Z"
        s.step(1.0)                            # G -> T is body
        self.assertTrue(s.over)
        self.assertFalse(s.won)

    def test_moving_into_tail_is_allowed(self):
        s = make(Snake)
        s.body = ["G", "T", "Y", "H"]
        s.direction = "right"
        s.apple = "Z"
        s.step(1.0)                            # tail H moves away as head enters it
        self.assertFalse(s.over)

    def test_render_has_head_and_apple(self):
        s = make(Snake)
        f = s.render(0.0)
        self.assertIn(s.body[0], f)
        self.assertIn(s.apple, f)


class MinesweeperTest(unittest.TestCase):
    def test_first_dig_is_safe_and_floods(self):
        m = make(Minesweeper)
        tap(m, "G", 1.0)
        self.assertFalse(m.over)
        self.assertNotIn("G", m.mine_set)
        self.assertEqual(m.counts["G"], 0)    # neighbours are excluded too -> zero
        self.assertGreater(len(m.revealed), 1)

    def test_long_press_flags(self):
        m = make(Minesweeper)
        tap(m, "Q", 1.0, hold=0.5)
        self.assertIn("Q", m.flags)
        tap(m, "Q", 2.0, shifted=True)        # terminal-style flag toggle
        self.assertNotIn("Q", m.flags)

    def test_win_and_lose(self):
        m = make(Minesweeper)
        tap(m, "G", 1.0)
        safe = [k for k in m.board if k not in m.mine_set]
        for i, k in enumerate(safe):
            tap(m, k, 2.0 + i)
        self.assertTrue(m.over and m.won)
        m2 = make(Minesweeper)
        tap(m2, "G", 1.0)
        tap(m2, next(iter(m2.mine_set)), 2.0)
        self.assertTrue(m2.over and not m2.won)


class LightsOutTest(unittest.TestCase):
    def test_flip_is_involution_and_solvable(self):
        g = make(LightsOut, seed=3)
        before = set(g.lit)
        g.flip("G")
        g.flip("G")
        self.assertEqual(g.lit, before)

    def test_replaying_scramble_solves(self):
        rng = random.Random(5)
        g = LightsOut(GMK67, rng, ALL)
        g.reset(0.0)
        # brute-force check: the puzzle is the XOR of some presses, solve by Gaussian elimination
        cells = g.board
        idx = {k: i for i, k in enumerate(cells)}
        rows = []
        for k in cells:                        # equation per cell: sum of presses touching it
            mask = 0
            for p in cells:
                if k == p or k in g.adj[p]:
                    mask |= 1 << idx[p]
            rows.append([mask, 1 if k in g.lit else 0])
        r = 0
        for c in range(len(cells)):
            piv = next((i for i in range(r, len(rows)) if rows[i][0] >> c & 1), None)
            if piv is None:
                continue
            rows[r], rows[piv] = rows[piv], rows[r]
            for i in range(len(rows)):
                if i != r and rows[i][0] >> c & 1:
                    rows[i][0] ^= rows[r][0]
                    rows[i][1] ^= rows[r][1]
            r += 1
        self.assertTrue(all(m or not b for m, b in rows), "puzzle is unsolvable")


class AllGamesSmokeTest(unittest.TestCase):
    def test_every_game_runs_a_minute_of_random_input(self):
        keys = sorted(ALL)
        for name, cls in GAMES.items():
            with self.subTest(game=name):
                rng = random.Random(9)
                g = make(cls)
                t = 0.0
                for _ in range(3600):
                    t += 1 / 60
                    if rng.random() < 0.1:
                        k = rng.choice(keys)
                        g.on_key(KeyEvent(k, True), t)
                        g.on_key(KeyEvent(k, False), t + 0.02)
                    if not g.over:
                        g.update(t)
                    frame = g.render(t)
                    for k, c in frame.items():
                        self.assertIn(k, GMK67)
                        self.assertTrue(all(0 <= ch <= 255 for ch in c), (k, c))
                    g.status()
                    if g.over:
                        g = make(cls)


class IoTest(unittest.TestCase):
    def test_terminal_decoding(self):
        evs = decode_terminal_bytes(b"\x1b[Aa Q\x1b", GMK67)
        pressed = [(e.key, e.shifted) for e in evs if e.pressed]
        self.assertEqual(pressed, [("UP", False), ("A", False), ("SPACE", False), ("Q", True),
                                   ("ESC", False)])

    def test_playable_without_evdev_excludes_modifiers(self):
        p = playable_keys(GMK67, None)
        self.assertIn("A", p)
        self.assertNotIn("LSHIFT", p)

    def test_terminal_render_shape(self):
        class FakeTerm:
            def write(self, s):
                pass
        lines = TerminalBackend(GMK67, FakeTerm()).render_lines({"A": (255, 0, 0)})
        self.assertEqual(len(lines), 15)
        self.assertIn("48;2;255;0;0", lines[6])            # row 2 (A) label line

    def test_mood(self):
        self.assertEqual(mood({}), (0, 0, 0))
        r, g, b = mood({"A": (0, 255, 0), "B": (0, 200, 0)})
        self.assertGreater(g, r)

    def test_openrgb_names(self):
        self.assertEqual(led_name_to_key("Key: Left Shift", GMK67), "LSHIFT")
        self.assertEqual(led_name_to_key("Key: A", GMK67), "A")
        self.assertEqual(led_name_to_key("Key: \\ (ANSI)", GMK67), "BSLS")
        self.assertIsNone(led_name_to_key("Key: F1", GMK67))

    def test_openrgb_parse(self):
        import struct

        def s(x):
            b = x.encode() + b"\0"
            return struct.pack("<H", len(b)) + b
        body = struct.pack("<i", 5) + s("Test KB") + s("d") + s("v") + s("s") + s("l")
        body += struct.pack("<Hi", 1, 0) + s("Direct") + struct.pack("<iIIIIIIII", 0, 0, 0, 0, 0, 0, 0, 0, 0)
        body += struct.pack("<H", 0)
        body += struct.pack("<H", 1) + s("Keys") + struct.pack("<iIII", 0, 2, 2, 2)
        body += struct.pack("<H", 12) + struct.pack("<III", 1, 1, 0)
        body += struct.pack("<H", 2) + s("Key: A") + struct.pack("<I", 0) + s("Key: Escape") + struct.pack("<I", 1)
        body += struct.pack("<H", 2) + bytes(8)
        dev = parse_controller(struct.pack("<I", len(body) + 4) + body)
        self.assertEqual(dev["name"], "Test KB")
        self.assertEqual(dev["leds"], ["Key: A", "Key: Escape"])


if __name__ == "__main__":
    unittest.main()
