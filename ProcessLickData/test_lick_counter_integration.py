#!/usr/bin/env python3
"""
Integration test for enhanced LickCounter - tests batch processing only
"""

import sys
import os

# Test the batch processing functionality by importing just what we need
try:
    import pandas as pd
    import numpy as np
    from library import data_reader, utils
    print("✓ Successfully imported pandas and local libraries")
    
    # Show available data
    print("\nAvailable data folders:")
    data_reader.print_data_folders_table()
    
    # Load some data
    contents = data_reader.read_data_folder(0)  # Use first available folder
    
    if contents.licks is None or contents.licks.empty:
        print("✗ No lick data available")
        sys.exit(1)
    
    print(f"✓ Loaded {len(contents.licks)} lick records")
    print("\nData preview:")
    print(contents.licks.head())
    
    # Test existing process_licks function
    print("\n--- Testing existing process_licks function ---")
    existing_processed, existing_summary = utils.process_licks(contents)
    print(f"✓ Existing function processed {len(existing_processed)} events")
    print(f"✓ Created {len(existing_summary)} bout summaries")
    
    if not existing_summary.empty:
        print("\nExisting bout summary sample:")
        print(existing_summary.head())
    
    # Now test importing the enhanced LickCounter
    print("\n--- Testing enhanced LickCounter import ---")
    
    # Add BoardCode to path
    board_code_path = os.path.join(os.path.dirname(__file__), '..', 'BoardCode')
    sys.path.insert(0, board_code_path)
    
    # Try to import just the LickCounter class
    try:
        # Create a minimal Settings module for testing
        class MockSettings:
            min_lick_ms = 50
            max_lick_ms = 150
            min_licks_per_bout = 3
            max_bout_gap_ms = 1000
            lick_data_filename = "test.dat"
            data_log_max_lines = 1000
        
        # Mock the components that aren't available
        class MockMyStore:
            def __init__(self, filename, auto_header=None, max_lines=None):
                self.filename = filename
                self.data = []
                if auto_header:
                    self.header = auto_header
                self.max_lines = max_lines
            
            def add(self, data):
                self.data.append(data)
                if self.max_lines and len(self.data) > self.max_lines:
                    self.data = self.data[-self.max_lines:]
            
            def empty(self):
                self.data = []
            
            def read(self):
                return self.data
            
            def header(self, header, label=None):
                self.header = header
        
        class MockMyADC:
            def __init__(self, channel):
                self.channel = channel
            
            def mean(self, num_samples=10):
                return 2.5  # Mock water level
        
        # Inject mocks
        sys.modules['components'] = type(sys)('components')
        sys.modules['components.MyStore'] = type(sys)('components.MyStore')
        sys.modules['components.MyStore'].MyStore = MockMyStore
        sys.modules['components.MyADC'] = type(sys)('components.MyADC')
        sys.modules['components.MyADC'].MyADC = MockMyADC
        sys.modules['Settings'] = MockSettings
        
        # Now import LickCounter
        from lib.LickCounter import LickCounter
        print("✓ Successfully imported enhanced LickCounter")
        
        # Test instantiation
        counter = LickCounter(cat_names=['test_cat'])
        print("✓ LickCounter instantiated successfully")
        
        # Test batch processing
        print("\n--- Testing enhanced LickCounter batch processing ---")
        enhanced_processed, enhanced_summary = counter.process_dataframe(contents.licks)
        print(f"✓ Enhanced LickCounter processed {len(enhanced_processed)} events")
        print(f"✓ Created {len(enhanced_summary)} bout summaries")
        
        if not enhanced_summary.empty:
            print("\nEnhanced bout summary sample:")
            print(enhanced_summary.head())
        
        # Compare results
        print("\n--- Comparison ---")
        print(f"Existing: {len(existing_processed)} events, {len(existing_summary)} bouts")
        print(f"Enhanced: {len(enhanced_processed)} events, {len(enhanced_summary)} bouts")
        
        if len(existing_summary) == len(enhanced_summary):
            print("✓ Same number of bouts detected")
        else:
            print(f"⚠ Different bout counts")
            
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n✓ Integration test completed!")
    
except ImportError as e:
    print(f"✗ Import failed: {e}")
    sys.exit(1)
except Exception as e:
    print(f"✗ Test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)