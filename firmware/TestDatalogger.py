# Datalogger test for the Feather ESP32-S3 Reverse TFT + Adalogger FeatherWing.
#
# Checks the two parts of the Adalogger wing, one step at a time, and prints a
# PASS/FAIL line per step plus a summary at the end:
#   1. I2C bus  - scan for the PCF8523 RTC at address 0x68.
#   2. RTC      - read the time, the "lost power" flag, the battery-switchover
#                 setting and the low-battery flag; optionally set the time;
#                 check that the clock is ticking.
#   3. SD card  - mount on the shared SPI bus (CS = D10), write a file, append
#                 to it, read it back, verify the contents, report free space,
#                 and time a burst of small appends (like licks.dat logging).
#
# The TFT also sits on board.SPI(), and it is active while this runs (the
# serial console is shown on it), so step 3 also tests SD + display sharing.
#
# To set the RTC: fill in SET_TIME below, run once, then put it back to None.
# Setting the time also turns on battery switchover, so the coin cell keeps
# the clock running when USB is unplugged.

import os
import time
import board
import storage
import sdcardio

# --- Configuration ---
SET_TIME = None             # e.g. (2026, 10, 19, 16, 30, 0) = y, m, d, h, min, s
SD_CS = board.D10           # Adalogger FeatherWing chip select
SD_BAUDRATE = 8_000_000
MOUNT_POINT = "/sd"
TEST_FILE = MOUNT_POINT + "/datalogger_test.txt"
BURST_FILE = MOUNT_POINT + "/datalogger_burst.csv"
BURST_LINES = 50            # appends timed in the burst test
RTC_ADDRESS = 0x68

results = []                # (step, ok, detail)


def report(step, ok, detail=""):
    results.append((step, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {step}" + (f": {detail}" if detail else ""))


def fmt_time(t):
    return (f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d} "
            f"{t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}")


print("TestDatalogger: Feather ESP32-S3 Reverse TFT + Adalogger FeatherWing")
print("-" * 60)

# --- 1. I2C bus --------------------------------------------------------------
i2c = None
try:
    i2c = board.I2C()
    while not i2c.try_lock():
        pass
    try:
        found = i2c.scan()
    finally:
        i2c.unlock()
    found_hex = [hex(a) for a in found]
    report("I2C scan", RTC_ADDRESS in found,
           f"devices {found_hex}, expect {hex(RTC_ADDRESS)}")
except Exception as e:
    report("I2C scan", False, repr(e))

# --- 2. RTC ------------------------------------------------------------------
rtc = None
if i2c is not None:
    try:
        from adafruit_pcf8523.pcf8523 import PCF8523
        rtc = PCF8523(i2c)
        report("RTC init", True)
    except Exception as e:
        report("RTC init", False, repr(e))

if rtc is not None:
    try:
        if SET_TIME is not None:
            y, mo, d, h, mi, s = SET_TIME
            # weekday is not used by our code; the PCF8523 just stores it
            rtc.datetime = time.struct_time((y, mo, d, h, mi, s, 0, -1, -1))
            print(f"  RTC set to {fmt_time(rtc.datetime)} - set SET_TIME back to None")

        t1 = rtc.datetime
        lost = rtc.lost_power
        pm = rtc.power_management
        low = rtc.battery_low
        print(f"  RTC time          : {fmt_time(t1)}")
        print(f"  lost_power        : {lost}  (True = time not valid, set it)")
        print(f"  power_management  : {pm:03b}  (000 = battery switchover on, "
              f"111 = off: clock stops without USB)")
        print(f"  battery_low       : {low}  (only meaningful with switchover on)")
        report("RTC time valid", not lost and 2024 <= t1.tm_year <= 2099,
               fmt_time(t1) + (" - lost power" if lost else ""))
        report("RTC battery switchover", pm == 0,
               "on" if pm == 0 else "off - set the time once to turn it on")
        if pm == 0:
            report("RTC backup battery", not low, "low!" if low else "ok")

        # The PCF8523 should advance by ~2 s while we wait 2.2 s.
        time.sleep(2.2)
        t2 = rtc.datetime
        elapsed = time.mktime(t2) - time.mktime(t1)
        report("RTC ticking", 1 <= elapsed <= 3, f"advanced {elapsed} s in 2.2 s")
    except Exception as e:
        report("RTC read", False, repr(e))

# --- 3. SD card --------------------------------------------------------------
mounted = False
try:
    try:
        storage.getmount(MOUNT_POINT)
        mounted = True               # already mounted by an earlier run
    except Exception:
        spi = board.SPI()            # shared with the TFT
        sd = sdcardio.SDCard(spi, SD_CS, baudrate=SD_BAUDRATE)
        storage.mount(storage.VfsFat(sd), MOUNT_POINT)
        mounted = True
    report("SD mount", True, f"at {MOUNT_POINT}")
except Exception as e:
    report("SD mount", False, f"{e!r} - card inserted? FAT32 formatted?")

if mounted:
    stamp = fmt_time(rtc.datetime) if rtc is not None else "no-rtc"
    line1 = f"write {stamp} mono={time.monotonic():.3f}"
    line2 = "append line 2"
    try:
        with open(TEST_FILE, "w") as f:
            f.write(line1 + "\n")
        with open(TEST_FILE, "a") as f:
            f.write(line2 + "\n")
        with open(TEST_FILE, "r") as f:
            back = f.read()
        ok = back == line1 + "\n" + line2 + "\n"
        report("SD write/append/read", ok,
               TEST_FILE if ok else f"read back {back!r}")
    except Exception as e:
        report("SD write/append/read", False, repr(e))

    try:
        st = os.statvfs(MOUNT_POINT)
        free_mb = st[0] * st[4] / (1024 * 1024)
        total_mb = st[0] * st[2] / (1024 * 1024)
        report("SD free space", free_mb > 1, f"{free_mb:.0f} MB free of {total_mb:.0f} MB")
    except Exception as e:
        report("SD free space", False, repr(e))

    # Burst of small appends, opening the file each time, the way MyStore
    # writes licks.dat. Tells us how long one log write blocks the loop.
    try:
        with open(BURST_FILE, "w") as f:
            f.write("time,mono_ms,i\n")
        worst_ms = 0
        t_start = time.monotonic()
        for i in range(BURST_LINES):
            t0 = time.monotonic()
            with open(BURST_FILE, "a") as f:
                f.write(f"{stamp},{int(t0 * 1000)},{i}\n")
            worst_ms = max(worst_ms, (time.monotonic() - t0) * 1000)
        mean_ms = (time.monotonic() - t_start) * 1000 / BURST_LINES
        with open(BURST_FILE, "r") as f:
            n_lines = sum(1 for _ in f)
        ok = n_lines == BURST_LINES + 1
        report("SD burst append", ok,
               f"{BURST_LINES} lines, mean {mean_ms:.1f} ms, worst {worst_ms:.1f} ms"
               + ("" if ok else f", found {n_lines} lines"))
    except Exception as e:
        report("SD burst append", False, repr(e))

    try:
        print(f"  files on SD: {sorted(os.listdir(MOUNT_POINT))}")
    except Exception as e:
        print(f"  could not list SD: {e!r}")

# --- Summary -----------------------------------------------------------------
print("-" * 60)
n_fail = sum(1 for _, ok, _ in results if not ok)
for step, ok, detail in results:
    print(f"  {'ok  ' if ok else 'FAIL'}  {step}")
print(f"TestDatalogger: {len(results) - n_fail}/{len(results)} passed")
