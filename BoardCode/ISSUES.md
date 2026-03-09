# Outstanding Issues

## HydraPurr.py — BT send blocks main loop
`bluetooth_send_data()` has a `time.sleep(0.002)` per line.
At 2000 lines = ~4s freeze: no lick detection, no RFID, no heartbeat.
A STOP-command check every 100 lines is now active, but the per-line sleep
remains. Needs non-blocking BT send or chunked transmission to fully resolve.

## MyBT.py — EOM delimiter
Default `eom_char='*'` will corrupt messages if data ever contains `*`.
Already configurable via constructor. Consider switching to `\n`.

## MyStore.py / MySystemLog.py — duplicated helpers
`_count_lines`, `_next_rotation_path`, and CSV escape logic exist in both files.
Not bugs, but changes must be made in two places.
