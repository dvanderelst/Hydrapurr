# Settings for the Simplified HydraPurr (Feather ESP32-S3 Reverse TFT +
# Adalogger FeatherWing, capacitive water wire, Sharp float sensor).
#
# Names match legacy/v1_firmware/lib/Settings.py wherever the meaning is the same, so
# the copied modules (BoutDetection, MyStore, MySystemLog) work unchanged.
# Every setting is written to the event log at each boot (`settings` rows).

import os
import board

# --- Files on the SD card -----------------------------------------------------
system_log_filename = "system.log"
system_log_max_lines = 2000

# --- Pins ---------------------------------------------------------------------
touch_pin = board.D12          # wire into the water (touchio)
water_pin = board.A5           # Sharp GP2Y0A51SK0F output (ADC1, WiFi-safe)
contact_led_pin = board.D9     # LED (+ side on the pin, resistor to GND), lit
                               # while the wire sees contact; for video checks.
                               # None = no LED.

# --- Touch (lick contact) -----------------------------------------------------
# A lick raises touchio's raw_value above a slowly tracking baseline.
# Contact starts when raw > baseline * (1 + touch_on_fraction) and ends when
# raw < baseline * (1 + touch_off_fraction) (hysteresis against flicker).
# PLACEHOLDERS until raw.csv recordings show real lick values.
touch_on_fraction = 0.10
touch_off_fraction = 0.05
touch_baseline_samples = 50    # reads averaged for the baseline at boot
touch_baseline_tau_ms = 30000  # time constant of the baseline tracker; it
                               # only updates while there is no contact, so it
                               # follows slow drift (water level, humidity)
touch_drop_settle_ms = 500     # after a `drop` re-baseline, follow lower values
                               # at once for this long (it is caught mid-fall)
touch_drop_samples = 3         # a drop must last this many readings (30 ms)
                               # before the baseline follows it (single-sample
                               # dips gave false 5-s contacts, 2026-11-23)
touch_stuck_ms = 5000          # contact longer than this is not a lick (paw
                               # resting, level step): re-take the baseline

# --- Water level (Sharp IR sensor above the float) -----------------------------
# Higher voltage = float closer to the sensor = higher water. The recorder
# stores single reads (WaterSensor.read_volts()); the smoothing settings are
# in the "not used" block below.

# --- Raw data recording --------------------------------------------------------
# Every sample goes to /sd/raw/<date>/<hour>.csv (see RawRecorder.py).
# ~44 bytes per row: at 100 rows/s that is ~380 MB per day.
raw_log_enabled = True
raw_log_interval_ms = 10       # one row per 10 ms = 100 rows/s
raw_log_sync_ms = 5000         # flush to the card this often; a power cut
                               # loses at most this much data

# --- Event log -------------------------------------------------------------------
# One row per event to /sd/events/<date>.csv (see EventLog.py): boot,
# settings, every touch contact, baseline resets, a status row every
# status_event_interval_ms, shutdown. Rows only when something happens: the
# raw files hold every sample.
events_enabled = True
events_sync_ms = 5000          # flush to the card this often
status_event_interval_ms = 15 * 60 * 1000  # status row: water, touch, contacts
status_event_first_ms = 60000    # first one this long after the loop starts
                                 # (after the post-reset water spikes)
status_water_window_ms = 10000   # its water value = mean over this long before it

# --- Lab WiFi (station mode: heartbeat, clock, file server) --------------------
# The credentials are NOT in this file: the repo is public. They go in
# settings.toml in the board's root (CIRCUITPY drive) and only there: no copy
# on the computer, sync2board never touches it. Edit it on the board, with
# two lines per network, up to 5 networks (numbered 2-5 after the first):
#   WIFI_SSID = "lab network"
#   WIFI_PASSWORD = "password"
#   WIFI_SSID_2 = "other network"     (WIFI_SSID2 works too)
#   WIFI_PASSWORD_2 = "password"
# At each join the board scans and tries the visible ones in this order (first
# = preferred). Don't use CircuitPython's own CIRCUITPY_WIFI_* names there:
# with those the board joins WiFi by itself at every boot (see HANDOFF.md).
WIFI_MAX_NETWORKS = 5


def _wifi_networks():
    nets = []
    for i in range(1, WIFI_MAX_NETWORKS + 1):
        # WIFI_SSID_2 or WIFI_SSID2 (both spellings accepted)
        for suffix in ([''] if i == 1 else [f'_{i}', f'{i}']):
            ssid = os.getenv('WIFI_SSID' + suffix)
            if ssid:
                nets.append((ssid, os.getenv('WIFI_PASSWORD' + suffix) or ''))
                break
    return nets


