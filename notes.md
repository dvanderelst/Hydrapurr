# HydraPurr

## Organization Notes

+ The BoardCode folder can be kept in sync with the board contents using my very own `DeviceSync` script: `/home/dieter/Dropbox/PythonRepos/DeviceSync`
+ The `BoardCode` folder is an independent Pycharm Project to avoid issues when using refactoring. Other code (code not running on the board) in this folder, should be put inside a new folder, as a different PyCharm project, for the same reason. For example:

````
HydraPurr
|___ BoardCode = a Pycharm project
|___ FitWaterFunction = a Pycharm project
|___ Other_Code_Part = a Pycharm Project

````

+ Thursday, 14. August 2025 09:43AM. The code for the (older) Raspberry Pi version of the HydraPurr is still available as a GitHub repository:
`https://github.com/habit-tech/Rpi_lickometer`. However, I have  added the local code to this HydraPurr code by way of archiving it. It is unlikely we will develop the Raspberry Pi version further at this point but the Raspberry Pi code might be a good reference for developing some things on the Rp2040.

+ Thursday, 14. August 2025 09:52AM I found a Pycharm project `ProcessLickData`, which I have now added to this repo.

## The `lib` folder

When CircuitPython starts, it automatically adds these locations to `sys.path`:

+ The root of the CIRCUITPY drive (/)
+ The lib/ folder at the root (/lib)

This means any .py file or package folder in lib/ can be imported without saying `lib.` in the path. Example:

```
/lib/adafruit_pcf8523/__init__.py
```

can be imported simply with:

```
import adafruit_pcf8523
```

This is why all official CircuitPython library examples look like:

```
import neopixel
import adafruit_ssd1306
```

### `Lib` should not be a package**

CircuitPython’s import magic depends on lib/ being just a directory of modules/packages, not a package itself.
If you add a `lib/__init__.py` and start doing:

```
from lib import adafruit_pcf8523
```

then:

+ On CircuitPython, this still works, but it’s non-standard and goes against every example/tutorial.
+ On desktop Python, lib could clash with system directories (Linux often has /lib for OS libraries).

If you ever zip/share your code, it will confuse people expecting the normal CircuitPython layout.

### Best practice

Keep lib/ as a plain folder, not a package.

Put your code in a subfolder (e.g., `lib/components/`) and make that a package (`__init__.py inside`).

Always import as if `lib/` didn’t exist:

```
from components import myADC
import adafruit_pcf8523
```

If testing on desktop Python (e.g., PyCharm), temporarily add lib/ to `sys.path` so these imports work. In PyCharm, if you mark lib/ as a Sources Root, it will behave like CircuitPython’s auto-path feature.


+ Right-click on your lib folder in the Project view.
+ Select "Mark Directory as → Sources Root".
+ PyCharm will turn the folder icon blue (by default).

Now PyCharm will treat everything inside lib/ as top-level modules.
You can write:

```
import adafruit_pcf8523
from components import myADC
```

and PyCharm will resolve the imports without any sys.path.append tricks.

This keeps the import style identical between the RP2040 board and local development. No sys.path modifications needed in your code.

IntelliSense/autocomplete will also work for everything in lib/.
