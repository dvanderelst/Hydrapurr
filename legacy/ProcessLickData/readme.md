# ProcessLickData (legacy) — analysis of the v1 prototype data

Offline analysis for the **first prototype** (`legacy/v1_firmware/`: RP2040,
transistor lick circuit, RFID): `licks.dat` / `system.log` readers
(`library/data_reader.py`), `analysis/BoutAnalyzer.py` and `run_my_viz.py`.
The current device's data processing is in `analysis/` at the top of the repo.

Data: `data/v1_rp2040_transistor/`, one folder per download (not in git; its
README.md lists the folders, dates and column formats). Original location of
the downloads: `~/Dropbox/HabitTechnology/Prototype_of_Hydropurr/testing/data/device_data`.

The old `.venv` was deleted on 2026-11-23 (it broke when the folder moved);
to run these scripts again:

    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
    .venv/bin/python run_my_viz.py
