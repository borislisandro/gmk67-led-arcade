# Feasibility report: games on the GMK67's RGB lighting

This is the log of the investigation done on a real **Zuoya GMK67 V2** (ANSI,
tri-mode, plugged in over USB) on 2026-11-01, plus the conclusions that shaped
the code in this repository. Every number below was measured on the actual board.

## 1. What the keyboard exposes

`lsusb` identifies it as `36b0:3068 RDMCTMZT ZUOYA GMK67 V2` (bcdDevice 0.02).
The 2.4 GHz dongle is `36b0:3002`. Over USB the board has three HID interfaces:

| Interface | Report descriptor | Purpose |
|---|---|---|
| if00 | Usage page 0x01 / usage 0x06, 8-byte boot report | Keyboard (6KRO) |
| **if01** | **Usage page 0xFF60 / usage 0x61, 32-byte in/out** | **VIA raw HID** |
| if02 | Mouse, system control, consumer, NKRO keyboard (report ids 2/3/4/6) | Extras |

The 0xFF60/0x61 pair is the signature of QMK's raw HID as used by VIA. The
dongle exposes the same VIA interface, so lighting control also works wirelessly.

## 2. Firmware identity

Read-only VIA queries:

| Query | Result |
|---|---|
| `id_get_protocol_version` (0x01) | **12** (current VIA protocol) |
| `id_dynamic_keymap_get_layer_count` (0x11) | 4 layers, 6x16 matrix |
| Macro buffer size (0x0D) | 322 bytes |
| Custom channel 3 (RGB Matrix) | brightness 255, effect 1 (solid), speed 127, hue 0, sat 0 |
| Custom channels 0-2, 4-255 | `0xFF` (unhandled) |

The keymap read back over VIA uses the **modern QMK keycode numbering**
(`0x7C16` = `QK_GESC` on Esc, `0x5222` = `MO(2)` on Fn, `0xA8` = mute on the
knob). The lighting menu lists the 45 standard QMK RGB Matrix effects in QMK
order. Conclusion: **this is a closed-source, QMK-derived vendor firmware.**
The vendor has not published its source, and the wireless stack is proprietary.

Note that the *original* GMK67 (USB `05ac:024f`) is a completely different
firmware (8051/Sinowealth-class MCU, a proprietary 64-byte feature-report protocol
with a per-key "Direct" mode). Community tools like
[OpenRGB's EK68 work](https://github.com/jezzaw007/QMK_EK68_openrgb),
[clackd](https://github.com/niltonperimneto/clackd) and
[GMK67-Configurator](https://github.com/arsenii754/GMK67-Configurator) target
that V1 protocol. None of them work on the V2.

## 3. Can a host set individual key colours?

**Not with the documented protocol.** VIA's lighting API is global by design.
You can set the effect, brightness, speed and one HSV colour for the whole
board, and nothing per key. Snake needs to say "key G is green, key P is red",
which the stock VIA protocol cannot express.

What I checked:

1. **Every custom-value channel and value id** (`0x08 ch v` for all 256x256): only
   channel 3, values 1-4 respond. There is no hidden per-key value.
2. **Known third-party per-key protocols**: Vial (`0xFE`) and SignalRGB's QMK
   protocol (`0x21`-`0x28`) both answer "unhandled".
3. **Every undocumented top-level command id** `0x16`-`0xFD` (after backing up
   keymap and macros): all answer `0xFF` (unhandled), **except `0xBB`, which never
   replies at all**. That suggests it is consumed by a vendor handler. Sweeping
   all 256 sub-commands of `0xBB` caused no reply, no disconnect and no change
   to keymap or lighting values.
4. **Hidden lighting effect**: the firmware accepts effect id **46**, one past
   the 45 listed in its VIA definition (writes of 47-255 are clamped to 46). In
   QMK-derived firmwares the slot after the stock effects is where vendors put
   their own modes, typically a "custom per-key" or "direct/streaming" mode.

Items 3 and 4 are promising, but they can only be confirmed by watching the
LEDs. `tools/gmk67.py probe` is an interactive test that does exactly that (it
asks you yes/no questions and bisects to the responsible packet).

## 4. Is it fast enough?

The transport is not the bottleneck:

| Measurement (USB, Linux hidraw) | Value |
|---|---|
| Global colour changes per second (with reply) | **~470/s** |
| Round-trip latency | median **2.0 ms**, p95 3.0 ms |

A per-key frame for 66 LEDs in 32-byte reports needs about 8 reports if 9 LEDs
fit per report, which works out to roughly **60 full frames per second**. Snake
moves 3-7 times a second, and the fastest game here needs about 20 visible
changes per second, so even a protocol 5x slower than this would look smooth.
The real limit is whether the firmware has a per-key command. If one exists, the
games will look good.

## 5. Options

| Path | Per-key? | Effort / risk | Status |
|---|---|---|---|
| **A. Stock firmware, VIA global colour** | No (whole board, one colour) | None | **Implemented**: `gmk67-ambient` backend flashes and tints the board with the game |
| **B. Hidden vendor per-key mode** (`0xBB` / effect 46) | Maybe | Low; needs a human to watch LEDs | **Probe tool ready**: `tools/gmk67.py probe` |
| **C. OpenRGB** | Yes | None, *if* the keyboard is supported in Direct mode | **Implemented**: `openrgb` backend (any supported keyboard) |
| **D. Custom QMK firmware on the GMK67** | Yes, natively | High: MCU unknown (needs opening the case); loses 2.4G/Bluetooth; brick risk | Not attempted |
| **E. Games inside the firmware** | Yes | Requires D | Not attempted |

Recommended order: run the probe (B). If it finds a per-key packet, a
`gmk67-direct` backend is a small addition (about 60 lines next to
`via_ambient.py`). If it finds nothing, the stock GMK67 stays a global-colour
"mood light", and per-key play runs on the simulator or an OpenRGB-supported board.

## 6. Safety notes

* All lighting writes are RAM-only. `custom_save` (0x09) is never sent, and the
  original lighting values are restored on exit, including on Ctrl+C.
* `tools/gmk67.py backup` / `restore` snapshot keymap, macros and lighting.
* The probe never sends `0x06` (keymap reset), `0x0A` (EEPROM reset), `0x0B`
  (bootloader jump) or `0x10` (macro reset).
