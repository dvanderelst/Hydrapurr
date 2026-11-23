import analogio
import board
import time

class MyADC:
    def __init__(self, channel):
        """Initialize the ADC pin based on the channel number."""
        if channel == 0: 
            pin = board.A0
        elif channel == 1: 
            pin = board.A1
        elif channel == 2: 
            pin = board.A2
        elif channel == 3: 
            pin = board.A3
        else:
            raise ValueError("Invalid channel. Choose between 0, 1, 2, or 3.")

        self.adc = analogio.AnalogIn(pin)

    def read(self):
        """Read the voltage from the ADC pin and convert it to a voltage value."""
        raw_value = self.adc.value
        voltage = (raw_value / 65535) * 3.3  # Assuming a 3.3V reference voltage
        return voltage

    def raw(self):
        """Read the raw ADC value (0-65535)."""
        return self.adc.value

    def mean(self, num_samples=100, sample_delay=0.001):
        """
        Read multiple samples from the ADC and return the mean voltage.
        """
        total_voltage = 0
        for _ in range(num_samples):
            total_voltage += self.read()
            time.sleep(sample_delay)

        return total_voltage / num_samples

    def deinit(self):
        """Deinitialize the ADC pin to free up resources."""
        self.adc.deinit()
