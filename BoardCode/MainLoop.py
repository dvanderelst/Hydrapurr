import time
import traceback

import Cats
import Settings
from components.MySystemLog import setup_system_log, set_system_log_level, DEBUG, INFO, WARN, ERROR
from components.MySystemLog import debug, info, warn, error

from LickSensor import LickSensor
from TagReader import TagReader     # new non-blocking, scheduled-reset version
from HydraPurr import HydraPurr

# A small helper to update the screen
def update_screen(hp, ctr, current_cat, cat_name=None):
    bout_count = ctr.get_bout_count(cat_name)
    line0 = current_cat
    line1 = f'[B] {bout_count}'
    hp.write_line(0, line0)
    hp.write_line(1, line1)
    hp.show_screen()


def main_loop(level=DEBUG, sd_ok=True):
    info("[Main Loop] Start")
    set_system_log_level(level)
    setup_system_log()
    info("[Main Loop] System Log Started")

    all_cat_names = Cats.get_all_names()
    info(f'[Main Loop] all defined cats: {all_cat_names}')
    # Hardware / objects
    hydrapurr = HydraPurr()
    hydrapurr.write_line(0, 'SD card')
    hydrapurr.write_line(1, 'OK' if sd_ok else 'FAILED')
    hydrapurr.show_screen()
    time.sleep(3)
    clock = hydrapurr.get_time(as_string=False)
    hydrapurr.write_line(0, f"{clock['day']:02d}/{clock['month']:02d}/{clock['year']}")
    hydrapurr.write_line(1, f"{clock['hour']:02d}:{clock['minute']:02d}:{clock['second']:02d}")
    hydrapurr.show_screen()
    time.sleep(3)
    reader = TagReader()
    counter = LickSensor(cat_names=all_cat_names)
    info("[Main Loop] Objects created")

    # Presence/attribution state
    previous_lick_state_string = None
    previous_active_cat = 'unknown'  # matches BoutManager's initial active_cat
    previous_bout_count = 0
    previous_printed_tag = None

    deployment_bout_count = Settings.deployment_bout_count

    info("[Main Loop] Starting monitoring loop")
    while True:
      try:
        cat_changed = False
        bout_changed = False

        hydrapurr.heartbeat()
        
        # --- Check for data requests
        command = hydrapurr.bluetooth_poll()
        if command is not None:
            info(f'[Main Loop] Processing command: {command}')
            if command == 'licks': hydrapurr.bluetooth_send_data(kind='licks')
            if command == 'system': hydrapurr.bluetooth_send_data(kind='system')

        # --- Get the active cat --------------------------------------
        pkt = reader.poll_active()
        if pkt is None: pkt = {}
        tag_key = pkt.get("tag_key", None)
        
        if tag_key is not None and previous_printed_tag != tag_key:
            info(f'[Main Loop] Detected key {str(tag_key)}')
            previous_printed_tag = tag_key
            
        current_cat = Cats.get_name(tag_key)
        switched_from = None
        if current_cat != previous_active_cat:
            p = ("%-10s" % str(previous_active_cat))
            c = ("%-10s" % str(current_cat))
            info(f'[Main Loop] Cat switched {p}-> {c}')
            switched_from = previous_active_cat
            previous_active_cat = current_cat
            cat_changed = True

        # --- Process the lick --------------------------------------
        raw_lick_value = hydrapurr.read_lick(binary=False)
        counter.set_active_cat(current_cat)  # finalises switched_from's bout if cat changed

        # Check if the departing cat crossed the threshold when their bout was finalised
        if switched_from is not None:
            prev_bouts = counter.get_bout_count(switched_from)
            if prev_bouts >= deployment_bout_count:
                bout_summary = counter.get_last_bout_summary(switched_from)
                if bout_summary is not None:
                    lick_count = bout_summary.get('lick_count', 0)
                    duration_ms = bout_summary.get('duration_ms', 0)
                    water_extent = bout_summary.get('water_extent') or 0
                    water_delta = bout_summary.get('water_delta') or 0
                    info(f'[Main Loop] Last bout: {lick_count} licks {duration_ms}ms extent={water_extent:.3f}mm delta={water_delta:.3f}mm')
                update_screen(hydrapurr, counter, switched_from, switched_from)  # show count reached
                info(f'[Main Loop] Deployment bout count {deployment_bout_count} reached, for {switched_from}')
                hydrapurr.feeder_on()
                time.sleep(Settings.deployment_duration_ms/1000)
                hydrapurr.feeder_off()
                counter.reset_counts(switched_from)
                update_screen(hydrapurr, counter, switched_from, switched_from)  # show reset to 0

        result = counter.update(raw_lick_value)
        if result['previous_state'] == 0 and result['current_state'] == 1:
            info(f'[Main Loop] Lick start ({result["cat_name"]})')
        current_lick_state_string = counter.get_state_string()
        if current_lick_state_string != previous_lick_state_string:
            debug('[Main Loop] ' + current_lick_state_string)
            previous_lick_state_string = current_lick_state_string
            bout_count = counter.get_bout_count()
            if previous_bout_count != bout_count:
                previous_bout_count = bout_count
                bout_changed = True


        bout_count = counter.get_bout_count()

        if bout_changed:
            bout_summary = counter.get_last_bout_summary()
            if bout_summary is not None:
                lick_count = bout_summary.get('lick_count', 0)
                duration_ms = bout_summary.get('duration_ms', 0)
                water_extent = bout_summary.get('water_extent') or 0
                water_delta = bout_summary.get('water_delta') or 0
                info(f'[Main Loop] Last bout: {lick_count} licks {duration_ms}ms extent={water_extent:.3f}mm delta={water_delta:.3f}mm')

        if bout_count >= deployment_bout_count:
            update_screen(hydrapurr, counter, current_cat)  # show count reached
            info(f'[Main Loop] Deployment bout count {deployment_bout_count} reached, for {current_cat}')
            hydrapurr.feeder_on()
            time.sleep(Settings.deployment_duration_ms/1000)
            hydrapurr.feeder_off()
            counter.reset_counts()
            previous_bout_count = 0
            update_screen(hydrapurr, counter, current_cat)  # show reset to 0

        # --- Update screen --------------------------------------
        elif cat_changed or bout_changed: update_screen(hydrapurr, counter, current_cat)

        time.sleep(0.001)
      except Exception as e:
        error(f'[Main Loop] Unhandled exception: {e}')
        traceback.print_exception(e)
        raise
