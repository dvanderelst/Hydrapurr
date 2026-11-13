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
            p[2] = Q('HydraPurr:Feather_Adalogger_Inverted_Stack')
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
     'HydraPurr:Feather_Adalogger_Inverted_Stack', 63.5, 101.6,
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
    ('Q2', 'Transistor_BJT:PN2222A', 'PN2222A', FP_TO92, 142.24, 83.82,
     {'1': 'GND', '2': 'Q2_BASE', '3': 'Q1_GATE'},
     {'Note': 'E-B-C pinout (PN2222A). A P2N2222A is C-B-E: check the part.'}, False),
    ('R1', 'Device:R', '4.7k', FP_R, 167.64, 83.82, {'1': 'FEEDER_EN', '2': 'Q2_BASE'}, {}, False),
    ('R2', 'Device:R', '4.7k', FP_R, 190.5, 83.82, {'1': 'Q2_BASE', '2': 'GND'}, {'Note': '4.7k, not 47k: must hold the base low against the ESP32 internal pull-up (~45k) during boot/reset.'}, False),
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
    ('Q3', 'Transistor_BJT:PN2222A', 'PN2222A', FP_TO92, 167.64, 210.82,
     {'1': 'GND', '2': 'Q3_BASE', '3': 'RFID_RST_N'},
     {'Note': 'E-B-C pinout (PN2222A). A P2N2222A is C-B-E: check the part.'}, False),
    ('R8', 'Device:R', '4.7k', FP_R, 193.04, 210.82, {'1': 'RFID_RST', '2': 'Q3_BASE'}, {}, False),
    ('R9', 'Device:R', '4.7k', FP_R, 215.9, 210.82, {'1': 'Q3_BASE', '2': 'GND'}, {'Note': '4.7k, not 47k: must hold the base low against the ESP32 internal pull-up (~45k) during boot/reset.'}, False),
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
# Build: placement and wiring
# --------------------------------------------------------------------------
def uid():
    return str(uuid.uuid4())


DIRS = {0: (1, 0), 90: (0, 1), 180: (-1, 0), 270: (0, -1)}
G = 2.54


def r(v):
    return round(v, 3)


def tf(vx, vy, rot, mirror):
    """Symbol-space vector (y up) -> schematic-space vector (y down)."""
    x, y = vx, -vy
    if mirror == 'x':
        y = -y
    if rot == 90:
        x, y = y, -x
    elif rot == 180:
        x, y = -x, -y
    elif rot == 270:
        x, y = -y, x
    return x, y


