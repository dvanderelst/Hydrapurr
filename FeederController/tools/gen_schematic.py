#!/usr/bin/env python3
"""Generate the first draft of the HydraPurr carrier-PCB schematic (KiCad 7).

One-shot generator: it writes FeederController.kicad_sch and HydraPurr.kicad_sym
from the part and net tables below. Every pin gets a short wire stub and a net
label (no drawn wires between parts), so connectivity is exactly the NETS
table. Once the schematic has been edited in KiCad, do not re-run this: it
would overwrite those edits (it refuses unless --force is given).

Usage:  python3 tools/gen_schematic.py [--force]
        python3 tools/gen_schematic.py --check   # compare exported netlist

Design source: the "HydraPurr Carrier PCB" draft (sheet 1 feeder driver,
sheet 2 sensors and connectors) and Simplified/HANDOFF.md, "Carrier PCB".
"""
import os
import re
import subprocess
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
SCH = os.path.join(PROJ, 'FeederController.kicad_sch')
SYMLIB = os.path.join(PROJ, 'HydraPurr.kicad_sym')
KISYM = '/usr/share/kicad/symbols'
PROJECT_NAME = 'FeederController'


# --------------------------------------------------------------------------
# Minimal s-expression reader/writer
# --------------------------------------------------------------------------
class Q(str):
    """A quoted string atom."""


def parse(text):
    tokens = re.finditer(r'\(|\)|"((?:[^"\\]|\\.)*)"|[^\s()"]+', text)
    stack = [[]]
    for m in tokens:
        t = m.group(0)
        if t == '(':
            stack.append([])
        elif t == ')':
            done = stack.pop()
            stack[-1].append(done)
        elif t.startswith('"'):
            stack[-1].append(Q(m.group(1).replace('\\"', '"').replace('\\\\', '\\')))
        else:
            stack[-1].append(t)
    return stack[0]


def dump(x, indent=0):
    if isinstance(x, Q):
        return '"' + x.replace('\\', '\\\\').replace('"', '\\"') + '"'
    if isinstance(x, str):
        return x
    if isinstance(x, (int, float)):
        return fmt(x)
    inner = [dump(e, indent + 1) for e in x]
    flat = '(' + ' '.join(inner) + ')'
    if len(flat) < 100 and not any(isinstance(e, list) and len(dump(e)) > 60 for e in x):
        return flat
    pad = '\n' + '  ' * (indent + 1)
    return '(' + inner[0] + ''.join(pad + s for s in inner[1:]) + ')'


def fmt(v):
    v = round(float(v), 4)
    return ('%.4f' % v).rstrip('0').rstrip('.') if v != int(v) else str(int(v))


def find(lst, key):
    return [e for e in lst if isinstance(e, list) and e and e[0] == key]


# --------------------------------------------------------------------------
# Library symbols
# --------------------------------------------------------------------------
_libcache = {}


def lib_symbols(lib):
    if lib not in _libcache:
        tree = parse(open(os.path.join(KISYM, lib + '.kicad_sym')).read())[0]
        _libcache[lib] = {e[1]: e for e in find(tree, 'symbol')}
    return _libcache[lib]


def flattened(lib, name):
    """Library symbol `name`, with `extends` resolved, renamed to lib:name."""
    syms = lib_symbols(lib)
    sym = syms[name]
    ext = find(sym, 'extends')
    if ext:
        parent = flattened(lib, ext[0][1])
        child_props = find(sym, 'property')
        out = ['symbol', Q(f'{lib}:{name}')]
        for e in parent[2:]:
            if isinstance(e, list) and e[0] == 'property':
                continue
            if isinstance(e, list) and e[0] == 'symbol':
                pname = ext[0][1]
                e = list(e)
                e[1] = Q(e[1].replace(pname + '_', name + '_', 1))
            out.append(e)
        # properties go right after the header flags
        idx = next(i for i, e in enumerate(out) if isinstance(e, list) and e[0] == 'symbol')
        return out[:idx] + child_props + out[idx:]
    out = list(sym)
    out[1] = Q(f'{lib}:{name}')
    return out


