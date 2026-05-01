# Run this script to manually test the feeder relay.
# Cycles the relay on for `on_seconds`, off for `off_seconds`, repeatedly.
# Driven directly via MyDigital so the test works without OLED/RTC/SD/BT.

import time
import board
from components import MyDigital

# --- Configuration ---
on_seconds = 2.0    # how long the feeder stays on per cycle
off_seconds = 5.0   # how long the feeder stays off per cycle
cycles = None       # int for a fixed number of cycles, or None to loop forever

# Feeder relay is wired to board.D6 via an NPN transistor (see HydraPurr.py).
feeder = MyDigital(pin=board.D6, direction='output')
feeder.write(False)  # start in a known-off state

label = f"{cycles} cycles" if cycles else "forever (reset to stop)"
print(f"TestFeeder: {on_seconds}s on / {off_seconds}s off, {label}")

count = 0
try:
    while cycles is None or count < cycles:
        count += 1
        print(f"[{count}] feeder ON")
        feeder.write(True)
        time.sleep(on_seconds)
        print(f"[{count}] feeder OFF")
        feeder.write(False)
        time.sleep(off_seconds)
finally:
    # Make sure the relay is open if the script exits for any reason.
    feeder.write(False)
    print("TestFeeder: done, feeder off")
