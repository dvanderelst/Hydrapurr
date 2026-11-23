#!/usr/bin/env python3
"""Footprint for the Feather + Adalogger stack on the carrier PCB.

Stack, top to bottom:
  - Feather ESP32-S3 Reverse TFT, screen up (its components face down);
  - Adalogger FeatherWing, upside down (coin cell and SD socket face down),
    the Feather plugged into its Feather header rows;
  - this PCB, taking pins from the Adalogger's *secondary* rows (the extra
    row of holes next to each Feather header).

Seen from above, the Adalogger is mirrored, so this footprint is the
mirror image of a normal FeatherWing. Pad numbers are the Feather pin
numbers (1-16 long header from RESET, 17-28 short header from SDA), the
same numbering as KiCad's Adafruit_Feather symbol/footprint, so the
schematic symbol does not change.

Hole positions are from Adafruit's own board file
(github.com/adafruit/Adafruit-Adalogger-FeatherWing-PCB, "adalogger
featherwing.brd", Eagle top view, mm, origin at the board corner):
  JP2, 16 holes at y = 3.30, x = 6.35 + 2.54*(n-1): next to Feather pin n
  JP1, 11 holes at y = 19.56: EN, USB, D13, D12, D11, D10, D9, D6, D5, SCL, SDA
      at x = 19.05 ... 44.45 (next to Feather pins 27 ... 17)
  JP3, VBAT (pin 28) at (19.05, 17.40): moved inwards for the coin cell
  Secondary rows are 2.03 mm (0.08") inside the header rows, not 2.54 mm.
  Mounting holes at (2.54|48.26, 2.54|20.32). Coin cell holder B1 spans
  about x 2.4-17.9, y 4.8-20.7; microSD socket X4 about x 33.7-54.2,
  y 4.3-18.5 (card enters at the x = 50.8 end).
Mirroring (viewing the upside-down board from above) is the same as using
the Eagle y values directly as KiCad y (which points down).

Usage: python3 tools/gen_stack_footprint.py   -> HydraPurr.pretty/Feather_Adalogger_Inverted_Stack.kicad_mod
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(os.path.dirname(HERE), 'HydraPurr.pretty')
NAME = 'Feather_Adalogger_Inverted_Stack'
CX, CY = 25.4, 11.43            # Adalogger centre (Eagle coordinates)

LONG = ['RESET', '3V3', 'NC', 'GND', 'A0', 'A1', 'A2', 'A3', 'A4', 'A5',
        'SCK', 'MOSI', 'MISO', 'RX', 'TX', 'NC']
SHORT = {17: 'SDA', 18: 'SCL', 19: 'D5', 20: 'D6', 21: 'D9', 22: 'D10', 23: 'D11',
         24: 'D12', 25: 'D13', 26: 'USB', 27: 'EN'}


def pads():
    out = []
    for n in range(1, 17):
        out.append((str(n), 6.35 + 2.54 * (n - 1), 3.30, LONG[n - 1]))
    for i, pin in enumerate(range(27, 16, -1)):        # EN ... SDA, left to right
        out.append((str(pin), 19.05 + 2.54 * i, 19.56, SHORT[pin]))
    out.append(('28', 19.05, 17.40, 'VBAT'))
    return out


def f(v):
    return ('%.3f' % v).rstrip('0').rstrip('.')


def xy(x, y):
    return f'{f(x - CX)} {f(y - CY)}'


def line(x1, y1, x2, y2, layer, w=0.12, dash=False):
    t = 'dash' if dash else 'solid'
    return (f'  (fp_line (start {xy(x1, y1)}) (end {xy(x2, y2)}) '
            f'(stroke (width {w}) (type {t})) (layer "{layer}"))')


def rect(x1, y1, x2, y2, layer, w=0.12, dash=False):
    return '\n'.join([line(x1, y1, x2, y1, layer, w, dash), line(x2, y1, x2, y2, layer, w, dash),
                      line(x2, y2, x1, y2, layer, w, dash), line(x1, y2, x1, y1, layer, w, dash)])


def text(s, x, y, layer, size=1.0, angle=0):
    th = round(size * 0.15, 3)
    return (f'  (fp_text user "{s}" (at {xy(x, y)} {angle}) (layer "{layer}") '
            f'(effects (font (size {size} {size}) (thickness {th}))))')


def build():
    L = [f'(footprint "{NAME}" (version 20221018) (generator gen_stack_footprint) (layer "F.Cu")',
         '  (descr "Feather ESP32-S3 Reverse TFT (screen up) on an upside-down Adalogger FeatherWing; '
         'pins from the Adalogger secondary rows. Mirrored FeatherWing pattern. Hole positions from '
         'Adafruit Adalogger FeatherWing board file.")',
         '  (tags "Adafruit Feather Adalogger FeatherWing stack inverted secondary row")',
         '  (attr through_hole)',
         f'  (fp_text reference "REF**" (at {xy(25.4, -1.6)}) (layer "F.SilkS") '
         '(effects (font (size 1 1) (thickness 0.15))))',
         f'  (fp_text value "{NAME}" (at {xy(25.4, 24.5)}) (layer "F.Fab") '
         '(effects (font (size 1 1) (thickness 0.15))))']
    # board outline (Feather and Adalogger share it): full on Fab, corner marks on silk
    L.append(rect(0, 0, 50.8, 22.86, 'F.Fab', 0.1))
    # (0.5 mm inside the outline: the SD end sits on the carrier's board edge)
    for cx, cy, dx, dy in ((0.5, 0.5, 1, 1), (50.3, 0.5, -1, 1), (0.5, 22.36, 1, -1), (50.3, 22.36, -1, -1)):
        L.append(line(cx, cy, cx + 3 * dx, cy, 'F.SilkS'))
        L.append(line(cx, cy, cx, cy + 3 * dy, 'F.SilkS'))
    # Courtyard only where something occupies the space between the Adalogger
    # and this board: the two socket rows (+VBAT), the coin cell holder and
    # the microSD socket (which sticks out 3.4 mm past the end). Low parts
    # (resistors, small ceramics, TO-92) may go under the rest of the logger;
    # with 8.5 mm sockets there are ~8 mm of clearance.
    L.append(rect(4.85, 1.8, 45.95, 4.8, 'F.CrtYd', 0.05))          # 16-pin socket
    poly = [(18.0, 16.4), (20.1, 16.4), (20.1, 18.06), (45.95, 18.06), (45.95, 21.06), (18.0, 21.06)]
    pts = ' '.join(f'(xy {xy(x, y)})' for x, y in poly)
    L.append(f'  (fp_poly (pts {pts}) (stroke (width 0.05) (type solid)) (fill none) (layer "F.CrtYd"))')
    L.append(rect(2.4, 4.85, 17.9, 20.7, 'F.CrtYd', 0.05))          # coin cell holder
    L.append(rect(33.7, 4.85, 54.2, 18.0, 'F.CrtYd', 0.05))         # microSD socket
    # parts on the Adalogger's underside, facing this board: keep tall parts away
    L.append(rect(2.4, 4.8, 17.9, 20.7, 'F.Fab', 0.1, dash=True))
    L.append(text('coin cell (faces down)', 10.15, 12.75, 'F.Fab', 0.8))
    L.append(rect(33.7, 4.3, 54.2, 18.5, 'F.Fab', 0.1, dash=True))
    L.append(text('microSD (faces down)', 43.9, 11.4, 'F.Fab', 0.8))
    # silkscreen part of the SD outline stops 0.5 mm inside the board edge
    L.append(line(50.3, 4.3, 33.7, 4.3, 'F.SilkS', 0.12, dash=True))
    L.append(line(33.7, 4.3, 33.7, 18.5, 'F.SilkS', 0.12, dash=True))
    L.append(line(33.7, 18.5, 50.3, 18.5, 'F.SilkS', 0.12, dash=True))
    L.append(text('SD card ->', 44.0, 16.6, 'F.SilkS', 1.0))
    L.append(text('USB', 1.9, 11.43, 'F.SilkS', 1.0, 90))
    L.append(text('Feather screen up / Adalogger upside down', 25.4, 25.9, 'F.Fab', 0.8))
    # pads
    for num, x, y, sig in pads():
        shape = 'rect' if num == '1' else 'circle'
        L.append(f'  (pad "{num}" thru_hole {shape} (at {xy(x, y)}) (size 1.7 1.7) (drill 1) '
                 '(layers "*.Cu" "*.Mask"))')
        ty = y + 1.9 if y < 11 else y - 1.9
        L.append(text(sig, x, ty, 'F.Fab', 0.6, 90))
    # pin 1 marker
    L.append(line(4.9, 1.6, 4.9, 5.0, 'F.SilkS'))
    # Feather / Adalogger mounting holes (M2.5)
    for hx in (2.54, 48.26):
        for hy in (2.54, 20.32):
            L.append(f'  (pad "" np_thru_hole circle (at {xy(hx, hy)}) (size 2.7 2.7) (drill 2.7) '
                     '(layers "*.Cu" "*.Mask"))')
    L.append(')')
    return '\n'.join(L) + '\n'


if __name__ == '__main__':
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, NAME + '.kicad_mod')
    with open(path, 'w') as fh:
        fh.write(build())
    print('wrote', path)
