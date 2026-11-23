# HydraPurr — handoff

Running notes for the whole project (firmware, analysis, PCB; the device was
first called the "Simplified" build). Update this file at the end of every
working session: what changed, what was learned, what is next.

**Repo layout since 2026-11-23:** the device's code (was `Simplified/`) is
`firmware/`; this file moved from there to the repo root; the v2 data processing is `analysis/` (reader, fetcher, plot;
data in `analysis/data/v2_esp32s3_touch/`); the carrier PCB is `pcb/` (was
`FeederController/`); everything of the first prototype is under `legacy/`
(`legacy/v1_firmware/` = the former `BoardCode/`, `legacy/ProcessLickData/`,
`legacy/CircuitSimulation/`, `legacy/HardwareDocs/`, `legacy/todo.md`). Log
entries below may still use the old names; paths have been updated.

## Goal

A simpler HydraPurr built on the **Adafruit Feather ESP32-S3 Reverse TFT**.
The 2-transistor (Darlington + optocoupler) lick detector on the custom PCB is
dropped. Instead, **one wire runs from a capacitive-touch pin straight into the
water**, read with CircuitPython's `touchio`. A lick shows up as a jump in the
pin's raw touch value.

## Why we dropped the transistor circuit

Background is in `legacy/CircuitSimulation/Notes.md` and the Notion page "HydraPurr
prototype". In short:

- The detector was far too sensitive: it tripped at ~20 MΩ of leakage, so damp
  paws and moisture films looked like licks. Plate-only touches caused false
  licks.
- Picking the filter capacitor was a trade-off with no good answer. Without it,
  mains hum caused false licks. With 0.1 µF, the output stayed latched for about
  2 s, so the 50–250 ms lick window rejected every lick.
- The isolated battery "island" still picked up the noisy supply through a few
  pF of stray coupling.
- The PCB needed three hand-wired fixes on every board: lick pin moved D5 → A1
  for an ADC read, the transistor emitter tied to GND, and I²C rerouted.
- On the ESP32-S3, the old analog pins (A0/A1) sit on ADC2, which is
  unreliable once WiFi is on. The touch peripheral doesn't have that problem.

## Current state (2026-11-17)

The paragraph below is from 2026-10-28; since then: WiFi (heartbeat, NTP
clock in UTC, file server with a start page), watchdog, 15-min status rows.
See the file table and the Log.

**Status:** the firmware is now a **recorder**: it samples the touch wire and
the float sensor 100×/s and writes everything to the SD card; licks and
water-level changes are found offline. Bout detection and feeding are out of
the main loop for now (code kept in `lib/`). Runs on the board (CircuitPython
**10.3.1**); touch on D12 and the Sharp on A5 read real values. **Recording to the
SD card is verified** (2026-10-20, re-checked 2026-10-28): ~83-85 rows/s,
longest gap ~160 ms (both from the once-a-second screen redraw, which is
skipped during contact), slowest single write ~15 ms. Both sensors respond (after a wiring fix, see log); not yet seen with a cat
lick.

Firmware (runs at boot via `code.py`):

| File | What it does |
| --- | --- |
| `code.py` | Mounts SD, runs `MainLoop.main_loop()`; **holding D2 at boot** runs `TestHeartbeat.run()` instead. Other test scripts are run by hand from Thonny. |
| `MainLoop.py` | Recording version. The loop sits in `try/finally`; `shutdown()` closes the data file and `system.log`, unmounts SD and releases the display however the loop ends (exception, Ctrl-C, auto-reload on file save). Every 10 ms (fixed grid): read touch (→ live contact 0/1 against the tracking baseline) and one Sharp reading, hand both to `RawRecorder`. Full-screen TFT redraw once a second, but only after 3 s without touch contact (a redraw pauses sampling ~150 ms, so the screen freezes while the cat drinks). Contact LED on D9. Settings snapshot in `system.log` at startup (`wifi_password` shown as `<set>`). Status line in `system.log` every minute: rows, errors, `rate` (samples/s), `max_gap` (longest time between samples), `slowest_write`, file, touch, contacts, water. (2026-11-17) Also: WiFi join + NTP clock (UTC) at boot and daily, heartbeat every 15 min when quiet, file server polled between samples (fast-download pause), 15-min `status` event row, watchdog (60 s, fed before every blocking step), WiFi icon. Any end of the loop after WiFi use, and any unexpected error (WiFi or not; also a failed start-up), ends in `microcontroller.reset()` after 10 s, so the board records again instead of sitting at the REPL; Ctrl-C without WiFi still stops at the REPL. Split: `start_up()` returns the parts; rarely run code (`heartbeat_body`, `draw_screen`, `server_status`) in functions; the per-sample work stays inline (locals). system.log: no sync per line (warnings/errors still synced at once), no RAM copy. |
| `Settings.py` | In the root (moved from `lib/` 2026-10-28), the one file to edit. All parameters, BoardCode names where the meaning is the same. Recording: `raw_log_interval_ms = 10`, `raw_log_sync_ms = 5000` (flush interval = max data lost on power cut). Touch thresholds are placeholders (+10 % on, +5 % off); they only affect the live `contact` column and the display. Bout/deployment settings are kept in a marked "not used" block. Home WiFi credentials are the exception: `Settings.py` reads them with `os.getenv` from `settings.toml` (see below). |
| `settings.toml` | On the board only (CIRCUITPY root), edited there: WiFi credentials (`WIFI_SSID`, `WIFI_PASSWORD`, more networks as `WIFI_SSID_2` ... `_5`, 2026-11-23) and `HEALTHCHECK_URL`. No copy on the computer or in git (repo is public); never print it. `sync2board` has `--filter='P settings.toml'`, so it never deletes it. Not CircuitPython's `CIRCUITPY_WIFI_*` names (the board would join by itself). |
| `lib/Network.py` | (2026-11-16) Lab WiFi (station) + healthchecks.io heartbeat. `join()` at boot (blocks up to `wifi_connect_timeout_s`), re-join at most every `wifi_retry_ms`; `heartbeat(body, fail)` = one HTTPS POST to `HEALTHCHECK_URL` (or `/fail`), ~3.5-4 s. `used` = radio touched. No-op without `WIFI_SSID` or with `wifi_enabled = False`. Also `ntp_time()` (UDP, ints only; rejects replies that are not mode 4, unsynchronised or outside stratum 1-15) and the mDNS name `hydrapurr.local`. `join()` sets up the socket pool and mDNS also when the radio is already connected. |
| `lib/TouchSensor.py` | `touchio` on D12 → 0/1. Baseline averaged at boot, then tracked (EMA, τ 30 s) only while untouched; hysteresis; contact > 5 s re-takes the baseline; big drops are followed at once. |
| `lib/WaterSensor.py` | Sharp on A5 in volts (higher = more water). The recorder uses single reads (`read_volts`); the smoothed `update()` is for the bout version. |
| `lib/FileServer.py` | (2026-11-16, replaces `DownloadMode.py`) Serves the SD card on the lab WiFi at `http://hydrapurr.local/` (mDNS, set in `Network.py`) while recording goes on. `/` = start page for testers (status, per-day `events` and joined `raw` downloads, optional fast download that pauses recording, 2026-11-17). Folder pages under `/files/` (`/raw/`, `/raw/<date>/`, `/events/`), files as downloads with `Content-Length`. Never blocks: `MainLoop` calls `poll(t, deadline)` every pass with deadline = next sample − `fileserver_margin_ms`; it accepts, reads the request, reads a `fileserver_chunk` (2 KB) piece and sends it, only until the deadline; EAGAIN = next pass. One client at a time, 10 s idle timeout, `..` refused. A file still being written is served up to its size at request time. |
| `lib/Button.py` | Edge-detecting button (was in `DownloadMode.py`); used by the test scripts. |
| `lib/RawRecorder.py` | Writes `/sd/raw/<YYYY-MM-DD>/<HH>.csv` (new file each wall-clock hour), columns `epoch_ms, mono_ms, touch_raw, touch_baseline, contact, water_v`. `epoch_ms` = wall-clock ms (RTC at boot + time since boot), so rows stay correctly timed when a restart appends to the same file and `mono_ms` restarts near 0. Each file (and each re-open) also gets a line `# start <wall time> mono_ms <n>` as a human-readable anchor. File stays open; each row is written as it is taken, `flush()` every 5 s. ~44 B/row → ~16 MB/hour, ~380 MB/day. Hourly files avoid FAT32's 4 GB limit and the slowdown of re-opening big files to append. (2026-11-17) New file exactly at the hour boundary (computed in ms, not checked once a second). After a write error: one warning, re-open at most once a second, lost rows counted (`dropped`, in the heartbeat and status line). |
| `lib/EventLog.py` | (2026-10-30) One row per event to `/sd/events/<YYYY-MM-DD>.csv`, columns `epoch_ms, mono_ms, event, f1..f4`. Events: `boot` (reset reason, safe-mode reason, rtc_ok, touch baseline), `settings` (one row per setting), `contact` (written when a contact ends: duration_ms, peak raw, baseline and water V from before it started; every contact, lick filtering is offline), `rebaseline` (`stuck`/`drop`, raw, old, new), `status` (every `status_event_interval_ms` = 15 min, first one 60 s after the loop starts: water V as the mean of the last 10 s, touch baseline, touch raw, contacts since the previous one; until 2026-11-17 a `water` row every 10 s instead), `shutdown` (reason, e.g. `KeyboardInterrupt()`), plus `wifi`, `clock`, `heartbeat_failed`, `paused`/`resumed`. Field table in the module docstring. Rows written at once, flushed every `events_sync_ms` (5 s; a flush is ~10 ms, too long after every lick). Decided with the user: only log when something happens; the one periodic row is `status` every 15 min (2026-11-17: shows the water level between drinks and that the board ran). |
| `lib/StatusDisplay.py` | 5 text lines on the TFT: `REC <rows>` (or NOT RECORDING in red), contact count, water V, touch raw (green on contact), baseline. Manual refresh; `refresh_all()` redraws the **whole screen** (root-group swap) when something changed. Lines padded to 19 characters. Status bar off; `release()` restores the console on shutdown. Uses `adafruit_display_text.label`. WiFi icon top right (`set_wifi`: green arcs / grey with red slash / hidden), 2026-11-17. |
| `lib/LickSensor.py`, `lib/BoutDetection.py` | Not used by the recorder; kept for the bout-detection version. `BoutDetection.py` is BoardCode's, unchanged; `LickSensor.py` is BoardCode's glue minus the ADC. |
| `lib/components/` | Copied from BoardCode: `MyStore`, `MySystemLog`, `TimeUtil`, `FileUtil`, `MySD`, `MyRTC`, `MyI2C`. Changes vs BoardCode: `TimeUtil` falls back to 2000-01-01 instead of epoch 0 (ESP32 can't format pre-2000 dates); `MySD` releases the card on a failed mount; `MyRTC` imports `adafruit_pcf8523.pcf8523`. `__init__.py` is a minimal new one. Simplified-build additions: `TimeUtil.set_clock()` (NTP; timebase first, then the RTC chip); `MySystemLog` syncs only warnings/errors when `autosync=False` and re-opens system.log after a failed write. |
| `lib/adafruit_pcf8523/`, `lib/adafruit_register/`, `lib/adafruit_display_text/` | 10.x `.mpy` builds from the library releases (pcf8523 2.0.9, register 1.13.0, display_text 5.0.6, only `label` kept). |

Tools and tests (run by hand):

| File | What it does |
| --- | --- |
| `TestDatalogger.py` | Adalogger test: I²C scan, RTC time / lost-power / switchover / battery / ticking, SD mount + write/read-back + free space + append timing. |
| `TestHeartbeat.py` | (2026-11-16) Times one HTTPS heartbeat to healthchecks.io (DNS, TLS, send, reply, memory), one per minute; D1 sends a `/fail` ping. **Hold D2 while the board starts.** Needs `WIFI_*` and `HEALTHCHECK_URL` in `settings.toml`. End with Reset, not Ctrl-C. |
| `SetTime.py` | Set the RTC (None = keep a field, Enter to set, printed directions). Also clears `lost_power` and turns on battery switchover. |
| `TestTouch.py` | Multi-pin touch tester (A5, D5, D6, D9). Note: A5 is now the Sharp input. |
| `sd/placeholder.txt` | Keeps the `/sd` mount point on CIRCUITPY. |

`./sync2board firmware` pushes `firmware/` (mirrors with `--delete`). It
never touches the board's `settings.toml`, but it does overwrite the board's
`SetTime.py` (which usually holds edited date/time values).
To see output: Thonny, or `python3 -m serial.tools.miniterm /dev/ttyACM0
115200` (Ctrl-D reruns `code.py`, Ctrl-] quits). The TFT shows the status
screen once the firmware runs.

