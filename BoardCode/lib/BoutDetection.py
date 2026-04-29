"""
BoutDetection.py - Pure lick detection algorithm

This module contains the core bout detection algorithm that works
identically on the microcontroller board and in offline data analysis.

Key Features:
- BoutTracker: Tracks licks and forms bouts for a single cat
- BoutManager: Manages multiple cats and routes samples appropriately
- Pure algorithm: No hardware dependencies, no pandas requirements
- Consistent results: Same detection logic everywhere

Algorithm Parameters (from Settings):
- min_lick_ms: Minimum valid lick duration (default: 50ms)
- max_lick_ms: Maximum valid lick duration (default: 150ms)
- min_licks_per_bout: Minimum licks to form a bout (default: 3)
- max_bout_gap_ms: Maximum gap between licks in a bout (default: 300000ms / 5 min)
- debounce_ms: Debounce time for state changes (default: 5ms)
"""

def now():
    """Placeholder for hardware-specific time function"""
    try:
        import time
        return int(time.monotonic() * 1000)
    except:
        return 0

class BoutTracker:
    """
    Tracks lick bouts for a single cat using pure algorithm.
    
    This class handles:
    - Debouncing of sensor signals
    - Lick duration validation
    - Bout formation and timing
    - Bout statistics calculation
    
    All methods use timestamp parameters rather than calling time functions,
    making this class testable and hardware-independent.
    """
    
    def __init__(self, cat_name, min_lick_ms=50, max_lick_ms=150,
                 min_licks_per_bout=3, max_bout_gap_ms=300000, debounce_ms=5,
                 min_water_extent=0.0):
        """Initialize bout tracker for a specific cat"""
        self.cat_name = cat_name
        
        # Detection parameters
        self.min_lick_ms = min_lick_ms
        self.max_lick_ms = max_lick_ms
        self.min_licks_per_bout = min_licks_per_bout
        self.max_bout_gap_ms = max_bout_gap_ms
        self.debounce_ms = debounce_ms
        self.min_water_extent = min_water_extent
        
        # State tracking
        self.state = 0  # Current debounced state (0 or 1)
        self.state_since = 0  # Timestamp when current state started
        self.candidate_state = 0  # Candidate state during debounce
        self.candidate_since = None  # When candidate state started
        self.last_lick_end_ms = None  # When last lick ended
        
        # Bout tracking
        self.current_bout_start_ms = None  # When current bout started
        self.current_bout_start_water = None  # Water level at bout start
        self.current_bout_licks = []  # List of (duration_ms, water_level)
        self.last_bout_summary = None  # Summary of last completed bout
        
        # Counters
        self.lick_count = 0  # Licks in current bout
        self.bout_count = 0  # Total bouts completed
    
    def process_sample(self, binary_state, timestamp_ms, water_level=None):
        """
        Process a single binary sample and detect licks/bouts.
        
        Args:
            binary_state: 0 or 1 (contact sensor state)
            timestamp_ms: Current time in milliseconds
            water_level: Current water level (optional)
            
        Returns:
            tuple: (prev_state, curr_state, duration_ms, lick_added, bout_closed)
        """
        # Debounce the input state
        previous, current, duration = self._debounce_state(binary_state, timestamp_ms)
        lick_added, bout_closed = False, False
        
        # Falling edge (1->0): potential lick end
        if previous == 1 and current == 0:
            self.last_lick_end_ms = timestamp_ms
            
            # Validate lick duration
            if self.min_lick_ms <= duration <= self.max_lick_ms:
                self.lick_count += 1
                lick_added = True
                self._track_lick(duration, water_level)
        
        # Rising edge (0->1): potential bout start
        if previous == 0 and current == 1:
            if self.current_bout_start_ms is None:
                self.current_bout_start_ms = timestamp_ms
                self.current_bout_start_water = water_level
        
        # Check if bout should be closed (quiet period exceeded)
        if current == 0 and self.current_bout_start_ms is not None:
            ref_time = self.last_lick_end_ms if self.last_lick_end_ms is not None else self.current_bout_start_ms
            gap = timestamp_ms - ref_time
            if gap >= self.max_bout_gap_ms:
                if self.lick_count >= self.min_licks_per_bout:
                    if self._finalize_bout(timestamp_ms, water_level):
                        self.bout_count += 1
                        bout_closed = True
                self._reset_bout_tracking()
                self.lick_count = 0
        
        return previous, current, duration, lick_added, bout_closed
    
    def _debounce_state(self, binary_state, timestamp_ms):
        """Debounce algorithm - filters noisy sensor inputs"""
        previous_state = self.state
        duration = timestamp_ms - self.state_since
        
        # New candidate state detected
        if binary_state != self.candidate_state:
            self.candidate_state = binary_state
            self.candidate_since = timestamp_ms
            return previous_state, self.state, duration
        
        # Already in this state
        if self.candidate_state == self.state:
            return previous_state, self.state, duration
        
        # Debounce period elapsed - accept new state
        if (self.candidate_since is not None and 
            (timestamp_ms - self.candidate_since) >= self.debounce_ms):
            self.state = self.candidate_state
            self.state_since = timestamp_ms
            return previous_state, self.state, duration
        
        # Still debouncing
        return previous_state, self.state, duration
    
    def _track_lick(self, duration_ms, water_level):
        """Track an individual lick for bout summary"""
        if water_level is not None:
            self.current_bout_licks.append((duration_ms, water_level))
        
        # Initialize bout tracking if not already started
        if self.current_bout_start_ms is None:
            self.current_bout_start_ms = self.state_since
            self.current_bout_start_water = water_level
    
    def _finalize_bout(self, end_time, end_water):
        """Calculate and store bout statistics. Returns True if bout was kept, False if filtered."""
        if self.current_bout_start_ms is None or len(self.current_bout_licks) == 0:
            return self.min_water_extent <= 0  # no water data: pass only if filter is disabled
        
        # Calculate bout statistics
        bout_duration = end_time - self.current_bout_start_ms
        lick_count = len(self.current_bout_licks)
        
        # Water statistics
        start_water = self.current_bout_start_water
        end_water_level = end_water if end_water is not None else self.current_bout_licks[-1][1]
        water_delta = end_water_level - start_water if start_water is not None else None
        
        # Water extent (max - min during bout)
        if self.current_bout_licks and start_water is not None:
            water_levels = [start_water] + [w for _, w in self.current_bout_licks]
            water_extent = max(water_levels) - min(water_levels)
        else:
            water_extent = None

        # Check minimum water consumption using extent (max - min during bout)
        if self.min_water_extent > 0 and water_extent is not None and water_extent <= self.min_water_extent:
            return False

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
        return True
    
    def _reset_bout_tracking(self):
        """Reset bout tracking variables"""
        self.current_bout_start_ms = None
        self.current_bout_start_water = None
        self.current_bout_licks = []
    
    def end_bout(self, timestamp_ms, finalize_current_lick=True, water_level=None):
        """Force end the current bout"""
        lick_finalized = False
        
        if finalize_current_lick and self.state == 1:
            lick_duration = timestamp_ms - self.state_since
            self.last_lick_end_ms = timestamp_ms
            if self.min_lick_ms <= lick_duration <= self.max_lick_ms:
                self.lick_count += 1
                lick_finalized = True
                self._track_lick(lick_duration, water_level)
        
        if self.lick_count >= self.min_licks_per_bout:
            if self._finalize_bout(timestamp_ms, water_level):
                self.bout_count += 1
        self._reset_bout_tracking()
        self.lick_count = 0
        
        # Reset state
        self.state = 0
        self.candidate_state = 0
        self.state_since = timestamp_ms
        self.candidate_since = None
        if self.last_lick_end_ms is None:
            self.last_lick_end_ms = timestamp_ms
        
        return lick_finalized
    
    def close_if_stale(self, now_ms, water_level=None):
        """Close an in-progress bout if the gap to the cat's last activity
        exceeds max_bout_gap_ms. Uses last_lick_end_ms (or current_bout_start_ms
        as fallback) as the bout end time, so duration reflects the real
        drinking window rather than including any absence."""
        if self.current_bout_start_ms is None:
            return False
        ref_time = (self.last_lick_end_ms
                    if self.last_lick_end_ms is not None
                    else self.current_bout_start_ms)
        if (now_ms - ref_time) < self.max_bout_gap_ms:
            return False
        closed = False
        if self.lick_count >= self.min_licks_per_bout:
            if self._finalize_bout(ref_time, water_level):
                self.bout_count += 1
                closed = True
        self._reset_bout_tracking()
        self.lick_count = 0
        return closed

    def reset_counts(self, reset_licks=True, reset_bouts=True):
        """Reset counters"""
        if reset_licks:
            self.lick_count = 0
        if reset_bouts:
            self.bout_count = 0
            self.last_bout_summary = None
            self._reset_bout_tracking()
    
    def get_last_bout_summary(self):
        """Get summary of last completed bout"""
        return self.last_bout_summary
    
    def get_current_bout_info(self):
        """Get info about ongoing bout"""
        if self.current_bout_start_ms is None:
            return None
        return {
            'start_time': self.current_bout_start_ms,
            'start_water': self.current_bout_start_water,
            'lick_count_so_far': len(self.current_bout_licks)
        }
    
    def get_state_string(self):
        """Get human-readable state string"""
        return f"{self.cat_name}: state={self.state} licks={self.lick_count} bouts={self.bout_count}"

