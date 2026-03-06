import Tests
import MainLoop
import Settings
from components.MySystemLog import DEBUG, INFO, WARN, ERROR 
from components.MyStore import delete_file
from components.MySD import quick_self_test, mount_sd_card

print('Running...')

mount_sd_card()
# quick_self_test()  # Debug-only

clear_system_log = Settings.clear_system_log_on_start
clear_lick_data = Settings.clear_lick_data_on_start

system_log_filename = Settings.system_log_filename
lick_data_filename = Settings.lick_data_filename

if clear_system_log: delete_file(system_log_filename)
if clear_lick_data: delete_file(lick_data_filename)

tests_to_run = []
# Select which tests to run (same numbering as the old script)
# 0 -> blinking indicator LED
# 1 -> switching relay
# 2 -> screen test
# 3 -> water level reading
# 4 -> Bluetooth module
# 5 -> lick detection
# 6 -> writing to SD (log file)
# 7 -> set/get RTC time
# 8 -> RFID module
if len(tests_to_run) > 0: hp, log = Tests.main(tests_to_run)
else: MainLoop.main_loop(level=INFO)
