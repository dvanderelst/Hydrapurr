#!/usr/bin/env python3
"""First-pass placement for the carrier PCB (writes FeederController.kicad_pcb).

Moves/rotates footprints to the positions in PLACE, sets the board outline
and checks courtyard overlaps, the board edge and the keep-outs below
(the flat Pololu module, the Feather's USB-C plug). Run with --check to
only report; without it, the board file is rewritten (KiCad must be
closed). Placement is a starting point to refine by hand in KiCad.

Rotation: KiCad degrees, counter-clockwise on screen.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_schematic as g  # noqa: E402  (s-expression reader/writer)

PCB = os.path.join(os.path.dirname(HERE), 'FeederController.kicad_pcb')

X0, Y0, W, H = 100.0, 100.0, 80.0, 80.0          # board outline

# Stack: SD end on the right edge (socket overhangs for card access),
# long-header row (A0, A5, RX, TX) on top, short-header row (D12, D9, SDA/SCL, USB) below.
CX, CY = X0 + W - 25.4, 142.43

PLACE = {
    'A1': (CX, CY, 0),
    # mounting holes, 3.5 mm in from the corners
    'H1': (103.5, 103.5, 0), 'H2': (176.5, 103.5, 0),
    'H3': (103.5, 176.5, 0), 'H4': (176.5, 176.5, 0),
    # connectors on the top edge: feeder | Sharp | RFID
    'J1': (110, 103, 0), 'J3': (151, 103, 0), 'J4': (162, 103, 0),
    # --- power / feeder driver (top left) ---
    'D1': (108, 110, 0), 'C3': (122, 110, 0), 'R3': (130, 110, 0), 'LED1': (143, 110, 0),
    'Q1': (110, 118, 0), 'R4': (121, 116, 0), 'R1': (121, 120, 0), 'Q2': (136, 117, 0),
    'R2': (142, 124, 90),
    'U1': (103, 126, 90), 'F1': (112, 127.5, 0), 'C2': (122, 128, 0), 'C1': (132, 127.5, 0),
    # --- Sharp (top middle, under J3) ---
    'C4': (149, 110, 0), 'C5': (150, 116, 0), 'R6': (147, 124, 0), 'C6': (149, 128.5, 0),
    # --- RFID data / reset (top right, under J4) ---
    'Q3': (160, 110, 0), 'R10': (166, 110, 0), 'R8': (160, 115, 0), 'R9': (160, 119, 0),
    'R11': (160, 123, 0), 'R12': (160, 127, 0), 'JP1': (175, 115, 0),
    # --- touch wire: straight down from D12 ---
    'R5': (156, 155, 270), 'J2': (154, 170, 0),
    # --- contact LED below D9, I2C below SDA/SCL ---
    'R13': (163, 155, 270), 'LED2': (163, 169, 270), 'R14': (168, 155, 270), 'J5': (169, 169, 270),
    'J6': (176, 158, 270),
    # --- spare header on the left edge, RFID supply bottom left ---
    'J7': (103, 142, 0),
    'FB1': (110, 158, 0), 'C7': (112, 165, 0), 'JP2': (122, 163, 0),
    'U2': (127, 174, 0), 'C8': (110, 173, 0), 'C9': (137, 173, 0),
}

# Extra keep-outs (absolute rectangles x1, y1, x2, y2) for things without a courtyard.
def keepouts():
    ko = []
    # Pololu module lying flat next to its 3 pins (body 8.1 x 13.1 mm, pins 1.27 mm
    # from one short edge): with U1 at rot 90 the body hangs below the pin row.
    ux, uy, _ = PLACE['U1']
    ko.append(('U1 module body', ux - 1.52, uy - 1.27, ux + 6.58, uy + 11.83, {'U1'}))
    # Feather USB-C plug + cable at the stack's left end, 15-18 mm above the board:
    # nothing tall here (headers and low parts are fine).
    ko.append(('USB plug zone (no tall parts)', X0 + 8, CY - 6, CX - 25.4, CY + 6, {'A1', 'J7'}))
    return ko


TALL = {'C1', 'C2', 'C5', 'C7', 'Q1', 'U2'}


# --------------------------------------------------------------------------
def ref_of(fp):
    for p in g.find(fp, 'property'):
        if p[1] == 'Reference':
            return p[2]
    for x in g.find(fp, 'fp_text'):
        if x[1] == 'reference':
            return x[2]


def rot_pt(x, y, deg):
    """Local -> board offset for a footprint rotated deg (CCW on screen, y down)."""
    a = math.radians(deg)
    return x * math.cos(a) + y * math.sin(a), -x * math.sin(a) + y * math.cos(a)


def crt_boxes(fp):
    """Courtyard rectangles (local), one per closed shape (A1 has several)."""
    boxes = []
    lines = []
    for kind in ('fp_line', 'fp_rect', 'fp_circle', 'fp_poly'):
        for e in g.find(fp, kind):
            if g.find(e, 'layer')[0][1] != 'F.CrtYd':
                continue
            if kind == 'fp_line':
                s, t = g.find(e, 'start')[0], g.find(e, 'end')[0]
                lines.append(((float(s[1]), float(s[2])), (float(t[1]), float(t[2]))))
            elif kind == 'fp_circle':
                c = [float(v) for v in g.find(e, 'center')[0][1:3]]
                en = [float(v) for v in g.find(e, 'end')[0][1:3]]
                r = math.hypot(en[0] - c[0], en[1] - c[1])
                boxes.append([(c[0] - r, c[1] - r), (c[0] + r, c[1] + r)])
            elif kind == 'fp_rect':
                s, t = g.find(e, 'start')[0], g.find(e, 'end')[0]
                boxes.append([(float(s[1]), float(s[2])), (float(t[1]), float(t[2]))])
            else:
                pts = [(float(q[1]), float(q[2])) for q in g.find(g.find(e, 'pts')[0], 'xy')]
                boxes.append(pts)
    # group connected line segments into loops
    while lines:
        loop = [lines.pop(0)]
        changed = True
        while changed:
            changed = False
            for l in list(lines):
                pts = {p for seg in loop for p in seg}
                if l[0] in pts or l[1] in pts:
                    loop.append(l)
                    lines.remove(l)
                    changed = True
        boxes.append([p for seg in loop for p in seg])
    return boxes


def abs_boxes(fp, x, y, rot):
    out = []
    for pts in crt_boxes(fp):
        tp = [rot_pt(px, py, rot) for px, py in pts]
        xs, ys = [x + p[0] for p in tp], [y + p[1] for p in tp]
        out.append((min(xs), min(ys), max(xs), max(ys)))
    return out


def overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def main():
    check_only = '--check' in sys.argv
    tree = g.parse(open(PCB).read())[0]
    fps = {ref_of(fp): fp for fp in g.find(tree, 'footprint')}
    missing = set(fps) - set(PLACE)
    extra = set(PLACE) - set(fps)
    if missing or extra:
        raise SystemExit(f'not placed: {sorted(missing)}  unknown: {sorted(extra)}')
    boxes = {r: abs_boxes(fps[r], *PLACE[r]) for r in fps}
    problems = 0
    refs = sorted(boxes)
    for i, a in enumerate(refs):
        for b in refs[i + 1:]:
            for ba in boxes[a]:
                for bb in boxes[b]:
                    if overlap(ba, bb):
                        problems += 1
                        print(f'overlap {a} {tuple(round(v, 2) for v in ba)}  {b} {tuple(round(v, 2) for v in bb)}')
    for r, bl in boxes.items():
        for bx in bl:
            if r == 'A1' and bx[2] > X0 + W:      # SD socket overhang is intended
                bx = (bx[0], bx[1], X0 + W, bx[3])
            if bx[0] < X0 or bx[1] < Y0 or bx[2] > X0 + W or bx[3] > Y0 + H:
                problems += 1
                print(f'off board {r} {tuple(round(v, 2) for v in bx)}')
    for name, x1, y1, x2, y2, allowed in keepouts():
        for r, bl in boxes.items():
            if r in allowed or (name.startswith('USB') and r not in TALL):
                continue
            for bx in bl:
                if overlap(bx, (x1, y1, x2, y2)):
                    problems += 1
                    print(f'keep-out "{name}" hit by {r}')
    print(f'{len(fps)} footprints, {problems} problems')
    if check_only or problems:
        return problems

    # ---- write ----------------------------------------------------------
    for r, fp in fps.items():
        x, y, rot = PLACE[r]
        at = g.find(fp, 'at')[0]
        old = float(at[3]) if len(at) > 3 else 0.0
        at[1:] = [g.fmt(x), g.fmt(y)] + ([g.fmt(rot)] if rot else [])
        # pad / text angles are stored including the footprint rotation
        for kind in ('pad', 'fp_text', 'property'):
            for e in g.find(fp, kind):
                for a in g.find(e, 'at'):
                    if len(a) == 4 or (rot != old and len(a) == 3):
                        ang = (float(a[3]) if len(a) == 4 else 0.0) - old + rot
                        ang = ((ang + 180) % 360) - 180
                        a[3:] = [g.fmt(ang)] if abs(ang) > 1e-9 else []
    # board outline
    keep = []
    for e in tree[1:]:
        if isinstance(e, list) and e and e[0] in ('gr_rect', 'gr_line', 'gr_arc') and \
                g.find(e, 'layer') and g.find(e, 'layer')[0][1] == 'Edge.Cuts':
            continue
        keep.append(e)
    tree[1:] = keep
    tree.append(['gr_rect', ['start', g.fmt(X0), g.fmt(Y0)], ['end', g.fmt(X0 + W), g.fmt(Y0 + H)],
                 ['stroke', ['width', '0.1'], ['type', 'default']], ['fill', 'none'],
                 ['layer', g.Q('Edge.Cuts')], ['tstamp', g.uid()]])
    with open(PCB, 'w') as fh:
        fh.write(g.dump(tree) + '\n')
    print('wrote', PCB)
    return 0


if __name__ == '__main__':
    sys.exit(1 if main() else 0)
