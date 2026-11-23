"""
MainLoop.py - Simplified HydraPurr main loop (recording version)

For now the device only records: the touch wire and the float sensor are
sampled every raw_log_interval_ms and written to the SD card as one raw
stream (RawRecorder). Licks and water-level changes are found offline.

TouchSensor computes a live contact state (0/1) against its tracking
baseline. It is stored in the raw stream, shown on the TFT, and each contact
is written to the event log (EventLog: boot, settings, contacts, baseline
resets, a status row every 15 min, WiFi, clock, pauses, shutdown).

The board joins the lab WiFi at boot (Network.py), sets its clock from NTP
(UTC; again once a day) and sends a heartbeat with a status line to
healthchecks.io every heartbeat_interval_ms, when the wire has been quiet
(each one stops recording ~3.5 s); /fail when something is wrong (not
recording, SD errors, RTC, touch, card nearly full). A watchdog resets the
board if the loop hangs. Once WiFi has been used, the loop ends with a hard
reset instead of a soft reboot (a soft reboot dropped USB), and auto-reload
is off: after copying files to the board, press Reset (or one Ctrl-C). An
unexpected error also ends in a reset, WiFi or not, so the board records
again instead of sitting at the REPL.

While connected, the SD card is served at http://hydrapurr.local/
(FileServer.py). The server works in small steps between samples, so
downloads don't stop the recording. A "fast" download (?pause=1, if
fileserver_allow_pause) stops sampling while it runs: `paused`/`resumed`
event rows mark the gap.

Structure: start_up() sets everything up and returns the parts; main_loop()
holds the loop. The per-sample work stays inline in the loop (locals are
fastest in CircuitPython); what runs rarely (heartbeat text, screen, status
line) is in functions.

Bout detection and feeding (BoutDetection.py, LickSensor.py) are not used in
this version; they stay in lib/ for later.
"""

import os
import time
import traceback
import digitalio
import supervisor
import microcontroller

import Settings
from components import TimeUtil
from components import MySD
from components.MySystemLog import setup_system_log, set_system_log_level, set_mem_max
from components.MySystemLog import flush, teardown, INFO, info, warn, error
from TouchSensor import TouchSensor
from WaterSensor import WaterSensor
from RawRecorder import RawRecorder
from EventLog import EventLog
from StatusDisplay import StatusDisplay
from FileServer import FileServer
from Network import Network

GREEN, YELLOW, RED, WHITE = 0x00FF00, 0xFFFF00, 0xFF4040, 0xFFFFFF
CRASH_RESET_DELAY_S = 10       # after an unexpected error: wait, then reset


def now_ms():
    return time.monotonic_ns() // 1_000_000


# --- settings, reset reason, clock ----------------------------------------------

def settings_items():
    """(name, value) for every setting, password masked."""
    for name in sorted(dir(Settings)):
        if name.startswith('_'):
            continue
        value = getattr(Settings, name)
        if callable(value) or type(value).__name__ == 'module':
            continue
        if name == 'healthcheck_url' and value:
            value = '<set>'      # from settings.toml; keep it out of the log
        elif name == 'wifi_networks':
            value = ' | '.join(ssid for ssid, _ in value) or None   # no passwords
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
        reasons = (str(microcontroller.cpu.reset_reason),
                   str(supervisor.runtime.safe_mode_reason))
    except Exception as e:
        warn(f'[Main Loop] could not read reset reason: {e!r}')
        return '?', '?'
    info(f'[Main Loop] reset reason: {reasons[0]}, safe mode reason: {reasons[1]}')
    return reasons


def check_rtc():
    """Return True when the RTC time can be trusted."""
    try:
        TimeUtil.init_timebase()
        rtc = TimeUtil.rtc
        if rtc is None:
            warn('[Main Loop] RTC not found: timestamps are not wall-clock time')
            return False
        if rtc.rtc.lost_power:
            warn('[Main Loop] RTC lost power: timestamps are invalid until NTP sets them')
            return False
        if rtc.rtc.power_management != 0:
            warn('[Main Loop] RTC battery switchover is off (NTP or SetTime.py turns it on)')
        info(f'[Main Loop] RTC time {rtc.dtstr()}')
        return True
    except Exception as e:        # I2C error reading the chip
        warn(f'[Main Loop] RTC check failed: {e!r}')
        return False


