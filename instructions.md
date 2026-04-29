# Code structure

This repository contains the code for a circuitpython-based devices for monitoring water consumption by cats by detecting licks. The code that runs on the microcontroller of this device is in the folder `BoardCode`. The folder `BoardPycharm` is a folder containing the configuration files for working with this code in `Pycharm`. 

**On circuitpython boards, the `lib` folder is added to the path automatically**

The folder `ProcessLickData` contains some code for processing data collected with the device.

The folder `BTDownloader` contains a prototype a BT-based method for downloading the data from the device.

# Important points

+ Since the code in `BoardCode` is meant to run on a Adafruit Microcontroller using CircuitPython, you can not run the code directly. Moreover, the does not only depend on a CircuitPython interpreter, it also assume certain hardward to be availble.

+ The code in the `ProcessLickData` can be run using the `.venv` in that folder.

+ The lick processing logic is kept in sync between the board code (`BoardCode`) and the data processing code (`ProcessLickData`) to ensure consistent behavior. Real-time detection on the device lives in `BoardCode/lib/BoutDetection.py`; offline analysis of the resulting `licks.dat` lives in `ProcessLickData/analysis/BoutAnalyzer.py`. See `BoardCode/goals.md` for an architecture overview and `ProcessLickData/datadescription.md` for the on-disk data format.

**After reading these instructions, pause and ask for input from the user. Do not start coding without further instructions.**