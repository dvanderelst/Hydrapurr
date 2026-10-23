# Simplified HydraPurr — handoff

Running notes for the simplified build. Update this file at the end of every
working session: what changed, what was learned, what is next.

## Goal

A simpler HydraPurr built on the **Adafruit Feather ESP32-S3 Reverse TFT**.
The 2-transistor (Darlington + optocoupler) lick detector on the custom PCB is
dropped. Instead, **one wire runs from a capacitive-touch pin straight into the
water**, read with CircuitPython's `touchio`. A lick shows up as a jump in the
pin's raw touch value.

## Why we dropped the transistor circuit

Background is in `CircuitSimulation/Notes.md` and the Notion page "HydraPurr
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

## Current state (2026-10-20)

**Status:** the firmware is now a **recorder**: it samples the touch wire and
the float sensor 100×/s and writes everything to the SD card; licks and
water-level changes are found offline. Bout detection and feeding are out of
the main loop for now (code kept in `lib/`). Runs on the board (CircuitPython
**10.3.1**); touch on D12 and the Sharp on A5 read real values. **Recording to the
SD card is verified** (2026-10-20): ~96 rows/s, longest gap between samples
~31 ms, slowest single write ~15 ms. Both sensors respond (after a wiring fix, see log); not yet seen with a cat
lick.

Firmware (runs at boot via `code.py`):