def utc_stamp():
    """Current wall-clock time from the timebase (not an RTC read, which can
    fail on I2C): 'YYYY-MM-DD HH:MM:SS', or '?'."""
    try:
        return TimeUtil._wall_time_from_mono(now_ms(), 'iso', False)
    except Exception:
        return '?'


def clock_line(rtc_ok):
    """Date/time (UTC) for the screen as (text, color), read once (not a
    live clock). 'MM-DD HH:MM:SS UTC' fits the 19-character line."""
    if rtc_ok:
        stamp = utc_stamp()
        if stamp != '?':
            return stamp[5:] + ' UTC', GREEN
    return 'RTC: set time!', RED


def sync_clock(net):
    """Set the RTC and the timebase from NTP (UTC). Returns (step_ms,
    rtt_ms), or None when the time server did not answer."""
    result = net.ntp_time()
    if result is None:
        return None
    utc_ms, mono_ms, rtt_ms = result
    try:
        step_ms = TimeUtil.set_clock(utc_ms, mono_ms)
    except Exception as e:
        warn(f'[Clock] could not set the clock: {e!r}')
        return None
    info(f'[Clock] set from NTP ({Settings.ntp_server}): {utc_stamp()} UTC, '
         f'step {step_ms} ms, round trip {rtt_ms} ms')
    return step_ms, rtt_ms


# --- watchdog, SD, shutdown ----------------------------------------------------

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


def flusher(recorder, events):
    """For FileServer: flush both data files before a file's size is taken."""
    def flush_data():
        recorder.flush()
        events.flush()
    return flush_data


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


def reset_board(why):
    print(f'{why}: resetting the board')
    time.sleep(0.5)
    microcontroller.reset()


# --- start-up -------------------------------------------------------------------

class Parts:
    """What start_up() sets up (unpacked into locals for the loop)."""
    pass


def start_up(sd_ok):
    p = Parts()
    p.reasons = reset_reasons()
    log_settings()

    screen = p.screen = StatusDisplay()
    screen.manual()
    screen.set_line(0, 'HydraPurr', now=True)
    screen.set_line(1, 'SD ok' if sd_ok else 'NO SD CARD', GREEN if sd_ok else RED, now=True)
    p.rtc_ok = check_rtc()
    text, color = clock_line(p.rtc_ok)
    screen.set_line(2, text, color, now=True)
    screen.set_line(3, 'baseline...', now=True)
    screen.set_line(4, '', now=True)

    p.led = None
    if Settings.contact_led_pin is not None:
        p.led = digitalio.DigitalInOut(Settings.contact_led_pin)
        p.led.switch_to_output(value=True)     # brief flash: shows the LED works
        time.sleep(0.5)
        p.led.value = False                    # off before the touch baseline
    p.touch = TouchSensor()
    p.water = WaterSensor()
    p.recorder = RawRecorder()

    # WiFi and the clock before anything goes into the event log, so all
    # rows of this boot carry the NTP time.
    net = p.net = Network()
    p.clock = None
    if net.enabled:
        screen.set_line(4, 'joining WiFi...', YELLOW, now=True)
        if net.join():
            screen.set_line(4, f'{net.ip()}', GREEN, now=True)
            screen.set_wifi(True, now=True)
            p.clock = sync_clock(net)
            if p.clock is not None:
                p.rtc_ok = True
                text, color = clock_line(True)
                screen.set_line(2, text, color, now=True)
        else:
            screen.set_line(4, 'no WiFi', RED, now=True)
            screen.set_wifi(False, now=True)

    events = p.events = EventLog()
    t = now_ms()
    events.log(t, 'boot', p.reasons[0], p.reasons[1], int(p.rtc_ok), round(p.touch.baseline))
    for name, value in settings_items():
        events.log(t, 'settings', name, str(value))
    if net.enabled:
        log_wifi(events, t, net)
        if net.connected:
            log_clock(events, t, p.clock)
    events.flush()

    p.server = None
    if net.connected and Settings.fileserver_enabled:
        p.server = FileServer(net.pool, net.ip(), flusher(p.recorder, events))
    if net.used:
        # A soft reboot after WiFi use dropped USB, and saving a file over
        # USB would trigger one: no auto-reload, press Reset after a copy.
        supervisor.runtime.autoreload = False
        info('[Main Loop] WiFi used: auto-reload off, press Reset after copying files')
    if p.touch.baseline <= 0:
        screen.set_line(3, 'TOUCH BROKEN', RED, now=True)
        screen.set_line(4, 'need CP 10.3.1+', RED, now=True)
        time.sleep(5)
    else:
        time.sleep(3)            # leave the startup checks on screen briefly
    screen.repaint()             # clear any leftovers of the boot console
    return p


