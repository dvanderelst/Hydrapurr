from library import utils
from library import data_reader
from analysis.BoutAnalyzer import BoutAnalyzer
from matplotlib import pyplot as plt
import plotly.graph_objects as go
import os
import sys

# Load board settings so offline analysis stays in sync with board config.
board_code_path = os.path.join(os.path.dirname(__file__), "..", "BoardCode")
sys.path.insert(0, board_code_path)
from lib import Settings

# Show available data folders
data_reader.print_data_folders_table()

# Select data folder (change index as needed)
data_folder_index = 1
contents = data_reader.read_data_folder(data_folder_index)
licks = contents.licks
system_log = contents.system_log

print(f"\nAnalyzing data folder: {contents.name}")
print(f"Loaded {len(licks)} lick records")

# NEW METHOD: Using BoutAnalyzer with 12-second bout gap (12000ms)
print("\n--- BOUT ANALYSIS (BoutAnalyzer) ---")
analyzer = BoutAnalyzer(settings=Settings)
group_gap_ms = Settings.max_bout_gap_ms
min_group_size = Settings.min_licks_per_bout
min_water_delta = Settings.min_water_delta_per_bout
processed, summary = analyzer.analyze_dataframe(
    licks, 
    group_gap_ms=group_gap_ms,
    min_group_size=min_group_size,
    min_water_delta=min_water_delta
)
print(f"Analysis: {len(processed)} events, {len(summary)} bouts")

# Add bout information summary
if not summary.empty:
    print(f"\n📊 Bout Analysis Summary:")
    print(f"   Total bouts: {len(summary)}")
    print(f"   Average duration: {summary['duration'].mean():.1f}ms")
    print(f"   Average licks per bout: {summary['n'].mean():.1f}")
    print(f"   Average water change: {summary['water_delta'].mean():.3f}")
    print(f"\nParameters used:")
    print(f"   Bout gap: {group_gap_ms}ms ({group_gap_ms / 1000:.0f} seconds)")
    print(f"   Min licks per bout: {min_group_size}")


time = processed['time']
water = processed['water']
duration = processed['duration']
water_delta = processed['water_delta']
group = processed['group']
group_index = processed['group_index']

processed["group_str"] = (
    processed["group"].astype("Int64").astype(str).replace("<NA>", "NaN")
)

line_trace = go.Scatter(
    x=processed["time"],
    y=processed["water"],
    mode="lines",
    name="Water Level",
    line={"color": "rgba(0,0,0,0.3)"},
    showlegend=False,
)

# Create scatter plot for lick events
scatter_trace = go.Scatter(
    x=processed["time"],
    y=processed["water"],
    mode="markers",
    name="Lick Events",
    marker={"color": "red", "size": 8},
    showlegend=True,
)

# Create bout extent rectangles (show duration of each bout)
bout_rectangles = []
if not summary.empty and 'group' in processed.columns:
    for bout_id, bout_data in summary.iterrows():
        # Get all events in this bout
        bout_events = processed[processed['group'] == bout_id]
        if len(bout_events) > 0:
            bout_start = bout_events['time'].min()
            bout_end = bout_events['time'].max()
            
            # Create rectangle showing bout extent
            rectangle = go.Scatter(
                x=[bout_start, bout_end, bout_end, bout_start, bout_start],
                y=[1.5, 1.5, 2.5, 2.5, 1.5],  # Fixed y-range for visibility
                mode="lines",
                line={"color": "blue", "width": 2},
                fill="toself",
                fillcolor="rgba(0,0,255,0.1)",
                name=f"Bout {int(bout_id)}",
                showlegend=False,
                hoverinfo="text",
                text=f"Bout {int(bout_id)}: {len(bout_events)} licks, {bout_data['duration']:.0f}ms",
            )
            bout_rectangles.append(rectangle)

fig = go.Figure(line_trace)
fig.add_trace(scatter_trace)

# Add bout rectangles
for rect in bout_rectangles:
    fig.add_trace(rect)

# Add bout boundaries as vertical lines (simplified)
if not summary.empty:
    for bout_id, bout_data in summary.iterrows():
        bout_events = processed[processed['group'] == bout_id]
        if len(bout_events) > 0:
            bout_start = bout_events['time'].min()
            bout_end = bout_events['time'].max()
            
            # Add vertical lines at bout boundaries (without annotations to avoid timestamp issues)
            fig.add_vline(
                x=bout_start, 
                line_dash="dash", 
                line_color="blue",
                line_width=1
            )
            fig.add_vline(
                x=bout_end, 
                line_dash="dash", 
                line_color="blue",
                line_width=1
            )

fig.show(renderer='browser')

# Save the interactive plot as HTML
fig.write_html("lick_analysis_interactive.html")
print("Interactive plot saved as 'lick_analysis_interactive.html'")

#%%
plt.figure()
plt.scatter(summary["duration"], -summary["water_delta"], c = summary["group"], cmap='jet')
plt.colorbar()
plt.show()
