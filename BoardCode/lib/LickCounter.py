# This file has been refactored into LickSensor.py
# The core algorithm is now in BoutDetection.py
# This file is kept for backward compatibility

import time
from components.MyStore import MyStore
from components.MyADC import MyADC
import Settings
from BoutDetection import BoutManager

def now(): return int(time.monotonic() * 1000)  # int ms for consistency

class LickState:
    def __init__(self, cat_name):
        self.cat_name = cat_name
        self.lick_count = 0
        self.bout_count = 0
        self.state = 0
        self.state_since = now()
        self.candidate_state = 0
        self.candidate_since = None
        self.last_lick_end_ms = None
        # Bout tracking
        self.current_bout_start_ms = None
        self.current_bout_start_water = None
        self.current_bout_licks = []  # List of (lick_duration_ms, water_level)
        self.last_bout_summary = None
        # Parameters
        self.debounce_ms = 5 # Let's keep this fixed for now
        self.min_lick_ms = Settings.min_lick_ms
        self.max_lick_ms = Settings.max_lick_ms
        self.min_licks_per_bout = Settings.min_licks_per_bout
        self.max_bout_gap_ms = Settings.max_bout_gap_ms

    def process_sample(self, sample, water_level=None):
        current_time = now()
        previous, current, duration = self.debounce_state(sample)
        lick_added, bout_closed = False, False

        # Falling edge (1->0): finalize lick
        if previous == 1 and current == 0:
            self.last_lick_end_ms = current_time
            if self.min_lick_ms <= duration <= self.max_lick_ms:
                self.lick_count += 1
                lick_added = True
                
                # Start bout tracking if not already started
                if self.current_bout_start_ms is None:
                    self.current_bout_start_ms = current_time - duration  # Approximate start
                    self.current_bout_start_water = water_level
                
                # Track this lick for bout summary
                if water_level is not None:
                    self.current_bout_licks.append((duration, water_level))

        # Rising edge (0->1): start potential bout
        if previous == 0 and current == 1:
            if self.current_bout_start_ms is None:
                self.current_bout_start_ms = current_time
                self.current_bout_start_water = water_level

        # Close bout if quiet long enough and we had licks
        if current == 0 and self.lick_count > 0:
            gap = current_time - self.last_lick_end_ms
            if gap >= self.max_bout_gap_ms:
                if self.lick_count >= self.min_licks_per_bout:
                    self.bout_count += 1
                    bout_closed = True
                    # Create bout summary
                    self._finalize_bout_summary(current_time, water_level)
                self.lick_count = 0  # reset per-bout counter
                self._reset_bout_tracking()

        return previous, current, duration, lick_added, bout_closed

    def debounce_state(self, sample):
        t = now()
        previous_state = self.state
        duration = t - self.state_since

        if sample != self.candidate_state:
            self.candidate_state = sample
            self.candidate_since = t
            return previous_state, self.state, duration

        if self.candidate_state == self.state:
            return previous_state, self.state, duration

        if self.candidate_since is not None and (t - self.candidate_since) >= self.debounce_ms:
            self.state = self.candidate_state
            self.state_since = t
            return previous_state, self.state, duration

        return previous_state, self.state, duration

    def _finalize_bout_summary(self, end_time, end_water):
        """Create a summary of the completed bout"""
        if self.current_bout_start_ms is None or len(self.current_bout_licks) == 0:
            return
        
        # Calculate bout statistics
        bout_duration = end_time - self.current_bout_start_ms
        lick_count = len(self.current_bout_licks)
        
        # Water statistics
        start_water = self.current_bout_start_water
        end_water_level = end_water if end_water is not None else (self.current_bout_licks[-1][1] if self.current_bout_licks else None)
        water_delta = end_water_level - start_water if (start_water is not None and end_water_level is not None) else None
        
        # Water extent (max - min during bout)
        if self.current_bout_licks and start_water is not None:
            water_levels = [start_water] + [w for _, w in self.current_bout_licks]
            water_extent = max(water_levels) - min(water_levels)
        else:
            water_extent = None
        
        # Store bout summary
        self.last_bout_summary = {
            'cat_name': self.cat_name,
            'start_time': self.current_bout_start_ms,
            'end_time': end_time,
            'duration_ms': bout_duration,
            'lick_count': lick_count,
            'start_water': start_water,
            'end_water': end_water_level,
            'water_delta': water_delta,
            'water_extent': water_extent,
            'lick_durations': [d for d, _ in self.current_bout_licks]
        }

    def _reset_bout_tracking(self):
        """Reset bout tracking variables"""
        self.current_bout_start_ms = None
        self.current_bout_start_water = None
        self.current_bout_licks = []

    def end_bout(self, hard=True, finalize_current_lick=True):
        current_time = now()
        lick_finalized, lick_duration, bout_closed = False, None, False

        if finalize_current_lick and self.state == 1:
            lick_duration = current_time - self.state_since
            self.last_lick_end_ms = current_time
            if self.min_lick_ms <= lick_duration <= self.max_lick_ms:
                self.lick_count += 1
                lick_finalized = True

        if self.lick_count > 0:
            if self.lick_count >= self.min_licks_per_bout:
                self.bout_count += 1
                bout_closed = True
                # Finalize bout summary before reset
                water_level = None  # We don't have water level in this context
                self._finalize_bout_summary(current_time, water_level)
            self.lick_count = 0
            self._reset_bout_tracking()

        if hard:
            self.state = 0
            self.candidate_state = 0
            self.state_since = current_time
            self.candidate_since = None
            if self.last_lick_end_ms is None:
                self.last_lick_end_ms = current_time

        return lick_finalized, lick_duration, bout_closed

    def reset_counts(self, reset_licks=True, reset_bouts=True):
        if reset_licks: self.lick_count = 0
        if reset_bouts: self.bout_count = 0
        if reset_bouts: self._reset_bout_tracking()
    
    def get_last_bout_summary(self):
        """Get summary of the last completed bout"""
        return self.last_bout_summary
    
    def get_current_bout_info(self):
        """Get info about the current ongoing bout (if any)"""
        if self.current_bout_start_ms is None:
            return None
        return {
            'start_time': self.current_bout_start_ms,
            'start_water': self.current_bout_start_water,
            'lick_count_so_far': len(self.current_bout_licks)
        }