| File | What it does |
| --- | --- |
| `code.py` | Mounts SD, runs `MainLoop.main_loop()`. Test scripts are run by hand from Thonny. |
| `MainLoop.py` | Recording version. The loop sits in `try/finally`; `shutdown()` closes the data file and `system.log`, unmounts SD and releases the display however the loop ends (exception, Ctrl-C, auto-reload on file save). Every 10 ms (fixed grid): read touch (→ live contact 0/1 against the tracking baseline) and one Sharp reading, hand both to `RawRecorder`. Full-screen TFT redraw once a second, but only after 3 s without touch contact (a redraw pauses sampling ~150 ms, so the screen freezes while the cat drinks). Status line in `system.log` every minute: rows, errors, `rate` (samples/s), `max_gap` (longest time between samples), `slowest_write`, file, touch, contacts, water. |
| `lib/Settings.py` | All parameters, BoardCode names where the meaning is the same. Recording: `raw_log_interval_ms = 10`, `raw_log_sync_ms = 5000` (flush interval = max data lost on power cut). Touch thresholds are placeholders (+10 % on, +5 % off); they only affect the live `contact` column and the display. Bout/deployment settings are kept in a marked "not used" block. |
| `lib/TouchSensor.py` | `touchio` on D12 → 0/1. Baseline averaged at boot, then tracked (EMA, τ 30 s) only while untouched; hysteresis; contact > 5 s re-takes the baseline; big drops are followed at once. |
| `lib/WaterSensor.py` | Sharp on A5 in volts (higher = more water). The recorder uses single reads (`read_volts`); the smoothed `update()` is for the bout version. |
| `lib/DownloadMode.py` | **D1** button → recording pauses, the board starts its own WiFi access point (`HydraPurr` / `hydrapurr`, `Settings.download_ap_*`) and serves the SD card at `http://192.168.4.1/`: a file list with download links (`/raw/<date>/<hour>.csv`, top-level files). Whole card: `wget -r -np -nH http://192.168.4.1/`. Files are streamed in 4 KB chunks by our own route (`send_file`); the library's static file serving is off. TX power lowered to 8.5 dBm. D1 again, or 15 min without requests, → access point off, recording resumes. The screen shows network, password, address and the RTC time read on entry (also shown at startup in place of "RTC ok"; red `RTC: set time!` when `lost_power` is set). Uses `adafruit_httpserver` 4.8.2. |
| `lib/RawRecorder.py` | Writes `/sd/raw/<YYYY-MM-DD>/<HH>.csv` (new file each wall-clock hour), columns `mono_ms, touch_raw, touch_baseline, contact, water_v`. Each file (and each re-open) gets a line `# start <wall time> mono_ms <n>` to anchor the rows in real time. File stays open; each row is written as it is taken, `flush()` every 5 s. ~30 B/row → ~11 MB/hour, ~260 MB/day. Hourly files avoid FAT32's 4 GB limit and the slowdown of re-opening big files to append. |
| `lib/StatusDisplay.py` | 5 text lines on the TFT: `REC <rows>` (or NOT RECORDING in red), contact count, water V, touch raw (green on contact), baseline. Manual refresh; `refresh_all()` redraws the **whole screen** (root-group swap) when something changed. Lines padded to 19 characters. Status bar off; `release()` restores the console on shutdown. Uses `adafruit_display_text.label`. |
| `lib/LickSensor.py`, `lib/BoutDetection.py` | Not used by the recorder; kept for the bout-detection version. `BoutDetection.py` is BoardCode's, unchanged; `LickSensor.py` is BoardCode's glue minus the ADC. |
| `lib/components/` | Copied from BoardCode: `MyStore`, `MySystemLog`, `TimeUtil`, `FileUtil`, `MySD`, `MyRTC`, `MyI2C`. Changes vs BoardCode: `TimeUtil` falls back to 2000-01-01 instead of epoch 0 (ESP32 can't format pre-2000 dates); `MySD` releases the card on a failed mount; `MyRTC` imports `adafruit_pcf8523.pcf8523`. `__init__.py` is a minimal new one. |
| `lib/adafruit_pcf8523/`, `lib/adafruit_register/`, `lib/adafruit_display_text/` | 10.x `.mpy` builds from the library releases (pcf8523 2.0.9, register 1.13.0, display_text 5.0.6, only `label` kept). |

Tools and tests (run by hand):

| File | What it does |
| --- | --- |
| `TestDatalogger.py` | Adalogger test: I²C scan, RTC time / lost-power / switchover / battery / ticking, SD mount + write/read-back + free space + append timing. |
| `SetTime.py` | Set the RTC (None = keep a field, Enter to set, printed directions). Also clears `lost_power` and turns on battery switchover. |
| `TestTouch.py` | Multi-pin touch tester (A5, D5, D6, D9). Note: A5 is now the Sharp input. |
| `test.py` | Single touch pin (D12) driving the red LED. Header comment is stale (describes the non-Reverse board). |
| `sd/placeholder.txt` | Keeps the `/sd` mount point on CIRCUITPY. |

`./sync2board Simplified` pushes this folder (mirrors with `--delete`).
To see output: Thonny, or `python3 -m serial.tools.miniterm /dev/ttyACM0
115200` (Ctrl-D reruns `code.py`, Ctrl-] quits). The TFT shows the status
screen once the firmware runs.

Measured on the board (2026-10-20): touch baseline on D12 with the wire in
water ≈ 19 500; one `raw_value` read ≈ 0.5 ms. Sharp ≈ 0.93 V at rest, noise
about ±20 mV; one ADC read ≈ 1.3 ms.

**Open issues:** RTC reports `lost_power` again since the reflash although
its time is right; run `SetTime.py`. SD not tested with this firmware.

### Recording timing (measured 2026-10-20, this board + card)

| Setup | Rate | Longest gap |
| --- | --- | --- |
| 100-row batch + flush every 1 s, all 5 TFT lines redrawn 4×/s | 88/s | 128 ms |
| same, TFT updates off | 99/s | 79 ms (the batch write) |
| **row-by-row writes, flush every 5 s, one TFT line per 200 ms (current)** | **96/s** | **31 ms** |

Measured in isolation: one row `write()` median 0.9 ms, p99 6.7 ms, max
10 ms; 100-row write 9–23 ms; `flush()` 8–14 ms. The card can still add an
occasional slow write (internal housekeeping); `max_gap` in the status line
shows it. Every row carries its own `mono_ms`, so gaps are visible offline.

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
  non-existent network and led to resets). `.gitignore` covers
  `Simplified/settings.toml*`.
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

