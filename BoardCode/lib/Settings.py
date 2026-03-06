
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
min_lick_ms = 50
max_lick_ms = 150
min_licks_per_bout = 3
max_bout_gap_ms = 12000
min_water_delta_per_bout = 0.0  # Minimum water extent (mm) to count a bout (0 = disabled)
                                # Uses extent = max_water_level - min_water_level during bout
                                # Positive extent = water level fluctuated during bout
                                # Larger extent = more water activity (likely consumption)
                                # Pass bouts with extent > threshold, filter bouts with extent <= threshold
                                # Set to 0.0 to disable water consumption filtering

cats={}
cats['61000000007E30010000000000'] = {'name': 'henk', 'age': 6}
cats['32E09C0000ED30010000000000'] = {'name': 'bob', 'age': 12}
cats['879B029A405D30010000000000'] = {'name': 'Handsome', 'age': 8}


