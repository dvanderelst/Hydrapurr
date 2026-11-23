"""
hydrapurr_reader.py - read the HydraPurr's SD card files

Folder layout (as fetched by hydrapurr_fetch.py, or copied from the card):

    raw/<YYYY-MM-DD>/<HH>.csv    every sample (100/s), one file per hour
    events/<YYYY-MM-DD>.csv      one row per event, one file per day
    system.log                   the board's own log

Times: epoch_ms is the board's wall clock (RTC) in ms. Since 2026-11-16
~21:46 UTC the board sets its RTC from NTP and keeps UTC; before that the
RTC ran on hand-set local time, which from November on was 1 h 03 min
ahead. The `time` column is lab time (LOCAL_TZ, naive): UTC rows are
converted, old-clock November rows corrected (OLD_CLOCK_AHEAD_MS), October
rows taken as they are. mono_ms restarts near 0 at every boot; `boot`
numbers the stretches between restarts.

The board's file and folder names follow its clock, so since the switch
they are UTC days and hours: a lab day spans two board days
(board_days_for()).

    from library.hydrapurr_reader import read_raw, read_events, contacts
    raw = read_raw(folder, "2026-11-16")              # one board day
    raw = read_raw(folder, "2026-11-16", hours=[21])  # one board hour
    ev = read_events(folder)                          # all days
    c = contacts(ev)                                  # contact table

File formats: firmware/lib/RawRecorder.py and firmware/lib/EventLog.py.
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd

RAW_COLUMNS = ["epoch_ms", "mono_ms", "touch_raw", "touch_baseline", "contact", "water_v"]
# The first rows after a (re)start can be off (water read 0.49 V instead of
# ~0.9 V right after boot, HANDOFF.md 2026-10-28): drop this many.
SKIP_AFTER_START = 5
# After some resets the Sharp reading has single-sample spikes (0.6 -> up to
# ~0.9 V, 5-10 per second) for up to ~25 s after the loop starts, i.e. up to
# ~45 s of mono_ms (the loop starts 10-18 s after the reset). Measured on the
# 2026-11-16/17 boots; cause unknown (not the WiFi radio: none during
# downloads). Water values before this mono_ms are set to NaN (raw water_v,
# contact water_v); water summaries whose 10-s window starts before it are
# dropped. Touch data is kept. Set to 0 to see the raw values.
WATER_SETTLE_MS = 50_000
WATER_EVENT_SPAN_MS = 10_000   # window of the old 10-s water rows

# Meaning of f1..f4 per event (EventLog.py docstring).
EVENT_FIELDS = {
    "boot": ["reset_reason", "safe_mode_reason", "rtc_ok", "touch_baseline"],
    "settings": ["name", "value"],
    "contact": ["duration_ms", "peak_touch_raw", "touch_baseline", "water_v"],
    "rebaseline": ["reason", "touch_raw", "old_baseline", "new_baseline"],
    "water": ["mean_v", "min_v", "max_v", "samples"],        # until 2026-11-17
    "status": ["water_v", "touch_baseline", "touch_raw", "contacts"],  # since then
    "shutdown": ["reason"],
    "wifi": ["state", "ip", "rssi", "ssid"],
    "heartbeat_failed": ["status", "ms_taken"],
    "clock": ["state", "step_ms", "rtt_ms", "server"],
    "paused": ["why", "path"],
    "resumed": ["reason", "paused_ms"],
}


LOCAL_TZ = "America/New_York"
# Board clock in UTC from here on. Any value between the last old-clock row
# (board time 2026-11-16 17:49) and the first UTC row (21:46) works.
UTC_SINCE_MS = int(pd.Timestamp("2026-11-16 20:00").value // 1_000_000)
# Before the switch, from the summer/winter time change on, the hand-set
# clock ran ahead of lab time. The first NTP sync measured it: step
# 14 213 816 ms to UTC = 5 h - 1 h 03 min 06.2 s, so the old clock was
# 1 h 03 min 06 s ahead (the hour from summer time, ~3 min drift). That
# correction is applied to old-clock rows from 2026-11-01 on (for the first
# days of November it is off by up to the ~3 min of drift). October rows
# are left as they are (right hour, a few minutes of drift).
OLD_CLOCK_AHEAD_MS = 18_000_000 - 14_213_816
OLD_CLOCK_FROM_MS = int(pd.Timestamp("2026-11-01 02:00").value // 1_000_000)


def _to_time(epoch_ms: pd.Series) -> pd.Series:
    """Board epoch ms -> naive lab time."""
    t = pd.to_datetime(epoch_ms, unit="ms")
    ahead = (epoch_ms >= OLD_CLOCK_FROM_MS) & (epoch_ms < UTC_SINCE_MS)
    if ahead.any():
        t = t.copy()
        t[ahead] = t[ahead] - pd.Timedelta(milliseconds=OLD_CLOCK_AHEAD_MS)
    utc = epoch_ms >= UTC_SINCE_MS
    if utc.any():
        t = t.copy()
        t[utc] = (t[utc].dt.tz_localize("UTC").dt.tz_convert(LOCAL_TZ)
                  .dt.tz_localize(None))
    return t


def board_days_for(day: str) -> list[str]:
    """Board folder/file days that can hold data of lab day `day`: the day
    itself and, since the board keeps UTC, the next one."""
    d = pd.Timestamp(day)
    return [day, (d + pd.Timedelta(days=1)).strftime("%Y-%m-%d")]


def raw_files(folder: str | Path, day: str | list[str] | None = None,
              hours: list[int] | None = None) -> list[Path]:
    """Hourly raw files under folder/raw, sorted; optionally board day(s)
    and board hours (file names, so UTC since the switch). Includes the
    fetcher's side copies (`16~2.csv`: same name, other card or boot)."""
    root = Path(folder) / "raw"
    if day is None:
        days = sorted(p for p in root.iterdir() if p.is_dir())
    else:
        days = [root / d for d in ([day] if isinstance(day, str) else day)]
        days = [d for d in days if d.is_dir()]
    files = []
    for d in days:
        for f in sorted(d.glob("*.csv")):
            if hours is None or int(f.stem.split("~")[0]) in hours:
                files.append(f)
    return files