The lick → bout → deploy logic in `BoardCode/` has nothing to do with the
sensor hardware. It only needs a binary contact state (0/1) per sample.

| Piece | File | Carry over? |
| --- | --- | --- |
| Lick/bout state machine (debounce, 50–250 ms lick window, bout gap, eligibility gates, `try_finalize_in_progress`) | `BoardCode/lib/BoutDetection.py` | **Yes, unchanged.** Pure logic with timestamp inputs; only depends on `MySystemLog.info`. |
| Glue: sensor → binary state → BoutManager → `licks.dat` | `BoardCode/lib/LickSensor.py` | **Yes, adapted.** Replace `lick_voltage < lick_threshold` with a touch-based contact state. The water-level reading stays (float sensor, see below). |
| Deployment logic (cat-switch trigger, active-cat trigger, no-wait mode, `unknown` never fed) | `BoardCode/MainLoop.py` | **Yes, slimmed.** Single-cat mode likely enough at first. |
| Parameters | `BoardCode/lib/Settings.py` | **Yes.** `lick_threshold` (volts) needs replacing with touch parameters. |
| Cat registry / RFID | `Cats.py`, `TagReader.py` (UART rx D9, RST D11) | Only if the simplified build keeps RFID. |
| Water level | `MyADC(0)` read in `LickSensor.update` during contact; `water_extent` gate in `BoutDetection.py` | **Yes.** New hardware (see below), same role. Remap `MyADC` to the chosen ADC1 pin. `min_water_extent_per_bout` (0.013 V) must be re-tuned for the float. |
| Feeder relay | `HydraPurr.feeder_on/off`, D6 via NPN | **Later.** Probably a smaller relay than before (the old one was overkill). `feeder_on/off` stays as the interface; the pin must not clash with the touch pin. |
| Logging + time | `MyStore`, `MySystemLog`, `TimeUtil`, `FileUtil`, `MySD`, `MyRTC`, `MyI2C`, `adafruit_pcf8523`, `adafruit_register` | **Yes, close to unchanged** (same Adalogger wing, verified on this board). Add a boot check of `rtc.lost_power` and flag timestamps as invalid when it is set. `SetTime.py` already ported. |
| Display | `MyOLED` (SSD1306 over I²C) | Replace with the built-in TFT (`board.DISPLAY` + `displayio`). |
| BT | `MyBT` (HC-05 UART) | No. ESP32-S3 has BLE only; the BT swap is planned separately. |
| Offline analysis | `ProcessLickData/` | Works if `licks.dat` keeps the same columns. |

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
   lightweight variant next to `BoardCode/`?
3. Which relay? (Touch pin = D12 and Sharp = GP2Y0A51SK0F are decided.)

## Next steps (proposed)

1. Run `SetTime.py` to clear the RTC's `lost_power` flag (time itself is
   right). Check the Sharp: it reads ~2.53 V since the rewiring, which means
   something ~2 cm away or the wrong pin.
2. Record with the wire in the water: idle, a finger touching the water, a
   cat drinking. Write an offline reader (ProcessLickData) for the hourly
   files; use it to find licks and set the touch thresholds, and check that
   baseline tracking holds over hours.
3. Characterise the float: Sharp voltage over the full water range and while
   a cat drinks; set `min_water_extent_per_bout`.
4. Fit the relay (`feeder_pin`), then RFID if wanted.
5. Merge branch `simplified-recorder` into master when happy.

## Log

- **2026-10-19** — Started this handoff. Reviewed `Simplified/`, `BoardCode/`,
  `CircuitSimulation/Notes.md` and the Notion page "HydraPurr prototype" (it
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
- **2026-10-20** — Committed `Simplified/`, `sync2board` and `.gitignore`
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