Measured on the board (2026-10-20): touch baseline on D12 with the wire in
water ≈ 19 500; one `raw_value` read ≈ 0.5 ms. Sharp ≈ 0.93 V at rest, noise
about ±20 mV; one ADC read ≈ 1.3 ms.

**Open issues:** check whether the RTC still reports `lost_power` (startup
screen shows red `RTC: set time!`); if so, run `SetTime.py`. `settings.toml`
on the board still holds placeholder WiFi values until the user fills them in.

### Recording timing (measured 2026-10-20, this board + card)

| Setup | Rate | Longest gap |
| --- | --- | --- |
| 100-row batch + flush every 1 s, all 5 TFT lines redrawn 4×/s | 88/s | 128 ms |
| same, TFT updates off | 99/s | 79 ms (the batch write) |
| row-by-row writes, flush every 5 s, one TFT line per 200 ms | 96/s | 31 ms |
| **same, full-screen redraw once a second, skipped during contact (current, 2026-10-28)** | **83-85/s** | **~160 ms** |

Measured in isolation: one row `write()` median 0.9 ms, p99 6.7 ms, max
10 ms; 100-row write 9–23 ms; `flush()` 8–14 ms. The card can still add an
occasional slow write (internal housekeeping); `max_gap` in the status line
shows it. Every row carries its own `mono_ms` and `epoch_ms`, so gaps are
visible offline. Per sample: touch ~0.5 ms + Sharp + row write ~0.9 ms, so
the loop is idle ~8 of every 10 ms; 10 ms is a chosen setting
(`raw_log_interval_ms`), not a hardware limit.

Offline: the first row(s) after each `# start` line can be off (water read
0.49 V instead of ~0.9 V right after boot); skip them.

### WiFi / download mode: lessons (2026-10-20)

- **Never sync or use the serial port while download mode is on.** With the
  access point active and a client connected, the board's USB drops out.
  A sync cut off this way corrupted CIRCUITPY (fixed with
  `storage.erase_filesystem()` + full re-sync; the SD card was unaffected).
  Use download mode on a charger, not on the computer.
- **Don't toggle `wifi.radio.enabled`.** Switching it off at startup made the
  next soft reboot hang USB. The code now only starts/stops the AP.
- **No `settings.toml` with `CIRCUITPY_WIFI_*`** on this board: CircuitPython
  then tries to join that network at boot (the first attempt used a
  non-existent network and led to resets). Our own keys are named
  `WIFI_*`, which CircuitPython ignores at boot. `.gitignore`
  covers `firmware/settings.toml*`. (The old `settings.toml.off` with the
  web-workflow keys was removed 2026-10-28.)
- A large download through the library's static file serving at full radio
  power hard-faulted the board (safe mode, `HARD_FAULT`). With 8.5 dBm both
  that path and our own chunked route worked; we keep our own route.
- CircuitPython quirk: a plain string literal next to an f-string is treated
  as part of the f-string, so `{...}` in it (CSS) became a placeholder →
  `KeyError('font-family')`. Keep such literals separate.
- Boot now logs `reset reason` and `safe mode reason` in `system.log`.
- On the PC, ModemManager probes new serial ports and can push an ESP32 into
  ROM download mode (USB `303a:1001`) during a reset; an udev rule with
  `ID_MM_DEVICE_IGNORE` for vendors 239a/303a prevents that (not installed).

## Board facts: Feather ESP32-S3 Reverse TFT

- Only **GPIO1–14** have the touch peripheral. Usable touch pins: SDA(3),
  SCL(4), D5, D6, A5(8), D9, D10, D11, D12, D13(LED), A4(14).
- Not touch-capable: A0–A3 (GPIO18/17/16/15) and TX/RX (GPIO39/38 on the
  Reverse).
- GPIO1/GPIO2 are the D1/D2 front buttons, D0 is BOOT. D13 drives the red LED.
- It has a built-in 240×135 TFT (replaces the SSD1306 OLED) and a NeoPixel.
- It has no RTC or SD card of its own, so the build **keeps the Adafruit
  Adalogger FeatherWing** (PCF8523 RTC on I²C + SD card on SPI, CS = D10), the
  same as BoardCode.
- **The Adalogger uses SDA, SCL and D10**, which removes three touch pins.
  Touch pins left for the water wire: D5, D6, A5, D9, D11, D12, A4, plus D13 if
  the red LED is not needed.
- **The water-level sensor needs an ADC1 pin.** ADC2 is unreliable while
  WiFi is on. ADC1 covers GPIO1–10, which are also touch pins, so the Sharp
  sensor and the water wire compete for the same few pins. A5 is a likely ADC1
  pin, but check the actual GPIO numbers on the board
  (`dir(board)` / `microcontroller.pin`) before choosing.
- The TFT on the Reverse board also uses the main SPI bus (`board.SPI()`), so
  the SD card shares it with the display. **Tested: works.**
- I²C devices seen: 0x68 (PCF8523 RTC on the Adalogger) and 0x36 (the board's
  own battery fuel gauge).
- `touchio.TouchIn(pin).raw_value` goes **up** when touched;
  `.threshold` sets the cut-off that `.value` uses.
- `time.monotonic()` is a float and loses precision with uptime (coarser
  than 1 ms after ~1 h, tens of ms after a day). All `now_ms()` helpers use
  `time.monotonic_ns() // 1_000_000` instead.

## Proposed pin map (2026-10-20, not yet confirmed on the board)

ESP32-S3: ADC1 = GPIO1–10 (WiFi-safe), ADC2 = GPIO11–20, touch = GPIO1–14.
On the Reverse TFT, A0–A4 are GPIO18/17/16/15/14, so they are all ADC2.
A5 = GPIO8 is the only A-pin on ADC1.

| Function | Pin | Why |
| --- | --- | --- |
| Sharp IR output | **A5** (GPIO8) | Only labelled analog pin on ADC1. |
| Water wire (touch) | **D12** (GPIO12) | Touch-capable, and uses no ADC1 pin. Leaves D9/D11 free for RFID. Already used by `test.py`. Opposite header from A5. |
| Feeder relay (later) | D6 | Same as BoardCode; plain digital output. |
| Contact LED | **D9** | LED + side on D9, resistor to GND; lit while `contact` = 1 (`contact_led_pin`). Fitted 2026-10-21. Takes RFID's old rx pin: RFID would need another UART pin. |
| RFID (if kept) | D11 reset; rx no longer D9 (LED) | BoardCode used D9 rx. |
| Adalogger | SDA, SCL, SPI, D10 | Fixed by the wing. |
| Spare | D5, D13 (red LED), A0–A4 | D5 is ADC1 + touch: backup for either sensor. |

Sharp power: 5 V from the USB pin (only when USB-powered) + GND, with a
~10 µF capacitor across its supply at the sensor.

## What carries over from BoardCode

The lick → bout → deploy logic in `legacy/v1_firmware/` has nothing to do with the
sensor hardware. It only needs a binary contact state (0/1) per sample.

