# __init__.py
# This file turns the "components" folder into a Python package
# and controls what is imported when someone does:
#   from components import myADC, myOLED
# Instead of importing each file separately.

# Import your classes from the individual files in this folder
# This the **classes** available them available when someone imports the package.
from .MyADC import MyADC         # from myADC.py import class myADC
from .MyBT import MyBT           # from myBT.py import class myBT
from .MyDigital import MyDigital # from myDigital.py import class myDigital
from .MyOLED import MyOLED       # from myOLED.py import class myOLED
from .MyPixel import MyPixel     # from myPixel.py import class myPixel
from .MyRTC import MyRTC         # from myRTC.py import class myRTC
from .MyStore import MyStore     # from myStore.py import class myStore

# __all__ defines what gets imported when someone does:
#   from components import *
# This prevents extra things (like helper functions) from leaking out.
__all__ = ["MyADC", "MyBT", "MyDigital", "MyOLED", "MyPixel", "MyRTC", "MyStore"]