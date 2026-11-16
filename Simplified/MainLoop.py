"""
MainLoop.py - Simplified HydraPurr main loop (recording version)

For now the device only records: the touch wire and the float sensor are
sampled every raw_log_interval_ms and written to the SD card as one raw
stream (RawRecorder). Licks and water-level changes are found offline.

TouchSensor computes a live contact state (0/1) against its tracking
baseline. It is stored in the raw stream, shown on the TFT, and each contact
is written to the event log (EventLog: boot, settings, contacts, baseline
resets, water summaries, shutdown).

The board joins the lab WiFi at boot (Network.py) and sends a heartbeat with
a status line to healthchecks.io every heartbeat_interval_ms, when the wire
has been quiet (each one stops recording ~3.5 s); /fail when something is
wrong (not recording, SD errors, RTC, touch, card nearly full). A watchdog
resets the board if the loop hangs. Once WiFi has been used, the loop ends
with a hard reset instead of a soft reboot (a soft reboot dropped USB), and
auto-reload is off: after copying files to the board, press Reset.

Press D1 to pause recording and serve the SD card over the board's own WiFi
network (DownloadMode.py); press D1 again to resume.

Bout detection and feeding (BoutDetection.py, LickSensor.py) are not used in
this version; they stay in lib/ for later.
"""

import os
import time
import traceback
import board
import digitalio
import supervisor
import microcontroller

import Settings
from components import TimeUtil
from components import MySD
from components.MySystemLog import setup_system_log, set_system_log_level, flush, teardown
from components.MySystemLog import INFO, info, warn, error
from TouchSensor import TouchSensor
from WaterSensor import WaterSensor
from RawRecorder import RawRecorder
from EventLog import EventLog
from StatusDisplay import StatusDisplay
import DownloadMode
from Network import Network

GREEN, YELLOW, RED, WHITE = 0x00FF00, 0xFFFF00, 0xFF4040, 0xFFFFFF


def now_ms():
    return time.monotonic_ns() // 1_000_000


def settings_items():
    """(name, value) for every setting, password masked."""
    for name in sorted(dir(Settings)):
        if name.startswith('_'):
            continue
        value = getattr(Settings, name)
        if callable(value) or type(value).__name__ == 'module':
            continue
        if name in ('wifi_password', 'healthcheck_url') and value:
            value = '<set>'      # from settings.toml; keep it out of the log
        yield name, value


def log_settings():
    info('[Settings] --- snapshot at startup ---')
    for name, value in settings_items():
        info(f'[Settings] {name} = {value}')
    info('[Settings] --- end snapshot ---')


def reset_reasons():
    """Why the board last restarted: e.g. BROWNOUT (power dip), PANIC
    (crash), POWER_ON, RESET_PIN. Logged to system.log and the event log."""
    try:
        import microcontroller
        import supervisor
        reasons = (str(microcontroller.cpu.reset_reason),
                   str(supervisor.runtime.safe_mode_reason))
    except Exception as e:
        warn(f'[Main Loop] could not read reset reason: {e!r}')
        return '?', '?'
    info(f'[Main Loop] reset reason: {reasons[0]}, safe mode reason: {reasons[1]}')
    return reasons


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


def start_watchdog():
    if Settings.watchdog_timeout_s is None:
        return
    from watchdog import WatchDogMode
    microcontroller.watchdog.timeout = Settings.watchdog_timeout_s
    microcontroller.watchdog.mode = WatchDogMode.RESET
    microcontroller.watchdog.feed()


def feed_watchdog():
    if Settings.watchdog_timeout_s is not None:
        microcontroller.watchdog.feed()


def stop_watchdog():
    if Settings.watchdog_timeout_s is None:
        return
    try:
        microcontroller.watchdog.deinit()
    except Exception as e:
        # Some ports can't stop it: then keep it fed instead.
        warn(f'[Main Loop] could not stop the watchdog: {e!r}')


def sd_free_mb():
    """Free space on the SD card in MB, or None."""
    try:
        st = os.statvfs('/sd')
        return st[0] * st[4] // (1024 * 1024)
    except OSError:
        return None


