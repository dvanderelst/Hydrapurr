import digitalio
import board

class MyDigital:
    def __init__(self, pin, direction="input", pull=None):
        """
        Initialize the pin as either input or output.
        
        Args:
            pin (Pin): The pin object (e.g., board.D5).
            direction (str): "input" or "output". Default is "input".
            pull (str): For input pins, "up" or "down" for pull-up or pull-down resistors. Default is None.
        """
        self.pin = digitalio.DigitalInOut(pin)
        if direction == "output":
            self.pin.direction = digitalio.Direction.OUTPUT
        elif direction == "input":
            self.pin.direction = digitalio.Direction.INPUT
            if pull == "up":
                self.pin.pull = digitalio.Pull.UP
            elif pull == "down":
                self.pin.pull = digitalio.Pull.DOWN
            else:
                self.pin.pull = None

    def read(self):
        """
        Read the state of the pin. Only valid if the pin is set as input.
        
        Returns:
            bool: True if the pin is HIGH, False if LOW.
        """
        if self.pin.direction != digitalio.Direction.INPUT:
            raise ValueError("Pin is not configured as input.")
        return self.pin.value

    def write(self, value):
        """
        Set the state of the pin. Only valid if the pin is set as output.
        
        Args:
            value (bool): True to set the pin HIGH, False to set it LOW.
        """
        if self.pin.direction != digitalio.Direction.OUTPUT:
            raise ValueError("Pin is not configured as output.")
        self.pin.value = value

    def toggle(self):
        """
        Toggle the state of the pin. Only valid if the pin is set as output.
        """
        if self.pin.direction != digitalio.Direction.OUTPUT:
            raise ValueError("Pin is not configured as output.")
        self.pin.value = not self.pin.value

    def cleanup(self):
        """
        Deinitialize the pin to free up resources.
        """
        self.pin.deinit()
