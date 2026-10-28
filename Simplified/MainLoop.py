"""
MainLoop.py - Simplified HydraPurr main loop (recording version)

For now the device only records: the touch wire and the float sensor are
sampled every raw_log_interval_ms and written to the SD card as one raw
stream (RawRecorder). Licks and water-level changes are found offline.

TouchSensor still computes a live contact state (0/1) against its tracking
baseline. It is stored in the stream and shown on the TFT as a quick check,
but nothing depends on it.

Press D1 to pause recording and serve the SD card over the board's own WiFi
network (DownloadMode.py); press D1 again to resume.

Bout detection and feeding (BoutDetection.py, LickSensor.py) are not used in
this version; they stay in lib/ for later.
"""

import time
import traceback
import board
import digitalio

import Settings
from components import TimeUtil
from components import MySD
from components.MySystemLog import setup_system_log, set_system_log_level, flush, teardown
from components.MySystemLog import INFO, info, warn, error
from TouchSensor import TouchSensor
from WaterSensor import WaterSensor
from RawRecorder import RawRecorder
from StatusDisplay import StatusDisplay
import DownloadMode

GREEN, YELLOW, RED, WHITE = 0x00FF00, 0xFFFF00, 0xFF4040, 0xFFFFFF


def now_ms():
    return time.monotonic_ns() // 1_000_000


def log_settings():
    info('[Settings] --- snapshot at startup ---')
    for name in sorted(dir(Settings)):
        if name.startswith('_'):
            continue
        value = getattr(Settings, name)
        if callable(value) or type(value).__name__ == 'module':
            continue
        if name == 'wifi_password' and value:
            value = '<set>'      # from settings.toml; keep it out of the log
        info(f'[Settings] {name} = {value}')
    info('[Settings] --- end snapshot ---')


def log_reset_reason():
    """Why the board last restarted: e.g. BROWNOUT (power dip), PANIC
    (crash), POWER_ON, RESET_PIN. Read it in system.log after an unexpected
    restart."""
    try:
        import microcontroller
        import supervisor
        info(f'[Main Loop] reset reason: {microcontroller.cpu.reset_reason}, '
             f'safe mode reason: {supervisor.runtime.safe_mode_reason}')
    except Exception as e:
        warn(f'[Main Loop] could not read reset reason: {e!r}')


def check_rtc():
    """Return True when the RTC time can be trusted."""
    TimeUtil.init_timebase()
    rtc = TimeUtil.rtc
    if rtc is None:
        warn('[Main Loop] RTC not found: timestamps are not wall-clock time')
        return False
    if rtc.rtc.lost_power:
        warn('[Main Loop] RTC lost power: timestamps are invalid, run SetTime.py')
        return False
    if rtc.rtc.power_management != 0:
        warn('[Main Loop] RTC battery switchover is off: run SetTime.py')
    info(f'[Main Loop] RTC time {rtc.dtstr()}')
    return True


def clock_line():
    """RTC date/time for the screen as (text, color), read once (not a live
    clock). 'YYYY-MM-DD HH:MM:SS' is 19 characters, exactly one line."""
    rtc = TimeUtil.rtc
    try:
        if rtc is not None and not rtc.rtc.lost_power:
            return TimeUtil.rtc_timestamp('iso', with_ms=False), GREEN
    except Exception:
        pass
    return 'RTC: set time!', RED


def shutdown(recorder, screen):
    """Close the data file, unmount the SD card, give the display back."""
    try:
        recorder.close()
        info('[Main Loop] shutting down')
        teardown()               # closes system.log, which is kept open on SD
    except Exception:
        pass
    try:
        MySD.unmount()
    except Exception:
        pass
    try:
        screen.release()
    except Exception:
        pass