def pins_of(sym):
    """{number: (x, y, angle, name, type)} for unit 0/1 pins."""
    res = {}
    for sub in find(sym, 'symbol'):
        m = re.search(r'_(\d+)_(\d+)$', sub[1])
        if m and m.group(1) not in ('0', '1'):
            continue
        for p in find(sub, 'pin'):
            at = find(p, 'at')[0]
            num = find(p, 'number')[0][1]
            nm = find(p, 'name')[0][1]
            res[str(num)] = (float(at[1]), float(at[2]), int(float(at[3])), nm, p[1])
    return res


# --------------------------------------------------------------------------
# Custom symbols (HydraPurr.kicad_sym)
# --------------------------------------------------------------------------
def font():
    return ['effects', ['font', ['size', 1.27, 1.27]]]


def font_hide():
    return ['effects', ['font', ['size', 1.27, 1.27]], 'hide']


def prop(k, v, x=0, y=0, hide=False):
    return ['property', Q(k), Q(v), ['at', x, y, 0], font_hide() if hide else font()]


def feather_symbol():
    """Adafruit_Feather_Generic with the Feather ESP32-S3 Reverse TFT pin names.

    The generic symbol numbers the pins like Module:Adafruit_Feather (1-16 the
    long header from RST, 17-28 the short header from SDA). Its D0..D6 are the
    short-header positions, which on this Feather carry D5, D6, D9..D13.
    """
    sym = flattened('MCU_Module', 'Adafruit_Feather_Generic')
    rename = {'3': 'NC', '16': 'NC', '19': 'D5', '20': 'D6', '21': 'D9',
              '22': 'D10', '23': 'D11', '24': 'D12', '25': 'D13'}
    for sub in find(sym, 'symbol'):
        for p in find(sub, 'pin'):
            num = find(p, 'number')[0][1]
            if num in rename:
                find(p, 'name')[0][1] = Q(rename[num])
    sym[1] = Q('HydraPurr:Feather_ESP32S3_ReverseTFT')
    for sub in find(sym, 'symbol'):
        sub[1] = Q(sub[1].replace('Adafruit_Feather_Generic', 'Feather_ESP32S3_ReverseTFT'))
    for p in find(sym, 'property'):
        if p[1] == 'Value':
            p[2] = Q('Feather_ESP32S3_ReverseTFT')
        elif p[1] == 'Footprint':
            p[2] = Q('Module:Adafruit_Feather_WithMountingHoles')
        elif p[1] == 'Datasheet':
            p[2] = Q('https://learn.adafruit.com/esp32-s3-reverse-tft-feather/pinouts')
        elif p[1] == 'ki_description':
            p[2] = Q('Adafruit Feather ESP32-S3 Reverse TFT (Feather pin positions). '
                     'On this board it sits on the Adalogger FeatherWing (stacking headers).')
    return sym


def pololu_symbol():
    def pin(kind, x, y, ang, name, num):
        return ['pin', kind, 'line', ['at', x, y, ang], ['length', 2.54],
                ['name', Q(name), font()], ['number', Q(num), font()]]
    return ['symbol', Q('HydraPurr:Pololu_U3V16F12'),
            ['in_bom', 'yes'], ['on_board', 'yes'],
            prop('Reference', 'U', 0, 6.35),
            prop('Value', 'Pololu_U3V16F12', 0, -10.16),
            prop('Footprint', 'Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical', 0, 0, True),
            prop('Datasheet', 'https://www.pololu.com/product/4945', 0, 0, True),
            prop('ki_description', 'Pololu 12 V step-up regulator U3V16F12 (#4945). '
                 'Pins along one edge: 1 VOUT, 2 GND, 3 VIN.', 0, 0, True),
            ['symbol', Q('Pololu_U3V16F12_0_1'),
             ['rectangle', ['start', -7.62, 3.81], ['end', 7.62, -3.81],
              ['stroke', ['width', 0.254], ['type', 'default']], ['fill', ['type', 'background']]]],
            ['symbol', Q('Pololu_U3V16F12_1_1'),
             pin('power_in', -10.16, 0, 0, 'VIN', '3'),
             pin('power_out', 10.16, 0, 180, 'VOUT', '1'),
             pin('power_in', 0, -6.35, 90, 'GND', '2')]]


