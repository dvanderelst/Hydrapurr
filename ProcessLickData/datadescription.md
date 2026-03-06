This repo processes data from a cat water lick sensor device. Ech data folder `data` is stored in two files: `licks.dat` and `system.log`. There might be multiple files for each as the device starts a new file after writing x number of lines.

Lick data fields

- time: timestamp recorded when the state changes.
- mono_ms: monotonic time in milliseconds since boot when the state changes.
- cat_name: detected cat name from the RFID reader (may be "unknown").
- state: 1 when the cat is in contact with the sensor, 0 when not.
- lick: number of detected licks for that event; a lick is a contact of a few hundred ms (not too short or too long).
- bout: number of licks in a specific time window (bout count).
- water: water level remaining in the device at that time.

System log format

Each line in system.log is a comma-separated record:

- time: timestamp of the log entry.
- mono_ms: monotonic time in milliseconds since boot when the state changes.
- ticks: system tick counter (integer).
- level: log level (for example INFO).
- source: bracketed component label (for example "Main Loop" or "MySystemLog").
- message: free-form message text, including events like cat switches and per-state summaries
  (for example "unknown: state=1 licks=0 bouts=0").
