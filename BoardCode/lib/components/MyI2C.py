import busio
import board
import time

def _init_i2c(retries=5, delay=0.1):
    for attempt in range(retries):
        try:
            return busio.I2C(board.SCL, board.SDA)
        except Exception:
            if attempt < retries - 1:
                time.sleep(delay)
    raise OSError("[MyI2C] I2C bus init failed after retries")

common_i2c = _init_i2c()