# --------------------------------------------------------------------------
# The design
# --------------------------------------------------------------------------
FP_R = 'Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal'
FP_C = 'Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm'
FP_PH3 = 'Connector_JST:JST_PH_B3B-PH-K_1x03_P2.00mm_Vertical'
FP_PH4 = 'Connector_JST:JST_PH_B4B-PH-K_1x04_P2.00mm_Vertical'
FP_TO92 = 'Package_TO_SOT_THT:TO-92_Inline'
FP_TO220 = 'Package_TO_SOT_THT:TO-220-3_Vertical'
FP_LED = 'LED_THT:LED_D3.0mm'

# ref, symbol (lib:name), value, footprint, x, y, {pin: net}, extra fields, dnp
# A pin mapped to None gets a no-connect flag.
PARTS = [
    # --- Feather (sits on the Adalogger, which plugs into this board) -------
    ('A1', 'HydraPurr:Feather_ESP32S3_ReverseTFT', 'Feather ESP32-S3 Reverse TFT',
     'Module:Adafruit_Feather_WithMountingHoles', 63.5, 101.6,
     {'1': None, '2': '+3V3', '3': None, '4': 'GND', '5': 'FEEDER_EN', '6': 'A1',
      '7': 'A2', '8': 'A3', '9': 'A4', '10': 'SHARP_VO', '11': None, '12': None,
      '13': None, '14': 'RFID_RX', '15': 'RFID_RST', '16': None, '17': 'SDA',
      '18': 'SCL', '19': 'D5', '20': 'D6', '21': 'LED_CONTACT', '22': None,
      '23': 'D11', '24': 'TOUCH', '25': 'D13', '26': '+5V', '27': None, '28': None},
     {'Note': 'Female 1x16 + 1x12 sockets. SPI, D10 and RST pass between the Feather and the Adalogger only.',
      '_refpos': (-12.7, 38.1)}, False),

    # --- Sheet 1: feeder driver ------------------------------------------------
    ('U1', 'HydraPurr:Pololu_U3V16F12', 'Pololu U3V16F12 12V step-up',
     'Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical', 139.7, 45.72,
     {'1': '+12V', '2': 'GND', '3': '+5V'},
     {'Note': 'Mounted flat on a straight header, soldered in. Silkscreen VIN/VOUT.'}, False),
    ('C1', 'Device:C_Polarized', '1000uF 16V', 'Capacitor_THT:CP_Radial_D10.0mm_P5.00mm',
     167.64, 45.72, {'1': '+5V', '2': 'GND'}, {}, False),
    ('C2', 'Device:C_Polarized', '100uF 25V', 'Capacitor_THT:CP_Radial_D6.3mm_P2.50mm',
     190.5, 45.72, {'1': '+12V', '2': 'GND'}, {}, False),
    ('F1', 'Device:Polyfuse', '0.5A PTC', 'Fuse:Fuse_Bourns_MF-RHT050',
     213.36, 45.72, {'1': '+12V', '2': '+12V_F'},
     {'Note': 'MF-RHT050 footprint; check the pitch against the fuse you buy.'}, False),
    ('R4', 'Device:R', '10k', FP_R, 236.22, 45.72, {'1': '+12V_F', '2': 'Q1_GATE'}, {}, False),
    ('Q1', 'Transistor_FET:IRF9540N', 'IRF9540N', FP_TO220, 261.62, 45.72,
     {'1': 'Q1_GATE', '2': 'FEEDER+', '3': '+12V_F'},
     {'Note': 'High-side switch: source on +12V_F, drain = FEEDER+.'}, False),
    ('Q2', 'Transistor_BJT:BC547', 'BC547', FP_TO92, 142.24, 83.82,
     {'1': 'Q1_GATE', '2': 'Q2_BASE', '3': 'GND'}, {}, False),
    ('R1', 'Device:R', '4.7k', FP_R, 167.64, 83.82, {'1': 'FEEDER_EN', '2': 'Q2_BASE'}, {}, False),
    ('R2', 'Device:R', '47k', FP_R, 190.5, 83.82, {'1': 'Q2_BASE', '2': 'GND'}, {}, False),
    ('D1', 'Device:D_Schottky', '1N5819', 'Diode_THT:D_DO-41_SOD81_P10.16mm_Horizontal',
     220.98, 83.82, {'1': 'FEEDER+', '2': 'GND'}, {}, False),
    ('C3', 'Device:C', '100nF 50V', FP_C, 246.38, 83.82, {'1': 'FEEDER+', '2': 'GND'}, {}, False),
    ('R3', 'Device:R', '1k', FP_R, 266.7, 83.82, {'1': 'FEEDER+', '2': 'LED1_A'}, {}, False),
    ('LED1', 'Device:LED', 'green', FP_LED, 292.1, 83.82,
     {'1': 'GND', '2': 'LED1_A'}, {}, False),
    ('J1', 'Connector_Generic:Conn_01x03', 'Feeder', FP_PH3, 330.2, 83.82,
     {'1': 'FEEDER+', '2': None, '3': 'GND'},
     {'Note': '1 FEEDER+, 2 empty (no LiPo fits), 3 FEEDER- = GND.'}, False),

    # --- Sheet 2: touch wire and Sharp --------------------------------------
    ('J2', 'Connector_Generic:Conn_01x03', 'Touch wire', FP_PH3, 142.24, 134.62,
     {'1': 'TOUCH_J', '2': None, '3': 'GND'},
     {'Note': 'Short trace from D12, no ground pour under it.'}, False),
    ('R5', 'Device:R', '0R', FP_R, 165.1, 134.62, {'1': 'TOUCH', '2': 'TOUCH_J'},
     {'Note': 'Wire link; room for a series resistor later.'}, False),
    ('J3', 'Connector_Generic:Conn_01x03', 'Sharp', FP_PH3, 203.2, 134.62,
     {'1': 'SHARP_OUT', '2': 'GND', '3': '+5V'},
     {'Note': 'Sensor pin order: 1 Vo, 2 GND, 3 Vcc. ZH-to-PH adapter cable.'}, False),
    ('C4', 'Device:C', '10uF 10V', FP_C, 226.06, 134.62, {'1': '+5V', '2': 'GND'}, {}, False),
    ('C5', 'Device:C_Polarized', '100uF 10V', 'Capacitor_THT:CP_Radial_D6.3mm_P2.50mm',
     246.38, 134.62, {'1': '+5V', '2': 'GND'}, {}, False),
    ('R6', 'Device:R', '1k', FP_R, 266.7, 134.62, {'1': 'SHARP_OUT', '2': 'SHARP_VO'}, {}, False),
    ('C6', 'Device:C', '100nF', FP_C, 287.02, 134.62, {'1': 'SHARP_VO', '2': 'GND'},
     {'Note': 'Optional filter; fit only if readings are noisy.'}, True),

    # --- Sheet 2: RFID power ---------------------------------------------------
    ('FB1', 'Device:FerriteBead', 'Ferrite bead', 'Inductor_THT:L_Axial_L5.3mm_D2.2mm_P10.16mm_Horizontal_Vishay_IM-1',
     142.24, 172.72, {'1': '+5V', '2': '+5V_RFID'}, {}, False),
    ('C7', 'Device:C_Polarized', '470uF 10V', 'Capacitor_THT:CP_Radial_D8.0mm_P3.50mm',
     165.1, 172.72, {'1': '+5V_RFID', '2': 'GND'}, {}, False),
    ('U2', 'Regulator_Linear:L7806', 'LM7806', FP_TO220, 200.66, 172.72,
     {'1': '+12V', '2': 'GND', '3': '+6V'},
     {'Note': 'Optional: 6 V for longer RFID read range (JP2 on 2-3).'}, True),
    ('C8', 'Device:C', '330nF', FP_C, 228.6, 172.72, {'1': '+12V', '2': 'GND'}, {}, True),
    ('C9', 'Device:C', '100nF', FP_C, 248.92, 172.72, {'1': '+6V', '2': 'GND'}, {}, True),
    ('JP2', 'Connector_Generic:Conn_01x03', '1-2 = 5V, 2-3 = 6V',
     'Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical', 279.4, 172.72,
     {'1': '+5V_RFID', '2': 'RFID_VCC', '3': '+6V'},
     {'Note': 'Jumper on 1-2 by default.'}, False),

    # --- Sheet 2: RFID data and reset ------------------------------------------
    ('J4', 'Connector_Generic:Conn_01x04', 'RFID', FP_PH4, 139.7, 210.82,
     {'1': 'RFID_VCC', '2': 'RFID_RST_N', '3': 'RFID_TX5', '4': 'GND'},
     {'Note': 'WL-134 order: 1 VCC, 2 RST, 3 TX, 4 GND (check pin 4 on the module).'}, False),
    ('Q3', 'Transistor_BJT:BC547', 'BC547', FP_TO92, 167.64, 210.82,
     {'1': 'RFID_RST_N', '2': 'Q3_BASE', '3': 'GND'}, {}, False),
    ('R8', 'Device:R', '4.7k', FP_R, 193.04, 210.82, {'1': 'RFID_RST', '2': 'Q3_BASE'}, {}, False),
    ('R9', 'Device:R', '47k', FP_R, 215.9, 210.82, {'1': 'Q3_BASE', '2': 'GND'}, {}, False),
    ('R10', 'Device:R', '10k', FP_R, 241.3, 210.82, {'1': 'RFID_VCC', '2': 'RFID_RST_N'}, {}, False),
    ('R11', 'Device:R', '10k', FP_R, 266.7, 210.82, {'1': 'RFID_TX5', '2': 'RFID_RX'}, {}, False),
    ('R12', 'Device:R', '18k', FP_R, 292.1, 210.82, {'1': 'RFID_RX', '2': 'GND'}, {}, False),
    ('JP1', 'Connector_Generic:Conn_01x02', 'OPEN = 5V TX',
     'Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical', 325.12, 210.82,
     {'1': 'RFID_TX5', '2': 'RFID_RX'},
     {'Note': 'Close only when the module 3.3 V TX pad is wired. Never with 5 V TX.'}, False),

    # --- Sheet 2: contact LED, I2C, spare --------------------------------------
    ('R13', 'Device:R', '330', FP_R, 142.24, 254, {'1': 'LED_CONTACT', '2': 'LED2_A'}, {}, False),
    ('LED2', 'Device:LED', 'red', FP_LED, 167.64, 254, {'1': 'GND', '2': 'LED2_A'}, {}, False),
    ('R14', 'Device:R', '330', FP_R, 195.58, 254, {'1': 'LED_CONTACT', '2': 'J5_LED'}, {}, False),
    ('J5', 'Connector_Generic:Conn_01x03', 'Panel LED', FP_PH3, 228.6, 254,
     {'1': 'J5_LED', '2': None, '3': 'GND'}, {'Note': '1 LED+, 2 empty, 3 GND.'}, False),
    ('J6', 'Connector_Generic:Conn_01x04', 'I2C', FP_PH4, 271.78, 254,
     {'1': 'GND', '2': '+3V3', '3': 'SDA', '4': 'SCL'}, {}, False),
    ('J7', 'Connector_Generic:Conn_01x12', 'Spare pins',
     'Connector_PinHeader_2.54mm:PinHeader_1x12_P2.54mm_Vertical', 370.84, 205.74,
     {'1': '+5V', '2': '+3V3', '3': 'GND', '4': 'D5', '5': 'D6', '6': 'D11', '7': 'D13',
      '8': 'A1', '9': 'A2', '10': 'A3', '11': 'A4', '12': 'GND'}, {}, False),
    ('H1', 'Mechanical:MountingHole', 'M3', 'MountingHole:MountingHole_3.2mm_M3', 365.76, 160.02, {}, {}, False),
    ('H2', 'Mechanical:MountingHole', 'M3', 'MountingHole:MountingHole_3.2mm_M3', 381, 160.02, {}, {}, False),
    ('H3', 'Mechanical:MountingHole', 'M3', 'MountingHole:MountingHole_3.2mm_M3', 365.76, 172.72, {}, {}, False),
    ('H4', 'Mechanical:MountingHole', 'M3', 'MountingHole:MountingHole_3.2mm_M3', 381, 172.72, {}, {}, False),

    # --- Power flags (ERC: these nets are supplied from off-sheet) -------------
    ('#FLG01', 'power:PWR_FLAG', 'PWR_FLAG', '', 30.48, 160.02, {'1': '+5V'}, {}, False),
    ('#FLG02', 'power:PWR_FLAG', 'PWR_FLAG', '', 50.8, 160.02, {'1': '+3V3'}, {}, False),
    ('#FLG03', 'power:PWR_FLAG', 'PWR_FLAG', '', 71.12, 160.02, {'1': 'GND'}, {}, False),
]