def log_wifi(events, t, net):
    if net.connected:
        events.log(t, 'wifi', 'joined', net.ip(), net.rssi(), net.ssid)
    else:
        events.log(t, 'wifi', 'join_failed')


def log_clock(events, t, clock):
    if clock is not None:
        events.log(t, 'clock', 'ntp', clock[0], clock[1], Settings.ntp_server)
    else:
        events.log(t, 'clock', 'ntp_failed')


def log_contact(events, t, start_ms, peak, baseline, water_v):
    """A contact row, written when the contact ends (row time = its end)."""
    events.log(t, 'contact', t - start_ms, peak, round(baseline), water_v)


# --- rarely run parts of the loop ------------------------------------------------

RATE_CHECK_MIN_MS = 60000      # low_rate only judged over this much recording time


def heartbeat_body(t, s, recorder, events, touch, net, server, water_v, contacts,
                   paused_ms):
    """Status line for the heartbeat and the list of problems (/fail when
    not empty). s holds the heartbeat bookkeeping (HeartbeatState);
    paused_ms = time paused for fast downloads since the last heartbeat."""
    errors = recorder.errors + events.errors
    free_mb = sd_free_mb()
    problems = []
    if not recorder.enabled:
        problems.append('not_recording')
    if errors > s.errors:
        problems.append('sd_errors')
    if not s.rtc_ok:
        problems.append('rtc')
    if touch.baseline <= 0:
        problems.append('touch')
    if free_mb is not None and free_mb < Settings.heartbeat_min_free_mb:
        problems.append('sd_low')
    # Rows per second of recording time: a fast-download pause is not counted.
    rec_ms = t - s.last_ms - paused_ms
    rate = (recorder.rows_written - s.rows) * 1000 // max(1, rec_ms)
    if (recorder.enabled and rec_ms >= RATE_CHECK_MIN_MS
            and rate < Settings.heartbeat_min_rate):
        problems.append('low_rate')
    if not s.reset_reported and s.reset in Settings.heartbeat_alert_resets:
        problems.append('reset_' + s.reset.lower())
    stamp = utc_stamp().replace(' ', 'T') + 'Z' if s.rtc_ok else 'unset'
    ntp_age = 'never' if s.last_ntp_ms is None else f'{(t - s.last_ntp_ms) // 1000}s'
    body = (f'problems={",".join(problems) or "none"} t={stamp} ntp_age={ntp_age} '
            f'up={(t - s.boot_ms) // 1000}s rows={recorder.rows_written} '
            f'rate={rate}/s max_gap={s.max_gap_ms}ms errors={errors} '
            f'dropped={recorder.dropped} '
            f'contacts={contacts - s.contacts} water={water_v:.3f}V '
            f'touch={touch.raw} base={touch.baseline:.0f} '
            f'sd_free={free_mb}MB rssi={net.rssi()} ip={net.ip()} '
            f'rtc={int(s.rtc_ok)} reset={s.reset} '
            f'last_hb={s.last_took_ms}ms '
            f'served={server.requests if server else 0} '
            f'sent={server.bytes_sent // 1024 if server else 0}KB '
            f'paused={s.paused_total_ms // 1000}s')
    return body, problems, errors