| Piece | File | Carry over? |
| --- | --- | --- |
| Lick/bout state machine (debounce, 50–250 ms lick window, bout gap, eligibility gates, `try_finalize_in_progress`) | `legacy/v1_firmware/lib/BoutDetection.py` | **Yes, unchanged.** Pure logic with timestamp inputs; only depends on `MySystemLog.info`. |
| Glue: sensor → binary state → BoutManager → `licks.dat` | `legacy/v1_firmware/lib/LickSensor.py` | **Yes, adapted.** Replace `lick_voltage < lick_threshold` with a touch-based contact state. The water-level reading stays (float sensor, see below). |
| Deployment logic (cat-switch trigger, active-cat trigger, no-wait mode, `unknown` never fed) | `legacy/v1_firmware/MainLoop.py` | **Yes, slimmed.** Single-cat mode likely enough at first. |
| Parameters | `legacy/v1_firmware/lib/Settings.py` | **Yes.** `lick_threshold` (volts) needs replacing with touch parameters. |
| Cat registry / RFID | `Cats.py`, `TagReader.py` (UART rx D9, RST D11) | Only if the simplified build keeps RFID. |
| Water level | `MyADC(0)` read in `LickSensor.update` during contact; `water_extent` gate in `BoutDetection.py` | **Yes.** New hardware (see below), same role. Remap `MyADC` to the chosen ADC1 pin. `min_water_extent_per_bout` (0.013 V) must be re-tuned for the float. |
| Feeder relay | `HydraPurr.feeder_on/off`, D6 via NPN | **Later.** Probably a smaller relay than before (the old one was overkill). `feeder_on/off` stays as the interface; the pin must not clash with the touch pin. |
| Logging + time | `MyStore`, `MySystemLog`, `TimeUtil`, `FileUtil`, `MySD`, `MyRTC`, `MyI2C`, `adafruit_pcf8523`, `adafruit_register` | **Yes, close to unchanged** (same Adalogger wing, verified on this board). Add a boot check of `rtc.lost_power` and flag timestamps as invalid when it is set. `SetTime.py` already ported. |
| Display | `MyOLED` (SSD1306 over I²C) | Replace with the built-in TFT (`board.DISPLAY` + `displayio`). |
| BT | `MyBT` (HC-05 UART) | No. ESP32-S3 has BLE only; the BT swap is planned separately. |
| Offline analysis | `legacy/ProcessLickData/` (v1 `licks.dat`) | Works if `licks.dat` keeps the same columns. |

## Water-level sensor: float in a chimney

- A dedicated 3D-printed float (rounded underside, flat top) sits in a
  "chimney" connected to the main bowl. A Sharp IR distance sensor above it
  reads the height of the flat top. The water level in the chimney follows the
  bowl, while the narrow chimney damps ripples from licking.
- Same role as before: confirm real drinking through the water swing during a
  bout (`water_extent`), and track how much is consumed (`water_delta`).
- **Sensor chosen: Sharp GP2Y0A51SK0F** (Pololu #2450), range 2–15 cm.
  4.5–5.5 V supply (from the Feather's USB pin), ~12 mA average in short
  bursts, new reading every ~16.5 ms. Output is roughly linear in 1/distance,
  about 1.65 V swing over the range; maximum is about 2.5 V near 2 cm (from
  the datasheet curve, to be measured), so it can go straight to A5 without a
  divider. JST ZH 1.5 mm connector: red = Vcc, black = GND, white = Vo.
  Wiring: red → USB, black → GND, white → A5, ≥10 µF across Vcc/GND at the
  sensor.
- Mounting: keep the float **at least 2 cm (better 3 cm) below the sensor**
  at the highest water level, since the output drops again below 2 cm.
  Resolution is best close to the sensor (1/d response), so mount it so the
  float moves within roughly 3–8 cm.
- Sampling faster than every ~17 ms just repeats the same reading; averaging
  should span several sensor updates.
- **Sharp sensor details (general):**
  - Most Sharp analog sensors need a 5 V supply (USB/BAT pin, not 3V). Their
    output stays below ~3.1 V, so the ESP32-S3 ADC can read it directly, but
    check this for the specific model.
  - The output is **not monotonic below the sensor's minimum range** (e.g.
    10 cm for GP2Y0A21, 4 cm for GP2Y0A41). Mount it so that the float never
    gets closer than that minimum, even with a full bowl.
  - Readings are non-linear in distance, and the sensor draws current spikes.
    A ~10 µF capacitor across its supply pins is the usual fix for the noise
    this causes; averaging a few samples (`water_samples`) helps too.
- The old code only reads water while the tongue is in contact. With a damped
  float, it may be better to sample on a slow timer and smooth the readings.
  To decide once real data is available.

## Things specific to touch sensing

- **The baseline will drift.** Wire + water + bowl form one large electrode.
  The untouched reading depends on water level, bowl position, humidity and
  what's nearby. A fixed baseline taken at boot (what both test scripts do)
  probably won't hold for days. Likely needs a slowly tracking baseline,
  updated only while not in contact, or detection based on the fast step a lick
  causes.
- **A paw in the water reads the same as a tongue.** The water-swing check
  (`min_water_extent_per_bout`) together with the 50–250 ms lick window and
  `min_licks_per_bout` is what separates real drinking from that. This makes the
  float sensor important for the touch approach, not just optional.
- **Mains hum through the cat's body** could still couple in. Watch the raw
  values for 50/60 Hz-like jitter while a cat stands near the bowl.
- **Sample rate.** Licks are ~50–250 ms, so the loop has to sample the touch pin
  every few ms. Check how long one `raw_value` read takes on the S3.
- **Logging blocks the loop.** One SD append (open, write, close) takes ~8 ms,
  worst ~12 ms. One row per lick is fine, but logging every raw sample is not;
  a raw-data recorder would need to buffer rows and write them in batches.

## Open questions (for the user)

1. Does RFID stay? (Decided: Adalogger, float water sensor, a smaller relay
   later.)
2. Is this meant to become the main firmware eventually, or stay a separate
   lightweight variant next to `legacy/v1_firmware/`?
3. Which relay? (Touch pin = D12 and Sharp = GP2Y0A51SK0F are decided.)
4. Upload destination for the automatic upload (Next steps 5): own HTTP
   endpoint, MQTT broker, or a hosted service?

## Next steps (proposed)

1. Run `SetTime.py` to clear the RTC's `lost_power` flag (time itself is
   right). Check the Sharp: it reads ~2.53 V since the rewiring, which means
   something ~2 cm away or the wrong pin.
2. Record with the wire in the water: idle, a finger touching the water, a
   cat drinking. Write an offline reader (ProcessLickData) for the hourly
   files; use it to find licks and set the touch thresholds, and check that
   baseline tracking holds over hours.
3. Characterise the float: Sharp voltage over the full water range and while
   a cat drinks; set `min_water_extent_per_bout`. (2026-11-23: range done,
   0.62 V empty to 1.16 V full, see Log; with a cat still to do.)
