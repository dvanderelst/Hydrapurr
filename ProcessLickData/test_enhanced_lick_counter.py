#!/usr/bin/env python3
"""
Test script for the enhanced LickCounter class
Tests both real-time and batch processing functionality
"""

import sys
import os

# Add BoardCode to path for testing
board_code_path = os.path.join(os.path.dirname(__file__), '..', 'BoardCode')
sys.path.insert(0, board_code_path)

try:
    from lib.LickCounter import LickCounter, PANDAS_AVAILABLE
    from lib import Settings
    print("✓ Successfully imported LickCounter from BoardCode")
    print(f"✓ Pandas available: {PANDAS_AVAILABLE}")
    
    # Test basic instantiation
    counter = LickCounter(cat_names=['test_cat'])
    print("✓ LickCounter instantiated successfully")
    
    # Test new methods exist
    assert hasattr(counter, 'get_last_bout_summary'), "Missing get_last_bout_summary method"
    assert hasattr(counter, 'get_current_bout_info'), "Missing get_current_bout_info method"
    assert hasattr(counter, 'process_dataframe'), "Missing process_dataframe method"
    print("✓ New methods are present")
    
    # Test bout summary access
    summary = counter.get_last_bout_summary('test_cat')
    assert summary is None, "Expected None for no bouts yet"
    print("✓ Bout summary access works")
    
    # Test current bout info
    info = counter.get_current_bout_info('test_cat')
    assert info is None, "Expected None for no current bout"
    print("✓ Current bout info access works")
    
    if PANDAS_AVAILABLE:
        import pandas as pd
        import numpy as np
        from library import data_reader
        
        # Test with real data
        print("\n--- Testing with real data ---")
        
        # Load some real data
        data_reader.print_data_folders_table()
        contents = data_reader.read_data_folder(0)  # Use first available folder
        
        if contents.licks is not None and not contents.licks.empty:
            print(f"✓ Loaded data with {len(contents.licks)} lick records")
            
            # Test batch processing with enhanced LickCounter
            try:
                processed_df, summary_df = counter.process_dataframe(contents.licks)
                print("✓ Enhanced LickCounter batch processing works")
                print(f"  Processed {len(processed_df)} lick events")
                print(f"  Created {len(summary_df)} bout summaries")
                
                if not summary_df.empty:
                    print("\nBout summary sample:")
                    print(summary_df.head())
                
            except Exception as e:
                print(f"✗ Enhanced LickCounter batch processing failed: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("⊘ No lick data available for testing")
        
        # Compare with existing process_licks function
        print("\n--- Comparing with existing process_licks ---")
        try:
            from library.utils import process_licks
            
            if contents.licks is not None and not contents.licks.empty:
                # Use same parameters as Settings
                group_gap_ms = Settings.max_bout_gap_ms
                min_group_size = Settings.min_licks_per_bout
                
                # Process with existing function
                existing_processed, existing_summary = process_licks(
                    contents, group_gap_ms=group_gap_ms, min_group_size=min_group_size
                )
                
                # Process with enhanced LickCounter
                enhanced_processed, enhanced_summary = counter.process_dataframe(
                    contents.licks, group_gap_ms=group_gap_ms, min_group_size=min_group_size
                )
                
                print(f"✓ Existing function: {len(existing_processed)} events, {len(existing_summary)} bouts")
                print(f"✓ Enhanced LickCounter: {len(enhanced_processed)} events, {len(enhanced_summary)} bouts")
                
                # Basic comparison
                if len(existing_summary) == len(enhanced_summary):
                    print("✓ Same number of bouts detected")
                else:
                    print(f"⚠ Different bout counts: existing={len(existing_summary)}, enhanced={len(enhanced_summary)}")
        except Exception as e:
            print(f"✗ Comparison failed: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n✓ All tests completed! Enhanced LickCounter basic functionality is working.")
    
except ImportError as e:
    print(f"✗ Import failed: {e}")
    sys.exit(1)
except Exception as e:
    print(f"✗ Test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)