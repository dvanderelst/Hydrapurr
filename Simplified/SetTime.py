# Set the PCF8523 RTC on the Adalogger FeatherWing.
#
# Fill in the fields below and run this from Thonny (or any serial console).
# A field set to None keeps the RTC's current value, so e.g. only hr/mn/sc can
# be corrected. The clock is set the moment you press Enter, so pick a time a
# few seconds ahead and press Enter when your watch reaches it.
#
# Keeping fields only makes sense when the RTC holds a sane time: after a
# power loss it can read garbage like month 15, so set every field then.
#
# Setting the time through the library also turns on battery switchover, so
# the coin cell keeps the clock running when USB is unplugged.
#
# Same behaviour as MyRTC.set_time in BoardCode, without the HydraPurr object.

import time
import board
from adafruit_pcf8523.pcf8523 import PCF8523

# To keep a field, set it to None
yr = 2026
mt = 10
dy = 19
hr = 17
mn = 0
sc = 0


def weekday_from_ymd(y, m, d):
    # Tomohiko Sakamoto's algorithm -> Monday=0..Sunday=6
    table = [0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4]
    y2 = y - (1 if m < 3 else 0)
    w_sun0 = (y2 + y2 // 4 - y2 // 100 + y2 // 400 + table[m - 1] + d) % 7
    return (w_sun0 - 1) % 7


def norm_year(y):
    # Map 0..99 -> 2000..2099; the PCF8523 only stores 2000..2099
    if 0 <= y <= 99:
        y = 2000 + y
    if not 2000 <= y <= 2099:
        print(f"Year must be 2000..2099, got {y}; clamping")
        y = min(max(y, 2000), 2099)
    return y


def show(label):
    t = rtc.datetime
    print(f"{label}: {t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d} "
          f"{t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}  "
          f"lost_power={rtc.lost_power}  "
          f"switchover={'on' if rtc.power_management == 0 else 'off'}")


def field(value, width=2):
    return "keep" if value is None else f"{value:0{width}d}"


print("=" * 60)
print("SetTime: set the real-time clock on the Adalogger FeatherWing")
print("=" * 60)
print("How to use this script:")
print("  1. Stop it now if the time below is not what you want (Ctrl-C,")
print("     or the Stop button in Thonny).")
print("  2. Open SetTime.py and edit yr, mt, dy, hr, mn, sc near the top.")
print("     Pick a time 30-60 s in the future. Use None to keep a field")
print("     as the clock has it now.")
print("  3. Save the file to the board and run it again.")
print("  4. Watch a clock. When it reaches the time you typed in, press")
print("     Enter in this window. The RTC is set at that moment.")
print()

rtc = PCF8523(board.I2C())
show("RTC now ")
if rtc.lost_power:
    print("  -> The RTC lost power, so its time is invalid. Fill in every")
    print("     field (no None) this time.")
if rtc.power_management != 0:
    print("  -> Battery backup is off. Setting the time turns it on.")
print()
print(f"Will set: {field(yr, 4)}-{field(mt)}-{field(dy)} "
      f"{field(hr)}:{field(mn)}:{field(sc)}")
print()
input(">>> Press Enter when your clock shows that time (Ctrl-C to cancel) ")

cur = rtc.datetime
year = norm_year(cur.tm_year if yr is None else yr)
month = cur.tm_mon if mt is None else mt
day = cur.tm_mday if dy is None else dy
hour = cur.tm_hour if hr is None else hr
minute = cur.tm_min if mn is None else mn
second = cur.tm_sec if sc is None else sc

if not (1 <= month <= 12 and 1 <= day <= 31 and hour <= 23 and minute <= 59 and second <= 59):
    print(f"Refusing to set an invalid time: {year}-{month}-{day} {hour}:{minute}:{second}")
    print("The RTC probably lost power - fill in every field instead of None.")
else:
    wday = weekday_from_ymd(year, month, day)
    rtc.datetime = time.struct_time((year, month, day, hour, minute, second, wday, -1, -1))
    show("RTC set")
    print()
    print("Done. Check that the time above is right and that it says")
    print("lost_power=False and switchover=on. Then run TestDatalogger.py")
    print("to confirm, and later unplug USB for a minute to check that the")
    print("coin cell keeps the clock running.")
