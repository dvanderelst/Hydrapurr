from adafruit_other import adafruit_ssd1306
from adafruit_other import adafruit_framebuf
from components.MyI2C import common_i2c
import board
import busio


class MyOLED:
    """
    OLED helper with line-mode text.
    All configuration is hardcoded in __init__ (no args).
    Draws directly via self.oled.* (no separate framebuffer wrapper).
    """

    def __init__(self):
        # ---- hardcoded config you can tweak here ----
        self.width  = 128
        self.height = 64

        # text defaults
        self.default_scale       = 2      # used by write(x,y)
        self.line_scale          = 2      # used by write_line()
        self.line_align          = "left" # 'left' | 'center' | 'right'
        self.line_clear_on_write = True
        self.auto_show           = True
        self.clear_on_write      = True   # write(x,y) clears entire screen first
        i2c = common_i2c
        # NOTE: use the driver directly; it already provides .fill, .pixel, .text, .show
        self.oled = adafruit_ssd1306.SSD1306_I2C(self.width, self.height, i2c)

        # Reusable 8×8 temp framebuffer for glyphs (MVLSB => 8 bytes)
        self._tmp_buf = bytearray(8)
        self._tmp_fb  = adafruit_framebuf.FrameBuffer(self._tmp_buf, 8, 8, adafruit_framebuf.MVLSB)

        # sanity: clear once
        self.oled.fill(0)
        self.oled.show()

    # ---------- basics ----------
    def set_rotation(self, value: int):
        """0/1 rotate; flips display if supported by driver."""
        self.oled.rotate(value)

    def show(self):
        self.oled.show()

    def clear(self, show=None):
        """Clear entire screen and optionally flush."""
        self.oled.fill(0)
        if (self.auto_show if show is None else show):
            self.oled.show()

    def clear_screen(self):
        """Convenience: clear + always flush."""
        self.oled.fill(0)
        self.oled.show()

    # ---------- metrics ----------
    def _char_size(self, scale: int):
        return 8 * scale, 8 * scale  # (cw, ch)

    def num_lines(self):
        """How many text lines fit using current line_scale."""
        _, ch = self._char_size(self.line_scale)
        return max(1, self.height // ch)

    # ---------- helpers to normalize input ----------
    def _to_text(self, s):
        if isinstance(s, str):
            return s
        if isinstance(s, (bytes, bytearray)):
            try:
                return s.decode("ascii")
            except Exception:
                return s.decode("utf-8", "ignore")
        return str(s)

    def _char_from(self, ch):
        if isinstance(ch, str):
            return ch[:1] if ch else " "
        if isinstance(ch, int):
            return chr(ch & 0x7F)
        s = str(ch)
        return s[:1] if s else " "

    # ---------- line mode ----------
    def clear_line(self, line: int, show=None):
        cw, ch = self._char_size(self.line_scale)
        rows = self.num_lines()
        if not (0 <= line < rows):
            return False
        y = line * ch
        self.oled.fill_rect(0, y, self.width, ch, 0)
        if (self.auto_show if show is None else show):
            self.oled.show()
        return True

    def clear_lines(self, start_line: int, count: int, show=None):
        cw, ch = self._char_size(self.line_scale)
        rows = self.num_lines()
        if count <= 0 or start_line >= rows:
            return False
        start_line = max(0, start_line)
        end_line = min(rows, start_line + count)
        y = start_line * ch
        h = (end_line - start_line) * ch
        self.oled.fill_rect(0, y, self.width, h, 0)
        if (self.auto_show if show is None else show):
            self.oled.show()
        return True

    def write_line(self, line: int, text):
        """Write text on a logical line using instance defaults."""
        scale = self.line_scale
        cw, ch = self._char_size(scale)
        rows = self.num_lines()
        if not (0 <= line < rows):
            return False

        y = line * ch
        if self.line_clear_on_write:
            self.oled.fill_rect(0, y, self.width, ch, 0)

        text = self._to_text(text)
        text_px = len(text) * cw

        if self.line_align == "right":
            x = max(0, self.width - text_px)
        elif self.line_align == "center":
            x = max(0, (self.width - text_px) // 2)
        else:
            x = 0

        max_chars = max(0, (self.width - x) // cw)
        for i in range(min(len(text), max_chars)):
            ch1 = self._char_from(text[i])
            self._draw_glyph(ch1, x + i * cw, y, scale)

        if self.auto_show:
            self.oled.show()
        return True

    # ---------- pixel-positioned write ----------
    def write(self, text, x: int, y: int):
        """Draw text at (x,y) using default_scale. Clears full screen first if clear_on_write."""
        if self.clear_on_write:
            self.oled.fill(0)

        text = self._to_text(text)
        scale = self.default_scale
        cw, ch = self._char_size(scale)
        if y + ch > self.height:
            return False

        max_chars = max(0, (self.width - x) // cw)
        for i in range(min(len(text), max_chars)):
            ch1 = self._char_from(text[i])
            self._draw_glyph(ch1, x + i * cw, y, scale)

        if self.auto_show:
            self.oled.show()
        return True

    # ---------- glyph rendering ----------
    def _draw_glyph(self, char, x, y, scale):
        # render glyph into 8x8 temp fb
        self._tmp_fb.fill(0)
        self._tmp_fb.text(char, 0, 0, 1)

        # scale and blit into the OLED directly
        for i in range(8):
            for j in range(8):
                if self._tmp_fb.pixel(i, j):
                    for dx in range(scale):
                        for dy in range(scale):
                            xx = x + i * scale + dx
                            yy = y + j * scale + dy
                            if 0 <= xx < self.width and 0 <= yy < self.height:
                                self.oled.pixel(xx, yy, 1)