class Sheet:
    def __init__(self):
        self.root = uid()
        self.custom = {'HydraPurr:Feather_ESP32S3_ReverseTFT': feather_symbol(),
                       'HydraPurr:Pololu_U3V16F12': pololu_symbol()}
        self.libsyms = {}
        self.items = []
        self.parts = {p[0]: p for p in PARTS}
        self.placed = {}          # ref -> {pin: ((x, y), (ox, oy))}
        self.wires = []           # ((x1, y1), (x2, y2))
        self.pinpts = []          # every pin end point (parts and power symbols)
        self.npwr = 0

    # -- symbols ------------------------------------------------------------
    def libsym(self, lid):
        if lid not in self.libsyms:
            if lid in self.custom:
                self.libsyms[lid] = self.custom[lid]
            else:
                lib, name = lid.split(':')
                self.libsyms[lid] = flattened(lib, name)
        return self.libsyms[lid]

    def _instance(self, ref, lid, value, fp, x, y, rot, mirror, dnp, extra, refpos, power=False):
        sym = self.libsym(lid)
        pins = pins_of(sym)
        geo = {}
        for num, (px, py, ang, _, _) in pins.items():
            dx, dy = tf(px, py, rot, mirror)
            bx, by = tf(*DIRS[ang], rot, mirror)
            geo[num] = ((r(x + dx), r(y + dy)), (-round(bx), -round(by)))
            self.pinpts.append(geo[num][0])
        hidden = power
        if refpos is None:
            outs = {o for (_, o) in geo.values()}
            if (1, 0) in outs and (-1, 0) in outs:
                body = max([abs(pt[1] - y) for pt, _ in geo.values()] + [1.27])
                top = y - max(body, 3.81) if len(geo) > 2 else y - 1.27
                rpos, vpos, just = (x, top - 3.81), (x, top - 1.78), []
            else:
                rpos, vpos, just = (x + 5.08, y - 1.27), (x + 5.08, y + 1.27), ['justify', 'left']
        else:
            rx, ry = refpos[0], refpos[1]
            side = refpos[2] if len(refpos) > 2 else 'left'
            rpos, vpos, just = (x + rx, y + ry), (x + rx, y + ry + 2.54), ['justify', side]
        fang = rot if rot in (90, 270) else 0     # keep text horizontal on rotated parts
        if fang:
            just = []                             # centred, as KiCad does for rotated parts

        def field(k, v, pos, hide):
            eff = ['effects', ['font', ['size', 1.27, 1.27]]] + ([just] if just else []) + (['hide'] if hide else [])
            return ['property', Q(k), Q(v), ['at', pos[0], pos[1], fang], eff]
        inst = ['symbol', ['lib_id', Q(lid)], ['at', x, y, rot]]
        if mirror:
            inst.append(['mirror', mirror])
        inst += [['unit', 1], ['in_bom', 'no' if power else 'yes'],
                 ['on_board', 'no' if power else 'yes'], ['dnp', 'yes' if dnp else 'no'],
                 ['uuid', uid()],
                 field('Reference', ref, rpos, True if power else False),
                 field('Value', value, (x, y + 3.81) if power and value == 'GND' else
                       ((x, y - 3.81) if power and refpos is None else vpos), False if not power or lid != 'power:PWR_FLAG' else False),
                 ['property', Q('Footprint'), Q(fp), ['at', x, y, 0], font_hide()],
                 ['property', Q('Datasheet'), Q('~'), ['at', x, y, 0], font_hide()]]
        for k, v in extra.items():
            inst.append(['property', Q(k), Q(v), ['at', x, y, 0], font_hide()])
        for num in pins:
            inst.append(['pin', Q(num), ['uuid', uid()]])
        inst.append(['instances', ['project', Q(PROJECT_NAME),
                                   ['path', Q('/' + self.root), ['reference', Q(ref)], ['unit', 1]]]])
        self.items.append(inst)
        return geo

    def place(self, ref, x, y, rot=0, mirror=None, refpos=None):
        _, lid, value, fp, _, _, nets, extra, dnp = self.parts[ref]
        extra = {k: v for k, v in extra.items() if not k.startswith('_')}
        self.placed[ref] = self._instance(ref, lid, value, fp, x, y, rot, mirror, dnp, extra, refpos)
        return self.placed[ref]

    def P(self, ref, pin):
        return self.placed[ref][str(pin)][0]

    def power(self, net, pt, rot=0):
        """Power symbol whose pin sits at pt. GND hangs below, others stand above."""
        self.npwr += 1
        lid = 'power:PWR_FLAG' if net == 'PWR_FLAG' else f'power:{net}'
        ref = f'#FLG{self.npwr:02d}' if net == 'PWR_FLAG' else f'#PWR{self.npwr:02d}'
        x, y = pt
        if rot:
            vpos = {90: (-1.27, 0), 270: (1.27, 0)}[rot]
        self._instance(ref, lid, net, '', x, y, rot, None, False, {}, None, power=True)
        if rot:   # sideways symbol: put its value text beside it, horizontal
            prop = find(self.items[-1], 'property')[1]
            off = -5.08 if (net == 'GND') == (rot == 270) else 5.08
            prop[3] = ['at', r(x + off), y, 0]
            prop[4] = ['effects', ['font', ['size', 1.27, 1.27]],
                       ['justify', 'right' if off < 0 else 'left']]

    # -- wires, labels ------------------------------------------------------
    def wire(self, *pts):
        for a, b in zip(pts, pts[1:]):
            a, b = (r(a[0]), r(a[1])), (r(b[0]), r(b[1]))
            if a != b:
                assert a[0] == b[0] or a[1] == b[1], f'diagonal wire {a} {b}'
                self.wires.append((a, b))

    def stub(self, ref, pin, length=G):
        pt, (ox, oy) = self.placed[ref][str(pin)]
        end = (r(pt[0] + ox * length), r(pt[1] + oy * length))
        self.wire(pt, end)
        return end, (ox, oy)

    def label(self, net, pt, direction, glob=False):
        """Net label at pt; direction = way the text runs (L or R, U or D)."""
        ang, just = {'R': (0, 'left'), 'L': (180, 'right'), 'U': (90, 'left'), 'D': (270, 'right')}[direction]
        if glob:
            self.items.append(['global_label', Q(net), ['shape', 'passive'], ['at', pt[0], pt[1], ang],
                               ['fields_autoplaced'], ['effects', ['font', ['size', 1.27, 1.27]], ['justify', just]],
                               ['uuid', uid()],
                               ['property', Q('Intersheetrefs'), Q('${INTERSHEET_REFS}'), ['at', pt[0], pt[1], 0],
                                font_hide()]])
        else:
            self.items.append(['label', Q(net), ['at', pt[0], pt[1], ang], ['fields_autoplaced'],
                               ['effects', ['font', ['size', 1.27, 1.27]], ['justify', just, 'bottom']],
                               ['uuid', uid()]])

    def pin_label(self, ref, pin, net, length=G, glob=False):
        end, (ox, oy) = self.stub(ref, pin, length)
        d = {(1, 0): 'R', (-1, 0): 'L', (0, -1): 'U', (0, 1): 'D'}[(ox, oy)]
        self.label(net, end, d, glob)

    def pin_power(self, ref, pin, net, length=G):
        end, (ox, oy) = self.stub(ref, pin, length) if length else (self.P(ref, pin), self.placed[ref][str(pin)][1])
        rot = 0
        if (ox, oy) in ((1, 0), (-1, 0)):     # sideways: point the symbol away from the pin
            if net == 'GND':
                rot = 270 if ox == -1 else 90
            else:
                rot = 90 if ox == -1 else 270
        self.power(net, end, rot)

    def nc(self, ref, pin):
        self.items.append(['no_connect', ['at', *self.P(ref, pin)], ['uuid', uid()]])

    def text(self, x, y, s, size=2.0, bold=True):
        eff = ['font', ['size', size, size]] + (['bold'] if bold else [])
        self.items.append(['text', Q(s), ['at', x, y, 0], ['effects', eff, ['justify', 'left', 'bottom']],
                           ['uuid', uid()]])

    # -- finish -------------------------------------------------------------
    def finish(self):
        ends = {}
        for a, b in self.wires:
            for pt in (a, b):
                ends[pt] = ends.get(pt, 0) + 1
        for pt in self.pinpts:
            if pt in ends:
                ends[pt] += 1

        def inside(pt, seg):
            (x1, y1), (x2, y2) = seg
            if x1 == x2 == pt[0]:
                return min(y1, y2) < pt[1] < max(y1, y2)
            if y1 == y2 == pt[1]:
                return min(x1, x2) < pt[0] < max(x1, x2)
            return False
        junctions = {pt for pt, n in ends.items() if n >= 3}
        for pt in list(ends):
            if any(inside(pt, s) for s in self.wires):
                junctions.add(pt)
        for pt in self.pinpts:
            for s in self.wires:
                if inside(pt, s):
                    raise SystemExit(f'pin at {pt} lies on the middle of wire {s}')
        for a, b in self.wires:
            self.items.append(['wire', ['pts', ['xy', *a], ['xy', *b]],
                               ['stroke', ['width', 0], ['type', 'default']], ['uuid', uid()]])
        for pt in sorted(junctions):
            self.items.append(['junction', ['at', *pt], ['diameter', 0], ['color', 0, 0, 0, 0], ['uuid', uid()]])
        return ['kicad_sch', ['version', '20230121'], ['generator', 'eeschema'],
                ['uuid', self.root], ['paper', Q('A3')],
                ['title_block', ['title', Q('HydraPurr carrier PCB')], ['date', Q('2026-11-13')],
                 ['rev', Q('draft 2')],
                 ['comment', 1, Q('Feather ESP32-S3 Reverse TFT + Adalogger FeatherWing, feeder driver, sensor connectors')]],
                ['lib_symbols'] + list(self.libsyms.values())] + self.items + \
               [['sheet_instances', ['path', Q('/'), ['page', Q('1')]]]]


