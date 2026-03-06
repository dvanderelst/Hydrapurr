# Lick Sensor Data Flow Documentation

## Overview

This document explains the data flow through the refactored lick detection system, showing how raw sensor data is processed into bout information that can be used for feeding decisions.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        MAIN LOOP (MainLoop.py)                        │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      LICK SENSOR (LickSensor.py)                      │
│                                                                         │
│  Hardware Integration Layer:                                           │
│  • Reads contact sensor (ADC)                                          │
│  • Reads water level sensor                                            │
│  • Manages SD card logging                                             │
│  • Provides clean interface to MainLoop                                │
│                                                                         │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    BOUT DETECTION (BoutDetection.py)                   │
│                                                                         │
│  Core Algorithm Layer:                                                 │
│  • BoutManager - Routes samples to correct cat                         │
│  • BoutTracker - Detects licks, forms bouts, calculates statistics    │
│  • Pure Python - No hardware dependencies                             │
│  • Works identically on board and offline                              │
│                                                                         │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    HARDWARE (HydraPurr.py, Components)                │
│                                                                         │
│  • ADC sensors                                                        │
│  • Water level sensor                                                  │
│  • SD card                                                            │
│  • Real-time clock                                                    │
│  • Feeder control                                                     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────┘
```

## Detailed Data Flow

### 1. Main Loop → Lick Sensor

**MainLoop.py calls:**
```python
lick_sample = hydrapurr.read_lick()  # Raw ADC value (0-65535)
result = lick_sensor.update(lick_sample)
```

**Data passed to LickSensor:**
- `raw_adc_value`: Raw ADC reading from contact sensor (0-65535)

### 2. Lick Sensor Processing

**LickSensor.update() does:**
```python
def update(self, raw_adc_value, cat_name=None):
    # 1. Convert raw ADC to binary state
    binary_state = 1 if raw_adc_value < self.lick_threshold else 0
    
    # 2. Get current timestamp and water level
    timestamp = now()
    water_level = self.water_sensor.mean(10)
    
    # 3. Pass to core algorithm
    result = self.bout_manager.process_sample(
        binary_state, timestamp, water_level, cat_name
    )
    
    # 4. Log to SD card if state changed
    if result['lick_added'] or result['bout_closed']:
        self._log_to_sd_card(...)
    
    # 5. Return comprehensive results
    return {
        'cat_name': ...,
        'previous_state': ...,
        'current_state': ...,
        'lick_added': ...,
        'bout_closed': ...,
        'bout_summary': ...  # ← Key for feeding decisions!
    }
```

### 3. Bout Detection Processing

**BoutManager.process_sample() routes to BoutTracker:**
```python
def process_sample(self, binary_state, timestamp_ms, water_level, cat_name):
    tracker = self.trackers[cat_name]
    return tracker.process_sample(binary_state, timestamp_ms, water_level)
```

**BoutTracker.process_sample() detects licks and bouts:**
```python
def process_sample(self, binary_state, timestamp_ms, water_level):
    # 1. Debounce the input
    prev, curr, duration = self._debounce_state(binary_state, timestamp_ms)
    
    # 2. Detect licks (falling edge 1→0)
    if prev == 1 and curr == 0 and duration in valid range:
        self.lick_count += 1
        self._track_lick(duration, water_level)
    
    # 3. Start bout (rising edge 0→1)
    if prev == 0 and curr == 1:
        self.current_bout_start_ms = timestamp_ms
    
    # 4. Close bout (if quiet period exceeded)
    if curr == 0 and gap > max_bout_gap_ms:
        self._finalize_bout(timestamp_ms, water_level)
        self.bout_count += 1
    
    return (prev, curr, duration, lick_added, bout_closed)
```

### 4. Bout Summary Generation

When a bout is closed, BoutTracker calculates comprehensive statistics:

```python
self.last_bout_summary = {
    'cat_name': 'henk',
    'start_time': 12345678,      # ms since boot
    'end_time': 12347890,        # ms since boot
    'duration_ms': 2212,         # Total bout duration
    'lick_count': 5,             # Licks in this bout
    'start_water': 2.345,        # Water level at start
    'end_water': 2.123,          # Water level at end
    'water_delta': -0.222,       # Water consumed
    'water_extent': 0.050,       # Water variation
    'lick_durations': [120, 140, 130, 125, 115]  # Individual lick durations
}
```

### 5. Return to Main Loop

**MainLoop receives:**
```python
result = {
    'cat_name': 'henk',
    'previous_state': 1,
    'current_state': 0,
    'state_duration_ms': 140,
    'lick_added': True,
    'bout_closed': True,  # ← Important!
    'lick_count': 5,
    'bout_count': 1,
    'bout_summary': { ... }  # ← All the bout statistics
}
```

### 6. Feeding Decision in Main Loop

**Using bout summary for smart decisions:**
```python
if result['bout_closed']:
    bout = result['bout_summary']
    
    # Example decision logic:
    if bout['lick_count'] >= 5 and bout['duration_ms'] >= 2000:
        # This was a substantial drinking session
        hydrapurr.feeder_on()
        time.sleep(Settings.deployment_duration_ms / 1000)
        hydrapurr.feeder_off()
        lick_sensor.reset_counts()  # Reset for next bout
