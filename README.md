# HydraPurr

> **Running the test device?** See the tester guide:
> [`firmware/README.md`](firmware/README.md) (set-up, the screen, getting the data).

A CircuitPython device that monitors cat drinking at a water bowl. It records every touch on a wire in the water and the water level, 100 times a second, so licks and drinking bouts can be found from the data. The longer-term goal is to dispense food once a cat has completed enough drinking bouts.

(An earlier prototype, on an RP2040 board with a transistor lick circuit, RFID and live bout detection, is kept under [`legacy/`](legacy/); its firmware is documented in [`legacy/v1_firmware/README.md`](legacy/v1_firmware/README.md).)

## Project layout

```
HydraPurr/
├── HANDOFF.md    Development notes, open items and log (whole project).
├── firmware/     The device's CircuitPython code. README.md = tester guide.
├── analysis/     Data processing: fetch from the board, read, plot (own .venv).
├── pcb/          Carrier PCB (KiCad): board stack, feeder driver, connectors.
├── sync2board    Push the firmware to a connected board.
├── legacy/       The first prototype: v1_firmware/ (was BoardCode/),
│                 ProcessLickData/, CircuitSimulation/, HardwareDocs/,
│                 BluetoothDownloader/, todo.md.
└── README.md     This file.
```

## Hardware

Adafruit Feather ESP32-S3 Reverse TFT (built-in screen, WiFi) on an Adalogger FeatherWing (microSD, PCF8523 RTC), CircuitPython 10.3.1. Details, pin map and the reasoning behind each choice: [`HANDOFF.md`](HANDOFF.md).

- **Touch sensor:** a wire in the water on `D12`, read with `touchio`. A tongue (or finger) in the water raises the reading well above a slowly tracking baseline. Touching the outside of the 3D-printed resin bowl registers too, but much weaker.
- **Water level:** a float in a chimney connected to the bowl; a Sharp GP2Y0A51SK0F IR distance sensor above it on `A5` (0.62 V empty to 1.16 V full in the current bowl).
- **Contact LED** on `D9` (lit while touched; for video checks).
- **WiFi:** joins the first configured network in range; serves the SD card at `http://hydrapurr.local/`, sets its clock from NTP, and sends a heartbeat to healthchecks.io every 15 min.
- **Planned:** a carrier PCB (`pcb/`) with a 12 V boost and MOSFET driver for a feeder; bout detection and feeding back on the board (the code is in `firmware/lib/BoutDetection.py`).

## Data

The board writes hourly raw files (`raw/<date>/<hour>.csv`, every sample: touch, baseline, contact, water) and a daily events file (`events/<date>.csv`: one row per contact, a status row every 15 min, restarts, settings) to its SD card, plus `system.log`. Columns: `firmware/lib/RawRecorder.py` and `firmware/lib/EventLog.py`. Reading, fetching and plotting: [`analysis/readme.md`](analysis/readme.md).

## Development

- **Syncing code to the board:** `./sync2board firmware` — `rsync` to the mounted CIRCUITPY drive (`/media/$USER/CIRCUITPY` by default; `-d` for another path, `-n` dry run). Mirrors with `--delete` but never touches the board's `settings.toml`; excludes Python caches and editor metadata, runs `sync` afterwards. Once WiFi has been used the board does not auto-reload: press Reset (or send Ctrl-C) after syncing.
- **`analysis/`** is desktop Python — create its `.venv` from `requirements.txt` (see its readme). Entry point: `plot_hydrapurr_day.py`. Data lives in `analysis/data/v2_esp32s3_touch/` (not in git; with a README on what it holds).
- **CircuitPython `lib/` convention.** CircuitPython auto-adds `/` and `/lib` to `sys.path` on boot, so any `.py` file or package directory directly under `lib/` is importable as a top-level module (`import adafruit_pcf8523`, `from components import MySD`). Do **not** add `lib/__init__.py` — that turns `lib` into a package and breaks the standard CircuitPython import style. To get the same behaviour in PyCharm during desktop development, mark `lib/` as a Sources Root (Right-click → *Mark Directory as → Sources Root*).

## Project notes

- Notion workspace for organisation: <https://www.notion.so/PyCharm-25581ad79c6d8070aaf2cc3cb64adce6>
- The older Raspberry Pi version of HydraPurr is archived (read-only reference): <https://github.com/habit-tech/Rpi_lickometer>.