4. **Done 2026-10-30 (`lib/EventLog.py`), not yet run on the board.**
   Check on the board: rows appear, `contact` durations match the raw
   stream, no extra sampling gaps. Original plan: events file next to the
   raw stream (user's idea, 2026-10-28): one row
   per significant event only — lick, water-level change, feeder deployment,
   settings snapshot at boot / settings change, download mode on/off, boot /
   shutdown. Written far less often than the raw file; it is the file we
   actually analyse. Then raw recording becomes a debug/calibration option
   (`raw_log_enabled` already exists and works). Costs measured so far: a raw
   row write takes ~1 ms of each 10 ms period (~10 %), the 5-s flush ~0.2 %;
   the once-a-second screen redraw costs more (~150 ms/s, ~15 %). So turning
   raw off mainly saves card space (~380 MB/day) and SD writes, not much loop
   time. Keep raw on until step 2 has validated the lick thresholds: the
   events file is only as good as the live lick detection. Reuse BoardCode's
   `licks.dat` / `MyStore` style (`epoch_ms`, `mono_ms`, event, fields).
5. Automatic upload instead of the D1 download (user's idea, 2026-10-28):
   the board joins the home WiFi (station mode) and uploads to a destination
   still to be decided (small HTTP endpoint or MQTT), so data reaches the
   cloud for monitoring without anyone pressing D1.
   - Upload the **events file** only: maybe a few hundred KB/day, so well
     under a second per upload. Raw is ~380 MB/day: at a guessed ~200 KB/s
     that is ~80 s per hourly file, ~30 min/day. Raw stays on the card,
     fetched with D1 download mode when needed for calibration/debugging.
   - No recording gap needed: send 1-4 KB per loop pass in the ~8 ms idle
     time of each 10 ms period (as `DownloadMode` already sends 4 KB pieces).
     Only joining the network blocks (a few seconds), once per connection.
   - While connected, sync the clock from NTP: fixes the frozen-at-boot wall
     time / drift item in `todo.md` and the RTC `lost_power` problem.
   - Could then drop the RTC entirely (SD-only logger board instead of the
     Adalogger). Catch: after a power cut without WiFi the time is unknown
     until the first sync. Log `mono_ms` plus a boot id on every row and
     write a time anchor once synced, so `epoch_ms` can be filled in
     afterwards. Decide after the upload has run reliably for a while.
   - Web search (2026-10-28) found no CircuitPython ESP32-S3 benchmark.
     Nearest figures: MicroPython on an S3 ~8.7 Mbit/s (~1 MB/s) TCP upload;
     ESP-IDF forum reports ~800 kB/s; CircuitPython 8 on a plain ESP32
     Feather ~7 kB/s. Note raw data averages only ~4.4 kB/s (380 MB/day), so
     uploading raw in the background is possible if the sustained chunked
     rate stays clearly above that.
   - To measure first: real upload speed (TX power is lowered to 8.5 dBm);
     the longest single socket send (must stay well under 10 ms or sampling
     gaps appear); whether `touch_raw`/baseline shift while the radio
     transmits; whether USB drops out in station mode as it does with the
     access point. The Sharp on A5 (GPIO8, ADC1) is WiFi-safe.
6. Fit the relay (`feeder_pin`), then RFID if wanted.

## Carrier PCB (planned, started 2026-11-13)

A through-hole PCB that carries the Adalogger (on stacking headers) with the
Reverse TFT on top, adds the feeder driver, and gives every peripheral a
connector. KiCad project: `pcb/` (empty so far). Draft
schematics, pin map and parts lists (sheet 1 feeder driver, sheet 2
sensors/connectors): claude.ai artifact "HydraPurr Carrier PCB"
(https://claude.ai/artifact/9ND6r2CwRtsV6qfNW5XWaY).

Decided with the user:
- Power stays USB 5 V only (Feather USB pin). A boost module makes 12 V for
  the feeder.
- Feeder = SuperFeeder ASF-1: runs while it gets 12 V (its own controllers
  are timers that switch its adapter); up to 0.15 A measured.
- **High-side MOSFET switch, no relay:** boost (always on) → PTC fuse 0.5 A
  → P-MOSFET IRF9540N (source on 12 V, drain = FEEDER+) → feeder; FEEDER− =
  GND. Gate pulled up to 12 V by 10 kΩ; PN2222A NPN pulls it low, driven from
  **A0** via 4.7 kΩ with **4.7 kΩ** base pulldown (was 47 kΩ: too weak
  against the ESP32's ~45 kΩ internal pull-up, which ESP-IDF's pin reset
  enables and may be on during boot/reset; R9 on the RFID reset likewise). A0 high = feeder on (same as
  `feeder_on()`); floating/reset = off. Across the output: 1N5819 flyback
  (cathode to FEEDER+), 100 nF, green LED + 1 kΩ. 1000 µF on 5 V, 100 µF
  on 12 V. Chosen over a low-side switch so the feeder cable is dead while
  idle (a chewed/wet cable can't start the motor or leak DC near the bowl),
  and over the old relay to keep coil current off the 3.3 V rail and contact
  noise away from the touch wire.
- Connectors: JST for everything except the feeder (decided later: PH 3-pin
  for the feeder too, see below). User has 2/3/4-pin through-hole JST
  sockets: **JST-PH, 2.0 mm pitch** (confirmed 2026-11-13). The Sharp gets
  an adapter cable (JST-ZH at the sensor, PH at the board). Caution: 2-pin
  PH is also the LiPo connector (the Feather's own battery socket), so keep
  2-pin PH off signal lines a LiPo could be plugged into by mistake.
- RFID data: divider 10 kΩ series / 18 kΩ to GND (5 V → 3.2 V) into RX,
  plus a 2-pin jumper across the 10 kΩ for when the WL-134's 3.3 V TX pad
  is used. Jumper open = safe default (5 V TX). Never close it with the
  5 V TX wired.
- Proposed pin map (not final): touch D12, Sharp A5, feeder A0, contact LED
  D9 (or A1), RFID data on RX via 5 V→3.3 V divider (or the WL-134's 3.3 V
  TX pad), RFID reset on TX via NPN, STEMMA QT on I²C, spare header D5, D6,
  D11, D13, A2–A4.

- Sheet 2 draft (2026-11-13, not yet reviewed by the user): touch J2 (PH-3,
  0 Ω link in series); Sharp J3 (PH-3 in sensor order Vo/GND/Vcc, 10 µF +
  100 µF, 1 kΩ to A5, optional 100 nF); RFID supply jumper JP2: 5 V via
  ferrite + 470 µF (default) or 6 V from an optional LM7806 on 12 V;
  RFID J4 (PH-4: VCC, RST, TX, GND), reset via PN2222A on TX (inverted, as the
  old board), data divider + JP1 on RX; contact LED on D9 (on-board LED +
  PH-3 J5 for a panel LED, 330 Ω each); I²C J6 (PH-4, STEMMA order); spare
  header J7 1×12 (5V, 3V3, GND, D5, D6, D11, D13, A1–A4, GND).

- Boost = Pololu **U3V16F12** (#4945, U3V16Fx family, as on the old board):
  fixed 12 V, 1×3 pins at 0.1″ in the order **VOUT, GND, VIN** (from the
  Pololu dimension drawing), board 8.1 × 13.1 mm, no mounting holes, no
  enable pin, ~1.5 A max input → ~0.5 A at 12 V from 5 V, ~1.2 MHz
  switching. Mounted flat on a straight header, soldered in (the user used
  to mount it upright on a 90° header). Under the Adalogger vs. in the power
  corner: decide at layout.
- Feeder current measured on the bench 2026-11-13: up to **0.15 A** under
  load. F1 stays 0.5 A hold. USB budget while feeding ≈ 0.45 A for the
  boost.
- Feeder connector J1 = **JST-PH 3-pin** (1 FEEDER+, 2 nc, 3 FEEDER−), via
  an adapter cable from the feeder's plug. 3-pin so no LiPo fits.

**Status (end of 2026-11-13):** schematic passes ERC; board 80 × 60 mm,
2 layers, fully routed (Freerouting), DRC: 0 errors, 0 unconnected, only
silkscreen warnings. Quote Gerbers in `pcb/fab/` (git-ignored;
`HydraPurr_carrier_gerbers.zip`, made with `kicad-cli pcb export gerbers`
+ `drill --excellon-separate-th`). Finish: lead-free HASL suggested (OSP is
lead-free too but has a short shelf life).

**Next (carrier PCB):**
1. In the PCB editor: Tools → Update Footprints from Library for **A1**
   (stack footprint silkscreen now stays off the board edge), then move
   the reference texts DRC flags (J1, J7, R9, R11, R13, H4, Q3).
2. Re-fill zones (B), DRC, 3D viewer: check C7's height next to the
   Feather's USB-C plug (and U2's, if ever fitted).
3. Regenerate the Gerbers before ordering (the quote set predates 1).
4. Optional: 2-3 GND stitching vias under the stack (top-layer ground is
   cut off there by tracks).
5. Before/after the board: breadboard test of touch noise with the boost
   and motor running; check WL-134 pin 4 = GND and a STEMMA cable against
   J6; measure the coin cell holder height (what fits under the logger);
   PN2222A vs P2N2222A pinout (footprint is E-B-C).
6. Firmware for the board: `feeder_pin = board.A0`, `feeder_off()` in
   `shutdown()`, drive A0 low first thing in `boot.py`.

ERC run by the user in eeschema (2026-11-13): no errors.

**KiCad schematic (2026-11-13, draft 1):** `pcb/FeederController.kicad_sch`
(KiCad 7, one A3 sheet, both "sheets" of the draft on it), generated by
`pcb/tools/gen_schematic.py`: PARTS table (values, footprints,
pin -> net) plus `build()` (placement and wires per block, power symbols,
auto junctions; net labels only where a block meets the Feather; global
labels for power on J6/J7). Draft 2 (2026-11-13) is fully wired. Custom symbols in
`pcb/HydraPurr.kicad_sym` (registered in `sym-lib-table`):
`Feather_ESP32S3_ReverseTFT` (KiCad's Adafruit_Feather_Generic with this
board's pin names, footprint `Module:Adafruit_Feather_WithMountingHoles`) and
`Pololu_U3V16F12` (pins 1 VOUT, 2 GND, 3 VIN). `gen_schematic.py --check`
exports the netlist with `kicad-cli` and compares the pin groups with PARTS
(names ignored): 35 nets, 122 connections, 0 mismatches. **KiCad 7's kicad-cli has no ERC** (KiCad 8
has); run ERC in eeschema. Once the schematic is edited by hand, don't
re-run the generator (it refuses without `--force`). Feather pin positions
checked against Adafruit's Reverse TFT display-side pinout: match the
symbol.

**Stack (decided 2026-11-13):** Feather Reverse TFT on top, screen up; under
it the Adalogger **upside down** (coin cell and microSD facing the carrier);
the carrier takes pins from the Adalogger's **secondary rows**. Seen from
above that is a mirrored FeatherWing, so A1 uses the project footprint
`HydraPurr:Feather_Adalogger_Inverted_Stack` (`HydraPurr.pretty`, made by
`tools/gen_stack_footprint.py`, registered in `fp-lib-table`), not KiCad's
Adafruit_Feather. Positions from Adafruit's board file
(github.com/adafruit/Adafruit-Adalogger-FeatherWing-PCB): secondary rows
2.03 mm inside the header rows (16.26 mm apart), long side 16 holes, short
side 11 holes EN..SDA, VBAT hole moved to (19.05, 17.40) for the coin cell.
Pad numbers = Feather pin numbers. Plan: 8.5 mm female sockets on the
carrier (1×16, 1×11, optional 1×1 VBAT), male pins in the Adalogger's
secondary rows; keep tall parts away from the coin cell and the SD end, and
put the SD end at the board edge so the card can be swapped.

**Placement (2026-11-13):** board 80 × 60 mm, arranged by the user, fixed with
`tools/fix_placement.py` (moves listed parts, swaps footprints keeping pad
nets, updates the schematic Footprint field, checks courtyard overlaps,
board edge, keep-outs). Pololu U1 **stands upright** on a right-angle header
(keep-out ~2 mm on the Q1 side). No tall parts (TO-220, big electrolytics)
in front of the stack's USB end: the Feather's USB-C plug sits there
15-18 mm up (C7 and the optional U2 now sit at its edge: user's choice,
check C7's height). All resistors lie flat (P10.16, user's choice). Strip
below the stack: LED2, J5, R5 (right under D12), J2; R13/R14 lie under the
logger in the pocket between coin cell and SD socket. J7 stands next to
the stack. GND zones on both layers, notched at x 150-167, y 147-160
around D12/R5/J2 (no rule area: KiCad 7's DSN export makes it a full
keep-out for Freerouting).

**Routing routine (Freerouting plugin, 2026-11-13):** net classes Default
0.3/0.3 mm, Power 0.8/0.3 mm, Touch 0.3/0.6 mm; board constraints
copper-to-edge 0.3 mm, min thermal spokes 1 (all in `FeederController.kicad_pro`,
set by `tools/setup_routing.py`). The plugin exports `temp-freerouting.dsn`
on every run and Freerouting rebuilds its clearance matrix from it, so
Freerouting does not take the edge clearance from the DSN (its board_edge
default is 250 µm), so the board has four 0.1 mm rule areas just inside the
edge (no tracks/vias, pour allowed): the DSN export makes them keep-outs and
Freerouting keeps its 0.3 mm from them. No matrix editing needed. Then route, import, fill zones (B), DRC, save the report
(`DRC.rpt`, ignored by git). U1's GND pad gets its own short track (boost
input current). Edit KiCad settings only with KiCad fully closed (the
project window holds settings in memory). `tools/place_parts.py`
was only the first pass (80 × 80) and is superseded. F1 uses the MF-RHT050 footprint (check
the pitch of the fuse bought). Q2/Q3 = PN2222A (2N2222), footprint pinout E-B-C;
a P2N2222A is C-B-E, so check the transistors bought. The old relay library (G6RL) is still in
`fp-lib-table` but no longer used.

## Log

- **2026-10-19** — Started this handoff. Reviewed `firmware/`, `legacy/v1_firmware/`,
  `legacy/CircuitSimulation/Notes.md` and the Notion page "HydraPurr prototype" (it
  doesn't mention the touch approach yet).
- **2026-10-19** — Decided: keep the Adalogger FeatherWing (SD + PCF8523
  RTC). That takes SDA, SCL and D10 out of the pool of touch pins.
- **2026-10-19** — Decided: the water-level sensor stays, as a 3D-printed
  float in a chimney read by a Sharp IR sensor. A relay comes later, probably
  smaller than the current one.
- **2026-10-19** — Wrote `TestDatalogger.py`, made `code.py` a selector, moved
  the touch tester to `TestTouch.py`, copied the RTC libraries. Note on RTC power loss: the PCF8523 powers up with battery
  switchover *off*, so the coin cell is ignored until the time is set once
  through the library. That explains the old `2105-15-11` boot timestamp in
  `todo.md`; running `SetTime` once on the RP2040 build should fix it there
  too.
- **2026-10-19** — First run of `TestDatalogger` on the board: 7/9 pass. I²C ok
  (0x68 RTC, 0x36 is the board's battery gauge). SD mount, write/read-back ok
  with the TFT on the same SPI bus; one append takes ~8 ms (worst 10–12 ms).
  RTC ticks but reads `2105-15-15`, `lost_power=True`, switchover off. That
  confirms the switchover explanation. The SD card
  is the old build's card (`licks.dat`, `system.log` on it).
- **2026-10-19** — Wrote `SetTime.py` (BoardCode's behaviour: `None` keeps a
  field, weekday computed, Enter to set; plus printed directions and a refusal
  to set impossible dates). Set the RTC with it: `lost_power=False`,
  switchover on. Unplugged USB, plugged back in: the time was kept. **The
  Adalogger (RTC + SD) is verified on this board.** The code we port should
  check `rtc.lost_power` at boot and flag the timestamps as invalid when it's
  set.
- **2026-10-20** — Probed the board: A5 = GPIO8, D12 = GPIO12. `touchio`
  read 0 on every pin: known CircuitPython **10.3.0** bug (adafruit/circuitpython
  #11150), fixed in 10.3.1 (#11307). Board reflashed to 10.3.1; touch now
  reads ~19 500. Warning: the front **D0/BOOT** button held during reset puts
  the board in ROM download mode (USB `303a:1001`); double-tap Reset for the
  UF2 drive `FTHRS3BOOT` instead.
- **2026-10-20** — Wrote the first firmware (see Current state). Replaced the
  CP9 `.mpy` libraries with 10.x builds; pcf8523 2.0.9 moved the class to
  `adafruit_pcf8523.pcf8523`. Runs on the board; SD card was out, so logging
  to SD is untested.
- **2026-10-20** — Changed the firmware into a pure recorder (user's choice:
  test whether the device sees water level and licks, filter offline). 100
  rows/s to hourly files under `/sd/raw/`; bout detection out of the loop.
  Runs on the board without SD card ("NOT RECORDING"); recording itself not
  yet tested.
- **2026-10-20** — Recording verified with the SD card (after a power
  cycle; a card inserted live stayed unresponsive with `OSError(11)`, and
  CircuitPython then keeps D10 claimed). Fixed sample loss: batch writes and
  full-screen redraws caused 88 rows/s with 128 ms gaps; row-by-row writes
  plus one-line-per-tick display give 96/s, 31 ms max gap. `MySD` now also
  prints mount errors to the console.
- **2026-10-20** — Wiring problem: the sensors go to a secondary row of
  pins on the logger board, and on one side that row is offset by one pin.
  Before the fix, D12 read ~18 500 regardless of touch and A5 sat at 2.52 V.
  After the fix:
  - Touch D12: ~21 800 untouched with the wire in air, ~34–36 k with it in
    the water (probably), **65535 (saturated) when touched**. Contact is
    unambiguous, but the recording only shows that and how long, not how
    strongly.
  - Sharp A5: follows a moving hand between 0.24 and 0.98 V (≈15 cm to
    ≈4–5 cm); held still it reads 0.538–0.540 V, so noise is small.
- **2026-10-20** — Display showed leftovers: a line that got shorter kept
  the tail of the previous text (manual partial refresh). Fixed by padding
  every line to the full 20 characters.
- **2026-10-20** — **Hard fault** ("memory access or instruction error",
  board then in safe mode) when the recorder was stopped (Ctrl-C) and
  soft-rebooted while its SD file was open and the display was in manual
  refresh. Fixed with `try/finally` + `shutdown()` in `MainLoop.py`; tested
  3× Ctrl-C + restart and an auto-reload during `sync2board`: clean.
  Note: in safe mode Ctrl-D only re-prints the safe-mode message; leave it
  with the reset button or `microcontroller.reset()` from the REPL.
  `MySystemLog.teardown()` now falls back to console output.
- **2026-10-20** — Stray marks on the TFT (left edge, gaps between lines),
  only in the running recorder. Ruled out by tests: SD writes on the shared
  bus, console printing, touch/analog reads, I²C, the drawn image itself
  (`display.fill_row` screenshot was clean). Marks only appeared with
  single-line (partial) refreshes; full-screen redraws were always clean.
  Padding lines to fit the width (19 chars) did not fix it. Root cause not
  found. Now: full-screen redraw (~150 ms!) once a second, skipped while
  there was touch contact in the last 3 s (`display_quiet_ms`), so the
  pauses fall in quiet periods. Status line `max_gap` will therefore show
  ~160 ms even though no samples are lost during drinking.
  Confirmed by the user: screen clean after a cold boot.
- **2026-10-20** — Committed `firmware/`, `sync2board` and `.gitignore`
  on branch `simplified-recorder`. `sd/placeholder.txt` had to be
  force-added: the `.gitignore` rule `*old*` matches "placeholder".
- **2026-10-20** — Wireless data retrieval: first tried joining the home
  WiFi via CircuitPython's web workflow (misunderstanding: the user expected
  the board to make its own network). Switched to our own download mode
  (D1 → access point + small web server). Problems found and fixed on the
  way: see "WiFi / download mode: lessons". Tested by the user: page, small
  file, 5 MB from RAM, largest raw file in chunks, and the normal links.
  Final version (all files via our chunked route) confirmed working by the
  user on a charger.
- **2026-10-21** — Contact LED on D9 (+ side on the pin, resistor to GND),
  so contacts show on video. Set in the sample step right after
  `touch.update()`, before the SD write: it matches the recorded `contact`
  column, delay <= one sample (10 ms) plus at most ~10 ms SD write; only the
  first contact after a quiet spell can fall in a ~150 ms screen redraw (the
  data has the same gap). 0.5 s flash at boot (before the touch baseline);
  off in download mode. Confirmed working by the user.
- **2026-10-28** — Raw rows now start with `epoch_ms` (wall-clock ms, RTC at
  boot + time since boot), so restarts that append to the same hourly file
  (mono_ms back to ~0) need no segment parsing. Checked on the card: matches
  the `# start` anchor to the ms. All `now_ms()` helpers switched from float
  `time.monotonic()` to `monotonic_ns()` (float loses ms precision after
  ~1 h). Rate unchanged (~83-85 rows/s with the once-a-second redraw).
  Lesson: never `readlines()` an hourly raw file on the board — out of
  memory, hard fault, safe mode; iterate line by line. Planned: events file
  (Next steps 4), then automatic WiFi upload of it, NTP clock sync, maybe no
  RTC (Next steps 5).
- **2026-10-28** — `Settings.py` moved from `lib/` to the root (the file you
  edit sits next to `code.py`; imports unchanged). Home WiFi credentials go in
  `settings.toml` (board only, never synced) as `WIFI_*`, read by
  `Settings.py`; the comment there says where. Removed `settings.toml.off`. Next: an upload test script
  showing signal strength, kB/s and the longest send on the screen, to carry
  around the house (Next steps 5).
- **2026-10-30** — Event log (`lib/EventLog.py`, Next steps 4). Event set
  agreed with the user: boot, settings, contact, rebaseline, water (10-s
  summary), shutdown. Dropped: periodic status rows ("only log when there is
  something to log") and download on/off (D1 download is to be replaced by
  the upload). `TouchSensor.rebaseline` reports baseline resets to the loop.
  Formatting tested on the desktop with stub modules; not yet run on the
  board.
- **2026-10-30** — Synced to the board and ran it: `boot`, `settings`,
  `water` and `shutdown` rows written as intended (contact/rebaseline not yet
  exercised, nobody touched the wire). Water rows read mean ~0.60 V with
  min/max 0.57-0.85 V per 10 s, far noisier than the ±20 mV in the notes.
  Likely cause (user): no water in the device, so the float lies tilted at
  the bottom (further away, slanted reflecting surface). Re-check with water
  before reading anything into the Sharp noise.
- **2026-10-30** — Upload speed test (Next steps 5, "to measure first"):
  `TestUpload.py` on the board (hold D2 at boot) + `UploadSink/upload_sink.py`
  on a computer. Sink tested locally; on the board only checked that it
  loads and stops at the "settings.toml ... missing" screen. Not yet run
  against a real network: `settings.toml` still has placeholder WiFi values
  and no `UPLOAD_TEST_HOST`. Normal start (D2 not held) checked: recorder
  runs as before.
- **2026-11-16** — Upload test run on the lab WiFi (ch 6,
  RSSI -43 dBm, board near the router, 8.5 dBm TX). First run failed: the
  board reconnected several times a second, ~10 KB per connection. Cause:
  CircuitPython sockets don't wait in `send()`; when the ~6 KB TCP send
  buffer is full they raise `OSError(11)` (EAGAIN), which the test treated
  as a broken connection. Fixed: EAGAIN = try again (counted as "buffer
  full"), real errors back off 1 s. Result: **~400-550 KB/s, longest single
  send 6-7 ms** (under the 8 ms budget). An hourly raw file (~16 MB) would
  take ~35 s; the events file well under a second. For the real upload this
  is good news: a non-blocking send that returns EAGAIN fits the "send a
  bit in each loop pass" plan. Not yet checked: rate further from the
  router, higher TX power, touch readings while transmitting.
  Second run in another room of the lab (8.5 dBm, real location not
  available): sink shows ~400-480 KB/s, one 1-s dip to ~80 KB/s. Lowest TX
  power is enough; even the dip is far above the ~4.4 KB/s raw average.
  Board screen there: max send 7 ms. **Upload speed test done.**
- **2026-11-16** — Decided with the user: **pull, plus a heartbeat.** No
  computer stays on in the lab, so push would have to go online (Dropbox
  API: OAuth refresh tokens, HTTPS uploads); the user's reason for push was
  seeing that the board still runs, and healthchecks.io does that better
  (alerts when pings stop). Plan:
  1. Board joins the lab WiFi at boot, reconnects on its own.
  2. Heartbeat to healthchecks.io every 15 min with a status line (rows,
     errors, rate, max_gap, contacts, water, SD free, RSSI, RTC ok, uptime,
     IP); `/fail` when something is wrong (SD errors, not recording, RTC
     lost power, touch 0). Watchdog resets the board if the loop hangs.
  3. mDNS name `hydrapurr.local` (IP also in the heartbeat).
  4. Own small HTTP server that sends 4 KB pieces between samples
     (EAGAIN = retry next pass), so fetching never stops recording.
  5. D1 download mode removed.
  Accepted by the user: data only reachable from the lab network; the SD
  card is the only copy until someone fetches it.
  First step: `TestHeartbeat.py` (D2 at boot now runs this instead of
  `TestUpload.py`), which times one HTTPS heartbeat (DNS, TLS handshake,
  send, reply) and its memory use, since that is the one blocking step.
  D1 sends a `/fail` ping to test the alert. Needs `HEALTHCHECK_URL` in
  `settings.toml`; `MainLoop` masks it in the settings snapshot. Written,
  compiles on the desktop, not yet run on the board.
- **2026-11-16** — USB dropped a second time on a soft reboot (Ctrl-D),
  this time with the WiFi station only *started* (`wifi.radio` touched by
  a failed test run, status bar "Wi-Fi: No IP"), never connected. Board then
  shows in `lsusb` as `239a:8124` "Device 000" with no `/dev/ttyACM0`;
  only Reset brings it back. Rule for now: **once WiFi has been touched,
  end with Reset, never Ctrl-D / auto-reload.** Consequence for the WiFi
  recorder: `sync2board` triggers an auto-reload, so syncing while it runs
  would drop USB mid-write (that is how CIRCUITPY was corrupted on
  2026-10-20). Options to test: `supervisor.runtime.autoreload = False` in
  the WiFi recorder plus `microcontroller.reset()` in `shutdown()`, or
  `wifi.radio.stop_station()` / `enabled = False` before the reload.
  Also: `settings.toml` values with a typo (here an extra `"` at the end)
  make `os.getenv` return None silently; the test then said nothing useful.
  `settings.toml` on the board: `HEALTHCHECK_URL` added by the user, extra
  quote removed.
- **2026-11-16** — **WiFi recorder, step 1** (`lib/Network.py`, `MainLoop.py`,
  `Settings.py`). Joins the WiFi at boot (screen shows the IP), event rows
  `wifi joined/join_failed/lost`. Heartbeat every 15 min, only after 30 s
  without contact (`heartbeat_quiet_ms`), sent anyway after 10 min delay;
  first one right after boot. Body: `problems=… t up rows rate max_gap
  errors contacts water touch base sd_free rssi ip rtc reset last_hb`.
  `/fail` when problems: not_recording, sd_errors (new since last
  heartbeat), rtc, touch, sd_low (< 1 GB). Failed heartbeat → event row
  `heartbeat_failed`, retry in 1 min. Heartbeat and re-join gaps are left
  out of `max_gap` (reported as `last_hb`). Watchdog 60 s (RESET), off in
  D1 download mode. Once WiFi is used: auto-reload off, and the loop ends
  with `microcontroller.reset()` instead of a soft reboot. Screen line 4:
  `base … WiFi` / `noWiFi` (red).
  Tested on the board: joins, heartbeat 3.8-4.1 s, status line arrives;
  after the first minute 85 rows/s, max_gap ~165 ms (screen), slowest write
  16-40 ms, touch steady with WiFi on (first minute: max_gap 305 ms,
  slowest write 76 ms, not repeated). **Ctrl-C now resets the board and USB
  comes back** by itself; recording and heartbeat resume. So the workflow
  is: copy files, then Ctrl-C (or Reset). Not yet tested: the watchdog
  firing on a hang, re-join after a WiFi loss, D1 download mode with the
  station connected, a `/fail` heartbeat from a real problem.
- **2026-11-16** — **WiFi recorder, step 2: file server while recording**
  (`lib/FileServer.py`, `lib/Button.py`; `DownloadMode.py` and its
  `download_*` settings removed, D1 does nothing in the recorder now).
  mDNS name `hydrapurr.local` (`mdns_hostname`). Heartbeat waits while a
  download runs (still capped by the 10 min max delay) and reports
  `served=` (requests) and `sent=` (KB). Tested first on the desktop
  (CPython sockets, simulated 10 ms grid: `wget -r` complete, files
  identical, 404/301/403 right, no late sample), then on the board from
  the lab computer: `hydrapurr.local` resolves; folder pages 75-175 ms;
  **1.8 MB file in 12.6 s, 4.6 MB (this hour's, still being written) in
  32.8 s, ~148 KB/s**; finished file has no broken lines, the open one
  ends at the last flushed row. **Recording during the downloads: 84
  rows/s, max_gap 169 ms** (= screen redraw, same as without WiFi), one
  slow write of 86 ms. An hourly raw file (~16 MB) therefore takes ~2 min
  to fetch. `lib/adafruit_httpserver/` removed (no longer used).
  Not yet tested: two clients at once, a fetch during a lick bout, a
  download interrupted half-way.
- **2026-11-16** — Reset the board remotely with Ctrl-C over serial (works
  now that WiFi use ends in `microcontroller.reset()`); CIRCUITPY then came
  back unmounted: `udisksctl mount -b /dev/sdc1`. Deleted
  `lib/adafruit_httpserver/` on the board; board now matches the repo.
  Lesson: **writing to CIRCUITPY while recording stalls the board**
  (internal flash writes block the CPU): max_gap 662 ms and 1466 ms in the
  minutes of a delete and a small copy, back to 165 ms after. Copy files
  to the board only when gaps don't matter.
- **2026-11-16** — **Offline reader** (`ProcessLickData/`, now `analysis/`):
  `library/hydrapurr_fetch.py` (mirrors the card over WiFi into
  `data/simplified/`, only new/changed files; folder pages now carry
  `data-size` with the exact byte count, `FileServer.py` updated on the
  board), `library/hydrapurr_reader.py` (raw with `time` and `boot`
  columns, drops 5 rows after each `# start` and broken lines; events with
  named fields per type), `plot_hydrapurr_day.py` (touch + baseline with
  contact ticks, water raw + 10-s summaries, boots and WiFi losses marked,
  lines broken at recording gaps). Ran it on today: 14 files / 19.8 MB in
  ~2 min, plot checked. `EventLog.py` docstring lists the `wifi` and
  `heartbeat_failed` events.
  **Board clock is ~1 h 2 min ahead** (RTC set in October during EDT, lab
  is on EST since 2026-11-01, plus ~2 min drift). All timestamps so far
  carry that offset. Fix options: run `SetTime.py`, or (better, WiFi is
  there now) NTP sync at boot and daily, ideally keeping the RTC in UTC
  so DST never shifts the data (reader converts to local time).
  Seen in the plot: the 10-s water max jumps to 0.85-0.9 V for the first
  seconds after every boot (the start-up artefact noted 2026-10-28), so
  the water summaries right after a boot should be skipped too.
- **2026-11-16** — **Clock from NTP, board keeps UTC.** `Network.ntp_time()`
  (one SNTP UDP packet to `pool.ntp.org`, integers only: CircuitPython
  floats can't hold an epoch to the ms), `TimeUtil.set_clock()` (sets the
  PCF8523, which also clears lost_power and turns on switchover, and
  re-anchors the timebase), `RawRecorder.retime()`. MainLoop: WiFi join
  and NTP now come **before** the first event row, so a whole boot carries
  NTP time; re-sync every 24 h when quiet and no download, retry every
  10 min after a failure. Event `clock` (`ntp`, step_ms, rtt_ms, server /
  `ntp_failed`); heartbeat has `t=…Z` and `ntp_age=`; a successful sync
  clears the `rtc` problem. Screen clock line `MM-DD HH:MM:SS UTC`.
  **Since then the card's file names are UTC days/hours.** `SetTime.py`
  header says to enter UTC (only needed without WiFi).
  First sync on the board: 21:46:01 UTC, round trip 37 ms, step
  14 213 816 ms, i.e. the old clock was **1 h 03 min 06 s ahead** of lab
  time (EST). Reader (`hydrapurr_reader.py`): `time` = lab time
  (America/New_York); UTC rows converted (from `UTC_SINCE_MS` = board time
  2026-11-16 20:00, between the last old row 17:49 and the first UTC row
  21:46); old-clock rows from 2026-11-01 shifted back by that measured
  offset; October rows as they are. A lab day spans two board days
  (`board_days_for`); the plot and the fetch use both. Checked: today's
  data is one monotonic timeline in lab time, the upload test gap sits at
  14:42-15:01 (sink log 14:40-14:49).
  Not yet seen: a daily re-sync (step should be a few hundred ms; a
  backward step makes a few timestamps repeat, visible in the `clock` row).
  **USB dropped out** (board gone from `lsusb`, needed Reset) on the soft
  reboot (Ctrl-C, Ctrl-D) after the test, with the station still connected.
  So the USB-loss problem is not only the access point. To check: does
  `wifi.radio.stop_station()` / disconnecting before the reload avoid it?
  Until then, assume Ctrl-C/auto-reload with WiFi up can drop USB.
- **2026-11-17** — Start page for testers on the board (no Python needed).
  `http://hydrapurr.local/` now shows what the board is doing (set by
  MainLoop once a second) and one row per (UTC) day: `events` (the day's
  events CSV) and `raw` (`/day/<date>/raw.csv`: the hourly files sent one
  after the other as one file, `hydrapurr_raw_<date>_UTC.csv`; nothing
  stored twice, the reader reads it as is). The folder pages moved to
  `/files/` with absolute links; the fetcher starts there (falls back to `/`
  for an older board). **Fast download**: `?pause=1` on any file link
  (`raw, fast` on the page) stops sampling while that one download runs;
  4 KB pieces, poll deadline t+50 ms. Ends with the download, a broken
  connection, the 10 s client timeout, or `fileserver_max_pause_ms` (20
  min). An open contact is ended at the pause; events `paused` / `resumed`
  (reason, paused_ms); heartbeat field `paused=` (s since boot); screen
  `PAUSED: download`. `fileserver_allow_pause = False` hides the fast links
  and ignores `?pause=1` (for real experiments).
  Measured: day file 201 MB (17 h) at **123 KB/s normal (rate 81-84/s,
  max_gap 165-171 ms: recording unaffected), 309 KB/s fast** (2.5x). A
  full day: ~27 min normal, ~11 min fast. A fast download cut off by the
  client: `resumed` with `error OSError(104,)`, recording back at once.
  Events files are ~460 KB/day, not ~100: 360 `water` rows per hour.
  Deploy lesson: send **one** Ctrl-C to reset the board. A second one
  lands in the 0.5 s sleep before `microcontroller.reset()` and leaves the
  board stopped at "Code done" (not recording); recover from the REPL with
  `import microcontroller; microcontroller.reset()`.
  RTC drift: the boot sync stepped the clock -4.8 s after ~19 h (~70 ppm,
  PCF8523); the daily NTP sync keeps that under ~6 s.

- **2026-11-17** — Fetcher `--pause` (also on `plot_hydrapurr_day.py`):
  each raw file is requested with `?pause=1`, so recording pauses per file
  and runs again in between (events files and logs never pause). Tested:
  two 4 MB hourly files in 13.4 s and 12.7 s (~300 KB/s), byte-identical
  to the card, one `paused`/`resumed` pair each. The day plot shades
  paused spans grey.

- **2026-11-17** — Water spikes after a reset, looked at in the raw data of
  13 boots (2026-11-16/17): single Sharp samples jump from ~0.60 V up to
  ~0.9 V, 5-10 per second, mean barely moved. Last spike ~23-25 s after the
  loop starts (~45 s of mono_ms) after boot 7 and today's restart (which
  followed 70 s stopped at "Code done"); none at all after the quick
  Ctrl-C resets 8-11. Not the radio: no spikes during downloads. Not the
  Sharp powering up either (it runs on USB 5 V through a reset). Cause
  unknown. The reader now sets water_v to NaN while mono_ms < 50 s
  (`WATER_SETTLE_MS`, also contact water_v) and drops water summaries
  covering that time; touch data is kept. Spikes left: three power-on boots
  of 2026-11-16 afternoon, 1.5-6 min in (board being moved; left in).
  Seen in the same plot: **touch raw drops ~150 counts (0.6 %) while the
  board sends files** (normal download 11:28-11:30 lab time, fetches
  ~11:38-11:40, and the WiFi traffic in the first minutes after boot). The
  baseline follows; the contact threshold is +10 % (~2 570 counts) and the
  shift is downward, so no false contacts. Keep in mind when setting the
  thresholds from real licks.

- **2026-11-17** — WiFi icon on the screen (top right, `StatusDisplay.set_wifi`):
  green arcs = connected, grey arcs + red slash = not, hidden with WiFi
  off; the bottom line is `base ...` only. Part of the once-a-second full
  redraw, no extra cost (rate 83/s, max_gap 165 ms as before). The
  disconnected look is not seen on the board yet.
  Server fix: a browser download of an 11 KB events file took 9.9 s. Chrome
  opens spare connections that send nothing, and with one client at a time
  the real request waited for the 10 s client timeout. Now a connection
  that has sent nothing is dropped as soon as another one is waiting, or
  after 2 s (`REQUEST_TIMEOUT_MS`). On the board: request behind an open
  idle connection served in 0.48 s.

- **2026-11-17** — Events file: the 10-s `water` rows (~8 600 a day, most of
  the file) are replaced by a `status` row every 15 min (water 10-s mean,
  touch baseline, touch raw, contacts since the last one), first one 60 s
  after the loop starts. Decided with the user: the events file reports
  what happens (contacts carry touch and water from just before them); the
  raw files hold every sample. Settings rows stay in the events file (user's
  choice). Reader: `status(events)`; `water()` still reads old files. Plot:
  status rows as dots.

- **2026-11-17** — First touch test by hand, on the board. 9 quick finger
  taps: 9 `contact` rows, 140-640 ms, peaks 39 000-65 535 (touchio's max)
  on a baseline of ~25 750, i.e. +50-155 % against the +10 % threshold
  (a tongue may give much less: thresholds still from cat data). Baseline
  crept up ~50 counts over 4 s of tapping (harmless). A ~6 s hold:
  `rebaseline stuck` at 5 s (contact row 5010 ms, baseline to 65 535), then
  on release `rebaseline drop`, caught mid-fall at 28 313 while the wire
  was back at ~25 760 within 0.35 s; at tau 30 s the baseline needed ~2 min
  to come back, contact threshold 14-20 % above rest meanwhile. Fix:
  `touch_drop_settle_ms` (500 ms) after a drop the baseline follows every
  lower value at once. Replaying the recorded hold through the new code
  gives the same stuck/drop events and a baseline of 25 725 after 0.5 s
  (old: 28 273).
  Checked on the board with a second hold: baseline 25 767 at 0.5 s after
  release, 25 750 later. That release fell in steps and gave four `drop`
  rows in 50 ms; a fall inside the settle window no longer logs a new
  `drop` (replay of both holds: one stuck + one drop each, end baseline
  ~25 750).

- **2026-11-17** — Code review (two fresh reviewers, findings checked) and
  clean-up. Robustness: RTC reads can no longer crash the loop (time stamps
  from the timebase, `check_rtc` guarded, `set_clock` sets the timebase
  before the chip); recorder and event log catch any exception and retry
  the card once a second (desktop test: 3 s outage = 3 re-opens, 300 rows
  counted as dropped, one warning); unexpected errors and a failed start-up
  reset the board after 10 s even without WiFi; watchdog fed before each
  blocking step; system.log no longer syncs every line; server refuses
  paths without a leading `/` (`GET _mount.log` reached `/sd_mount.log`),
  `yield from` closes the file of a broken-off day download, data flushed
  before a file's size is taken (current-hour download now ends at the
  request, was up to 5 s behind); `Network.join` sets up pool + mDNS when
  already connected; NTP replies checked; hour files split exactly on the
  hour. Reader: boots counted in recording order (a backward NTP step no
  longer counts as a boot). Fetcher: `_finished` in UTC.
  Clean-up: unused settings removed (cat name, feeder pin, deployment,
  upload test), bout-only ones moved to the "not used" block; `TestUpload.py`,
  `test.py`, `UploadSink/` deleted (results stay in this log); stale
  comments fixed; `Archive.zip` (77 MB of old Rpi code) untracked, kept
  locally (still in git history); `.gitignore` `*old*` / `*.html*`
  narrowed. `MainLoop` split into `start_up()` + loop + small functions.
  On the board after deploying: the first boot's system.log stopped mid-line
  and every later line failed with OSError(5) (recording itself fine).
  FatFs keeps an error on the file object; with the per-line sync gone, one
  failed write during start-up (cause not found, not reproduced) broke the
  handle for good. MySystemLog now re-opens the file after a failed write.
  Checked on the board: heartbeat ok, 84 rows/s, max_gap 159-170 ms, fast
  download 359 KB/s, `GET _mount.log` -> 403.

- **2026-11-23** — **First test with water in the bowl** (the bowl had been
  empty until now: all earlier touch values were the wire in air). Fill in
  50 ml steps, values from the start page (settled, ~10 s after each pour):

  | water | water_v | step |
  | --- | --- | --- |
  | empty | 0.623 | |
  | wire just covered | 0.772 | |
  | +50 ml | 0.853 | +0.081 |
  | +100 ml | 0.927 | +0.074 |
  | +150 ml | 1.024 | +0.097 |
  | +200 ml (about full) | 1.157 | +0.133 |

  Rises at every step, steps grow toward the top (1/d response); full is
  well below the ~2.5 V peak at 2 cm, so the float stays far enough from
  the Sharp (roughly 4-6 cm, not measured). Noise ±5 mV, so one reading
  resolves a few ml. Touch: wire into water 25 650 -> 34 700 (+35 %),
  counted as one contact, `rebaseline stuck` after 5 s; then the baseline
  rises with the level (37 500 full) and the tracker follows, no false
  contacts from the pours (a pour peaked at +7 %). Finger taps on the
  water: 16 taps = 16 `contact` rows, 90-690 ms, all 65 535 (touchio's max)
  on a baseline of ~37 800; a ~6 s hold gives one `stuck` and one `drop`,
  baseline back to 37 909 within seconds. Water stays at 1.15-1.16 V during
  taps. Next: the device goes to a colleague for a test with a cat; carrier
  PCB on hold until then.
- **2026-11-23** — Fast download made explicit, two new heartbeat problems.
  Start page: red box "fast stops the recording ... Don't use it while a
  cat may drink", link renamed "raw, fast (stops recording)" with a browser
  confirm giving the expected minutes (size / 300 KB/s; a full day ~18 min,
  measured speed gives ~15). Status line and screen during a pause:
  "NOT RECORDING: paused ..." / red `NOT REC: download` (was yellow
  `PAUSED: download`). Heartbeat `rate` is now rows per second of recording
  time (fast-download pauses not counted, also a pause still running).
  New problems (/fail): `low_rate` when that rate < `heartbeat_min_rate`
  (50/s; normal ~84), judged only over >= 60 s; `reset_watchdog` /
  `reset_brownout` / `reset_panic` (`heartbeat_alert_resets`) on the first
  heartbeat after such a boot, so healthchecks.io goes down once and back
  up at the next heartbeat. A pause itself still never alerts (capped at
  20 min, heartbeats continue). Tested on the board with interval 2 min
  and threshold 90: healthchecks.io showed `problems=low_rate` (82/s) and
  went Down; `reset=SOFTWARE` (Ctrl-C reset) correctly not flagged. Not
  tested: a real watchdog/brownout reset (CircuitPython should report
  `ResetReason.WATCHDOG` for the ESP32's watchdog). Deploying note: after
  WiFi use auto-reload is off, so `sync2board` needs a Ctrl-C (or Reset)
  afterwards; `printf '\x03' > /dev/ttyACM0` works.

- **2026-11-23** — Several WiFi networks. `settings.toml` may list up to 5:
  `WIFI_SSID` / `WIFI_PASSWORD`, then `WIFI_SSID_2` / `WIFI_PASSWORD_2` ...
  `_5` (`WIFI_SSID2` without the underscore works too: the user wrote it
  that way first and the board saw only network 1). `Settings.wifi_networks`
  = [(ssid, password)], list order = preference. `Network.join()` scans
  (~2-3 s, only when more than one is listed) and tries the visible ones in
  order, up to `wifi_connect_timeout_s` each, feeding the watchdog before
  each try; a failed scan tries all. The `wifi` event row has the SSID as
  4th field; the settings snapshot lists the SSIDs, never the passwords.
  `TestHeartbeat.py` tries the list in order (no scan). Checked on the
  board: two networks listed, only the second (lab) in range -> joined
  it, no attempt on the first. Not yet seen: a join on the second
  network after the first refuses (desktop stub test only).

- **2026-11-23** — Fast download checked on the board: confirm dialog, red
  `NOT REC: download` on the screen, `paused` / `resumed done` rows; today's
  ~210 MB took 9.6 min (~365 KB/s; the page estimated ~12 min).
- **2026-11-23** — **Touching the bowl also gives a contact.** Bowl is 3D
  printed in Formlabs Grey 4 resin (a dielectric): a finger on the outside
  couples to the water through the wall. 10 taps on the outside: peaks
  44 900-46 900 = **+18 to +23 %** over a baseline of ~38 200, 140-270 ms.
  10 taps on the water: all **65 535** (saturated, +71 %), 140-240 ms. So
  duration doesn't separate them, the peak does (nothing between 47 k and
  65 k; a cut near +40 % would split these two sets). But an earlier
  mixed group (user unsure: bowl and water) gave +51 % (770 ms), +71 %,
  +12 %, +22 %: wet surfaces and touches near the water line land in
  between. Decision: keep the live threshold at +10 % (record every
  contact), classify offline by `peak_touch_raw` once cat data exists; a
  tongue may well not saturate, and a chin on the rim during a bout is the
  realistic mixed case. Saturation also hides how strong water contacts
  are (lower gain = smaller wire or series resistor, if ever needed).
  **Bowl design options if cat data shows bowl contacts near lick values**
  (user designs the bowl): coupling ∝ area × εr / distance, so a double
  wall with an air gap is the strongest lever (2 mm resin + 3 mm air ≈
  5-6× less than 2 mm resin), then a thicker wall (∝ 1/d), a wide or
  hollow rim (where a chin touches, close to the water line); other
  plastics change little (PP/PE εr ~2.3 vs resin ~3-4). A grounded shield
  also lowers the lick signal; a driven guard is not possible with
  touchio. Cheap checks first: thick vs thin spot, a foam spacer as a
  stand-in air gap.

- **2026-11-23** — **Bug: false 5-s contacts from single-sample dips.** On
  the dry-bowl days (11-18..22) 1-2 contacts a day of 5007-5012 ms with
  nobody there. Raw (2026-11-23 02:43:50 UTC): one sample dips 25 929 ->
  23 105 (-11 %) for 10 ms; the "big drops are followed at once" rule sets
  the baseline to it; the next normal sample is +12 % = contact, held until
  `rebaseline stuck` at 5 s. Fix to do in `TouchSensor.py`: follow a drop
  only once it lasts several samples (e.g. 3 = 30 ms) or use the median of
  the last few. Offline: recognisable by ~5010 ms, peak = normal raw,
  baseline before it well below normal (noted in the v2 data README).
  **Fixed** the same day: `touch_drop_samples = 3`; shorter dips are
  ignored (no slow tracking from them either). Replay of every raw sample
  2026-11-17..23 through old and new `TouchSensor`: contacts 90 -> 81,
  ~5-s contacts 13 -> 4; the 9 removed are exactly the board's false ones,
  the 4 left are real (two holds 11-17, today's fill and hold); today's
  fill/tap hour identical (18 contacts, same stuck/drop). Deployed.
- **2026-11-23** — **Damaged spots in the raw files.** 6 of ~145 hourly
  files (11-18 07 h and 21 h, 11-19 23 h, 11-20 04 h, 11-21 16 h, 11-22
  20 h UTC; about once a day) hold one place where ~1 s of rows is written
  twice and 3-6 lines are cut off or have bad bytes; the row count is
  normal (~307 k/h). The board noticed nothing (no write errors, normal
  status lines, no download at the time). Cause unknown: candidates are
  the card or FatFs/CircuitPython writing a sector twice. The reader now
  drops the repeated rows (they also counted as extra boots). Worth
  checking: does it happen on another card; does it line up with flushes
  (every 5 s) or with hourly file switches (no: mid-hour).
- **2026-11-23** — Data folders renamed by hardware generation:
  `ProcessLickData/data/v1_rp2040_transistor/` (old dated folders) and
  `data/v2_esp32s3_touch/` (was `data/simplified/`, now merged with a full
  copy of the SD card taken 2026-11-23 ~11:18, 1.9 GB). Each has a
  README.md (not in git: `data/` is ignored). Fetcher default and
  `data_reader.V1_DATA_ROOT` updated.

- **2026-11-23** — **Repo reorganised** (see the note at the top): the
  touch-wire version is now *the* code. `git mv` throughout (history kept:
  `git log --follow`). `sync2board` finds sources at the top level and in
  `legacy/` (`./sync2board firmware`, `./sync2board legacy/v1_firmware`).
  `analysis/` has a fresh `.venv` (pandas, matplotlib; `requirements.txt`);
  the old ProcessLickData `.venv` (322 MB) was deleted, its package list is
  `legacy/ProcessLickData/requirements.txt`. PyCharm projects need
  re-opening at the new paths.

- **2026-11-23** — **Fetcher overwrote local data; fixed.** After the card
  was copied and put back (now holding only data from 11:32 lab time on), a
  fetch replaced the local `events/2026-11-23.csv` (the whole morning: fill,
  taps) with the board's shorter new one; restored from Dropbox's version
  history. Cause: the fetcher mirrored by size and replaced any differing
  file. Now a board file replaces a local one only if it starts with the
  local bytes (same file, grown); otherwise the local file stays and the
  board's is saved as `name~2.csv` (`16~2.csv`, `system.log~2`, ...), which
  later fetches grow. The reader reads the side copies. Checked on the
  board: `2026-11-23~2.csv` and `16~2.csv` created, morning untouched, the
  day plot shows both halves.

- **2026-11-13** — Started the carrier PCB design (see "Carrier PCB"). Feeder
  driver decided: high-side P-MOSFET + NPN, PTC fuse, on A0.
- **2026-11-13** — R2 and R9 (base pulldowns) 47 kΩ → 4.7 kΩ, so Q2/Q3 stay
  off if A0/TX carry the internal pull-up during boot or after code.py stops.
  To check on the board: A0 voltage with nothing connected, during boot and
  after Ctrl-C. Firmware backstop: drive A0 low first thing in `boot.py`.

- **2026-11-13** — Carrier PCB taken from schematic to a routed, DRC-clean
  board in one session. Decisions on the way: Q2/Q3 PN2222A on the wide
  TO-92 footprint; stack = Feather screen up on an upside-down Adalogger
  (own footprint from Adafruit's board file); all resistors flat; Pololu
  boost upright; GND zones on both layers notched at the touch line.
  Lessons: KiCad 7's kicad-cli has no ERC/DRC (run them in the GUI, save
  the report); edit `.kicad_pro` only with KiCad fully closed; the
  Specctra DSN export turns every rule area into a full keep-out (broke
  routing at the touch line, but is used on purpose for the edge strips);
  Freerouting ignores KiCad's edge clearance (board_edge 250 µm default).