NOTES = [
    (127, 25.4, 'SHEET 1 - FEEDER DRIVER (high-side). A0 high: Q2 on, gate 0 V, Q1 on, feeder runs. '
                'A0 floating: R2 keeps Q2 off, R4 keeps Q1 off.'),
    (127, 116.84, 'SHEET 2 - TOUCH WIRE and SHARP WATER LEVEL'),
    (127, 154.94, 'RFID SUPPLY. Default JP2 1-2: USB 5 V via FB1 + C7. Fit U2, C8, C9 and move JP2 to 2-3 for 6 V.'),
    (127, 193.04, 'RFID DATA and RESET. TX high = RST low (inverted, as the old board). '
                  'R11/R12: 5 V TX -> 3.2 V. JP1 closed only for the 3.3 V TX pad.'),
    (127, 231.14, 'CONTACT LED, I2C'),
    (345.44, 152.4, 'MOUNTING HOLES, SPARE PINS'),
    (25.4, 50.8, 'FEATHER on ADALOGGER'),
    (25.4, 281.94, 'All parts through-hole. DNP: C6, U2, C8, C9. Generated by tools/gen_schematic.py (draft).'),
]


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------
def uid():
    return str(uuid.uuid4())


DIRS = {0: (1, 0), 90: (0, 1), 180: (-1, 0), 270: (0, -1)}


