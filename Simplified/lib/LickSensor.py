"""
LickSensor.py - glue between the sensors, BoutDetection and licks.dat

Adapted from BoardCode/lib/LickSensor.py. The difference: it no longer reads
any hardware itself. The caller passes in the contact state (from
TouchSensor) and the water level (from WaterSensor), so the old
`lick_voltage < lick_threshold` conversion is gone.

licks.dat keeps BoardCode's columns (time, mono_ms, cat_name, lick, bout,
water, duration_ms) so ProcessLickData can read it.
"""

import time
from components.MyStore import MyStore
import Settings
from BoutDetection import BoutManager

LICK_COLUMNS = ["cat_name", "lick", "bout", "water", "duration_ms"]


def now_ms():
    return int(time.monotonic() * 1000)


class LickSensor:
    def __init__(self, cat_names=None):
        self.data_store = MyStore(
            Settings.lick_data_filename,
            auto_header=LICK_COLUMNS,
            max_lines=Settings.data_log_max_lines
        )
        self.bout_manager = BoutManager(
            cat_names=cat_names,
            min_lick_ms=Settings.min_lick_ms,
            max_lick_ms=Settings.max_lick_ms,
            min_licks_per_bout=Settings.min_licks_per_bout,
            max_bout_gap_ms=Settings.max_bout_gap_ms,
            debounce_ms=Settings.debounce_ms,
            min_water_extent=Settings.min_water_extent_per_bout
        )
        self._last_water = None

    def update(self, contact, water_level, t_ms=None):
        """Feed one contact sample (0/1) and the current water level.
        Returns BoutManager's result dict plus 'water_level'."""
        t_ms = now_ms() if t_ms is None else t_ms
        self._last_water = water_level
        result = self.bout_manager.process_sample(contact, t_ms, water_level)

        if result['lick_added'] or result['bout_closed']:
            # On bout close lick_count is already reset to 0; use summary for true count
            log_lick_count = result['lick_count']
            if result['bout_closed'] and result.get('bout_summary'):
                log_lick_count = result['bout_summary'].get('lick_count', 0)
            self.data_store.add([result['cat_name'], log_lick_count, result['bout_count'],
                                 water_level, result['state_duration_ms']])

        result['water_level'] = water_level
        return result

    def set_active_cat(self, cat_name):
        self.bout_manager.set_active_cat(cat_name, water_level=self._last_water)

    def try_finalize_in_progress(self, cat_name=None):
        """No-wait deploy mode: early-close the in-progress bout. See
        BoutTracker.try_finalize_in_progress."""
        return self.bout_manager.try_finalize_in_progress(now_ms(), self._last_water, cat_name)

    def get_last_bout_summary(self, cat_name=None):
        return self.bout_manager.get_last_bout_summary(cat_name)

    def get_lick_count(self, cat_name=None):
        return self.bout_manager.get_lick_count(cat_name)

    def get_bout_count(self, cat_name=None):
        return self.bout_manager.get_bout_count(cat_name)

    def reset_counts(self, cat_name=None):
        self.bout_manager.reset_counts(cat_name)

    def get_state_string(self, cat_name=None):
        cat_name = cat_name or self.bout_manager.active_cat
        tracker = self.bout_manager.trackers.get(cat_name)
        if tracker:
            return tracker.get_state_string()
        return f"{cat_name}: state=0 licks=0 bouts=0"
