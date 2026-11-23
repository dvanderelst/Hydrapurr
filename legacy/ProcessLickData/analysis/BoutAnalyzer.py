"""
BoutAnalyzer.py - Offline lick data analysis

Each row in licks.dat is one detected lick with a pre-computed `duration_ms`.
A new bout starts wherever the `lick` column resets to 1; rows with `duration_ms`
outside the valid lick window are firmware bout-closure markers and are dropped.
"""

import numpy as np
import pandas as pd


class BoutAnalyzer:
    def __init__(self, settings):
        self.min_lick_ms = settings.min_lick_ms
        self.max_lick_ms = settings.max_lick_ms
        self.min_licks_per_bout = settings.min_licks_per_bout
        self.min_water_extent = getattr(settings, 'min_water_extent_per_bout', 0.0)

    def analyze_dataframe(self, df, min_group_size=None, min_water_extent=None):
        """Build (processed, summary) from logged licks.

        Args:
            df: DataFrame from licks.dat with columns including
                ['mono_ms', 'lick', 'water', 'duration_ms']
            min_group_size: override min_licks_per_bout for this call
            min_water_extent: override min_water_extent for this call

        Returns:
            (processed, summary) - per-lick events and per-bout statistics
        """
        if min_group_size is None:
            min_group_size = self.min_licks_per_bout
        if min_water_extent is None:
            min_water_extent = self.min_water_extent

        proc_cols = ['index', 'time', 'duration', 'water', 'water_delta', 'group', 'group_index']
        summ_cols = ['group', 'duration', 'n', 'water_delta', 'water_extent']

        valid = df[
            (df['duration_ms'] >= self.min_lick_ms) &
            (df['duration_ms'] <= self.max_lick_ms)
        ].reset_index(drop=True)

        starts = (valid['lick'] == 1)
        if not starts.any():
            return pd.DataFrame(columns=proc_cols), pd.DataFrame(columns=summ_cols)
        valid = valid.iloc[starts.idxmax():].reset_index(drop=True)

        group = (valid['lick'] == 1).cumsum() - 1
        water_delta = valid.groupby(group)['water'].diff().fillna(0.0)

        processed = pd.DataFrame({
            'index': range(len(valid)),
            'time': valid['time'].values,
            'duration': valid['duration_ms'].values,
            'water': valid['water'].values,
            'water_delta': water_delta.values,
            'group': group.astype(float).values,
        })

        counts = processed['group'].value_counts()
        too_small = counts[counts < min_group_size].index
        processed.loc[processed['group'].isin(too_small), 'group'] = np.nan

        if min_water_extent > 0:
            for gid, gdf in processed.dropna(subset=['group']).groupby('group'):
                if gdf['water'].max() - gdf['water'].min() <= min_water_extent:
                    processed.loc[processed['group'] == gid, 'group'] = np.nan

        kept = sorted(processed['group'].dropna().unique())
        renum = {g: i for i, g in enumerate(kept)}
        processed.loc[processed['group'].notna(), 'group'] = (
            processed.loc[processed['group'].notna(), 'group'].map(renum)
        )

        processed['group_index'] = np.nan
        mask = processed['group'].notna()
        processed.loc[mask, 'group_index'] = processed.loc[mask].groupby('group').cumcount()

        rows = []
        kept_df = processed.dropna(subset=['group']).copy()
        if not kept_df.empty:
            kept_df['group'] = kept_df['group'].astype(int)
            for gid, gdf in kept_df.groupby('group'):
                duration = (gdf['time'].iloc[-1] - gdf['time'].iloc[0]).total_seconds() * 1000
                rows.append({
                    'group': gid,
                    'duration': duration,
                    'n': int(len(gdf)),
                    'water_delta': gdf['water'].iloc[-1] - gdf['water'].iloc[0],
                    'water_extent': gdf['water'].max() - gdf['water'].min(),
                })
        summary = pd.DataFrame(rows, columns=summ_cols)
        return processed, summary


__all__ = ['BoutAnalyzer']
