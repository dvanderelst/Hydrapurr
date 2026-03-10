# HydraPurr — Goals

## Purpose
Monitor cat drinking behaviour at a shared water fountain and automatically dispense food when a cat has completed enough drinking bouts.

## Core logic
1. **Cat identification** — RFID tags on each cat are read by a WL-134 reader (`TagReader`). The active cat is the last tag seen within a configurable timeout; if no tag is seen the cat is "unknown".
2. **Lick / contact detection** — An ADC reads a contact sensor on the water fountain. A raw voltage below a threshold is treated as contact (lick state = 1). Individual licks are validated by duration (`min_lick_ms` / `max_lick_ms`).
3. **Bout detection** — Valid licks are grouped into *bouts* (drinking sessions). A bout closes when there is no lick for `max_bout_gap_ms`. A bout only counts if it contains at least `min_licks_per_bout` licks (and optionally a minimum water-level fluctuation to confirm real drinking).
4. **Water level** — A second ADC channel monitors the physical water level. A sample is taken only when lick contact is active (state = 1), controlled by `water_samples` in Settings. The change in water level during a bout (`water_extent`) can be used to filter out false bouts (e.g. paw-touching without drinking).
5. **Feeder trigger** — When the bout count for a cat reaches `deployment_bout_count`, the relay/feeder is activated for `deployment_duration_ms` (blocking), then that cat's counter is reset. This is checked both for the currently active cat and for a departing cat at the moment of a cat-switch.
6. **Display** — An OLED screen shows the current cat name and cumulative bout count, updated on cat switch or bout change.
7. **Data logging** — Lick events (cat, state, lick count, bout count, water level) are appended to an SD card file (`licks.dat`). A separate system log (`system.log`) records diagnostic messages.
8. **Bluetooth interface** — A BT module listens for commands (`licks` / `system`) and streams the corresponding log file over Bluetooth for offline analysis.

## Architecture
- `code.py` — Entry point: mounts SD card, clears logs if configured, starts the main loop.
- `MainLoop.py` — Main polling loop: RFID → cat ID → lick ADC → bout detection → feeder → screen.
- `HydraPurr.py` — Hardware facade: wraps all peripherals (LED, feeder relay, OLED, BT, ADC, RTC, NeoPixel, data stores).
- `LickSensor.py` — Reads contact + water ADC, converts to binary state, feeds `BoutManager`, logs events to SD.
- `BoutDetection.py` — Pure algorithm (no hardware deps): `BoutTracker` per cat + `BoutManager` multi-cat router. Also supports offline batch processing of logged data via pandas.
- `TagReader.py` — Non-blocking RFID reader with rate-limiting, periodic reset, deduplication, and sticky "last seen" helper.
- `Cats.py` — Resolves RFID tag keys to cat names using the `Settings.cats` dict.
- `Settings.py` — Central configuration: filenames, thresholds, timing parameters, cat registry.
- `lib/components/` — Low-level drivers: `MyADC`, `MyDigital`, `MyOLED`, `MyBT`, `MyRTC`, `MyPixel`, `MySD`, `MyStore`, `MySystemLog`.
- `lib/components/FileUtil.py` — Shared file/CSV utilities (`count_lines`, `next_rotation_path`, `escape_csv`, `parse_csv_line`) used by `MyStore` and `MySystemLog`.

## Design constraints
- Runs on CircuitPython (RP2040 / Raspberry Pi Pico-class board).
- No OS, limited RAM — no pandas on device; `BoutDetection.py` gracefully falls back when pandas is absent.
- Most I/O is non-blocking; the main loop sleeps only 1 ms per iteration. Intentional exceptions: the feeder relay blocks for `deployment_duration_ms` (detection pauses while food is dispensed), and BT data streaming blocks while transmitting.
