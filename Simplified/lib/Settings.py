# Settings for the Simplified HydraPurr (Feather ESP32-S3 Reverse TFT +
# Adalogger FeatherWing, capacitive water wire, Sharp float sensor).
#
# Names match BoardCode/lib/Settings.py wherever the meaning is the same, so
# the copied modules (BoutDetection, MyStore, MySystemLog) work unchanged.

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
# ~30 bytes per row: at 100 rows/s that is ~260 MB per day.
raw_log_enabled = True
raw_log_interval_ms = 10       # one row per 10 ms = 100 rows/s
raw_log_sync_ms = 5000         # flush to the card this often; a power cut
                               # loses at most this much data

# --- Download mode (D1 button, see DownloadMode.py) ------------------------------
# The board's own WiFi network, only on while in download mode.
download_ap_ssid = "HydraPurr"
download_ap_password = "hydrapurr"     # WPA2: at least 8 characters
download_timeout_ms = 15 * 60 * 1000   # back to recording after 15 min idle
download_tx_power_dbm = 8.5            # radio power in download mode (max ~20);
                                       # lower = smaller current spikes

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