def _read_raw_file(path: Path) -> pd.DataFrame:
    """One hourly file: split at '# start' lines, drop the first rows after
    each, and drop broken lines (a cut-off last line, a power cut)."""
    parts = []
    rows: list[str] = []
    for line in path.read_text(errors="replace").splitlines():
        if line.startswith("#"):
            if rows:
                parts.append(rows)
            rows = []
            continue
        if line.startswith("epoch_ms"):
            continue
        rows.append(line)
    if rows:
        parts.append(rows)
    frames = []
    for rows in parts:
        rows = rows[SKIP_AFTER_START:]
        if not rows:
            continue
        df = pd.read_csv(io.StringIO("\n".join(rows)), names=RAW_COLUMNS,
                         on_bad_lines="skip")
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=RAW_COLUMNS)
    df = pd.concat(frames, ignore_index=True)
    for c in RAW_COLUMNS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna()


def read_raw(folder: str | Path, day: str | list[str] | None = None,
             hours: list[int] | None = None) -> pd.DataFrame:
    """Raw samples with a `time` column (lab time) and a `boot` counter.
    day/hours select board files (see raw_files). A day of raw data is
    ~8.6 M rows; pass hours= to read less."""
    return _finish_raw([_read_raw_file(f) for f in raw_files(folder, day, hours)])


