"""
LickSensor.py - Hardware integration layer for lick detection

This module provides the hardware-specific implementation that:
- Reads contact and water level sensors
- Logs data to SD card
- Uses BoutDetection for the core algorithm
- Provides clean interface to MainLoop

The LickSensor class replaces the old LickCounter, providing the same
interface but with enhanced bout tracking capabilities.
"""

import time
from components.MyStore import MyStore
from components.MyADC import MyADC
import Settings
from BoutDetection import BoutManager

def now(): 
    """Get current time in milliseconds (hardware-specific)"""
    return int(time.monotonic() * 1000)

class LickSensor:
    """
    Hardware integration for lick detection and bout tracking.
    
    This class handles:
    - Reading contact sensor (ADC → binary conversion)
    - Reading water level sensor
    - Logging to SD card
    - Managing cat switching
    - Providing clean interface to MainLoop
    
    Uses BoutManager for the core detection algorithm.
    """
    
    def __init__(self, cat_names=None, min_water_delta=None):
        """
        Initialize LickSensor with optional list of cat names.
        
        Args:
            cat_names: List of cat names to track (default: ['unknown'])
            min_water_delta: Minimum water level change to count a bout (mm)
                           If None, uses Settings.min_water_delta_per_bout
        """
        # Hardware components
        self.water_sensor = MyADC(0)  # Water level sensor on channel 0
        self.data_store = MyStore(
            Settings.lick_data_filename,
            auto_header=["cat_name", "state", "lick", "bout", "water"],
            max_lines=Settings.data_log_max_lines
        )
        self.lick_threshold = 2.0  # Voltage threshold for contact detection
        
        # Core detection algorithm
        if min_water_delta is None:
            min_water_delta = getattr(Settings, 'min_water_delta_per_bout', 0.1)
        
        self.bout_manager = BoutManager(
            cat_names=cat_names,
            min_lick_ms=Settings.min_lick_ms,
            max_lick_ms=Settings.max_lick_ms,
            min_licks_per_bout=Settings.min_licks_per_bout,
            max_bout_gap_ms=Settings.max_bout_gap_ms,
            min_water_delta=min_water_delta
        )
    
    def update(self, raw_adc_value, cat_name=None):
        """
        Process a raw ADC sample and update lick/bout detection.
        
        Args:
            raw_adc_value: Raw ADC value from contact sensor (0-65535)
            cat_name: Name of cat (optional, uses active cat if None)
            
        Returns:
            dict: Processing results including:
                - cat_name: Which cat this applies to
                - previous_state: Previous binary state (0 or 1)
                - current_state: Current binary state (0 or 1)
                - state_duration_ms: Duration of current state
                - lick_added: True if a valid lick was detected
                - bout_closed: True if a bout was completed
                - lick_count: Total licks for this cat
                - bout_count: Total bouts for this cat
                - bout_summary: Summary of last completed bout (if any)
                - water_level: Current water level
        """
        # Convert raw ADC to binary state
        binary_state = 1 if raw_adc_value < self.lick_threshold else 0
        
        # Get current timestamp and water level
        timestamp_ms = now()
        water_level = self.water_sensor.mean(10)  # Average 10 samples
        
        # Process through core algorithm
        result = self.bout_manager.process_sample(
            binary_state, timestamp_ms, water_level, cat_name
        )
        
        # Log to SD card if state changed (lick added or bout closed)
        if result['lick_added'] or result['bout_closed']:
            self._log_to_sd_card(
                result['cat_name'],
                result['current_state'],
                result['lick_count'],
                result['bout_count'],
                water_level
            )
        
        # Add water level to results
        result['water_level'] = water_level
        
        return result
    
    def _log_to_sd_card(self, cat_name, state, lick_count, bout_count, water_level):
        """Log event data to SD card"""
        data = [cat_name, state, lick_count, bout_count, water_level]
        self.data_store.add(data)
    
    def set_active_cat(self, cat_name):
        """Set the active cat (finalizes previous cat's bout)"""
        self.bout_manager.set_active_cat(cat_name)
    
    def get_last_bout_summary(self, cat_name=None):
        """Get summary of last completed bout for specified cat"""
        return self.bout_manager.get_last_bout_summary(cat_name)
    
    def get_current_bout_info(self, cat_name=None):
        """Get info about ongoing bout for specified cat"""
        return self.bout_manager.get_current_bout_info(cat_name)
    
    def get_lick_count(self, cat_name=None):
        """Get lick count for specified cat"""
        return self.bout_manager.get_lick_count(cat_name)
    
    def get_bout_count(self, cat_name=None):
        """Get bout count for specified cat"""
        return self.bout_manager.get_bout_count(cat_name)
    
    def reset_counts(self, cat_name=None):
        """Reset lick and bout counts for specified cat"""
        self.bout_manager.reset_counts(cat_name)
    
    def clear_log(self):
        """Clear the SD card log file"""
        self.data_store.empty()
        # Re-add header
        self.data_store.header(
            ["cat_name", "state", "lick", "bout", "water"],
            label=self.data_store.time_label
        )
    
    def read_data_log(self):
        """Read the logged data from SD card"""
        return self.data_store.read()
    
    # Backward compatibility methods
    def get_state_string(self, cat_name=None):
        """Get state string (backward compatibility)"""
        cat_name = cat_name or self.bout_manager.active_cat
        tracker = self.bout_manager.trackers.get(cat_name)
        if tracker:
            return tracker.get_state_string()
        return f"{cat_name}: state=0 licks=0 bouts=0"
    
    def get_state_data(self, cat_name=None):
        """Get state data (backward compatibility)"""
        cat_name = cat_name or self.bout_manager.active_cat
        water_level = self.water_sensor.mean(10)
        return [
            cat_name,
            self.bout_manager.get_state(cat_name),  # This method needs to be added
            self.get_lick_count(cat_name),
            self.get_bout_count(cat_name),
            water_level
        ]

# Backward compatibility: alias LickCounter to LickSensor
LickCounter = LickSensor