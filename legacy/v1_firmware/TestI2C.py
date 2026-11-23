import board
import busio
i2c = board.I2C()  # Uses the default I2C pins for your board
while not i2c.try_lock():
    pass
try:
    devices = i2c.scan()
    print("I2C devices found:", [hex(device) for device in devices])
finally:
    i2c.unlock()
