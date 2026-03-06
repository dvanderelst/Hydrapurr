"""
BoutAnalyzer.py - Offline lick data analysis using BoutDetection algorithm

This module provides tools for analyzing logged lick data using the same
detection algorithm as the board, ensuring consistent results between
real-time and offline analysis.

Key Features:
- Analyze logged data using BoutDetection algorithm
- Compare results with existing utils.process_licks()
- Generate bout statistics and visualizations
- No hardware dependencies
"""

import os
import sys
import pandas as pd

# Add BoardCode to path to import BoutDetection
board_code_path = os.path.join(os.path.dirname(__file__), '..', '..', 'BoardCode')
sys.path.insert(0, board_code_path)

from lib.BoutDetection import BoutManager

class BoutAnalyzer:
    """
    Offline lick data analyzer using BoutDetection algorithm.
    
    This class provides methods to analyze logged lick data using the
    same algorithm as the board, ensuring consistent results.
    """
    
    def __init__(self, settings=None):
        """
        Initialize analyzer with board settings or custom parameters.
        
        Args:
            settings: Settings object with detection parameters (optional)
                     If None, uses default values
        """
        if settings:
            # Use board settings
            min_water_delta = getattr(settings, 'min_water_delta_per_bout', 0.1)
            self.bout_manager = BoutManager(
                min_lick_ms=settings.min_lick_ms,
                max_lick_ms=settings.max_lick_ms,
                min_licks_per_bout=settings.min_licks_per_bout,
                max_bout_gap_ms=settings.max_bout_gap_ms,
                min_water_delta=min_water_delta
            )
        else:
            # Use defaults
            self.bout_manager = BoutManager()
    
    def analyze_dataframe(self, df, group_gap_ms=None, min_group_size=None, min_water_delta=None):
        """
        Analyze a dataframe of lick data.
        
        Args:
            df: DataFrame with columns ['time', 'cat_name', 'state', 'water']
            group_gap_ms: Override max_bout_gap_ms for this analysis
            min_group_size: Override min_licks_per_bout for this analysis
            min_water_delta: Override min_water_delta for this analysis
            
        Returns:
            tuple: (events_df, summary_df)
                   events_df - individual lick events with bout assignments
                   summary_df - bout-level statistics
        """
        return self.bout_manager.process_dataframe(
            df, group_gap_ms=group_gap_ms, min_group_size=min_group_size, min_water_delta=min_water_delta
        )
    
    def analyze_data_folder(self, folder_path):
        """
        Analyze a complete data folder.
        
        Args:
            folder_path: Path to data folder containing licks.dat
            
        Returns:
            dict: {'events': events_df, 'summaries': summary_df, 'system_log': log_df}
        """
        from library.data_reader import read_data_folder
        
        contents = read_data_folder(folder_path)
        
        if contents.licks is not None and not contents.licks.empty:
            events, summaries = self.analyze_dataframe(contents.licks)
            return {
                'events': events,
                'summaries': summaries,
                'system_log': contents.system_log
            }
        return None
    
    def compare_with_existing(self, contents, group_gap_ms=None, min_group_size=None):
        """
        Compare results with existing utils.process_licks() function.
        
        Args:
            contents: DataFolderContents object from data_reader
            group_gap_ms: group_gap_ms parameter for comparison
            min_group_size: min_group_size parameter for comparison
            
        Returns:
            dict: Comparison results including both approaches' outputs
        """
        from library.utils import process_licks
        
        # Process with our algorithm
        our_events, our_summaries = self.analyze_dataframe(
            contents.licks, 
            group_gap_ms=group_gap_ms, 
            min_group_size=min_group_size
        )
        
        # Process with existing algorithm
        their_events, their_summaries = process_licks(
            contents, 
            group_gap_ms=group_gap_ms, 
            min_group_size=min_group_size
        )
        
        return {
            'our_results': (our_events, our_summaries),
            'their_results': (their_events, their_summaries),
            'events_match': len(our_events) == len(their_events),
            'bouts_match': len(our_summaries) == len(their_summaries),
            'our_event_count': len(our_events),
            'their_event_count': len(their_events),
            'our_bout_count': len(our_summaries),
            'their_bout_count': len(their_summaries)
        }
    
    def get_last_bout_summary(self, cat_name=None):
        """Get last bout summary (proxy to bout_manager)"""
        return self.bout_manager.get_last_bout_summary(cat_name)
    
    def get_current_bout_info(self, cat_name=None):
        """Get current bout info (proxy to bout_manager)"""
        return self.bout_manager.get_current_bout_info(cat_name)

# Create analysis package
__all__ = ['BoutAnalyzer']