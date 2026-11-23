import time as _time

# Shared time utilities for consistent RTC + monotonic timestamps.

rtc = None            # shared RTC instance
timebase_ready = False
boot_mono_ms = None
boot_epoch = None

# Fallback epoch when there is no usable RTC: 2000-01-01 00:00:00.
# (Change vs the v1 firmware, which uses 0; but CircuitPython on the
# ESP32-S3 raises OverflowError for localtime() before 2000.)
FALLBACK_EPOCH = 946684800

def init_timebase():
    global rtc, timebase_ready, boot_mono_ms, boot_epoch
    if timebase_ready:
        return True
    if rtc is None:
        try:
            from components.MyRTC import MyRTC
            rtc = MyRTC()
        except Exception as e:
            print(f"[TimeUtil] RTC init failed: {e}")
            boot_mono_ms = monotonic_ms()
            boot_epoch = FALLBACK_EPOCH
            timebase_ready = True
            return False
    boot_mono_ms = monotonic_ms()
    try:
        boot_epoch = int(_time.mktime(rtc.now()))
    except Exception:
        boot_epoch = FALLBACK_EPOCH
    timebase_ready = True
    return True

def monotonic_ms():
    try:
        return _time.monotonic_ns() // 1_000_000
    except Exception:
        return 0

def _format_time(t, fmt):
    if fmt == 'iso':
        return f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d} {t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}"
    if fmt == 'dt':
        days = ("Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday")
        return f"{days[t.tm_wday]} {t.tm_mday}/{t.tm_mon}/{t.tm_year} {t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}"
    if fmt == 'epoch':
        try:
            return str(int(_time.mktime(t)))
        except Exception:
            return f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d} {t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}"
    return f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d} {t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}"

def _wall_time_from_mono(mono_now, fmt='iso', with_ms=True):
    if not timebase_ready:
        init_timebase()
    delta_ms = mono_now - (boot_mono_ms or 0)
    if delta_ms < 0:
        delta_ms = 0
    base_seconds = (boot_epoch or FALLBACK_EPOCH) + (delta_ms // 1000)
    frac_ms = int(delta_ms % 1000)
    try:
        t = _time.localtime(base_seconds)
    except Exception:
        t = rtc.now() if rtc is not None else _time.localtime(FALLBACK_EPOCH)
    base = _format_time(t, fmt)
    return f"{base}.{frac_ms:03d}" if with_ms else base

def monotonic_wall_time(fmt='iso', with_ms=True):
    mono_now = monotonic_ms()
    return _wall_time_from_mono(mono_now, fmt, with_ms)

def rtc_timestamp(fmt='iso', with_ms=True):
    if not timebase_ready:
        init_timebase()
    t = rtc.now()
    base = _format_time(t, fmt)
    if not with_ms:
        return base
    return base + ".000"

def timestamp(fmt='iso', with_ms=True):
    return monotonic_wall_time(fmt, with_ms)

def timestamp_pair(fmt='iso', with_ms=True):
    """Return (rtc_str, mono_ms)."""
    mono_now = monotonic_ms()
    return _wall_time_from_mono(mono_now, fmt, with_ms), mono_now


def set_clock(utc_ms, mono_ms):
    """Set the RTC to utc_ms (integer ms since 1970, UTC) as measured at
    monotonic time mono_ms, and re-anchor the timebase on it. Returns the
    step in ms (new wall time - old wall time for the same moment), or None
    when there was no timebase. Integers only (CircuitPython floats are too
    coarse for an epoch). Setting the PCF8523 also clears lost_power and
    turns on battery switchover. (Added in this firmware, 2026-11-16.)"""
    global boot_epoch, boot_mono_ms, timebase_ready
    old_ms = None
    if timebase_ready and boot_epoch is not None:
        old_ms = boot_epoch * 1000 + (mono_ms - boot_mono_ms)
    whole_s = utc_ms // 1000
    frac_ms = utc_ms % 1000
    # Timebase first: if writing the RTC chip fails (I2C), this boot's
    # timestamps are still right.
    boot_epoch = whole_s
    boot_mono_ms = mono_ms - frac_ms
    timebase_ready = True
    if rtc is not None:
        try:
            rtc.rtc.datetime = _time.localtime(whole_s)
        except Exception as e:
            print(f"[TimeUtil] could not write the RTC: {e!r}")
    return None if old_ms is None else utc_ms - old_ms