class BoutManager:
    """
    Manages bout detection for multiple cats.
    
    This class routes samples to the appropriate BoutTracker for each cat
    and provides a unified interface for bout detection.
    """
    
    def __init__(self, cat_names=None, **kwargs):
        """Initialize with list of cat names and detection parameters"""
        if cat_names is None:
            cat_names = ['unknown']
        
        if 'unknown' not in cat_names:
            cat_names.insert(0, 'unknown')
        
        self.cat_names = cat_names
        self.trackers = {name: BoutTracker(name, **kwargs) for name in cat_names}
        self.active_cat = cat_names[0]
    
    def process_sample(self, binary_state, timestamp_ms, water_level=None, cat_name=None):
        """
        Process a sample for the specified cat (or active cat).
        
        Args:
            binary_state: 0 or 1 (contact sensor state)
            timestamp_ms: Current time in milliseconds
            water_level: Current water level (optional)
            cat_name: Which cat to process for (optional)
            
        Returns:
            dict: Processing results including bout summary
        """
        cat_name = cat_name or self.active_cat
        tracker = self.trackers.get(cat_name)
        if tracker is None:
            # Create tracker for new cat
            tracker = BoutTracker(cat_name, **self._get_tracker_kwargs())
            self.trackers[cat_name] = tracker
            self.cat_names.append(cat_name)
        
        prev, curr, dur, lick_added, bout_closed = tracker.process_sample(
            binary_state, timestamp_ms, water_level
        )
        
        return {
            'cat_name': cat_name,
            'previous_state': prev,
            'current_state': curr,
            'state_duration_ms': dur,
            'lick_added': lick_added,
            'bout_closed': bout_closed,
            'lick_count': tracker.lick_count,
            'bout_count': tracker.bout_count,
            'bout_summary': tracker.get_last_bout_summary()
        }
    
    def _get_tracker_kwargs(self):
        """Get initialization parameters from first tracker"""
        first_tracker = next(iter(self.trackers.values()))
        return {
            'min_lick_ms': first_tracker.min_lick_ms,
            'max_lick_ms': first_tracker.max_lick_ms,
            'min_licks_per_bout': first_tracker.min_licks_per_bout,
            'max_bout_gap_ms': first_tracker.max_bout_gap_ms,
            'debounce_ms': first_tracker.debounce_ms,
            'min_water_extent': first_tracker.min_water_extent
        }
    
    def set_active_cat(self, cat_name, water_level=None):
        """Switch the active cat"""
        if cat_name == self.active_cat:
            return

        timestamp = now()

        # Only finalise the previous cat's bout when switching TO a known cat.
        # Switching to 'unknown' is treated as a transient RFID dropout, so the
        # previous cat's bout state is preserved for resumption when (or if)
        # they're seen again. A real departure is then handled by the gap-close
        # path inside process_sample.
        if cat_name != 'unknown' and self.active_cat in self.trackers:
            self.trackers[self.active_cat].end_bout(timestamp, water_level=water_level)

        # The cat we're switching to may carry a stale in-progress bout from
        # before they last disappeared. If too long has passed since their
        # last activity, close that bout now using their actual last-activity
        # time as the end (not now), so duration reflects real drinking, not
        # the absence.
        if cat_name in self.trackers:
            self.trackers[cat_name].close_if_stale(timestamp)

        self.active_cat = cat_name
    
    def get_last_bout_summary(self, cat_name=None):
        """Get last bout summary for specified cat"""
        cat_name = cat_name or self.active_cat
        tracker = self.trackers.get(cat_name)
        return tracker.get_last_bout_summary() if tracker else None
    
    def get_current_bout_info(self, cat_name=None):
        """Get current bout info for specified cat"""
        cat_name = cat_name or self.active_cat
        tracker = self.trackers.get(cat_name)
        return tracker.get_current_bout_info() if tracker else None
    
    def get_lick_count(self, cat_name=None):
        """Get lick count for specified cat"""
        cat_name = cat_name or self.active_cat
        tracker = self.trackers.get(cat_name)
        return tracker.lick_count if tracker else 0
    
    def get_bout_count(self, cat_name=None):
        """Get bout count for specified cat"""
        cat_name = cat_name or self.active_cat
        tracker = self.trackers.get(cat_name)
        return tracker.bout_count if tracker else 0

    def get_state(self, cat_name=None):
        """Get current binary sensor state for specified cat"""
        cat_name = cat_name or self.active_cat
        tracker = self.trackers.get(cat_name)
        return tracker.state if tracker else 0
    
    def reset_counts(self, cat_name=None):
        """Reset counts for specified cat"""
        cat_name = cat_name or self.active_cat
        if cat_name in self.trackers:
            self.trackers[cat_name].reset_counts()