def build():
    root = uid()
    custom = {'HydraPurr:Feather_ESP32S3_ReverseTFT': feather_symbol(),
              'HydraPurr:Pololu_U3V16F12': pololu_symbol()}
    libsyms = {}
    items = []
    for ref, lid, value, fp, x, y, nets, extra, dnp in PARTS:
        if lid not in libsyms:
            if lid in custom:
                libsyms[lid] = custom[lid]
            else:
                lib, name = lid.split(':')
                libsyms[lid] = flattened(lib, name)
        sym = libsyms[lid]
        pins = pins_of(sym)
        missing = set(pins) - set(nets)
        if missing and not ref.startswith('H'):
            raise SystemExit(f'{ref}: pins not assigned: {sorted(missing)}')
        is_power = lid.startswith('power:')
        angles = {a for (_, _, a, _, _) in pins.values()}
        extra = dict(extra)
        if '_refpos' in extra:
            dx, dy = extra.pop('_refpos')
            rpos, vpos, rj = (x + dx, y + dy), (x + dx, y + dy + 2.54), ['justify', 'left']
        elif 0 in angles and 180 in angles:               # pins left and right: text above
            rpos, vpos, rj = (x, y - 8.89), (x, y - 6.35), []
        else:
            rpos, vpos, rj = (x + 5.08, y - 1.27), (x + 5.08, y + 1.27), ['justify', 'left']
        inst = ['symbol', ['lib_id', Q(lid)], ['at', x, y, 0], ['unit', 1],
                ['in_bom', 'no' if is_power else 'yes'], ['on_board', 'no' if is_power else 'yes'],
                ['dnp', 'yes' if dnp else 'no'], ['uuid', uid()],
                ['property', Q('Reference'), Q(ref), ['at', rpos[0], rpos[1], 0],
                 ['effects', ['font', ['size', 1.27, 1.27]]] + ([rj] if rj else []) + (['hide'] if is_power else [])],
                ['property', Q('Value'), Q(value), ['at', vpos[0], vpos[1], 0],
                 ['effects', ['font', ['size', 1.27, 1.27]]] + ([rj] if rj else []) + (['hide'] if is_power else [])],
                ['property', Q('Footprint'), Q(fp), ['at', x, y, 0], font_hide()],
                ['property', Q('Datasheet'), Q('~'), ['at', x, y, 0], font_hide()]]
        for k, v in extra.items():
            inst.append(['property', Q(k), Q(v), ['at', x, y, 0], font_hide()])
        for num in pins:
            inst.append(['pin', Q(num), ['uuid', uid()]])
        inst.append(['instances', ['project', Q(PROJECT_NAME),
                                   ['path', Q('/' + root), ['reference', Q(ref)], ['unit', 1]]]])
        items.append(inst)

        for num, net in nets.items():
            px, py, ang, _, _ = pins[num]
            ax, ay = x + px, y - py                       # schematic y points down
            bx, by = DIRS[ang]                            # pin points toward the body
            ox, oy = -bx, by                              # outward, schematic coords
            if net is None:
                items.append(['no_connect', ['at', ax, ay], ['uuid', uid()]])
                continue
            ex, ey = ax + ox * 2.54, ay + oy * 2.54
            items.append(['wire', ['pts', ['xy', ax, ay], ['xy', ex, ey]],
                          ['stroke', ['width', 0], ['type', 'default']], ['uuid', uid()]])
            if ox == 1:
                lang, just = 0, ['justify', 'left', 'bottom']
            elif ox == -1:
                lang, just = 180, ['justify', 'right', 'bottom']
            elif oy == -1:
                lang, just = 90, ['justify', 'left', 'bottom']
            else:
                lang, just = 270, ['justify', 'right', 'bottom']
            items.append(['label', Q(net), ['at', ex, ey, lang], ['fields_autoplaced'],
                          ['effects', ['font', ['size', 1.27, 1.27]], just], ['uuid', uid()]])

    for x, y, text in NOTES:
        items.append(['text', Q(text), ['at', x, y, 0],
                      ['effects', ['font', ['size', 2, 2], 'bold'], ['justify', 'left', 'bottom']],
                      ['uuid', uid()]])

    sch = ['kicad_sch', ['version', '20230121'], ['generator', 'eeschema'],
           ['uuid', root], ['paper', Q('A3')],
           ['title_block', ['title', Q('HydraPurr carrier PCB')], ['date', Q('2026-11-13')],
            ['rev', Q('draft 1')],
            ['comment', 1, Q('Feather ESP32-S3 Reverse TFT + Adalogger FeatherWing, feeder driver, sensor connectors')]],
           ['lib_symbols'] + list(libsyms.values())] + items + \
          [['sheet_instances', ['path', Q('/'), ['page', Q('1')]]]]
    return sch, custom


