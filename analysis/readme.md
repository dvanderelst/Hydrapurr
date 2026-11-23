# analysis — data processing for the HydraPurr

Reading, fetching and plotting the data of the current device (`firmware/`).
This is the place for the new data processing; the old v1 analysis is in
`legacy/ProcessLickData/`.

Set up once (Python 3.12+), from this folder:

    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt

Data: `data/v2_esp32s3_touch/` (not in git; its README.md says what the
device was and what the data holds: dry-bowl days, the water fill, the
bowl-vs-water tap test).

## Getting and plotting the data

The board serves its SD card on the WiFi at
`http://hydrapurr.local/` while it keeps recording. Without Python, open
that address in a browser: one row per (UTC) day with the events file and
the day's raw data as one CSV (`raw, fast` pauses recording during that
download, ~2.5x faster). Read such a day file with
`read_raw_file(path)` from `library/hydrapurr_reader.py`.

    .venv/bin/python plot_hydrapurr_day.py                  # fetch new data, plot today
    .venv/bin/python plot_hydrapurr_day.py --day 2026-11-16 --hours 15 16
    .venv/bin/python plot_hydrapurr_day.py --no-raw         # events only (fast)
    .venv/bin/python -m library.hydrapurr_fetch --no-raw    # fetch only, no plot
    .venv/bin/python -m library.hydrapurr_fetch --pause     # faster (~310 KB/s): the board
                                                  # stops recording per raw file

- `library/hydrapurr_fetch.py` mirrors the card into `data/v2_esp32s3_touch/`
  (gitignored), fetching only new or changed files (~150 KB/s; a full
  hourly raw file takes ~2 min). The plot script fetches raw files only for
  the day it plots.
- `library/hydrapurr_reader.py`: `read_raw(folder, day, hours)`,
  `read_events(folder)`, `contacts(events)`, `water(events)`,
  `event_table(events, name)`, `settings_at_boots(events)`.
- Plots go to `data/v2_esp32s3_touch/plots/`.

Times: the `time` column is lab time (America/New_York). Since
2026-11-16 21:46 UTC the board sets its clock from NTP and keeps UTC, so the
card's file names are UTC days/hours and a lab day spans two board days;
older rows were on a hand-set clock and are corrected where the offset is
known (see `library/hydrapurr_reader.py` and `HANDOFF.md`).

Water after a reset: the Sharp reading can spike for up to ~45 s after a
reset, so the reader sets water values to NaN for the first 50 s of each
boot (`WATER_SETTLE_MS`, 0 = keep them) and drops the water summaries of
that time. Touch data is kept.
