
# Capacitive touch test for the Adafruit Feather ESP32-S3 TFT.
#
# Wire a short jumper (or a piece of foil / a metal strip) to one of the pins
# listed in `pin_names` below and touch it. The script prints the raw touch
# reading for every pin it could claim, marking the ones that read as touched.
#
# Note: on the ESP32-S3 only GPIO1-GPIO14 have the capacitive touch peripheral.
# On this board that means: TX(1), RX(2), SDA(3), SCL(4), D5, D6, A5(8),
# D9, D10, D11, D12, D13 and A4(14). A0-A3 are *not* touch capable.

import time
import board
import touchio
import digitalio

# --- Configuration ---
pin_name = "D12"  
sample_period_s = 0.2                 # delay between prints
baseline_samples = 20                 # reads used to measure the untouched level
touch_margin = 1.15                   # touched when raw > baseline * this

led = digitalio.DigitalInOut(board.LED)
led.direction = digitalio.Direction.OUTPUT
pin = getattr(board, pin_name, None)


touch = touchio.TouchIn(pin)

total = 0
for _ in range(baseline_samples):
    total += touch.raw_value
    time.sleep(0.01)
baseline = total / baseline_samples
threshold = baseline * touch_margin

print('Threshold:', threshold)
touch.threshold = int(threshold)

while True:
    raw = touch.raw_value
    binary = touch.value
    led.value = binary * 1.0
    print(raw, binary)
    time.sleep(sample_period_s)


