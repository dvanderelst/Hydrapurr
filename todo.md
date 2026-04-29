# TODO

## Reward-delay problem (open — not started)

The feeder fires when `bout_count >= deployment_bout_count`, but `bout_count` only increments when a bout *closes*. Bouts close either via cat-switch `end_bout` (now constrained — see Done below) or via the `max_bout_gap_ms` quiet period (currently 5 min). Result: a cat that stays at the bowl after their 5th bout's last lick can wait up to 5 min for the reward, well outside any operant association window.

**Two options floated:**
- **A1.** Lower `max_bout_gap_ms` to ~15-30 s. One-line change; redefines a "bout" as one visit to the bowl rather than a daily session.
- **A2.** Fire feeder mid-bout based on lick count, decoupled from bout closure. Closer to real-time reinforcement; changes the meaning of `deployment_bout_count`.

---

## Verify the deployment trigger paths still behave sensibly post-attribution-fix

With the attribution fix in (see Done), the cat-switch deployment branch (`MainLoop.py:93-109`) no longer fires on A → unknown — only on A → known-B. The fast-deployment-when-cat-leaves path now relies on the gap-close finalising the bout instead. Worth a sanity check on real data once new logs come in.

---

## Deferred — BT hardware swap planned

The current Bluetooth module is mac-incompatible and will be replaced; not worth cleaning the existing BT code. Revisit after the swap:

- `HydraPurr.py` — `bluetooth_send_data()` has a `time.sleep(0.002)` per line. At 2000 lines = ~4s freeze: no lick detection, no RFID, no heartbeat. Needs non-blocking BT send or chunked transmission.
- `MyBT.py` — default `eom_char='*'` will corrupt messages if data ever contains `*`. Already configurable via constructor. Consider switching to `\n`.

---

## Done

- ~~Cat-attribution: treat RFID dropout to `unknown` as "still the same cat"~~ — fixed: `BoutManager.set_active_cat` now skips `end_bout` when switching to `unknown` (`BoardCode/lib/BoutDetection.py:325-339`), and `cat_timeout_ms` bumped from 1000 ms to 2000 ms (`BoardCode/lib/Settings.py:10`) so the existing RFID stickiness keeps lick routing on the last known cat for ~6 missed-read cycles before falling through to `unknown`.
- ~~Stale doc references (`goals.md` pandas mention, `datadescription.md` `state` column, broken `LICK_SENSOR_DATA_FLOW.md` link in `instructions.md`)~~ — fixed: `goals.md:21` redirects to `BoutAnalyzer.py`; `datadescription.md` rewrites the lick-data fields (drop `state`, add `duration_ms`, clarify lick vs bout-closure markers); `instructions.md:17` now points to `goals.md` and `datadescription.md`.
- ~~Stale `last_bout_summary` reported after deployment~~ — fixed: `BoutTracker.reset_counts` now clears `last_bout_summary` (`BoardCode/lib/BoutDetection.py:235`).
- ~~Suspicious 32-hour bout duration / stuck `current_bout_start_ms`~~ — fixed: `process_sample` gates the gap-close on `current_bout_start_ms is not None` with a fallback reference time (`BoardCode/lib/BoutDetection.py:107-109`), and `end_bout` unconditionally clears bout tracking (`BoardCode/lib/BoutDetection.py:213-217`).
- ~~`state` column in `licks.dat` always 0~~ — removed from `LickSensor.py` logging; `auto_header`, `_log_to_sd_card`, and `clear_log` updated.
- ~~Stale `max_bout_gap_ms=12000` default in `BoutTracker.__init__`~~ — aligned to `300000` (5 min) to match `Settings.py`; module docstring corrected.
- ~~Legacy code paths still reading the removed `state` column~~ — removed: `library/utils.py`, `test_enhanced_lick_counter.py`, `test_lick_counter_integration.py`, and the `process_dataframe` / `_filter_lick_events` / `_process_lick_events` / `_filter_small_groups` / `_add_group_indices` / `_create_bout_summary` block (plus pandas/numpy imports) in `BoutDetection.py`.