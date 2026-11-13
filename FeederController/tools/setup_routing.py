#!/usr/bin/env python3
"""Routing setup for the carrier PCB (KiCad must be closed).

- Net classes in FeederController.kicad_pro (KiCad 7 netclass patterns):
    Default  0.3 mm tracks, 0.25 mm clearance, vias 0.8/0.4 mm
    Power    0.8 mm tracks, 0.3 mm clearance, vias 1.0/0.5 mm
    Touch    0.3 mm tracks, 0.6 mm clearance (keeps other copper away)
- GND zones on B.Cu and F.Cu over the whole board, each with a notch cut
  out of its outline around D12 -> R5 -> J2: ground next to the touch line
  adds capacitance and shifts the touch baseline.
  (Not a rule area: KiCad 7's Specctra DSN export turns any rule area into
  a full keep-out, so Freerouting could not reach the pins inside it.)
Fill the zones in KiCad afterwards (press B), then run DRC.
Re-running replaces the zones / rule area it made (matched by name).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_schematic as g  # noqa: E402

PROJ = os.path.dirname(HERE)
PCB = os.path.join(PROJ, 'FeederController.kicad_pcb')
PRO = os.path.join(PROJ, 'FeederController.kicad_pro')
BOARD = (100.0, 100.0, 180.0, 160.0)
TOUCH_AREA = (151.5, 147.0, 165.5, 160.0)     # D12 pad, R5, J2 (x1, y1, x2, y2)

POWER = ['+5V', '+12V', '/+12V_F', '/FEEDER+', '+6V', '/+5V_RFID', '/RFID_VCC', '+3V3', 'GND']
TOUCH = ['/TOUCH', 'Net-(J2-Pin_1)']


def netclass(name, track, clearance, via_d, via_drill):
    return {"bus_width": 12, "clearance": clearance, "diff_pair_gap": 0.25,
            "diff_pair_via_gap": 0.25, "diff_pair_width": 0.2, "line_style": 0,
            "microvia_diameter": 0.3, "microvia_drill": 0.1, "name": name,
            "pcb_color": "rgba(0, 0, 0, 0.000)", "schematic_color": "rgba(0, 0, 0, 0.000)",
            "track_width": track, "via_diameter": via_d, "via_drill": via_drill, "wire_width": 6}


def setup_project():
    pro = json.load(open(PRO))
    ns = pro.setdefault('net_settings', {})
    ns['classes'] = [netclass('Default', 0.3, 0.25, 0.8, 0.4),
                     netclass('Power', 0.8, 0.3, 1.0, 0.5),
                     netclass('Touch', 0.3, 0.6, 0.8, 0.4)]
    ns['netclass_patterns'] = ([{"netclass": "Power", "pattern": p} for p in POWER] +
                               [{"netclass": "Touch", "pattern": p} for p in TOUCH])
    ns.setdefault('meta', {})['version'] = 3
    ns.setdefault('net_colors', None)
    ns.setdefault('netclass_assignments', None)
    with open(PRO, 'w') as fh:
        json.dump(pro, fh, indent=2)
        fh.write('\n')


def rect_pts(x1, y1, x2, y2):
    return ['pts'] + [['xy', g.fmt(x), g.fmt(y)] for x, y in ((x1, y1), (x2, y1), (x2, y2), (x1, y2))]


def setup_board():
    tree = g.parse(open(PCB).read())[0]
    gnd = next(n for n in g.find(tree, 'net') if n[2] == 'GND')
    names = {'GND plane (bottom)', 'GND plane (top)', 'No ground near touch line'}
    tree[1:] = [e for e in tree[1:] if not (isinstance(e, list) and e and e[0] == 'zone'
                                            and g.find(e, 'name') and g.find(e, 'name')[0][1] in names)]
    x1, y1, x2, y2 = BOARD
    tx1, ty1, tx2, ty2 = TOUCH_AREA
    assert ty2 == y2, 'notch is cut in from the bottom edge'
    outline = [(x1, y1), (x2, y1), (x2, y2), (tx2, y2), (tx2, ty1), (tx1, ty1), (tx1, y2), (x1, y2)]
    pts = ['pts'] + [['xy', g.fmt(x), g.fmt(y)] for x, y in outline]
    for layer, name, prio in (('B.Cu', 'GND plane (bottom)', '0'), ('F.Cu', 'GND plane (top)', '0')):
        tree.append(['zone', ['net', gnd[1]], ['net_name', g.Q('GND')], ['layer', g.Q(layer)],
                     ['tstamp', g.uid()], ['name', g.Q(name)], ['hatch', 'edge', '0.5'],
                     ['priority', prio],
                     ['connect_pads', ['clearance', '0.5']], ['min_thickness', '0.25'],
                     ['filled_areas_thickness', 'no'],
                     ['fill', 'yes', ['thermal_gap', '0.5'], ['thermal_bridge_width', '0.5']],
                     ['polygon', list(pts)]])
    with open(PCB, 'w') as fh:
        fh.write(g.dump(tree) + '\n')


if __name__ == '__main__':
    lock = os.path.join(PROJ, '~FeederController.kicad_pcb.lck')
    if os.path.exists(lock):
        raise SystemExit('KiCad has the board open (lock file); save and close it first.')
    setup_project()
    setup_board()
    print('net classes set in', PRO)
    print('GND zones (B.Cu, F.Cu) with a notch at the touch line written to', PCB)
