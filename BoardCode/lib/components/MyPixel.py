import board
from adafruit_other import neopixel
import math, time

# Preset colors with more comprehensive set
PRESET_COLORS = {
    'red': (255, 0, 0),
    'green': (0, 255, 0),
    'blue': (0, 0, 255),
    'yellow': (255, 255, 0),
    'cyan': (0, 255, 255),
    'magenta': (255, 0, 255),
    'white': (255, 255, 255),
    'off': (0, 0, 0),
    'purple': (128, 0, 128),
    'orange': (255, 165, 0),
    'pink': (255, 192, 203),
    'lime': (0, 255, 0),
    'teal': (0, 128, 128)
}

class MyPixel:
    def __init__(self, pixel_pin=board.NEOPIXEL, num_pixels=1, brightness=0.1, auto_write=True):
        """
        Initialize the NeoPixel controller.
        
        :param pixel_pin: Pin for the NeoPixel (default: board.NEOPIXEL)
        :param num_pixels: Number of pixels (default: 1)
        :param brightness: Brightness level (0.0 to 1.0, default: 0.1)
        :param auto_write: Automatically write changes (default: True)
        """
        self.pixels = neopixel.NeoPixel(
            pixel_pin, 
            num_pixels, 
            brightness=brightness, 
            auto_write=auto_write
        )
        self._brightness = brightness
        self.toggle_colors = []
        self.color_index = 0

    def cycle(self, brightness=None):
        nr_colors = len(self.toggle_colors)
        if nr_colors == 0: return
        color = self.toggle_colors[self.color_index]
        self.set_color(color, brightness)
        self.color_index = self.color_index + 1
        if self.color_index == nr_colors: self.color_index = 0

    def heartbeat(self, base_color="blue"):

        min_brightness = 0.1
        max_brightness = 0.8
        heartbeat_cycle_ms = 3000

        t = time.monotonic() * 1000.0
        phase = (t % heartbeat_cycle_ms) / heartbeat_cycle_ms
        wave = 0.5 * (1 - math.cos(2 * math.pi * phase))  # 0..1
        brightness = min_brightness + (max_brightness - min_brightness) * wave
        self.set_color(base_color, brightness)

    def set_color(self, color_name, brightness=None):
        """
        Set the NeoPixel to a preset color by name with optional brightness.
        
        :param color_name: Name of the preset color
        :param brightness: Optional brightness level (0.0 to 1.0)
        :raises ValueError: If color name is not in preset colors or brightness is out of range
        """
        if color_name.lower() not in PRESET_COLORS:
            raise ValueError(f"Color '{color_name}' not found. Available presets: {list(PRESET_COLORS.keys())}")
        
        # Get the color tuple
        color = PRESET_COLORS[color_name.lower()]
        
        # Adjust brightness if specified
        if brightness is not None:
            if not 0 <= brightness <= 1.0:
                raise ValueError("Brightness must be between 0.0 and 1.0")
            
            # Scale the color based on brightness
            color = tuple(int(c * brightness) for c in color)
            
            # Update the pixel's overall brightness
            self.pixels.brightness = brightness
        
        # Set the color
        self.pixels.fill(color)
        
    def set_custom_color(self, r, g, b):
        """
        Set the NeoPixel to a custom RGB color.
        
        :param r: Red value (0-255)
        :param g: Green value (0-255)
        :param b: Blue value (0-255)
        :raises ValueError: If color values are out of range
        """
        # Validate color values
        if not all(0 <= val <= 255 for val in (r, g, b)):
            raise ValueError("RGB values must be between 0 and 255")
        
        self.pixels.fill((r, g, b))

    def turn_off(self):
        """Turn off the NeoPixel."""
        self.pixels.fill(PRESET_COLORS['off'])

    def set_brightness(self, brightness):
        """
        Set the brightness of the NeoPixel.
        
        :param brightness: Brightness level (0.0 to 1.0)
        :raises ValueError: If brightness is out of range
        """
        if not 0 <= brightness <= 1.0:
            raise ValueError("Brightness must be between 0.0 and 1.0")
        
        self._brightness = brightness
        self.pixels.brightness = brightness

    def blink(self, color_name, times=3, duration=0.5):
        """
        Make the NeoPixel blink a specified number of times.
        
        :param color_name: Name of the preset color to blink
        :param times: Number of blinks (default: 3)
        :param duration: Duration of each blink in seconds (default: 0.5)
        """
        import time
        
        for _ in range(times):
            self.set_color(color_name)
            time.sleep(duration)
            self.turn_off()
            time.sleep(duration)

    def rainbow_cycle(self, cycles=5, delay=0.05):
        """
        Create a rainbow cycle effect.
        
        :param cycles: Number of rainbow cycles (default: 5)
        :param delay: Delay between color changes (default: 0.05)
        """
        import time
        
        for _ in range(cycles):
            for j in range(255):
                self.pixels.fill(self._wheel(j & 255))
                time.sleep(delay)
        
        self.turn_off()

    def _wheel(self, pos):
        """
        Generate color wheel for rainbow effect.
        
        :param pos: Position on the color wheel (0-255)
        :return: RGB color tuple
        """
        if pos < 85:
            return (pos * 3, 255 - pos * 3, 0)
        elif pos < 170:
            pos -= 85
            return (255 - pos * 3, 0, pos * 3)
        else:
            pos -= 170
            return (0, pos * 3, 255 - pos * 3)

    def __str__(self):
        """
        String representation of the NeoPixel controller.
        
        :return: Current color and brightness information
        """
        current_color = self.pixels[0]
        return f"NeoPixel: Color RGB{current_color}, Brightness: {self._brightness}"