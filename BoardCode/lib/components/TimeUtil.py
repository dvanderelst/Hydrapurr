import time as _time

# Shared time utilities for consistent RTC + monotonic timestamps.

rtc = None            # shared RTC instance
timebase_ready = False
boot_mono_ms = None
boot_epoch = None

def init_timebase():
    global rtc, timebase_ready, boot_mono_ms, boot_epoch
    if timebase_ready:
        return True
    if rtc is None:
        from components.MyRTC import MyRTC
        rtc = MyRTC()
    boot_mono_ms = monotonic_ms()
    try:
        boot_epoch = int(_time.mktime(rtc.now()))
    except Exception:
        boot_epoch = 0
    timebase_ready = True
    return True

def monotonic_ms():
    try:
        return int(_time.monotonic() * 1000)
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
    base_seconds = (boot_epoch or 0) + (delta_ms // 1000)
    frac_ms = int(delta_ms % 1000)
    try:
        t = _time.localtime(base_seconds)
    except Exception:
        t = rtc.now()
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
