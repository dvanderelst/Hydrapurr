import numpy as np
import pandas as pd

# This code filters double 0s (and 1s) in the lick state
# This is needed as lick/bout changes are also in the record
# These also have state = 0, but come after the lick event is over.

def filter_lick_events(contents):
    licks = contents.licks
    line_count = licks.shape[0]
    retained_lines = []
    previous_state = 0
    for line_nr in range(0, line_count):
        current_line = licks.iloc[line_nr, :]
        current_state = int(current_line['state'])
        if previous_state == 0 and current_state == 1:
            retained_lines.append(current_line)
        if previous_state == 1 and current_state == 0:
            retained_lines.append(current_line)
        previous_state = current_state * 1

    retained_lines = pd.DataFrame(retained_lines)
    print('Lick events filtered:')
    print('Original Lines:', line_count)
    print('Retained Lines:', retained_lines.shape[0])
    print("-" * 55)
    return retained_lines

def process_licks(contents, group_gap_ms=2 * 60 * 1000, min_group_size=1):
    lick_events = filter_lick_events(contents)
    line_count = lick_events.shape[0]
    previous_state = 0
    count = 0
    onset_time = None
    previous_water = None
    last_offset_time = None
    group = -1
    results = []
    for line_nr in range(0, line_count):
        current_line = lick_events.iloc[line_nr, :]
        current_state = int(current_line['state'])
        if previous_state == 0 and current_state == 1:
            print('Lick started')
            onset_time = current_line['time']
            previous_water = current_line['water']
        if previous_state == 1 and current_state == 0:
            offset_time = current_line['time']
            current_water = current_line['water']
            duration = offset_time - onset_time
            water_delta = current_water - previous_water
            duration = duration.total_seconds() * 1000
            if last_offset_time is None:
                group += 1
            else:
                gap_ms = (offset_time - last_offset_time).total_seconds() * 1000
                if gap_ms > group_gap_ms:
                    group += 1
            results.append([count, offset_time, duration, current_water, water_delta, group])
            last_offset_time = offset_time
            count = count + 1
            print(line_nr, 'Lick ended', duration)
        previous_state = current_state
    results_df = pd.DataFrame(
        results,
        columns=['index', 'time', 'duration', 'water', 'water_delta', 'group'],
    )
    if min_group_size > 1 and not results_df.empty:
        group_counts = results_df["group"].value_counts()
        small_groups = group_counts[group_counts < min_group_size].index
        results_df.loc[results_df["group"].isin(small_groups), "group"] = np.nan
        kept_groups = sorted(results_df["group"].dropna().unique())
        group_map = {group_id: idx for idx, group_id in enumerate(kept_groups)}
        results_df.loc[results_df["group"].notna(), "group"] = (
            results_df.loc[results_df["group"].notna(), "group"].map(group_map)
        )
    results_df["group_index"] = np.nan
    if not results_df.empty:
        grouped_mask = results_df["group"].notna()
        results_df.loc[grouped_mask, "group_index"] = (
            results_df.loc[grouped_mask]
            .groupby("group")
            .cumcount()
        )
    summary_rows = []
    if not results_df.empty:
        grouped = results_df.dropna(subset=["group"]).copy()
        if not grouped.empty:
            grouped["group"] = grouped["group"].astype(int)
            for group_id, group_df in grouped.groupby("group"):
                start_time = group_df["time"].iloc[0]
                end_time = group_df["time"].iloc[-1]
                duration_ms = (end_time - start_time).total_seconds() * 1000
                start_water = group_df["water"].iloc[0]
                end_water = group_df["water"].iloc[-1]
                summary_rows.append(
                    {
                        "group": group_id,
                        "duration": duration_ms,
                        "n": int(group_df.shape[0]),
                        "water_delta": end_water - start_water,
                        "water_extent": group_df["water"].max() - group_df["water"].min(),
                    }
                )
    summary_df = pd.DataFrame(
        summary_rows,
        columns=["group", "duration", "n", "water_delta", "water_extent"],
    )
    return results_df, summary_df
