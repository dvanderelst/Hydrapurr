
system_log_filename = "system.log"
lick_data_filename = "licks.dat"
system_log_max_lines = 2000
data_log_max_lines = 2000

clear_system_log_on_start = False
clear_lick_data_on_start = False

cat_timeout_ms = 1000  # switch to 'unknown' if no valid tag is seen for x ms
max_tag_read_hz = 3.0  # change here to adjust read refresh limit (Hz)
deployment_bout_count = 5
deployment_duration_ms = 2000
lick_threshold = 2.0
min_lick_ms = 50
max_lick_ms = 150
min_licks_per_bout = 3
max_bout_gap_ms = 1000
water_samples = 1               # Samples averaged per water-level reading.
                                # 1 = single read (~0ms, default); higher values add
                                # 1ms blocking per extra sample (via MyADC.mean) but
                                # reduce noise. Only read during lick contact.
min_water_extent_per_bout = 0.0 # Minimum water extent (mm) to count a bout (0 = disabled)
                                # extent = max_water_level - min_water_level during bout
                                # Pass bouts with extent > threshold, filter bouts with extent <= threshold
                                # Set to 0.0 to disable water consumption filtering

cats={}
cats['61000000007E30010000000000'] = {'name': 'henk', 'age': 6}
cats['32E09C0000ED30010000000000'] = {'name': 'bob', 'age': 12}
cats['879B029A405D30010000000000'] = {'name': 'Handsome', 'age': 8}


