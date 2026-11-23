# HydraPurr

> **Running the test device?** See the tester guide:
> [`Simplified/README.md`](Simplified/README.md) (set-up, the screen, getting the data).

A CircuitPython device that monitors cat drinking at a water bowl. It records every touch on a wire in the water and the water level, 100 times a second, so licks and drinking bouts can be found from the data. The longer-term goal is to dispense food once a cat has completed enough drinking bouts.

(An earlier prototype, on an RP2040 board with a transistor lick circuit, RFID and live bout detection, is documented in [`BoardCode/README.md`](BoardCode/README.md).)

## Project layout

```
HydraPurr/
├── Simplified/           Firmware of the device. README.md = tester guide,
│                         HANDOFF.md = development notes and log.
├── ProcessLickData/      Offline: fetch data from the board, read it, plot a day.
├── FeederController/     Carrier PCB (KiCad): board stack, feeder driver, connectors.
├── sync2board            Push the firmware to a connected board.
├── BoardCode/            Earlier prototype (see its README).
├── CircuitSimulation/    Study of the earlier prototype's lick circuit.
├── BluetoothDownloader/, HardwareDocs/, todo.md   Earlier prototype.
└── README.md             This file.
```

## Hardware

Adafruit Feather ESP32-S3 Reverse TFT (built-in screen, WiFi) on an Adalogger FeatherWing (microSD, PCF8523 RTC), CircuitPython 10.3.1. Details, pin map and the reasoning behind each choice: [`Simplified/HANDOFF.md`](Simplified/HANDOFF.md).

- **Touch sensor:** a wire in the water on `D12`, read with `touchio`. A tongue (or finger) in the water raises the reading well above a slowly tracking baseline. Touching the outside of the 3D-printed resin bowl registers too, but much weaker.
- **Water level:** a float in a chimney connected to the bowl; a Sharp GP2Y0A51SK0F IR distance sensor above it on `A5` (0.62 V empty to 1.16 V full in the current bowl).
- **Contact LED** on `D9` (lit while touched; for video checks).
- **WiFi:** joins the first configured network in range; serves the SD card at `http://hydrapurr.local/`, sets its clock from NTP, and sends a heartbeat to healthchecks.io every 15 min.
- **Planned:** a carrier PCB (`FeederController/`) with a 12 V boost and MOSFET driver for a feeder; bout detection and feeding back on the board (the code is in `Simplified/lib/BoutDetection.py`).

## Data

The board writes hourly raw files (`raw/<date>/<hour>.csv`, every sample: touch, baseline, contact, water) and a daily events file (`events/<date>.csv`: one row per contact, a status row every 15 min, restarts, settings) to its SD card, plus `system.log`. Columns: `Simplified/lib/RawRecorder.py` and `Simplified/lib/EventLog.py`. Reading, fetching and plotting: [`ProcessLickData/readme.md`](ProcessLickData/readme.md).

## Development

- **Syncing code to the board:** `./sync2board Simplified` — `rsync` to the mounted CIRCUITPY drive (`/media/$USER/CIRCUITPY` by default; `-d` for another path, `-n` dry run). Mirrors with `--delete` but never touches the board's `settings.toml`; excludes Python caches and editor metadata, runs `sync` afterwards. Once WiFi has been used the board does not auto-reload: press Reset (or send Ctrl-C) after syncing.
- **`ProcessLickData`** is desktop Python — use the `.venv` inside that folder. Entry point: `plot_hydrapurr_day.py`. Data lives in `ProcessLickData/data/` (not in git; one folder per hardware generation, each with a README).
- **CircuitPython `lib/` convention.** CircuitPython auto-adds `/` and `/lib` to `sys.path` on boot, so any `.py` file or package directory directly under `lib/` is importable as a top-level module (`import adafruit_pcf8523`, `from components import MySD`). Do **not** add `lib/__init__.py` — that turns `lib` into a package and breaks the standard CircuitPython import style. To get the same behaviour in PyCharm during desktop development, mark `lib/` as a Sources Root (Right-click → *Mark Directory as → Sources Root*).

## Project notes

- Notion workspace for organisation: <https://www.notion.so/PyCharm-25581ad79c6d8070aaf2cc3cb64adce6>
- The older Raspberry Pi version of HydraPurr is archived (read-only reference): <https://github.com/habit-tech/Rpi_lickometer>.