def build():
    S = Sheet()
    P, W = S.P, S.wire

    # ===== Feather ==========================================================
    S.text(25.4, 50.8, 'FEATHER on ADALOGGER')
    S.place('A1', 63.5, 101.6, refpos=(-12.7, 41.91))
    for pin, net in S.parts['A1'][6].items():
        if net is None:
            S.nc('A1', pin)
        elif net == '+3V3':
            S.pin_power('A1', pin, '+3V3', 2.54)
        elif net == '+5V':
            S.pin_power('A1', pin, '+5V', 7.62)
        elif net == 'GND':
            S.pin_power('A1', pin, 'GND', 2.54)
        else:
            S.pin_label('A1', pin, net)
    # power flags: these rails come from off this board (USB, Feather regulator)
    S.text(25.4, 154.94, 'Power flags (supplied by the Feather)', 1.27, False)
    for i, net in enumerate(['+5V', '+3V3', 'GND']):
        x = 30.48 + i * 25.4
        S.power(net, (x, 165.1))
        S.power('PWR_FLAG', (x + 10.16, 165.1))
        W((x, 165.1), (x + 10.16, 165.1))

    # ===== Sheet 1: feeder driver ==========================================
    S.text(127, 30.48, 'FEEDER DRIVER (high-side switch)', 1.75)
    S.text(127, 34.29, 'A0 high: Q2 on, Q1 gate at 0 V, feeder runs. A0 floating: R2 keeps Q2 off, R4 keeps Q1 off.',
           1.27, False)
    rail = 50.8
    S.place('C1', 134.62, rail + 6.35)
    S.place('U1', 152.4, rail, refpos=(-7.62, -8.89))
    S.place('C2', 172.72, rail + 6.35)
    S.place('F1', 190.5, rail, rot=90, refpos=(-3.81, -6.35))
    S.place('R4', 200.66, rail + 3.81)
    S.place('Q1', 215.9, rail + 7.62, mirror='x', refpos=(5.08, -3.81))
    S.power('+5V', (129.54, rail))
    W((129.54, rail), (134.62, rail), P('U1', 3))
    W((134.62, rail), P('C1', 1))
    S.pin_power('C1', 2, 'GND', 0)
    S.pin_power('U1', 2, 'GND', 0)
    W(P('U1', 1), (167.64, rail), (172.72, rail), P('F1', 1))
    S.power('+12V', (167.64, rail))
    W((172.72, rail), P('C2', 1))
    S.pin_power('C2', 2, 'GND', 0)
    W(P('F1', 2), (200.66, rail), (P('Q1', 3)[0], rail), P('Q1', 3))
    S.label('+12V_F', (209.55, rail), 'R')
    gate = P('R4', 2)
    W(gate, P('Q1', 1))
    S.place('Q2', gate[0] - 2.54, gate[1] + 12.7)
    W(P('Q2', 3), gate)
    S.pin_power('Q2', 1, 'GND', 0)
    base_y = P('Q2', 2)[1]
    S.place('R2', 190.5, base_y + 3.81, refpos=(-2.54, 1.27, 'right'))
    S.place('R1', 185.42, base_y, rot=90, refpos=(-3.81, -6.35))
    W(P('R1', 2), P('R2', 1), P('Q2', 2))
    S.pin_power('R2', 2, 'GND', 0)
    S.pin_label('R1', 1, 'FEEDER_EN')
    fp_y = 83.82
    drain = P('Q1', 2)
    S.place('D1', 228.6, fp_y + 6.35, rot=270, refpos=(-6.35, -1.27))
    S.place('C3', 241.3, fp_y + 6.35)
    S.place('R3', 259.08, fp_y + 6.35)
    S.place('LED1', 259.08, fp_y + 17.78, rot=90, refpos=(6.35, -1.27))
    S.place('J1', 284.48, fp_y + 2.54, refpos=(2.54, -6.35))
    W(drain, (drain[0], fp_y), (228.6, fp_y), (241.3, fp_y), (259.08, fp_y), P('J1', 1))
    S.label('FEEDER+', (264.16, fp_y), 'R')
    for ref in ('D1', 'C3', 'R3'):
        W((P(ref, 1)[0], fp_y), P(ref, 1))
    S.pin_power('D1', 2, 'GND', 0)
    S.pin_power('C3', 2, 'GND', 0)
    W(P('R3', 2), P('LED1', 2))
    S.pin_power('LED1', 1, 'GND', 0)
    S.nc('J1', 2)
    j3 = P('J1', 3)
    W(j3, (j3[0] - 5.08, j3[1]))
    S.power('GND', (j3[0] - 5.08, j3[1]))

    # ===== Sheet 2, row 1: touch, Sharp, contact LED, I2C =====================
    S.text(127, 121.92, 'TOUCH WIRE', 1.75)
    S.place('R5', 147.32, 134.62, rot=90, refpos=(-3.81, -6.35))
    S.place('J2', 165.1, 137.16, refpos=(2.54, -6.35))
    S.pin_label('R5', 1, 'TOUCH')
    W(P('R5', 2), P('J2', 1))
    S.nc('J2', 2)
    j = P('J2', 3)
    W(j, (j[0] - 5.08, j[1]))
    S.power('GND', (j[0] - 5.08, j[1]))
    S.text(127, 147.32, 'Short trace, no ground pour under it.', 1.27, False)

    S.text(203.2, 121.92, 'WATER LEVEL (SHARP)', 1.75)
    S.place('J3', 251.46, 137.16, refpos=(2.54, -6.35))
    S.place('R6', 233.68, 134.62, rot=270, refpos=(-3.81, -6.35))
    S.place('C6', 226.06, 140.97, refpos=(-10.16, 1.27))
    S.place('C4', 213.36, 158.75, refpos=(-2.54, -1.27, 'right'))
    S.place('C5', 226.06, 158.75)
    W(P('J3', 1), P('R6', 1))
    W(P('R6', 2), (226.06, 134.62), (220.98, 134.62))
    S.label('SHARP_VO', (220.98, 134.62), 'L')
    W((226.06, 134.62), P('C6', 1))
    S.pin_power('C6', 2, 'GND', 0)
    j = P('J3', 2)
    W(j, (240.03, j[1]), (240.03, j[1] + 2.54))
    S.power('GND', (240.03, j[1] + 2.54))
    j = P('J3', 3)
    W(j, (243.84, j[1]), (243.84, 152.4), (226.06, 152.4), (213.36, 152.4), (205.74, 152.4))
    S.power('+5V', (205.74, 152.4))
    W((226.06, 152.4), P('C5', 1))
    W((213.36, 152.4), P('C4', 1))
    S.pin_power('C4', 2, 'GND', 0)
    S.pin_power('C5', 2, 'GND', 0)

    S.text(274.32, 121.92, 'CONTACT LED', 1.75)
    S.place('R13', 289.56, 134.62, rot=90, refpos=(-3.81, -6.35))
    S.place('LED2', 297.18, 142.24, rot=90, refpos=(6.35, -1.27))
    S.place('R14', 289.56, 154.94, rot=90, refpos=(0, -6.35))
    S.place('J5', 312.42, 157.48, refpos=(2.54, -6.35))
    W((276.86, 134.62), (281.94, 134.62), P('R13', 1))
    S.label('LED_CONTACT', (276.86, 134.62), 'L')
    W(P('R13', 2), (P('LED2', 2)[0], 134.62), P('LED2', 2))
    S.pin_power('LED2', 1, 'GND', 0)
    W((281.94, 134.62), (281.94, 154.94), P('R14', 1))
    W(P('R14', 2), P('J5', 1))
    S.nc('J5', 2)
    j = P('J5', 3)
    W(j, (j[0] - 5.08, j[1]), (j[0] - 5.08, j[1] + 2.54))
    S.power('GND', (j[0] - 5.08, j[1] + 2.54))

    S.text(325.12, 121.92, 'I2C (STEMMA order)', 1.75)
    S.place('J6', 350.52, 137.16, refpos=(2.54, -7.62))
    S.pin_label('J6', 1, 'GND', 2.54, glob=True)
    S.pin_label('J6', 2, '+3V3', 12.7, glob=True)
    S.pin_label('J6', 3, 'SDA', 5.08)
    S.pin_label('J6', 4, 'SCL', 5.08)

    # ===== Sheet 2, row 2: RFID supply, RFID data/reset, spare, holes =========
    S.text(127, 180.34, 'RFID SUPPLY', 1.75)
    S.text(127, 184.15, 'JP2 1-2 = USB 5 V via FB1, C7 (default). Fit U2, C8, C9 and set JP2 2-3 for 6 V.', 1.27, False)
    S.place('FB1', 139.7, 190.5, rot=90, refpos=(0, 5.08))
    S.place('C7', 152.4, 196.85)
    S.place('C8', 137.16, 222.25)
    S.place('U2', 152.4, 215.9, refpos=(-5.08, -10.16))
    S.place('C9', 167.64, 222.25)
    S.place('JP2', 185.42, 205.74, refpos=(2.54, -6.35))
    S.power('+5V', (127, 190.5))
    W((127, 190.5), P('FB1', 1))
    W(P('FB1', 2), (152.4, 190.5), (175.26, 190.5), (175.26, P('JP2', 1)[1]), P('JP2', 1))
    S.label('+5V_RFID', (157.48, 190.5), 'R')
    W((152.4, 190.5), P('C7', 1))
    S.pin_power('C7', 2, 'GND', 0)
    S.power('+12V', (127, 215.9))
    W((127, 215.9), (137.16, 215.9), P('U2', 1))
    W((137.16, 215.9), P('C8', 1))
    S.pin_power('C8', 2, 'GND', 0)
    S.pin_power('U2', 2, 'GND', 0)
    W(P('U2', 3), (167.64, 215.9), (172.72, 215.9), (172.72, P('JP2', 3)[1]), P('JP2', 3))
    S.power('+6V', (172.72, 215.9))
    W((167.64, 215.9), P('C9', 1))
    S.pin_power('C9', 2, 'GND', 0)
    S.pin_label('JP2', 2, 'RFID_VCC')

    S.text(254, 180.34, 'RFID DATA and RESET', 1.75)
    S.text(254, 184.15, 'TX high = RST low (inverted, as the old board).', 1.27, False)
    S.text(254, 241.3, 'JP1 open = 5 V TX (default). Close only for the 3.3 V TX pad.', 1.27, False)
    S.place('J4', 317.5, 205.74, refpos=(2.54, -7.62))
    p1, p2, p3, p4 = (P('J4', n) for n in (1, 2, 3, 4))
    S.place('R10', 297.18, 194.31)
    W(p1, (304.8, p1[1]), (304.8, 190.5), (297.18, 190.5), (289.56, 190.5))
    S.label('RFID_VCC', (289.56, 190.5), 'L')
    W(P('R10', 2), (297.18, p2[1]))
    S.place('Q3', 281.94, p2[1] + 5.08)
    W(p2, (297.18, p2[1]), P('Q3', 3))
    S.pin_power('Q3', 1, 'GND', 0)
    qb = P('Q3', 2)
    S.place('R9', 271.78, qb[1] + 3.81, refpos=(-2.54, 1.27, 'right'))
    S.place('R8', 264.16, qb[1], rot=90, refpos=(-3.81, -6.35))
    W(P('R8', 2), P('R9', 1), qb)
    S.pin_power('R9', 2, 'GND', 0)
    S.pin_label('R8', 1, 'RFID_RST')
    W(p3, (302.26, p3[1]), (302.26, 226.06))
    W(p4, (309.88, p4[1]), (309.88, p4[1] + 2.54))
    S.power('GND', (309.88, p4[1] + 2.54))
    S.place('R11', 294.64, 226.06, rot=270, refpos=(0, -6.35))
    S.place('R12', 287.02, 229.87, refpos=(-10.16, 1.27))
    S.place('JP1', 295.91, 236.22, rot=270, refpos=(11.43, -1.27))
    W((302.26, 226.06), P('R11', 1))
    W(P('R11', 2), (289.56, 226.06), (287.02, 226.06), (281.94, 226.06))
    S.label('RFID_RX', (281.94, 226.06), 'L')
    S.pin_power('R12', 2, 'GND', 0)
    jp1, jp2 = P('JP1', 1), P('JP1', 2)
    W((302.26, 226.06), (302.26, jp1[1]), jp1)
    W(jp2, (289.56, jp2[1]), (289.56, 226.06))

    S.text(345.44, 180.34, 'SPARE PINS, MOUNTING HOLES', 1.75)
    S.place('J7', 378.46, 223.52, refpos=(2.54, -17.78))
    for pin, net in S.parts['J7'][6].items():
        is_pwr = net in ('+5V', '+3V3', 'GND')
        S.pin_label('J7', pin, net, 2.54 if is_pwr and pin != '2' else 12.7, glob=is_pwr)
    for ref, x, y in (('H1', 345.44, 193.04), ('H2', 358.14, 193.04),
                      ('H3', 345.44, 203.2), ('H4', 358.14, 203.2)):
        S.place(ref, x, y)

    S.text(25.4, 281.94, 'All parts through-hole. DNP: C6, U2, C8, C9. '
                         'Generated by tools/gen_schematic.py; check with --check.', 1.5, False)
    return S.finish(), S.custom


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
    """Export the netlist with kicad-cli; compare pin groups with PARTS."""
    out = os.path.join(HERE, 'check.net')
    subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format', 'kicadsexpr',
                    '-o', out, SCH], check=True, capture_output=True)
    tree = parse(open(out).read())[0]
    os.remove(out)
    got = {}
    names = {}
    for net in find(find(tree, 'nets')[0], 'net'):
        name = find(net, 'name')[0][1]
        members = frozenset((find(n, 'ref')[0][1], find(n, 'pin')[0][1]) for n in find(net, 'node'))
        for m in members:
            got[m] = members
            names[m] = name
    want = {}
    for ref, _, _, _, _, _, nets, _, _ in PARTS:
        if ref.startswith('#'):
            continue
        for p, n in nets.items():
            if n is not None:
                want.setdefault(n, set()).add((ref, p))
    bad = 0
    for n, members in sorted(want.items()):
        any_m = next(iter(members))
        have = got.get(any_m, frozenset())
        if have != frozenset(members):
            bad += 1
            print(f'NET {n}: want {sorted(members)}')
            print(f'      netlist {names.get(any_m)}: {sorted(have)}')
        if len(members) < 2:
            bad += 1
            print(f'NET {n} has only one pin')
    print(f'{len(want)} nets, {sum(len(m) for m in want.values())} connections, {bad} problems')
    return bad


if __name__ == '__main__':
    if '--check' in sys.argv:
        sys.exit(1 if check() else 0)
    write('--force' in sys.argv)
