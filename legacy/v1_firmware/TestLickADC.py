# Run this script to sample the lick contact-sensor ADC in a loop.
# Prints raw (0-65535) and voltage (0.0-3.3 V) so you can pick a value for
# Settings.lick_threshold (binary_state = 1 if lick_voltage < lick_threshold).
# Standalone: uses MyADC directly, no OLED/RTC/SD/BT needed.

import time
from components import MyADC

# --- Configuration ---
sample_period_s = 0.1   # delay between prints
samples_per_read = 1    # set >1 to print a mean over N quick samples

# Lick contact sensor is on ADC channel 1 (see HydraPurr.py: self.lick = MyADC(1)).
lick = MyADC(1)

print("TestLickADC: sampling lick ADC (channel 1). Reset board to stop.")
print("touch / release the contact to see the high/low voltage range")
print("-" * 60)
print(f"{'raw':>8}  {'volts':>7}")

try:
    while True:
        if samples_per_read <= 1:
            v = lick.read()
            raw = lick.raw()
        else:
            v = lick.mean(samples_per_read)
            raw = int((v / 3.3) * 65535)
        print(f"{raw:>8d}  {v:>7.3f}")
        time.sleep(sample_period_s)
finally:
    lick.deinit()
    print("TestLickADC: done")