def write(force):
    if os.path.exists(SCH) and os.path.getsize(SCH) > 200 and not force:
        raise SystemExit(f'{SCH} already has content; re-run with --force to overwrite.')
    sch, custom = build()
    with open(SCH, 'w') as f:
        f.write(dump(sch) + '\n')
    lib = ['kicad_symbol_lib', ['version', '20220914'], ['generator', 'gen_schematic']]
    for sym in custom.values():
        s = list(sym)
        s[1] = Q(s[1].split(':', 1)[1])
        lib.append(s)
    with open(SYMLIB, 'w') as f:
        f.write(dump(lib) + '\n')
    table = os.path.join(PROJ, 'sym-lib-table')
    if not os.path.exists(table):
        with open(table, 'w') as f:
            f.write('(sym_lib_table\n  (version 7)\n'
                    '  (lib (name "HydraPurr")(type "KiCad")(uri "${KIPRJMOD}/HydraPurr.kicad_sym")(options "")(descr "HydraPurr custom symbols"))\n)\n')
    print('wrote', SCH)


def check():
    """Export the netlist with kicad-cli and compare it with PARTS."""
    out = os.path.join(HERE, 'check.net')
    subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format', 'kicadsexpr',
                    '-o', out, SCH], check=True, capture_output=True)
    tree = parse(open(out).read())[0]
    got = {}
    for net in find(find(tree, 'nets')[0], 'net'):
        name = find(net, 'name')[0][1].lstrip('/')
        for node in find(net, 'node'):
            r, p = find(node, 'ref')[0][1], find(node, 'pin')[0][1]
            got[(r, p)] = name
    os.remove(out)
    bad = 0
    want_nets = {}
    for ref, _, _, _, _, _, nets, _, _ in PARTS:
        if ref.startswith('#'):
            continue
        for p, n in nets.items():
            if n is None:
                continue
            want_nets.setdefault(n, set()).add((ref, p))
            if got.get((ref, p)) != n:
                bad += 1
                print(f'MISMATCH {ref}.{p}: want {n}, netlist has {got.get((ref, p))}')
    for n, members in sorted(want_nets.items()):
        if len(members) < 2:
            bad += 1
            print(f'NET {n} has only one pin: {members}')
    print(f'{len(want_nets)} nets, {sum(len(m) for m in want_nets.values())} connections, {bad} problems')
    return bad


if __name__ == '__main__':
    if '--check' in sys.argv:
        sys.exit(1 if check() else 0)
    write('--force' in sys.argv)
