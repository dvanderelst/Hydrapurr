# Outstanding Issues

## HydraPurr.py — BT send blocks main loop
`bluetooth_send_data()` has a `time.sleep(0.002)` per line.
At 2000 lines = ~4s freeze: no lick detection, no RFID, no heartbeat.
Needs non-blocking BT send or chunked transmission.

## MyBT.py — EOM delimiter
Default `eom_char='*'` will corrupt messages if data ever contains `*`.
Already configurable via constructor. Consider switching to `\n`.

## ~~MyStore.py / MySystemLog.py — duplicated helpers~~ RESOLVED
Extracted `count_lines`, `next_rotation_path`, `escape_csv`, and `parse_csv_line`
into `lib/components/FileUtil.py`. Both files now import from there.

## MyADC.py / LickSensor.py — water sensor read blocks ~10ms every loop iteration
`LickSensor.update()` calls `self.water_sensor.mean(10)` unconditionally on every
loop iteration. With the default `sample_delay=0.001`, that is 10 × 1ms = ~10ms of
blocking before any lick or RFID processing. Combined with the 1ms sleep at the end
of the main loop, the effective sample rate is ~90 Hz instead of ~1000 Hz.
Side-effects:
- The 5ms debounce window (`BoutTracker.debounce_ms`) cannot function at finer
  than ~11ms resolution, so debounce is effectively ~11ms.
- Lick duration estimates are limited to ~11ms granularity.
- Water level is read even during long idle periods with no lick activity.
Consider reading the water level only on lick events, or using a single `read()`
instead of `mean(10)` and averaging over the bout in software.

## MainLoop.py — `previous_bout_count` not reset after feeder fires
After `counter.reset_counts()` in the feeder-trigger branch, `previous_bout_count`
still holds the old deployment threshold value. On the very next loop iteration the
state string changes (counts reset to 0), `bout_count` is now 0, and
`previous_bout_count != bout_count` triggers `bout_changed = True`. This causes the
last bout summary to be logged a second time and triggers an extra screen update.
Fix: add `previous_bout_count = 0` immediately after `counter.reset_counts()`.

## MainLoop.py / BoutManager.py — final bout at cat-switch is not checked for feeder threshold
`set_active_cat(new_cat)` calls `end_bout()` on the previous cat, which can
increment that cat's `bout_count`. But the feeder threshold check that follows reads
`counter.get_bout_count()` for the *new* active cat, not the previous one. If cat A
reaches `deployment_bout_count` exactly when a cat-switch occurs (RFID timeout or
new tag read), the feeder never fires until cat A is active again.

## BoutDetection.py — `_finalize_bout` bypasses water filter when lick list is empty
`_finalize_bout()` returns `True` early (counting the bout) when
`current_bout_licks` is empty, without evaluating `min_water_delta`. Lick water
readings are only appended when `water_level is not None`; `end_bout()` called from
`BoutManager.set_active_cat()` passes no water level, so any lick in progress at
switch time is not appended. In the extreme case where a whole bout is finalized
this way, it is counted even if water filtering is enabled.

## BoutDetection.py — offline inter-bout gap measured offset-to-offset instead of offset-to-onset
In `_process_lick_events()`, `gap_ms = offset_time - last_offset_time` measures the
time between the end of the last lick of one group and the end of the first lick of
the next group. This includes the duration of the opening lick of the new bout,
systematically underestimating the quiet gap by ~50–150ms. With
`max_bout_gap_ms=1000` this is unlikely to cause incorrect grouping in practice, but
the semantics are slightly wrong. Should use onset-to-onset or offset-to-onset.
