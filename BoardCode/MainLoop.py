import time

import Cats
import Settings
from components.MySystemLog import setup_system_log, set_system_log_level, DEBUG, INFO, WARN, ERROR
from components.MySystemLog import debug, info, warn, error

from LickSensor import LickSensor
from TagReader import TagReader     # new non-blocking, scheduled-reset version
from HydraPurr import HydraPurr

def now_ms(): return int(time.monotonic() * 1000)

# A small helper to update the screen
def update_screen(hp,ctr, current_cat):
    bout_count = ctr.get_bout_count()
    line0 = current_cat
    line1 = f'[B] {bout_count}'
    hp.write_line(0, line0)
    hp.write_line(1, line1)
    hp.show_screen()


def main_loop(level=DEBUG):
    info("[Main Loop] Start")
    set_system_log_level(level)
    setup_system_log()
    info("[Main Loop] System Log Started")

    all_cat_names = Cats.get_all_names()
    info(f'[Main Loop] all defined cats: {all_cat_names}')
    # Hardware / objects
    hydrapurr = HydraPurr()
    reader = TagReader()
    counter = LickSensor(cat_names=all_cat_names)
    info("[Main Loop] Objects created")

    # Presence/attribution state
    previous_lick_state_string = None
    previous_active_cat = None  # no cat at start
    previous_bout_count = 0
    previous_printed_tag = None

    info("[Main Loop] Starting monitoring loop")
    while True:
        cat_changed = False
        state_changed = False
        bout_changed = False
        
        #current_time = now_ms()
        hydrapurr.heartbeat()
        
        # --- Check for data requests
        command = hydrapurr.bluetooth_poll()
        if command is not None:
            info(f'[Main Loop] Processing command: {command}')
            if command == 'licks': hydrapurr.bluetooth_send_data(kind='licks')
            if command == 'system': hydrapurr.bluetooth_send_data(kind='system')
            info(f'[Main Loop] Processed command: {command}')

        # --- Get the active cat --------------------------------------
        pkt = reader.poll_active()
        if pkt is None: pkt = {}
        tag_key = pkt.get("tag_key", None)
        
        if tag_key is not None and previous_printed_tag != tag_key:
            info(f'[Main Loop] Detected key {str(tag_key)}')
            previous_printed_tag = tag_key
            
        current_cat = Cats.get_name(tag_key)
        if current_cat != previous_active_cat:
            p = ("%-10s" % str(previous_active_cat))
            c = ("%-10s" % str(current_cat))
            info(f'[Main Loop] Cat switched {p}-> {c}')
            previous_active_cat = current_cat
            cat_changed = True
        
        # --- Process the lick --------------------------------------
        raw_lick_value = hydrapurr.read_lick(binary=False)
        counter.set_active_cat(current_cat)
        counter.update(raw_lick_value)
        current_lick_state_string = counter.get_state_string()
        if current_lick_state_string != previous_lick_state_string:
            info('[Main Loop] ' + current_lick_state_string)
            previous_lick_state_string = current_lick_state_string
            bout_count = counter.get_bout_count()
            if previous_bout_count != bout_count:
                previous_bout_count = bout_count
                bout_changed = True


        deployment_bout_count = Settings.deployment_bout_count
        bout_count = counter.get_bout_count()
        
        # Access rich bout information for smarter feeding decisions
        bout_summary = counter.get_last_bout_summary()
        if bout_summary is not None:
            lick_count = bout_summary.get('lick_count', 0)
            duration_ms = bout_summary.get('duration_ms', 0)
            water_extent = bout_summary.get('water_extent', 0)
            water_delta = bout_summary.get('water_delta', 0)
            
            info(f'[Main Loop] Last bout: {lick_count} licks, {duration_ms}ms, extent={water_extent:.3f}mm, delta={water_delta:.3f}mm')
            
            # Example: Only feed if bout shows significant water consumption
            # if water_extent > Settings.min_water_delta_per_bout:
            #     info(f'[Main Loop] Significant consumption detected, feeding {current_cat}')
            #     hydrapurr.feeder_on()
            #     time.sleep(Settings.deployment_duration_ms/1000)
            #     hydrapurr.feeder_off()
            #     counter.reset_counts()
            #     bout_changed = True
        
        if bout_count >= deployment_bout_count:
            # update before feeding to make sure user sees the count reached
            update_screen(hydrapurr, counter, current_cat)

            info(f'[Main Loop] Deployment bout count {deployment_bout_count} reached, for {current_cat}')
            hydrapurr.feeder_on()
            time.sleep(Settings.deployment_duration_ms/1000)
            hydrapurr.feeder_off()
            counter.reset_counts()
            bout_changed = True

        # --- Update screen --------------------------------------
        if cat_changed or bout_changed: update_screen(hydrapurr,counter, current_cat)

            
