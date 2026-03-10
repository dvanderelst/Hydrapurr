# Outstanding Issues

## ~~MainLoop.py — spurious "Cat switched None → unknown" log entry on startup~~ RESOLVED
`previous_active_cat` initialises to `None` but `BoutManager.active_cat` starts as
`'unknown'`. On the first iteration with no RFID tag, `current_cat = 'unknown'` and
`'unknown' != None` triggers a cat-switch log entry. No functional effect (feeder
check is skipped since `switched_from = None`), but the log is misleading.
Fix: initialise `previous_active_cat = 'unknown'`.

## ~~LickSensor.py / BoutDetection.py — bout-close SD log entry records lick_count = 0~~ RESOLVED
When a bout closes, `BoutTracker.process_sample` resets `lick_count = 0` before
returning. `BoutManager` then returns `'lick_count': tracker.lick_count` = 0, and
`LickSensor` logs that to the SD card. The "bout closed" row in `licks.dat` always
shows lick=0 instead of the count of licks in the bout. The actual count is in
`last_bout_summary['lick_count']` but is not written to the log at that moment.
For offline analysis this means the bout lick count must be reconstructed from
preceding rows rather than read directly from the bout-close entry.

## HydraPurr.py — BT send blocks main loop
`bluetooth_send_data()` has a `time.sleep(0.002)` per line.
At 2000 lines = ~4s freeze: no lick detection, no RFID, no heartbeat.
Needs non-blocking BT send or chunked transmission.

## ~~MainLoop.py — `update_screen` shows wrong bout count in `switched_from` feeder path~~ RESOLVED
## ~~LickSensor.py — water level is `None` on every falling edge, breaking water tracking~~ RESOLVED

## ~~LickSensor.py — `_last_water` stale after cat switch~~ RESOLVED
`set_active_cat` reads the water sensor and passes the value to `end_bout`, but does
not update `self._last_water`. The new active cat's first bout inherits the previous
cat's last contact reading as `current_bout_start_water`.
Fix: add `self._last_water = water_level` in `set_active_cat` after the sensor read.

## ~~MainLoop.py — `water_extent` / `water_delta` can be `None`, crashing f-string format~~ RESOLVED
`bout_summary.get('water_extent', 0)` returns `0` only when the key is absent.
`_finalize_bout` always stores the key but sometimes with value `None`; calling
`f'{None:.3f}'` raises `TypeError`. Affects both the `bout_changed` log block and the
`switched_from` log block. Fix: use `or 0` when reading these values from the summary.

## MyBT.py — EOM delimiter
Default `eom_char='*'` will corrupt messages if data ever contains `*`.
Already configurable via constructor. Consider switching to `\n`.

## ~~MainLoop.py — `switched_from` feeder path missing screen feedback and bout summary log~~ RESOLVED
When the departing cat's bout triggers the feeder at a cat-switch, the code fires
the relay and resets the count but does not: (a) update the screen before/after to
show the threshold was reached, or (b) log the bout summary. The normal feeder path
does both. Inconsistent user-visible behaviour.

## ~~BoutDetection.py — `_finalize_bout` early return still bypasses water filter~~ RESOLVED
`_finalize_bout` returns `True` early when `current_bout_licks` is empty, without
evaluating `min_water_delta`. `_track_lick` only appends to `current_bout_licks`
when `water_level is not None`, so a water sensor failure during a bout would leave
the list empty and allow the bout to count unfiltered. The root cause (missing
water_level at cat-switch) was fixed, but the bypass path remains for the sensor
failure scenario.