def main_loop(level=INFO, sd_ok=True):
    set_system_log_level(level)
    setup_system_log()
    info('[Main Loop] Simplified HydraPurr start (recording version)')
    log_reset_reason()
    log_settings()

    screen = StatusDisplay()
    screen.manual()
    screen.set_line(0, 'HydraPurr', now=True)
    screen.set_line(1, 'SD ok' if sd_ok else 'NO SD CARD', GREEN if sd_ok else RED, now=True)
    check_rtc()
    text, color = clock_line()
    screen.set_line(2, text, color, now=True)
    screen.set_line(3, 'baseline...', now=True)
    screen.set_line(4, 'D1 = download', now=True)

    button = DownloadMode.Button(board.D1)
    led = None
    if Settings.contact_led_pin is not None:
        led = digitalio.DigitalInOut(Settings.contact_led_pin)
        led.switch_to_output(value=True)     # brief flash: shows the LED works
        time.sleep(0.5)
        led.value = False                    # off before the touch baseline
    touch = TouchSensor()
    water = WaterSensor()
    recorder = RawRecorder()
    if touch.baseline <= 0:
        screen.set_line(3, 'TOUCH BROKEN', RED, now=True)
        screen.set_line(4, 'need CP 10.3.1+', RED, now=True)
        time.sleep(5)
    else:
        time.sleep(3)            # leave the startup checks on screen briefly
    screen.repaint()             # clear any leftovers of the boot console

    interval_ms = Settings.raw_log_interval_ms
    next_sample_ms = now_ms()
    next_status_ms = now_ms() + Settings.status_log_interval_ms
    next_display_ms = 0
    water_v = water.read_volts()
    contacts = 0                 # contact onsets since boot, for the display
    last_contact_ms = -Settings.display_quiet_ms
    previous_contact = 0
    samples = 0                  # samples taken since the last status line
    max_gap_ms = 0               # longest time between two samples
    last_sample_ms = None

    info('[Main Loop] Starting recording loop')
    try:
        while True:
            try:
                t = now_ms()
                if button.pressed(t):
                    info('[Main Loop] D1 pressed: download mode, recording paused')
                    recorder.close()
                    flush()
                    if led is not None:
                        led.value = False
                    DownloadMode.run(screen, button, clock_line())
                    # Restart timing so the pause is not counted as a gap.
                    t = now_ms()
                    next_sample_ms = t
                    last_sample_ms = None
                    next_display_ms = 0
                    last_contact_ms = -Settings.display_quiet_ms
                    continue
                if t >= next_sample_ms:
                    # Fixed sampling grid, so the interval doesn't drift with loop
                    # jitter; skip ahead if the loop fell behind (e.g. a flush).
                    next_sample_ms += interval_ms
                    if next_sample_ms <= t:
                        next_sample_ms = t + interval_ms
                    if last_sample_ms is not None:
                        max_gap_ms = max(max_gap_ms, t - last_sample_ms)
                    last_sample_ms = t
                    samples += 1
                    contact = touch.update(t)
                    water_v = water.read_volts()
                    # LED first: it should match the recorded contact column,
                    # with no SD write in between.
                    if led is not None and contact != previous_contact:
                        led.value = bool(contact)
                    if contact and not previous_contact:
                        contacts += 1
                    if contact:
                        last_contact_ms = t
                    previous_contact = contact
                    recorder.add(t, touch, water_v)

                # A full-screen redraw pauses sampling for ~150 ms, so the
                # screen only updates when the wire has been quiet for
                # display_quiet_ms: frozen while drinking, catches up after.
                if t >= next_display_ms and t - last_contact_ms >= Settings.display_quiet_ms:
                    next_display_ms = t + Settings.display_interval_ms
                    if recorder.enabled:
                        screen.set_line(0, f'REC {recorder.rows_written}', GREEN)
                    else:
                        screen.set_line(0, 'NOT RECORDING', RED)
                    screen.set_line(1, f'contacts {contacts}')
                    screen.set_line(2, f'water {water_v:.3f}V')
                    screen.set_line(3, f'touch {touch.raw}', GREEN if touch.contact else WHITE)
                    screen.set_line(4, f'base {touch.baseline:.0f}')
                    screen.refresh_all()

                if t >= next_status_ms:
                    next_status_ms = t + Settings.status_log_interval_ms
                    rate = samples * 1000 // Settings.status_log_interval_ms
                    info(f'[Status] rows={recorder.rows_written} errors={recorder.errors} '
                         f'rate={rate}/s max_gap={max_gap_ms}ms '
                         f'slowest_write={recorder.take_slowest_ms()}ms file={recorder.path} '
                         f'touch raw={touch.raw} baseline={touch.baseline:.0f} '
                         f'contacts={contacts} water={water_v:.3f}V')
                    samples = 0
                    max_gap_ms = 0
                    flush()
            except Exception as e:
                error(f'[Main Loop] Unhandled exception: {e}')
                traceback.print_exception(e)
                raise
    finally:
        # Runs however the loop ends: exception, Ctrl-C, or CircuitPython's
        # auto-reload when a file is saved to the board. Leaving the SD file
        # open with the display in manual refresh made the following soft
        # reboot hard-fault.
        shutdown(recorder, screen)
