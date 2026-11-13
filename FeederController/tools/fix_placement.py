#!/usr/bin/env python3
"""Targeted placement fixes on the hand-arranged board (KiCad must be closed).

Unlike place_parts.py (the first pass), this keeps every footprint where it
is except the ones in MOVE, optionally swaps footprints (SWAP: new library
footprint, nets kept per pad number, schematic Footprint field updated too),
and then runs the same checks: courtyard overlaps, board edge, keep-outs.
--check only reports.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_schematic as g   # noqa: E402
import place_parts as pp    # noqa: E402

PROJ = os.path.dirname(HERE)
PCB = pp.PCB
SCH = os.path.join(PROJ, 'FeederController.kicad_sch')
KIFP = '/usr/share/kicad/footprints'
BOARD = (100.0, 100.0, 180.0, 160.0)          # x1, y1, x2, y2 (user's 80 x 60 mm outline)

VERT_R = 'Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P2.54mm_Vertical'
SWAP = {'R5': VERT_R, 'R13': VERT_R, 'R14': VERT_R}

MOVE = {
    'H3': (108.5, 156.5, 0),
    'C1': (129.5, 123, 0),          # clear of R2
    'C7': (120.5, 130.7, 0),        # out of the USB plug zone
    'U2': (118, 151, 0),            # TO-220 out of the USB plug zone
    # strip below the stack: R13 LED2 R14 J5 | R5 J2 (R5 right under D12)
    'R13': (126, 156.4, 0), 'LED2': (132, 156.3, 0), 'R14': (138.5, 156.4, 0),
    'J5': (145, 156, 0),
    'R5': (155.9, 156.4, 0), 'J2': (162.5, 156, 0),
}

TALL = pp.TALL


def keepouts(pos):
    ux, uy, _ = pos['U1']
    cx, cy, _ = pos['A1']
    return [
        # Pololu standing upright on a right-angle header: ~2 mm beside the
        # pin row for its board and components (on the Q1 side).
        ('U1 module (standing)', ux - 1.8, uy - 3.8, ux + 6.9, uy - 1.8, {'U1'}),
        ('USB plug zone (no tall parts)', BOARD[0] + 8, cy - 6, cx - 25.4, cy + 6, {'A1', 'J7'}),
    ]


def lib_footprint(libid):
    lib, name = libid.split(':')
    return g.parse(open(os.path.join(KIFP, lib + '.pretty', name + '.kicad_mod')).read())[0]


def swap(old, libid):
    """New pcb footprint node from the library, keeping identity, texts and pad nets."""
    lib = lib_footprint(libid)
    nets = {}
    for p in g.find(old, 'pad'):
        nets[p[1]] = [e for e in p if isinstance(e, list) and e[0] in ('net', 'pintype')]
    ref = next(t[2] for t in g.find(old, 'fp_text') if t[1] == 'reference')
    val = next(t[2] for t in g.find(old, 'fp_text') if t[1] == 'value')
    at = g.find(old, 'at')[0]
    node = ['footprint', g.Q(libid), g.find(old, 'layer')[0], g.find(old, 'tstamp')[0],
            ['at', at[1], at[2]]]
    node += g.find(lib, 'descr') + g.find(lib, 'tags')
    node += g.find(old, 'property') + g.find(old, 'path') + g.find(lib, 'attr')
    for e in lib[2:]:
        if not isinstance(e, list) or e[0] in ('version', 'generator', 'layer', 'descr', 'tags', 'attr'):
            continue
        e = list(e)
        if e[0] == 'fp_text' and e[1] == 'reference':
            e[2] = g.Q(ref)
        if e[0] == 'fp_text' and e[1] == 'value':
            e[2] = g.Q(val)
        if e[0] in ('fp_line', 'fp_circle', 'fp_arc', 'fp_rect', 'fp_poly'):
            # library files use (width w); boards use (stroke (width w) (type solid))
            w = g.find(e, 'width')
            if w:
                e = [x for x in e if not (isinstance(x, list) and x[0] == 'width')]
                e.insert(-1 if g.find(e, 'tstamp') else len(e),
                         ['stroke', ['width', w[0][1]], ['type', 'solid']])
        if e[0] == 'pad':
            e = [x for x in e if not (isinstance(x, list) and x[0] in ('net', 'pintype'))]
            e[-1:-1] = nets.get(e[1], [])
        node.append(e)
    return node


def set_sch_footprint(text, ref, libid):
    m = re.search(r'\(property "Reference" "%s"' % re.escape(ref), text)
    start = text.rfind('(symbol (lib_id', 0, m.start())
    fm = re.compile(r'\(property "Footprint" "[^"]*"').search(text, start)
    assert fm and fm.start() < m.start() + 2000, ref
    return text[:fm.start()] + f'(property "Footprint" "{libid}"' + text[fm.end():]


def main():
    tree = g.parse(open(PCB).read())[0]
    idx = {pp.ref_of(e): i for i, e in enumerate(tree) if isinstance(e, list) and e and e[0] == 'footprint'}
    for ref, libid in SWAP.items():
        tree[idx[ref]] = swap(tree[idx[ref]], libid)
    fps = {r: tree[i] for r, i in idx.items()}
    pos = {}
    for r, fp in fps.items():
        a = g.find(fp, 'at')[0]
        pos[r] = (float(a[1]), float(a[2]), float(a[3]) if len(a) > 3 else 0.0)
    old_pos = dict(pos)
    pos.update(MOVE)

    boxes = {r: pp.abs_boxes(fps[r], *pos[r]) for r in fps}
    problems = 0
    refs = sorted(boxes)
    for i, a in enumerate(refs):
        for b in refs[i + 1:]:
            if any(pp.overlap(x, y) for x in boxes[a] for y in boxes[b]):
                problems += 1
                print('overlap', a, b)
    x1, y1, x2, y2 = BOARD
    for r, bl in boxes.items():
        for bx in bl:
            right = min(bx[2], x2) if r == 'A1' else bx[2]
            if bx[0] < x1 or bx[1] < y1 or right > x2 or bx[3] > y2:
                problems += 1
                print('off board', r, [round(v, 2) for v in bx])
    for name, kx1, ky1, kx2, ky2, allowed in keepouts(pos):
        for r, bl in boxes.items():
            if r in allowed or (name.startswith('USB') and r not in TALL):
                continue
            if any(pp.overlap(b, (kx1, ky1, kx2, ky2)) for b in bl):
                problems += 1
                print(f'keep-out "{name}" hit by {r}')
    print(f'{len(fps)} footprints, {problems} problems')
    if '--check' in sys.argv or problems:
        return problems

    for r, fp in fps.items():
        x, y, rot = pos[r]
        old = 0.0 if r in SWAP else old_pos[r][2]
        at = g.find(fp, 'at')[0]
        at[1:] = [g.fmt(x), g.fmt(y)] + ([g.fmt(rot)] if rot else [])
        if rot == old and r not in SWAP:
            continue
        for kind in ('pad', 'fp_text'):
            for e in g.find(fp, kind):
                for a in g.find(e, 'at'):
                    ang = (float(a[3]) if len(a) == 4 else 0.0) - old + rot
                    ang = ((ang + 180) % 360) - 180
                    a[3:] = [g.fmt(ang)] if abs(ang) > 1e-9 else []
    with open(PCB, 'w') as fh:
        fh.write(g.dump(tree) + '\n')
    sch = open(SCH).read()
    for ref, libid in SWAP.items():
        sch = set_sch_footprint(sch, ref, libid)
    with open(SCH, 'w') as fh:
        fh.write(sch)
    print('wrote', PCB, 'and footprint fields in', SCH)
    return 0


if __name__ == '__main__':
    sys.exit(1 if main() else 0)