def _finish_raw(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Join files (in recording order), number the boots, sort by time."""
    frames = [f for f in frames if len(f)]
    if not frames:
        return pd.DataFrame(columns=RAW_COLUMNS + ["time", "boot"])
    df = pd.concat(frames, ignore_index=True)
    df[["epoch_ms", "mono_ms", "touch_raw", "contact"]] = (
        df[["epoch_ms", "mono_ms", "touch_raw", "contact"]].astype("int64"))
    # Damaged spots on the card (2026-11, ~once a day): a stretch of ~1 s is
    # written twice, with a few broken lines (dropped above). Drop the
    # repeated rows, or mono_ms stepping back there counts as a boot.
    df = df.drop_duplicates(["epoch_ms", "mono_ms"]).reset_index(drop=True)
    # A restart shows as mono_ms jumping back. Counted in recording order
    # (files by name, rows as written), before sorting by time: after a
    # backward clock step (NTP) the time order interleaves a few rows, which
    # would count as extra boots.
    df["boot"] = (df["mono_ms"].diff() < 0).cumsum()
    df = df.sort_values("epoch_ms", kind="stable").reset_index(drop=True)
    df["time"] = _to_time(df["epoch_ms"])
    df.loc[df["mono_ms"] < WATER_SETTLE_MS, "water_v"] = float("nan")
    return df


def read_raw_file(path: str | Path) -> pd.DataFrame:
    """One raw CSV as downloaded from the board's start page (a whole day,
    hydrapurr_raw_<date>_UTC.csv) or a single hourly file: same columns as
    read_raw."""
    return _finish_raw([_read_raw_file(Path(path))])


def read_events(folder: str | Path, days: list[str] | None = None) -> pd.DataFrame:
    """All event rows: epoch_ms, mono_ms, event, f1..f4 (strings), time."""
    root = Path(folder) / "events"
    files = sorted(root.glob("*.csv"))
    if days is not None:
        files = [f for f in files if f.stem.split("~")[0] in days]
    frames = []
    for f in files:
        df = pd.read_csv(f, dtype=str, keep_default_na=False, on_bad_lines="skip")
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["epoch_ms", "mono_ms", "event", "f1", "f2", "f3", "f4", "time"])
    df = pd.concat(frames, ignore_index=True)
    df = df[df["epoch_ms"].str.fullmatch(r"\d+")]          # drop broken rows
    df["epoch_ms"] = df["epoch_ms"].astype("int64")
    df["mono_ms"] = pd.to_numeric(df["mono_ms"], errors="coerce")
    df["time"] = _to_time(df["epoch_ms"])
    return df.sort_values("epoch_ms", kind="stable").reset_index(drop=True)


def event_table(events: pd.DataFrame, event: str) -> pd.DataFrame:
    """Rows of one event type with f1..f4 renamed (and numbers converted)."""
    names = EVENT_FIELDS.get(event, [])
    df = events[events["event"] == event].copy()
    rename = {f"f{i + 1}": n for i, n in enumerate(names)}
    df = df.rename(columns=rename)
    df = df.drop(columns=[c for c in ("f1", "f2", "f3", "f4") if c in df.columns])
    for n in names:
        converted = pd.to_numeric(df[n], errors="coerce")
        if converted.notna().all() and len(df):
            df[n] = converted
    return df.reset_index(drop=True)


def contacts(events: pd.DataFrame) -> pd.DataFrame:
    """Contacts with start, end and duration. The row's time is the end of
    the contact; start = end - duration_ms."""
    df = event_table(events, "contact")
    if "water_v" in df:
        df.loc[df["mono_ms"] - df["duration_ms"] < WATER_SETTLE_MS, "water_v"] = float("nan")
    df["end"] = df["time"]
    df["start"] = df["end"] - pd.to_timedelta(df["duration_ms"], unit="ms")
    return df[["start", "end", "duration_ms", "peak_touch_raw", "touch_baseline", "water_v"]]


def water(events: pd.DataFrame) -> pd.DataFrame:
    """10-s water summaries (mean/min/max V; files until 2026-11-17, later
    ones have status rows instead), without those that cover the first
    WATER_SETTLE_MS after a reset."""
    df = event_table(events, "water")
    return df[df["mono_ms"] - WATER_EVENT_SPAN_MS >= WATER_SETTLE_MS].reset_index(drop=True)


def status(events: pd.DataFrame) -> pd.DataFrame:
    """Status rows (every 15 min since 2026-11-17): water_v (10-s mean),
    touch_baseline, touch_raw, contacts since the previous status row."""
    return event_table(events, "status")


def settings_at_boots(events: pd.DataFrame) -> pd.DataFrame:
    """Settings snapshot of each boot, one column per boot time."""
    df = event_table(events, "settings")
    if df.empty:
        return df
    return df.pivot_table(index="name", columns="time", values="value", aggfunc="first")
