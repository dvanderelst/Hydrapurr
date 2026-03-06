import board
import busio
import sdcardio
import storage
import os

spi = board.SPI()
cs = board.D10  # Use the pin you connected to CS

try:
    # Create the /sd directory if it doesn't exist
    try:
        os.mkdir("/sd")
    except OSError:
        pass  # Directory already exists

    sdcard = sdcardio.SDCard(spi, cs)
    print("SD card detected and initialized successfully!")
    vfs = storage.VfsFat(sdcard)
    storage.mount(vfs, "/sd")
    print("SD card mounted as /sd")

    # Test writing a file
    with open("/sd/test.txt", "w") as f:
        f.write("Hello, SD card!\n")
    print("File written to /sd/test.txt")

except Exception as e:
    print("Error:", e)
