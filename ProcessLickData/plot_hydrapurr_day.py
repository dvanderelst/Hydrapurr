#!/usr/bin/env python3
"""
plot_hydrapurr_day.py - fetch the Simplified HydraPurr's data and plot a day

    python plot_hydrapurr_day.py                     # fetch, plot today
    python plot_hydrapurr_day.py --day 2026-11-16 --hours 15 16
    python plot_hydrapurr_day.py --no-fetch          # plot what is here
    python plot_hydrapurr_day.py --no-raw            # events only (fast)

Panels (shared time axis):
    touch   raw touch value and the board's baseline; contacts shaded
    water   Sharp float sensor: raw samples and the 10-s event summaries
Restarts (boot events) are dashed vertical lines, WiFi losses dotted.

The PNG goes to data/simplified/plots/<day>[_<hours>].png. Data comes from
data/simplified/ (see library/hydrapurr_fetch.py).
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import matplotlib
import pandas as pd

from library.hydrapurr_fetch import DEFAULT_DEST, DEFAULT_URL, fetch
from library.hydrapurr_reader import (board_days_for, contacts, event_table, read_events,
                                     read_raw, water)

MAX_POINTS = 200_000           # above this, raw data is reduced to 1-s bins
GAP = pd.Timedelta(seconds=2)  # no data for longer = not recording: break lines


def break_gaps(df: pd.DataFrame, max_gap: pd.Timedelta = GAP) -> pd.DataFrame:
    """Insert an empty row after every gap, so lines are not drawn across
    the time the board was not recording."""
    if len(df) < 2:
        return df
    gaps = df["time"].diff() > max_gap
    if not gaps.any():
        return df
    fill = df.loc[gaps].copy()
    fill["time"] = fill["time"] - pd.Timedelta(milliseconds=1)
    for col in fill.columns:
        if col != "time":
            fill[col] = float("nan")
    return pd.concat([df, fill]).sort_values("time", kind="stable").reset_index(drop=True)


def reduce(raw: pd.DataFrame) -> pd.DataFrame:
    """1-s bins: touch max (keeps contacts visible), the rest as means."""
    if len(raw) <= MAX_POINTS:
        return raw
    g = raw.set_index("time").resample("1s")
    out = pd.DataFrame({
        "touch_raw": g["touch_raw"].max(),
        "touch_baseline": g["touch_baseline"].mean(),
        "water_v": g["water_v"].mean(),
    }).dropna()
    return out.reset_index()


def plot_day(folder: Path, day: str, hours: list[int] | None, use_raw: bool,
             show: bool) -> Path:
    if not show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # The board keeps UTC, so a lab day spans two board days: read both and
    # keep the rows whose lab time falls on `day` (and `hours`).
    days = board_days_for(day)
    ev = read_events(folder, days=days)
    raw = read_raw(folder, days) if use_raw else pd.DataFrame()

    def keep(df, col="time"):
        if not len(df):
            return df
        sel = df[col].dt.strftime("%Y-%m-%d") == day
        if hours is not None:
            sel &= df[col].dt.hour.isin(hours)
        return df[sel]
    raw = keep(raw)
    c = keep(contacts(ev), "end")
    w = keep(water(ev))
    boots = keep(event_table(ev, "boot"))
    wifi = keep(event_table(ev, "wifi"))

    fig, (ax_t, ax_w) = plt.subplots(2, 1, sharex=True, figsize=(14, 7),
                                     gridspec_kw={"height_ratios": [3, 2]})
    title = f"HydraPurr {day}" + (f" hours {hours}" if hours else "")
    lick_like = c[(c["duration_ms"] >= 50) & (c["duration_ms"] <= 250)] if len(c) else c
    ax_t.set_title(f"{title}: {len(c)} contacts, {len(lick_like)} of 50-250 ms "
                   f"(lick length), {len(boots)} boots")

    if len(raw):
        r = break_gaps(reduce(raw))
        ax_t.plot(r["time"], r["touch_raw"], lw=0.6, color="#3060c0", label="touch raw")
        ax_t.plot(r["time"], r["touch_baseline"], lw=1.0, color="#909090", label="baseline")
        ax_w.plot(r["time"], r["water_v"], lw=0.5, color="#40a070", alpha=0.6,
                  label="water (raw)" + (", 1-s means" if len(r) < len(raw) else ""))
    if len(c):
        for start, end in zip(c["start"], c["end"]):
            ax_t.axvspan(start, end, color="#e04040", alpha=0.25, lw=0)
        # A 100-ms span is invisible on an hours-long axis: tick each contact.
        ax_t.plot(c["start"], [1.0] * len(c), "|", color="#e04040", ms=14, mew=1.5,
                  transform=ax_t.get_xaxis_transform(), clip_on=False, label="contact")
    if len(w):
        # 10-s summaries: more than 15 s apart = a gap in recording.
        w = break_gaps(w[["time", "mean_v", "min_v", "max_v"]], pd.Timedelta(seconds=15))
        ax_w.fill_between(w["time"], w["min_v"], w["max_v"], color="#205030",
                          alpha=0.2, step="mid", label="10-s min/max")
        ax_w.plot(w["time"], w["mean_v"], color="#205030", lw=1.2, label="10-s mean")
    for ax in (ax_t, ax_w):
        for t in boots["time"] if len(boots) else []:
            ax.axvline(t, color="black", ls="--", lw=0.8)
        if len(wifi):
            for t in wifi[wifi["state"] == "lost"]["time"]:
                ax.axvline(t, color="#c08000", ls=":", lw=1)
    ax_t.set_ylabel("touch raw")
    ax_w.set_ylabel("water (V, higher = fuller)")
    ax_w.set_xlabel("lab time")
    ax_t.legend(loc="upper right", fontsize=8)
    ax_w.legend(loc="upper right", fontsize=8)
    fig.autofmt_xdate()
    fig.tight_layout()

    out_dir = folder / "plots"
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = ("_" + "-".join(f"{h:02d}" for h in hours)) if hours else ""
    out = out_dir / f"{day}{suffix}.png"
    fig.savefig(out, dpi=110)
    print(f"plot: {out}")
    if show:
        plt.show()
    plt.close(fig)
    return out


def main():
    p = argparse.ArgumentParser(description="Fetch and plot one day of HydraPurr data")
    p.add_argument("--day", default=time.strftime("%Y-%m-%d"))
    p.add_argument("--hours", type=int, nargs="*", help="only these hours (0-23)")
    p.add_argument("--folder", default=str(DEFAULT_DEST))
    p.add_argument("--url", default=DEFAULT_URL)
    p.add_argument("--no-fetch", action="store_true", help="plot what is already here")
    p.add_argument("--no-raw", action="store_true", help="events only: no raw fetch or plot")
    p.add_argument("--show", action="store_true", help="also open a window")
    a = p.parse_args()
    folder = Path(a.folder)
    if not a.no_fetch:
        fetch(folder, a.url, include_raw=not a.no_raw, raw_days=board_days_for(a.day))
    plot_day(folder, a.day, a.hours or None, use_raw=not a.no_raw, show=a.show)


if __name__ == "__main__":
    main()
