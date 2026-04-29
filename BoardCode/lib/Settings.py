
system_log_filename = "system.log"
lick_data_filename = "licks.dat"
system_log_max_lines = 2000
data_log_max_lines = 2000

clear_system_log_on_start = False
clear_lick_data_on_start = False

rfid_enabled = False    # When False, the RFID reader is not initialised and the device
                       # runs in single-cat mode: every lick is attributed to
                       # `single_cat_name` and the cat-switch logic is bypassed.
                       # Use for single-cat households or while the RFID hardware is
                       # being validated.
single_cat_name = 'Handsome'  # Cat that owns all licks when rfid_enabled = False.
                          # Must be one of the names registered in `cats` below
                          # (or any string — a tracker will be created on demand).
cat_timeout_ms = 2000  # switch to 'unknown' if no valid tag is seen for x ms.
                       # At ~333 ms RFID refresh + reset overhead, this tolerates
                       # ~6 missed read cycles before declaring a departure.
                       # (Only used when rfid_enabled = True.)
max_tag_read_hz = 3.0  # change here to adjust read refresh limit (Hz)
deployment_bout_count = 5
deployment_duration_ms = 2000
lick_threshold = 2.0
min_lick_ms = 50
max_lick_ms = 150
min_licks_per_bout = 3
max_bout_gap_ms = 10000   # 10 s. Two implications worth understanding:
                          # 1. Bout semantics — consecutive licks separated by less
                          #    than this value belong to the same bout. Shorter values
                          #    make a "bout" mean one visit to the bowl; longer values
                          #    make a "bout" span multiple drinking sessions in a
                          #    sitting. 10 s ≈ a single visit.
                          # 2. Reward latency — the feeder fires when a bout closes,
                          #    and a bout cannot close until `max_bout_gap_ms` of
                          #    silence has elapsed after the last lick. Keep this
                          #    small enough that the reward still falls inside the
                          #    operant association window (seconds, not minutes).
debounce_ms = 5                 # Debounce window for the contact-sensor state machine.
water_samples = 1               # Samples averaged per water-level reading.
                                # 1 = single read (~0ms, default); higher values add
                                # 1ms blocking per extra sample (via MyADC.mean) but
                                # reduce noise. Only read during lick contact.
min_water_extent_per_bout = 0.013 # Minimum water extent (V) to count a bout (0 = disabled)
                                # extent = max_water_level - min_water_level during bout
                                # Pass bouts with extent > threshold, filter bouts with extent <= threshold
                                # Set to 0.0 to disable water consumption filtering

cats={}
cats['61000000007E30010000000000'] = {'name': 'henk', 'age': 6}
cats['32E09C0000ED30010000000000'] = {'name': 'bob', 'age': 12}
cats['879B029A405D30010000000000'] = {'name': 'Handsome', 'age': 8}


