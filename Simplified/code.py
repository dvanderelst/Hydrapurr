# Simplified HydraPurr - entry point.
#
# Runs the lick monitor (MainLoop.py). The standalone test scripts are run by
# hand from Thonny instead of from here:
#   TestDatalogger.py - Adalogger FeatherWing: I2C scan, PCF8523 RTC, SD card
#   SetTime.py        - set the RTC
#   TestTouch.py      - capacitive touch readings on several pins
#   test.py           - single touch pin driving the red LED
#
# Hold D2 while the board starts to run the heartbeat test
# (TestHeartbeat.py) instead of the monitor; it works on a battery.
# (TestUpload.py, the upload speed test, is done; run it from Thonny.)
#
# To run another test at boot instead, replace the lines below with e.g.
#   import TestDatalogger

import board
import digitalio

d2 = digitalio.DigitalInOut(board.D2)
d2.switch_to_input(pull=digitalio.Pull.DOWN)   # reads True while pressed
heartbeat_test = d2.value
d2.deinit()

if heartbeat_test:
    print('Simplified HydraPurr: D2 held, heartbeat test')
    import TestHeartbeat
    TestHeartbeat.run()
else:
    from components.MySD import mount_sd_card
    from components.MySystemLog import INFO
    import MainLoop

    print('Simplified HydraPurr: running...')
    sd_ok = mount_sd_card()
    MainLoop.main_loop(level=INFO, sd_ok=sd_ok)
