# Simplified HydraPurr - entry point.
#
# Runs the lick monitor (MainLoop.py). The standalone test scripts are run by
# hand from Thonny instead of from here:
#   TestDatalogger.py - Adalogger FeatherWing: I2C scan, PCF8523 RTC, SD card
#   SetTime.py        - set the RTC
#   TestTouch.py      - capacitive touch readings on several pins
#   test.py           - single touch pin driving the red LED
#
# To run a test at boot instead, replace the lines below with e.g.
#   import TestDatalogger

from components.MySD import mount_sd_card
from components.MySystemLog import INFO
import MainLoop

print('Simplified HydraPurr: running...')
sd_ok = mount_sd_card()
MainLoop.main_loop(level=INFO, sd_ok=sd_ok)
