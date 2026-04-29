# TODO

## Deferred — BT hardware swap planned

The current Bluetooth module is mac-incompatible and will be replaced; not worth cleaning the existing BT code. Revisit after the swap:

- `HydraPurr.py` — `bluetooth_send_data()` has a `time.sleep(0.002)` per line. At 2000 lines = ~4s freeze: no lick detection, no RFID, no heartbeat. Needs non-blocking BT send or chunked transmission.
- `MyBT.py` — default `eom_char='*'` will corrupt messages if data ever contains `*`. Already configurable via constructor. Consider switching to `\n`.

---

## Done

- ~~Reward-delay problem (A1)~~ — fixed: `max_bout_gap_ms` lowered from 5 min to 10 s in `Settings.py`. Redefines a "bout" as one visit to the bowl. Reward now follows the last lick by at most 10 s (when the cat lingers); cat-leave path still triggers near-instant via `set_active_cat → end_bout`. Settings comment captures both implications (bout semantics + reward latency).
- ~~Inflated bout duration after long absence (B1 side effect)~~ — fixed: new `BoutTracker.close_if_stale(now_ms)` finalises a stale in-progress bout using `last_lick_end_ms` (or `current_bout_start_ms` as fallback) as the end time. Called from `BoutManager.set_active_cat` when switching into a tracker, so a returning cat's pre-absence bout is closed with a duration that reflects actual drinking, not the absence.
- ~~"Deployment ... for unknown" log entries / spurious feeds for the `unknown` bucket~~ — fixed: both deployment branches in `MainLoop.py` now skip `unknown` (`switched_from != 'unknown'` on the cat-switch branch, `current_cat != 'unknown'` on the active-cat branch). The `unknown` tracker still accumulates misattributed counts but is no longer feeder-eligible.
- ~~Cat-attribution: treat RFID dropout to `unknown` as "still the same cat"~~ — fixed: `BoutManager.set_active_cat` now skips `end_bout` when switching to `unknown` (`BoardCode/lib/BoutDetection.py:325-339`), and `cat_timeout_ms` bumped from 1000 ms to 2000 ms (`BoardCode/lib/Settings.py:10`) so the existing RFID stickiness keeps lick routing on the last known cat for ~6 missed-read cycles before falling through to `unknown`.
- ~~Stale doc references (`goals.md` pandas mention, `datadescription.md` `state` column, broken `LICK_SENSOR_DATA_FLOW.md` link in `instructions.md`)~~ — fixed: `goals.md:21` redirects to `BoutAnalyzer.py`; `datadescription.md` rewrites the lick-data fields (drop `state`, add `duration_ms`, clarify lick vs bout-closure markers); `instructions.md:17` now points to `goals.md` and `datadescription.md`.
- ~~Stale `last_bout_summary` reported after deployment~~ — fixed: `BoutTracker.reset_counts` now clears `last_bout_summary` (`BoardCode/lib/BoutDetection.py:235`).
- ~~Suspicious 32-hour bout duration / stuck `current_bout_start_ms`~~ — fixed: `process_sample` gates the gap-close on `current_bout_start_ms is not None` with a fallback reference time (`BoardCode/lib/BoutDetection.py:107-109`), and `end_bout` unconditionally clears bout tracking (`BoardCode/lib/BoutDetection.py:213-217`).
- ~~`state` column in `licks.dat` always 0~~ — removed from `LickSensor.py` logging; `auto_header`, `_log_to_sd_card`, and `clear_log` updated.
- ~~Stale `max_bout_gap_ms=12000` default in `BoutTracker.__init__`~~ — aligned to `300000` (5 min) to match `Settings.py`; module docstring corrected.
- ~~Legacy code paths still reading the removed `state` column~~ — removed: `library/utils.py`, `test_enhanced_lick_counter.py`, `test_lick_counter_integration.py`, and the `process_dataframe` / `_filter_lick_events` / `_process_lick_events` / `_filter_small_groups` / `_add_group_indices` / `_create_bout_summary` block (plus pandas/numpy imports) in `BoutDetection.py`.