This repo processes data from a cat water lick sensor device. Ech data folder `data` is stored in two files: `licks.dat` and `system.log`. There might be multiple files for each as the device starts a new file after writing x number of lines.

Lick data fields

- time: wall-clock timestamp of the event.
- mono_ms: monotonic time in milliseconds since boot at the event.
- cat_name: detected cat name from the RFID reader (may be "unknown").
- lick: running count of valid licks within the current bout. Resets to 1 at the start of each new bout. On a bout-closure marker row, holds the total lick count of the just-closed bout.
- bout: cumulative bout count for the active cat at that moment.
- water: water level (V) sampled while in contact with the sensor.
- duration_ms: for a lick row, the contact duration; for a bout-closure marker row, the silent gap that triggered the close. Lick rows are the ones with `min_lick_ms <= duration_ms <= max_lick_ms`; rows outside that window are bout-closure markers.

System log format

Each line in system.log is a comma-separated record:

- time: timestamp of the log entry.
- mono_ms: monotonic time in milliseconds since boot when the state changes.
- ticks: system tick counter (integer).
- level: log level (for example INFO).
- source: bracketed component label (for example "Main Loop" or "MySystemLog").
- message: free-form message text, including events like cat switches and per-state summaries
  (for example "unknown: state=1 licks=0 bouts=0").