wifi_networks = _wifi_networks()   # [(ssid, password), ...], may be empty

# --- Health check (healthchecks.io) --------------------------------------------
# The board POSTs a short status line to this URL; healthchecks.io alerts when
# it stops coming. Secret-ish (anyone with it can ping), so it lives in
# settings.toml on the board:
#   HEALTHCHECK_URL = "https://hc-ping.com/<uuid>"
healthcheck_url = os.getenv("HEALTHCHECK_URL")

# --- WiFi in the recorder (Network.py) ------------------------------------------
wifi_enabled = True            # False = recorder never touches the radio
wifi_connect_timeout_s = 10    # a join blocks this long at most (gap in data)
wifi_retry_ms = 5 * 60 * 1000  # re-join a lost connection at most this often
wifi_tx_power_dbm = 8.5        # enough in the lab (2026-11-16 tests)
mdns_hostname = "hydrapurr"     # the board answers as hydrapurr.local

# --- Clock (NTP) ----------------------------------------------------------------
# The RTC is set from a time server at boot (right after the WiFi join, before
# anything is logged) and every ntp_interval_ms. The board keeps UTC: no
# summer/winter time steps in the data, and the hourly file names are UTC
# hours. The reader in analysis/ converts to lab time.
ntp_server = "pool.ntp.org"
ntp_timeout_s = 2
ntp_interval_ms = 24 * 60 * 60 * 1000
ntp_retry_ms = 10 * 60 * 1000         # after a failed sync

# --- File server (FileServer.py): the SD card at http://hydrapurr.local/ --------
fileserver_enabled = True
fileserver_chunk = 2048        # bytes read from the card and sent per step
fileserver_margin_ms = 2       # stop server work this long before a sample is due
# Fast download: a link with ?pause=1 (the start page's "raw, fast") stops
# sampling while that one download runs. Set False during real experiments:
# then nobody can pause recording from the page.
fileserver_allow_pause = True
fileserver_pause_chunk = 4096          # bytes per step while paused
fileserver_max_pause_ms = 20 * 60 * 1000   # recording restarts after this at the latest

# --- Heartbeat --------------------------------------------------------------------
# One heartbeat stops recording ~3.5 s, so it waits for a quiet wire; past
# heartbeat_max_delay_ms it goes anyway, so a long session can't trigger a
# false alarm. Set the healthchecks.io check to period 15 min, grace 15 min.
heartbeat_interval_ms = 15 * 60 * 1000
heartbeat_quiet_ms = 30000            # no contact for this long before sending
heartbeat_max_delay_ms = 10 * 60 * 1000
heartbeat_min_free_mb = 1024          # less free on the SD card = /fail (~2.5 days of raw)
heartbeat_min_rate = 50               # rows/s since the last heartbeat (paused time not
                                      # counted) below this = /fail `low_rate`; normal ~84
heartbeat_alert_resets = ('WATCHDOG', 'BROWNOUT', 'PANIC')  # these reset reasons
                                      # = /fail on the first heartbeat after the boot

# --- Watchdog ---------------------------------------------------------------------
# Resets the board when the loop stops feeding it (hang). Longer than the
# longest blocking step: WiFi join (10 s), heartbeat (up to ~3 x 10 s timeouts).
watchdog_timeout_s = 60               # None = no watchdog

# =============================================================================
# Not used by the recording version (MainLoop.py). Kept for when bout
# detection and feeding come back (LickSensor.py, BoutDetection.py).
# =============================================================================

# --- Lick / bout detection (same meaning as in BoardCode) ----------------------
min_lick_ms = 50
max_lick_ms = 250
min_licks_per_bout = 3
max_bout_gap_ms = 2000
debounce_ms = 5
min_water_extent_per_bout = 0.0  # disabled until the float is characterised;
                                 # bout summaries still log the extent so it
                                 # can be tuned from data

# --- Files of the bout version (LickSensor / MyStore) ---------------------------
lick_data_filename = "licks.dat"
data_log_max_lines = 2000

# --- Smoothed water level (WaterSensor.update()) --------------------------------
water_sample_ms = 20           # the Sharp updates every ~16.5 ms
water_smooth_samples = 10      # moving average over this many samples (~200 ms)

# (Feeder and deployment settings come back with the feeder; see
# legacy/v1_firmware/lib/Settings.py for the old ones.)

# =============================================================================

# --- Status ---------------------------------------------------------------------
status_log_interval_ms = 60000  # periodic status line in system.log
display_interval_ms = 1000      # full-screen TFT redraw interval. Each redraw
                                # pauses sampling for ~150 ms, so ...
display_quiet_ms = 3000         # ... the screen is only redrawn after this long
                                # without touch contact (frozen while drinking)