class HeartbeatState:
    """Bookkeeping between heartbeats (only touched when one is sent)."""
    def __init__(self, t, rtc_ok, reasons, last_ntp_ms):
        self.boot_ms = t
        self.due_ms = t              # first one soon after boot (when quiet)
        self.last_ms = t
        self.rows = 0                # recorder.rows_written at the last one
        self.errors = 0              # recorder + events errors at the last one
        self.contacts = 0            # contacts at the last one
        self.max_gap_ms = 0          # longest gap between samples since then
        self.last_took_ms = 0        # how long the previous one blocked
        self.paused_total_ms = 0     # time paused since boot (ended pauses)
        self.paused_at_last = 0      # paused time since boot at the last one
        self.reset_reported = False  # the boot's reset reason went out
        self.rtc_ok = rtc_ok
        self.last_ntp_ms = last_ntp_ms
        self.reset = reasons[0].split('.')[-1]


def draw_screen(screen, recorder, touch, contacts, water_v, wifi):
    """Full redraw (~150 ms): only called when the wire has been quiet."""
    if recorder.enabled:
        screen.set_line(0, f'REC {recorder.rows_written}', GREEN)
    else:
        screen.set_line(0, 'NOT RECORDING', RED)
    screen.set_line(1, f'contacts {contacts}')
    screen.set_line(2, f'water {water_v:.3f}V')
    screen.set_line(3, f'touch {touch.raw}', GREEN if touch.contact else WHITE)
    screen.set_line(4, f'base {touch.baseline:.0f}')
    screen.set_wifi(wifi)
    screen.refresh_all()


def server_status(paused, recorder, t, boot_ms, contacts, water_v, touch):
    """One line for the start page."""
    state = ('<b>NOT RECORDING</b>: paused for a fast download' if paused
             else 'Recording' if recorder.enabled else '<b>NOT RECORDING</b>')
    return (f'{state}. Up {(t - boot_ms) // 60000} min, '
            f'{recorder.rows_written} rows, {contacts} contacts, '
            f'water {water_v:.3f} V, touch {touch.raw} (baseline {touch.baseline:.0f}).')


# --- the loop ---------------------------------------------------------------------

