# Capacitive touch test (TestTouch.py) for the Adafruit ESP32-S3 Reverse TFT Feather.
#
# Wire a short jumper (or a piece of foil / a metal strip) to one of the pins
# listed in `pin_names` below and touch it. The script prints the raw touch
# reading for every pin it could claim, marking the ones that read as touched.
#
# Note: on the ESP32-S3 only GPIO1-GPIO14 have the capacitive touch peripheral,
# so on this board the usable pins run from SDA up to A4:
#   SDA(3), SCL(4), D5, D6, A5(8), D9, D10, D11, D12, D13, A4(14)
# Caveats: GPIO1/GPIO2 are the D1/D2 buttons, D13 also drives the red LED, and
# A0-A3 are GPIO18/17/16/15 so they are *not* touch capable. (TX/RX are GPIO39
# and GPIO38 on the Reverse TFT, unlike the plain TFT Feather - also no touch.)

import time
import board
import touchio

# --- Configuration ---
pin_names = ["A5", "D5", "D6", "D9"]  # pins to test, in print order
sample_period_s = 0.2                 # delay between prints
baseline_samples = 20                 # reads used to measure the untouched level
touch_margin = 1.15                   # touched when raw > baseline * this

print("TestTouch: setting up capacitive touch inputs")

pins = []       # (name, TouchIn, baseline)
for name in pin_names:
    pin = getattr(board, name, None)
    if pin is None:
        print(f"  {name}: no such pin on this board, skipping")
        continue
    try:
        touch = touchio.TouchIn(pin)
    except Exception as error:          # pin has no touch peripheral, or in use
        print(f"  {name}: unusable for touch ({error})")
        continue

    # Measure the untouched level ourselves so the threshold does not depend on
    # whatever default the core picked at construction time.
    total = 0
    for _ in range(baseline_samples):
        total += touch.raw_value
        time.sleep(0.01)
    baseline = total / baseline_samples
    touch.threshold = int(baseline * touch_margin)

    print(f"  {name}: baseline {baseline:.0f}, threshold {touch.threshold}")
    pins.append((name, touch, baseline))

if not pins:
    raise SystemExit("TestTouch: no usable touch pins, check pin_names")

print("Keep your hands off the wires while the baselines are measured above.")
print("Touch a pin to see its value jump. Reset the board to stop.")
print("-" * (12 * len(pins)))
print("".join(f"{name:>12}" for name, _, _ in pins))

try:
    while True:
        cells = []
        for name, touch, baseline in pins:
            raw = touch.raw_value
            mark = "*" if touch.value else " "
            cells.append(f"{raw:>10d}{mark} ")
        print("".join(cells))
        time.sleep(sample_period_s)
finally:
    for _, touch, _ in pins:
        touch.deinit()
    print("TestTouch: done")
