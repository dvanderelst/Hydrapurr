# Settings for the Simplified HydraPurr (Feather ESP32-S3 Reverse TFT +
# Adalogger FeatherWing, capacitive water wire, Sharp float sensor).
#
# Names match BoardCode/lib/Settings.py wherever the meaning is the same, so
# the copied modules (BoutDetection, MyStore, MySystemLog) work unchanged.

import os
import board

# --- Files on the SD card -----------------------------------------------------
system_log_filename = "system.log"
lick_data_filename = "licks.dat"      # not written by the recording version
system_log_max_lines = 2000
data_log_max_lines = 2000

# --- Cat ----------------------------------------------------------------------
# No RFID in this build yet: every lick belongs to this cat.
single_cat_name = 'Handsome'

# --- Pins ---------------------------------------------------------------------
touch_pin = board.D12          # wire into the water (touchio)
water_pin = board.A5           # Sharp GP2Y0A51SK0F output (ADC1, WiFi-safe)
feeder_pin = None              # relay not fitted yet; e.g. board.D6 later.
                               # None = deployments are logged, nothing switches.
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
touch_stuck_ms = 5000          # contact longer than this is not a lick (paw
                               # resting, level step): re-take the baseline

# --- Water level (Sharp IR sensor above the float) -----------------------------
# Higher voltage = float closer to the sensor = higher water.
# The recording version stores single reads; the two settings below are only
# used by WaterSensor.update(), i.e. by the bout-detection version.
water_sample_ms = 20           # the Sharp updates every ~16.5 ms
water_smooth_samples = 10      # moving average over this many samples (~200 ms)

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

# --- Lab WiFi (station mode: heartbeat, later fetching files) -------------------
# The credentials are NOT in this file: the repo is public. They go in
# settings.toml in the board's root (CIRCUITPY drive) and only there: no copy
# on the computer, sync2board never touches it. Edit it on the board, with
# these two lines:
#   WIFI_SSID = "network name"
#   WIFI_PASSWORD = "password"
# Don't use CircuitPython's own CIRCUITPY_WIFI_* names there: with those the
# board joins WiFi by itself at every boot (see HANDOFF.md). None = not set.
wifi_ssid = os.getenv("WIFI_SSID")
wifi_password = os.getenv("WIFI_PASSWORD")

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
# hours. ProcessLickData's reader converts to lab time.
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

# --- Watchdog ---------------------------------------------------------------------
# Resets the board when the loop stops feeding it (hang). Longer than the
# longest blocking step: WiFi join (10 s), heartbeat (up to ~3 x 10 s timeouts).
watchdog_timeout_s = 60               # None = no watchdog

# --- Upload speed test (TestUpload.py; done 2026-11-16, run it from Thonny) -----
# Sends to UploadSink/upload_sink.py on a computer on the home network. Its
# address depends on the network, so like the WiFi credentials it lives in
# settings.toml on the board:
#   UPLOAD_TEST_HOST = "192.168.1.23"
upload_test_host = os.getenv("UPLOAD_TEST_HOST")
upload_test_port = 5001
upload_test_window_ms = 5000           # one result per window
upload_test_chunk = 4096               # bytes per send(), as the real upload would
upload_test_tx_powers = (8.5, 13.0, 20.0)  # dBm; D1 cycles through them

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

# --- Deployment ----------------------------------------------------------------
deployment_bout_count = 1
wait_for_bout_close = False    # see BoardCode/lib/Settings.py for the meaning
deployment_duration_ms = 2000

# =============================================================================

# --- Status ---------------------------------------------------------------------
status_log_interval_ms = 60000  # periodic status line in system.log
display_interval_ms = 1000      # full-screen TFT redraw interval. Each redraw
                                # pauses sampling for ~150 ms, so ...
display_quiet_ms = 3000         # ... the screen is only redrawn after this long
                                # without touch contact (frozen while drinking)