def main_loop(level=INFO, sd_ok=True):
    set_system_log_level(level)
    # No sync after every line (that stalled sampling); warnings and errors
    # still go to the card at once, the rest with the 60-s flush() below.
    setup_system_log(autosync=False)
    set_mem_max(0)                   # no copy of the log in RAM
    info('[Main Loop] Simplified HydraPurr start (recording version)')
    try:
        p = start_up(sd_ok)
    except Exception as e:
        error(f'[Main Loop] start-up failed: {e!r}')
        traceback.print_exception(e)
        teardown()
        print(f'start-up failed: resetting in {CRASH_RESET_DELAY_S} s')
        time.sleep(CRASH_RESET_DELAY_S)
        reset_board('start-up failed')

    screen, led, touch, water = p.screen, p.led, p.touch, p.water
    recorder, events, net, server = p.recorder, p.events, p.net, p.server

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
    water_sum, water_n = 0.0, 0  # water mean for the next status row
    next_status_event_ms = now_ms() + Settings.status_event_first_ms
    status_contacts = 0          # contacts at the last status row
    stop_reason = 'unknown'
    crashed = False
    hb = HeartbeatState(now_ms(), p.rtc_ok, p.reasons,
                        now_ms() if p.clock is not None else None)
    next_wifi_check_ms = 0
    wifi_up = net.connected
    next_ntp_ms = now_ms() + (Settings.ntp_interval_ms if p.clock is not None
                              else Settings.ntp_retry_ms)
    paused = False               # a fast download has stopped sampling
    pause_start_ms = 0

    start_watchdog()

    info('[Main Loop] Starting recording loop')
    try:
        while True:
            try:
                feed_watchdog()
                t = now_ms()

                # Fast download: stop sampling while it runs.
                want_pause = server is not None and server.pausing
                if want_pause and not paused:
                    paused = True
                    pause_start_ms = t
                    if contact_start_ms is not None:
                        # End an open contact here; its end is not seen.
                        log_contact(events, t, contact_start_ms, contact_peak,
                                    contact_baseline, contact_water_v)
                        contact_start_ms = None
                    previous_contact = 0
                    events.log(t, 'paused', 'download', server.pause_what)
                    info(f'[Main Loop] recording paused for download {server.pause_what}')
                    if led is not None:
                        led.value = False
                    screen.set_line(0, 'NOT REC: download', RED, now=True)
                    t = now_ms()
                elif paused and not want_pause:
                    paused = False
                    took = t - pause_start_ms
                    hb.paused_total_ms += took
                    why = server.pause_end if server is not None else 'wifi lost'
                    events.log(t, 'resumed', why, took)
                    info(f'[Main Loop] recording again after {took} ms paused ({why})')
                    last_sample_ms = None   # the pause is not a recording gap
                    next_sample_ms = t
                    water_sum, water_n = 0.0, 0
                    next_display_ms = 0

                if not paused and t >= next_sample_ms:
                    # Fixed sampling grid, so the interval doesn't drift with loop
                    # jitter; skip ahead if the loop fell behind (e.g. a flush).
                    next_sample_ms += interval_ms
                    if next_sample_ms <= t:
                        next_sample_ms = t + interval_ms
                    if last_sample_ms is not None:
                        gap = t - last_sample_ms
                        if gap > max_gap_ms:
                            max_gap_ms = gap
                        if gap > hb.max_gap_ms:
                            hb.max_gap_ms = gap
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
                        if touch.raw > contact_peak:
                            contact_peak = touch.raw
                    elif previous_contact and contact_start_ms is not None:
                        log_contact(events, t, contact_start_ms, contact_peak,
                                    contact_baseline, contact_water_v)
                        contact_start_ms = None
                    previous_contact = contact
                    recorder.add(t, touch, water_v)

                    # Status row: water averaged over the window just before it.
                    if t >= next_status_event_ms - Settings.status_water_window_ms:
                        water_sum += water_v
                        water_n += 1
                    if t >= next_status_event_ms:
                        next_status_event_ms = t + Settings.status_event_interval_ms
                        events.log(t, 'status', water_sum / water_n if water_n else water_v,
                                   round(touch.baseline), touch.raw, contacts - status_contacts)
                        status_contacts = contacts
                        water_sum, water_n = 0.0, 0

                events.update(t)

                # File server: small steps until just before the next sample.
                if server is not None:
                    if paused:
                        server.poll(t, t + 50)    # only sending: no sample is due
                    else:
                        server.poll(t, next_sample_ms - Settings.fileserver_margin_ms)
                    t = now_ms()

                quiet = t - last_contact_ms >= Settings.heartbeat_quiet_ms
                busy = server is not None and server.busy

                # WiFi upkeep, once a second: log a lost connection, re-join
                # when the wire is quiet (a join blocks up to 10 s).
                if net.enabled and t >= next_wifi_check_ms:
                    next_wifi_check_ms = t + 1000
                    up = net.connected
                    if wifi_up and not up:
                        warn('[Network] WiFi connection lost')
                        events.log(t, 'wifi', 'lost')
                        if server is not None:
                            server.stop()
                            server = None
                    wifi_up = up
                    if server is not None:
                        server.status = server_status(paused, recorder, t, hb.boot_ms,
                                                      contacts, water_v, touch)
                    if not up and quiet and net.join_due(t):
                        feed_watchdog()
                        last_sample_ms = None    # the join's gap is expected
                        wifi_up = net.join(feed_watchdog)
                        log_wifi(events, now_ms(), net)
                        if wifi_up and Settings.fileserver_enabled:
                            server = FileServer(net.pool, net.ip(), flusher(recorder, events))
                        t = now_ms()

                # Clock: re-sync from NTP once a day (and retry after a
                # failure) when the wire is quiet and nobody is downloading.
                if wifi_up and t >= next_ntp_ms and quiet and not busy:
                    feed_watchdog()
                    clock = sync_clock(net)
                    log_clock(events, now_ms(), clock)
                    if clock is not None:
                        recorder.retime()
                        hb.rtc_ok = True
                        hb.last_ntp_ms = now_ms()
                        next_ntp_ms = t + Settings.ntp_interval_ms
                    else:
                        next_ntp_ms = t + Settings.ntp_retry_ms
                    t = now_ms()
                    last_sample_ms = None    # not a recording problem

                # Heartbeat when due and the wire is quiet; after
                # heartbeat_max_delay_ms it goes anyway (no false alarm).
                if (wifi_up and net.host is not None and t >= hb.due_ms
                        and ((quiet and not busy)
                             or t - hb.due_ms >= Settings.heartbeat_max_delay_ms)):
                    feed_watchdog()
                    paused_now = hb.paused_total_ms + (t - pause_start_ms if paused else 0)
                    body, problems, errors = heartbeat_body(t, hb, recorder, events, touch,
                                                            net, server, water_v, contacts,
                                                            paused_now - hb.paused_at_last)
                    ok, took, status = net.heartbeat(body, fail=bool(problems))
                    if ok:
                        info(f'[Heartbeat] sent in {took} ms: {body}')
                        hb.due_ms = t + Settings.heartbeat_interval_ms
                        hb.last_ms = t
                        hb.rows = recorder.rows_written
                        hb.errors = errors
                        hb.contacts = contacts
                        hb.max_gap_ms = 0
                        hb.paused_at_last = paused_now
                        hb.reset_reported = True
                    else:
                        warn(f'[Heartbeat] failed after {took} ms: {status}')
                        events.log(now_ms(), 'heartbeat_failed', status, took)
                        hb.due_ms = now_ms() + 60000     # try again in a minute
                    hb.last_took_ms = took
                    t = now_ms()
                    last_sample_ms = None    # its own gap is reported as last_hb

                # A full-screen redraw pauses sampling for ~150 ms, so the
                # screen only updates when the wire has been quiet for
                # display_quiet_ms: frozen while drinking, catches up after.
                if (not paused and t >= next_display_ms
                        and t - last_contact_ms >= Settings.display_quiet_ms):
                    next_display_ms = t + Settings.display_interval_ms
                    draw_screen(screen, recorder, touch, contacts, water_v,
                                wifi_up if net.enabled else None)

                if t >= next_status_ms:
                    next_status_ms = t + Settings.status_log_interval_ms
                    rate = samples * 1000 // Settings.status_log_interval_ms
                    info(f'[Status] rows={recorder.rows_written} errors={recorder.errors} '
                         f'dropped={recorder.dropped} rate={rate}/s max_gap={max_gap_ms}ms '
                         f'slowest_write={recorder.take_slowest_ms()}ms file={recorder.path} '
                         f'touch raw={touch.raw} baseline={touch.baseline:.0f} '
                         f'contacts={contacts} water={water_v:.3f}V')
                    samples = 0
                    max_gap_ms = 0
                    flush()
            except Exception as e:
                error(f'[Main Loop] Unhandled exception: {e}')
                traceback.print_exception(e)
                crashed = True
                raise
    except BaseException as e:   # also Ctrl-C and auto-reload
        stop_reason = repr(e)
        raise
    finally:
        # Runs however the loop ends: exception, Ctrl-C, or CircuitPython's
        # auto-reload when a file is saved to the board. Leaving the SD file
        # open with the display in manual refresh made the following soft
        # reboot hard-fault.
        if server is not None:
            server.stop()
        shutdown(recorder, events, screen, stop_reason)
        if crashed:
            # Unexpected error: record again after a reset rather than sit
            # at the REPL (with or without WiFi).
            time.sleep(CRASH_RESET_DELAY_S)
            reset_board('unexpected error')
        if net.used:
            # A soft reboot after WiFi use dropped USB (HANDOFF 2026-11-16):
            # reset the whole chip instead. Ctrl-C / Thonny's stop therefore
            # restarts the board rather than leaving it at the REPL.
            reset_board('WiFi was used')
        stop_watchdog()