class LickCounter:
    def __init__(self, cat_names=None):
        file_name= Settings.lick_data_filename
        if cat_names is None: cat_names = ['unknown']
        if 'unknown' not in cat_names: cat_names.insert(0, 'unknown')
        self.active_cat_name = 'unknown'
        self.cat_names = cat_names
        self.header = ["cat_name", "state", "lick", "bout", 'water']
        self.store = MyStore(file_name, auto_header=self.header, max_lines=Settings.data_log_max_lines)
        self.states = {name: LickState(name) for name in cat_names}
        self.water_level = MyADC(0)

    def set_active_cat(self, cat_name):
        if cat_name == self.active_cat_name: return
        prev_cat = self.active_cat_name
        self.states[prev_cat].end_bout()   # finalize previous cat
        self.log_data(prev_cat)            # log closure/reset for prev cat
        self.active_cat_name = cat_name
        # Optional: also log an entry for the new active cat immediately:
        # self.log_data(cat_name)

    def get_active_state(self): return self.states.get(self.active_cat_name)

    def clear_log(self):
        self.store.empty()
        self.store.header(self.header, label=self.store.time_label)

    def read_data_log(self): return self.store.read()

    def update(self, sample, cat_name=None):
        if cat_name is None: cat_name = self.active_cat_name
        state = self.states.get(cat_name)
        previous_state_string = self.get_state_string(cat_name=cat_name)
        
        # Get current water level for bout tracking
        water_level = self.water_level.mean(10)  # update reading
        
        prev, curr, dur, lick_added, bout_closed = state.process_sample(sample, water_level)
        current_state_string = self.get_state_string(cat_name=cat_name)
        if previous_state_string != current_state_string: self.log_data(cat_name=cat_name)
        return {
            "cat_name": state.cat_name,
            "previous_state": prev,
            "current_state": curr,
            "state_duration_ms": dur,
            "lick_added": lick_added,
            "bout_closed": bout_closed,
            "lick_count": state.lick_count,
            "bout_count": state.bout_count,
            "state_string": current_state_string,
            "water_level": water_level,
        }

    def get_bout_count(self, cat_name=None):
        if cat_name is None: cat_name = self.active_cat_name
        return self.states.get(cat_name).bout_count

    def get_lick_count(self, cat_name=None):
        if cat_name is None: cat_name = self.active_cat_name
        return self.states.get(cat_name).lick_count

    def get_state_string(self, cat_name=None):
        if cat_name is None: cat_name = self.active_cat_name
        s = self.states.get(cat_name)
        return f"{cat_name}: state={s.state} licks={s.lick_count} bouts={s.bout_count}"

    def get_state_data(self, cat_name=None):
        if cat_name is None: cat_name = self.active_cat_name
        s = self.states.get(cat_name)
        water_level = self.water_level.mean(10)  # update reading
        return [cat_name, s.state, s.lick_count, s.bout_count, water_level]
    
    def get_last_bout_summary(self, cat_name=None):
        """Get summary of the last completed bout for a cat"""
        if cat_name is None: cat_name = self.active_cat_name
        state = self.states.get(cat_name)
        return state.get_last_bout_summary()
    
    def get_current_bout_info(self, cat_name=None):
        """Get info about the current ongoing bout for a cat"""
        if cat_name is None: cat_name = self.active_cat_name
        state = self.states.get(cat_name)
        return state.get_current_bout_info()

    def reset_counts(self, cat_name=None):
        if cat_name is None: cat_name = self.active_cat_name
        s = self.states.get(cat_name)
        s.reset_counts()
        self.log_data(cat_name=cat_name)

    def log_data(self, cat_name=None):
        if cat_name is None: cat_name = self.active_cat_name
        self.store.add(self.get_state_data(cat_name=cat_name))
    
    def process_dataframe(self, df, group_gap_ms=None, min_group_size=None):
        """
        Batch process a dataframe of lick data (offline analysis)
        
        Args:
            df: DataFrame with columns ['time', 'cat_name', 'state', 'lick', 'bout', 'water']
            group_gap_ms: Maximum gap between licks to consider them part of same bout (ms)
            min_group_size: Minimum number of licks in a bout to be valid
            
        Returns:
            tuple: (processed_df, summary_df) matching the format of utils.process_licks()
        """
        if not PANDAS_AVAILABLE:
            raise ImportError("pandas and numpy required for dataframe processing")
        
        # Use provided parameters or fall back to settings
        if group_gap_ms is None:
            group_gap_ms = Settings.max_bout_gap_ms
        if min_group_size is None:
            min_group_size = Settings.min_licks_per_bout
        
        # Filter to keep only state transitions (0->1 and 1->0)
        lick_events = self._filter_lick_events(df)
        
        # Process events to create lick/bout records
        results = self._process_lick_events(lick_events, group_gap_ms)
        results_df = pd.DataFrame(
            results,
            columns=['index', 'time', 'duration', 'water', 'water_delta', 'group'],
        )
        
        # Apply minimum group size filtering
        if min_group_size > 1 and not results_df.empty:
            results_df = self._filter_small_groups(results_df, min_group_size)
        
        # Add group_index column
        results_df = self._add_group_indices(results_df)
        
        # Create summary statistics
        summary_df = self._create_bout_summary(results_df)
        
        return results_df, summary_df
    
    def _filter_lick_events(self, df):
        """Filter dataframe to keep only state transitions"""
        line_count = df.shape[0]
        retained_lines = []
        previous_state = 0
        
        for line_nr in range(0, line_count):
            current_line = df.iloc[line_nr, :]
            current_state = int(current_line['state'])
            if previous_state == 0 and current_state == 1:
                retained_lines.append(current_line)
            if previous_state == 1 and current_state == 0:
                retained_lines.append(current_line)
            previous_state = current_state
        
        retained_lines = pd.DataFrame(retained_lines)
        print('Lick events filtered:')
        print('Original Lines:', line_count)
        print('Retained Lines:', retained_lines.shape[0])
        print("-" * 55)
        return retained_lines
    
    def _process_lick_events(self, lick_events, group_gap_ms):
        """Process lick events into bouts"""
        line_count = lick_events.shape[0]
        previous_state = 0
        count = 0
        onset_time = None
        previous_water = None
        last_offset_time = None
        group = -1
        results = []
        
        for line_nr in range(0, line_count):
            current_line = lick_events.iloc[line_nr, :]
            current_state = int(current_line['state'])
            
            if previous_state == 0 and current_state == 1:
                print('Lick started')
                onset_time = current_line['time']
                previous_water = current_line['water']
                
            if previous_state == 1 and current_state == 0:
                offset_time = current_line['time']
                current_water = current_line['water']
                duration = offset_time - onset_time
                water_delta = current_water - previous_water
                duration = duration.total_seconds() * 1000
                
                if last_offset_time is None:
                    group += 1
                else:
                    gap_ms = (offset_time - last_offset_time).total_seconds() * 1000
                    if gap_ms > group_gap_ms:
                        group += 1
                
                results.append([count, offset_time, duration, current_water, water_delta, group])
                last_offset_time = offset_time
                count = count + 1
                print(line_nr, 'Lick ended', duration)
            
            previous_state = current_state
        
        return results
    
    def _filter_small_groups(self, results_df, min_group_size):
        """Filter out groups with fewer than min_group_size licks"""
        group_counts = results_df["group"].value_counts()
        small_groups = group_counts[group_counts < min_group_size].index
        results_df.loc[results_df["group"].isin(small_groups), "group"] = np.nan
        
        kept_groups = sorted(results_df["group"].dropna().unique())
        group_map = {group_id: idx for idx, group_id in enumerate(kept_groups)}
        results_df.loc[results_df["group"].notna(), "group"] = (
            results_df.loc[results_df["group"].notna(), "group"].map(group_map)
        )
        return results_df
    
    def _add_group_indices(self, results_df):
        """Add group_index column showing position within group"""
        results_df["group_index"] = np.nan
        if not results_df.empty:
            grouped_mask = results_df["group"].notna()
            results_df.loc[grouped_mask, "group_index"] = (
                results_df.loc[grouped_mask]
                .groupby("group")
                .cumcount()
            )
        return results_df
    
    def _create_bout_summary(self, results_df):
        """Create summary statistics for each bout"""
        summary_rows = []
        if not results_df.empty:
            grouped = results_df.dropna(subset=["group"]).copy()
            if not grouped.empty:
                grouped["group"] = grouped["group"].astype(int)
                for group_id, group_df in grouped.groupby("group"):
                    start_time = group_df["time"].iloc[0]
                    end_time = group_df["time"].iloc[-1]
                    duration_ms = (end_time - start_time).total_seconds() * 1000
                    start_water = group_df["water"].iloc[0]
                    end_water = group_df["water"].iloc[-1]
                    summary_rows.append(
                        {
                            "group": group_id,
                            "duration": duration_ms,
                            "n": int(group_df.shape[0]),
                            "water_delta": end_water - start_water,
                            "water_extent": group_df["water"].max() - group_df["water"].min(),
                        }
                    )
        
        return pd.DataFrame(
            summary_rows,
            columns=["group", "duration", "n", "water_delta", "water_extent"],
        )