```

## Key Data Structures

### Bout Summary Structure

```python
{
    'cat_name': str,           # Which cat drank
    'start_time': int,         # Monotonic time (ms)
    'end_time': int,           # Monotonic time (ms)
    'duration_ms': int,        # Total bout duration
    'lick_count': int,         # Number of licks in bout
    'start_water': float,      # Water level at start
    'end_water': float,        # Water level at end
    'water_delta': float,      # Water consumed (end - start)
    'water_extent': float,     # Water variation (max - min)
    'lick_durations': [int]    # Individual lick durations
}
```

### Current Bout Info

```python
{
    'start_time': int,         # When bout started
    'start_water': float,      # Water level at start
    'lick_count_so_far': int   # Licks detected so far
}
```

## Example Data Flow Sequence

```
Time: 1000ms
MainLoop: read_lick() → 32000 (raw ADC)
LickSensor: 32000 < 2.0V threshold → binary_state = 1
BoutTracker: 0→1 transition → start potential bout
Result: {'current_state': 1, 'lick_added': False, 'bout_closed': False}

Time: 1120ms  
MainLoop: read_lick() → 18000 (raw ADC)
LickSensor: 18000 < 2.0V threshold → binary_state = 1
BoutTracker: still in contact → continue bout
Result: {'current_state': 1, 'lick_added': False, 'bout_closed': False}

Time: 1140ms
MainLoop: read_lick() → 35000 (raw ADC) 
LickSensor: 35000 > 2.0V threshold → binary_state = 0
BoutTracker: 1→0 transition, duration=120ms (valid lick!)
Result: {'current_state': 0, 'lick_added': True, 'bout_closed': False}

Time: 1250ms
MainLoop: read_lick() → 19000 (raw ADC)
LickSensor: 19000 < 2.0V threshold → binary_state = 1
BoutTracker: 0→1 transition → continue bout
Result: {'current_state': 1, 'lick_added': False, 'bout_closed': False}

Time: 1270ms
MainLoop: read_lick() → 34000 (raw ADC)
LickSensor: 34000 > 2.0V threshold → binary_state = 0
BoutTracker: 1→0 transition, duration=130ms (valid lick!)
Result: {'current_state': 0, 'lick_added': True, 'bout_closed': False}

... (more licks) ...

Time: 3500ms (2+ seconds after last lick)
MainLoop: read_lick() → 33000 (raw ADC)
LickSensor: 33000 > 2.0V threshold → binary_state = 0
BoutTracker: gap > 1000ms, 5 licks detected → CLOSE BOUT!
Result: {'current_state': 0, 'lick_added': False, 'bout_closed': True,
         'bout_summary': {'lick_count': 5, 'duration_ms': 2460, ...}}

MainLoop: bout_closed → check bout_summary → FEED THE CAT! 🐱
```

## Integration with Existing Code

### MainLoop.py Changes

**Before:**
```python
lick_state = 1 if hydrapurr.read_lick(binary=True) else 0
counter.set_active_cat(current_cat)
counter.update(lick_state)
if counter.get_bout_count() >= deployment_bout_count:
    hydrapurr.feeder_on()
    # ...
```

**After:**
```python
lick_sample = hydrapurr.read_lick()  # Raw ADC value
result = lick_sensor.update(lick_sample, current_cat)

if result['bout_closed']:
    bout = result['bout_summary']
    if bout['lick_count'] >= Settings.min_licks_for_feeding:
        hydrapurr.feeder_on()
        # ...
```

### Benefits of New Approach

1. **Rich Bout Information**: Access to duration, water change, lick count
2. **Smarter Decisions**: Can base feeding on actual drinking behavior
3. **Consistent Algorithm**: Same detection on board and offline
4. **Clean Interface**: Simple `update()` method returns everything needed
5. **Backward Compatible**: Can still use simple bout counting if desired

## Offline Analysis Flow

```python
# ProcessLickData/analysis/BoutAnalyzer.py
from BoardCode.lib.BoutDetection import BoutManager

# Load logged data
lick_data = pd.read_csv('licks.dat')

# Create bout manager with same settings as board
analyzer = BoutManager(
    min_lick_ms=Settings.min_lick_ms,
    max_lick_ms=Settings.max_lick_ms,
    min_licks_per_bout=Settings.min_licks_per_bout,
    max_bout_gap_ms=Settings.max_bout_gap_ms
)

# Process data using identical algorithm
events, summaries = analyzer.process_dataframe(lick_data)

# Results match what board would detect!
print(f"Found {len(summaries)} bouts")
for bout in summaries:
    print(f"Bout: {bout['duration']}ms, {bout['n']} licks, "
          f"Δwater: {bout['water_delta']:.3f}")
```

## Summary

The refactored system provides:

1. **Clean Data Flow**: Raw ADC → Binary State → Lick Detection → Bout Formation → Feeding Decision
2. **Separation of Concerns**: Hardware vs Algorithm vs Analysis
3. **Rich Information**: Detailed bout statistics for smart decisions
4. **Consistency**: Same algorithm on board and offline
5. **Testability**: Pure algorithm can be tested independently

The `LickSensor` class serves as the perfect integration point, combining sensor data and providing the MainLoop with exactly what it needs to make intelligent feeding decisions based on actual drinking behavior.