def shutdown(recorder, events, screen, reason):
    """Close the data files, unmount the SD card, give the display back."""
    try:
        events.log(now_ms(), 'shutdown', reason)
        events.close()
    except Exception:
        pass
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
    reasons = reset_reasons()
    log_settings()

    screen = StatusDisplay()
    screen.manual()
    screen.set_line(0, 'HydraPurr', now=True)
    screen.set_line(1, 'SD ok' if sd_ok else 'NO SD CARD', GREEN if sd_ok else RED, now=True)
    rtc_ok = check_rtc()
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
    events = EventLog()
    t = now_ms()
    events.log(t, 'boot', reasons[0], reasons[1], int(rtc_ok), round(touch.baseline))
    for name, value in settings_items():
        events.log(t, 'settings', name, str(value))
    events.flush()

    net = Network()
    if net.enabled:
        screen.set_line(4, 'joining WiFi...', YELLOW, now=True)
        joined = net.join()
        if joined:
            screen.set_line(4, f'{net.ip()}', GREEN, now=True)
            events.log(now_ms(), 'wifi', 'joined', net.ip(), net.rssi())
        else:
            screen.set_line(4, 'no WiFi', RED, now=True)
            events.log(now_ms(), 'wifi', 'join_failed')
        events.flush()
    if net.used:
        # A soft reboot after WiFi use dropped USB, and saving a file over
        # USB would trigger one: no auto-reload, press Reset after a copy.
        supervisor.runtime.autoreload = False
        info('[Main Loop] WiFi used: auto-reload off, press Reset after copying files')
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
    contact_start_ms = None      # current contact, for its event row
    contact_peak = 0
    contact_baseline = 0
    contact_water_v = 0.0
    water_sum, water_n = 0.0, 0  # water summary for the event log
    water_min, water_max = None, None
    next_water_event_ms = now_ms() + Settings.water_event_interval_ms
    stop_reason = 'unknown'
    # Heartbeat: first one soon after boot (once the wire is quiet).
    boot_ms = now_ms()
    hb_due_ms = now_ms()
    hb_last_ms = now_ms()
    hb_rows = 0                  # recorder.rows_written at the last heartbeat
    hb_errors = 0                # recorder.errors + events.errors at the last one
    hb_contacts = 0              # contacts at the last heartbeat
    hb_max_gap_ms = 0            # longest gap between samples since then
    hb_last_took_ms = 0          # how long the previous heartbeat blocked
    next_wifi_check_ms = 0
    wifi_up = net.connected

    start_watchdog()

    info('[Main Loop] Starting recording loop')
    try:
        while True:
            try:
                feed_watchdog()
                t = now_ms()
                if button.pressed(t):
                    info('[Main Loop] D1 pressed: download mode, recording paused')
                    recorder.close()
                    events.close()
                    flush()
                    if led is not None:
                        led.value = False
                    stop_watchdog()      # a big file can take minutes
                    DownloadMode.run(screen, button, clock_line())
                    start_watchdog()
                    # Restart timing so the pause is not counted as a gap.
                    t = now_ms()
                    next_sample_ms = t
                    last_sample_ms = None
                    next_display_ms = 0
                    last_contact_ms = -Settings.display_quiet_ms
                    # A contact or water summary spanning the pause is dropped.
                    contact_start_ms = None
                    water_sum, water_n, water_min, water_max = 0.0, 0, None, None
                    next_water_event_ms = t + Settings.water_event_interval_ms
                    continue
                if t >= next_sample_ms:
                    # Fixed sampling grid, so the interval doesn't drift with loop
                    # jitter; skip ahead if the loop fell behind (e.g. a flush).
                    next_sample_ms += interval_ms
                    if next_sample_ms <= t:
                        next_sample_ms = t + interval_ms
                    if last_sample_ms is not None:
                        max_gap_ms = max(max_gap_ms, t - last_sample_ms)
                        hb_max_gap_ms = max(hb_max_gap_ms, t - last_sample_ms)
                    last_sample_ms = t
                    samples += 1
                    water_before = water_v
                    contact = touch.update(t)
                    water_v = water.read_volts()
                    # LED first: it should match the recorded contact column,
                    # with no SD write in between.
                    if led is not None and contact != previous_contact:
                        led.value = bool(contact)
                    if touch.rebaseline is not None:
                        events.log(t, 'rebaseline', touch.rebaseline[0], touch.rebaseline[1],
                                   round(touch.rebaseline[2]), round(touch.rebaseline[3]))
                    if contact and not previous_contact:
                        contacts += 1
                        contact_start_ms = t
                        contact_peak = touch.raw
                        # A stuck re-take sets the baseline to the contact
                        # level, so use the one from before it.
                        contact_baseline = touch.baseline
                        contact_water_v = water_before
                    if contact:
                        last_contact_ms = t
                        contact_peak = max(contact_peak, touch.raw)
                    elif previous_contact and contact_start_ms is not None:
                        events.log(t, 'contact', t - contact_start_ms, contact_peak,
                                   round(contact_baseline), contact_water_v)
                        contact_start_ms = None
                    previous_contact = contact
                    recorder.add(t, touch, water_v)

                    water_sum += water_v
                    water_n += 1
                    water_min = water_v if water_min is None else min(water_min, water_v)
                    water_max = water_v if water_max is None else max(water_max, water_v)
                    if t >= next_water_event_ms:
                        next_water_event_ms = t + Settings.water_event_interval_ms
                        events.log(t, 'water', water_sum / water_n, water_min, water_max, water_n)
                        water_sum, water_n, water_min, water_max = 0.0, 0, None, None

                events.update(t)

                quiet = t - last_contact_ms >= Settings.heartbeat_quiet_ms

                # WiFi upkeep, once a second: log a lost connection, re-join
                # when the wire is quiet (a join blocks up to 10 s).
                if net.enabled and t >= next_wifi_check_ms:
                    next_wifi_check_ms = t + 1000
                    up = net.connected
                    if wifi_up and not up:
                        warn('[Network] WiFi connection lost')
                        events.log(t, 'wifi', 'lost')
                    wifi_up = up
                    if not up and quiet and net.join_due(t):
                        last_sample_ms = None    # the join's gap is expected
                        if net.join():
                            wifi_up = True
                            events.log(now_ms(), 'wifi', 'joined', net.ip(), net.rssi())
                        else:
                            events.log(now_ms(), 'wifi', 'join_failed')

                # Heartbeat when due and the wire is quiet; after
                # heartbeat_max_delay_ms it goes anyway (no false alarm).
                if (wifi_up and net.host is not None and t >= hb_due_ms
                        and (quiet or t - hb_due_ms >= Settings.heartbeat_max_delay_ms)):
                    errors = recorder.errors + events.errors
                    free_mb = sd_free_mb()
                    problems = []
                    if not recorder.enabled:
                        problems.append('not_recording')
                    if errors > hb_errors:
                        problems.append('sd_errors')
                    if not rtc_ok:
                        problems.append('rtc')
                    if touch.baseline <= 0:
                        problems.append('touch')
                    if free_mb is not None and free_mb < Settings.heartbeat_min_free_mb:
                        problems.append('sd_low')
                    span_s = max(1, (t - hb_last_ms) // 1000)
                    rate = (recorder.rows_written - hb_rows) // span_s
                    clock = clock_line()[0].replace(' ', 'T')
                    reset = reasons[0].split('.')[-1]
                    body = (f'problems={",".join(problems) or "none"} t={clock} '
                            f'up={(t - boot_ms) // 1000}s rows={recorder.rows_written} '
                            f'rate={rate}/s max_gap={hb_max_gap_ms}ms errors={errors} '
                            f'contacts={contacts - hb_contacts} water={water_v:.3f}V '
                            f'touch={touch.raw} base={touch.baseline:.0f} '
                            f'sd_free={free_mb}MB rssi={net.rssi()} ip={net.ip()} '
                            f'rtc={int(rtc_ok)} reset={reset} '
                            f'last_hb={hb_last_took_ms}ms')
                    ok, took, status = net.heartbeat(body, fail=bool(problems))
                    if ok:
                        info(f'[Heartbeat] sent in {took} ms: {body}')
                        hb_due_ms = t + Settings.heartbeat_interval_ms
                        hb_last_ms = t
                        hb_rows = recorder.rows_written
                        hb_errors = errors
                        hb_contacts = contacts
                        hb_max_gap_ms = 0
                    else:
                        warn(f'[Heartbeat] failed after {took} ms: {status}')
                        events.log(now_ms(), 'heartbeat_failed', status, took)
                        hb_due_ms = now_ms() + 60000     # try again in a minute
                    hb_last_took_ms = took
                    t = now_ms()
                    last_sample_ms = None    # its own gap is reported as last_hb

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
                    if not net.enabled:
                        screen.set_line(4, f'base {touch.baseline:.0f}')
                    elif wifi_up:
                        screen.set_line(4, f'base {touch.baseline:.0f} WiFi')
                    else:
                        screen.set_line(4, f'base {touch.baseline:.0f} noWiFi', RED)
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
    except BaseException as e:   # also Ctrl-C and auto-reload
        stop_reason = repr(e)
        raise
    finally:
        # Runs however the loop ends: exception, Ctrl-C, or CircuitPython's
        # auto-reload when a file is saved to the board. Leaving the SD file
        # open with the display in manual refresh made the following soft
        # reboot hard-fault.
        shutdown(recorder, events, screen, stop_reason)
        if net.used:
            # A soft reboot after WiFi use dropped USB (HANDOFF 2026-11-16):
            # reset the whole chip instead. Ctrl-C / Thonny's stop therefore
            # restarts the board rather than leaving it at the REPL.
            print('WiFi was used: resetting the board instead of a soft reboot')
            time.sleep(0.5)
            microcontroller.reset()
        stop_watchdog()
