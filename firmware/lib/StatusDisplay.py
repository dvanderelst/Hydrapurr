"""
StatusDisplay.py - status screen on the Reverse TFT's built-in 240x135 display

Replaces BoardCode's SSD1306 OLED (MyOLED). Shows a few lines of text with
the built-in terminalio font, scaled 2x. Taking over the display hides the
serial console that CircuitPython normally shows on it; print() output still
goes to USB serial.

The display is in manual refresh. The caller hands over new texts with
set_line() (cheap, nothing is drawn) and calls refresh_all() about once a
second, which redraws the whole screen. Redrawing single lines (partial
refreshes) left stray marks on the left edge and between lines on this board,
while full-screen redraws come out clean (tested 2026-10-20).

A small WiFi icon sits in the top-right corner (set_wifi): green arcs when
connected, grey arcs with a red slash when not, hidden when WiFi is off. It
is drawn once at startup; a change of state only swaps palette colours and
is shown with the next refresh_all(), so it costs no extra redraws.
"""

import board
import supervisor
import displayio
import terminalio
from adafruit_display_text import label

LINE_HEIGHT = 26
N_LINES = 5
LINE_CHARS = 19               # x=4 + 19 x 12 px = 232 px. Must stay inside the
                              # 240 px width: a line that ran past the right
                              # edge (20 chars = 244 px) wrapped its overflow
                              # onto the left edge / next rows as stray marks.
ICON_W, ICON_H = 22, 17
ICON_X, ICON_Y = 240 - ICON_W - 3, 3   # right of line 0 (keep its text <= 16 chars)
WIFI_ON, WIFI_OFF_ARCS, WIFI_OFF_SLASH = 0x00FF00, 0x606060, 0xFF4040


def _icon_bitmap():
    """WiFi icon: 1 = dot and two arcs, 2 = slash (drawn over the arcs)."""
    bmp = displayio.Bitmap(ICON_W, ICON_H, 3)
    cx, cy = ICON_W // 2, ICON_H - 1
    for y in range(ICON_H):
        for x in range(ICON_W):
            dx, dy = x - cx, cy - y
            d2 = dx * dx + dy * dy
            if (dy >= abs(dx) * 1.05 or d2 <= 6) and (d2 <= 5 or 42 <= d2 <= 72
                                                       or 132 <= d2 <= 182):
                bmp[x, y] = 1
            if 2 <= x <= ICON_W - 3 and abs((x - 2) * (ICON_H - 1) / (ICON_W - 5)
                                            - (ICON_H - 1 - y)) < 1.1:
                bmp[x, y] = 2
    return bmp


class StatusDisplay:
    def __init__(self):
        self.display = getattr(board, "DISPLAY", None)
        self.lines = []
        self.texts = [None] * N_LINES      # wanted (text, color) per line
        self.shown = [None] * N_LINES      # what is on screen
        if self.display is None:
            return
        # The status bar ("Wi-Fi: off | BLE: ...") would otherwise keep drawing
        # over the top of the screen.
        try:
            supervisor.status_bar.display = False
        except Exception:
            pass
        group = displayio.Group()
        # Full-screen black background: every refresh then paints black under
        # the text, so nothing of the boot console survives a partial redraw.
        self.background = displayio.Bitmap(self.display.width, self.display.height, 1)
        palette = displayio.Palette(1)
        palette[0] = 0x000000
        group.append(displayio.TileGrid(self.background, pixel_shader=palette))
        for i in range(N_LINES):
            text = label.Label(terminalio.FONT, text="", color=0xFFFFFF, scale=2,
                               x=4, y=12 + i * LINE_HEIGHT)
            group.append(text)
            self.lines.append(text)
        self.icon_palette = displayio.Palette(3)
        self.icon_palette.make_transparent(0)
        self.icon = displayio.TileGrid(_icon_bitmap(), pixel_shader=self.icon_palette,
                                       x=ICON_X, y=ICON_Y)
        self.icon.hidden = True
        group.append(self.icon)
        self.wifi = None                   # wanted icon state: None/True/False
        self.wifi_shown = None
        self.group = group
        self.display.root_group = group
        self.repaint()

    def set_line(self, i, text, color=0xFFFFFF, now=False):
        """Set the wanted text of line i. Drawn by refresh_all(), or right
        away with now=True (for startup messages)."""
        if not self.lines or i >= N_LINES:
            return
        # Pad to the full width: when a line got shorter, the redraw only
        # covered the new text and the tail of the old one stayed on screen.
        self.texts[i] = (text[:LINE_CHARS] + " " * (LINE_CHARS - len(text)), color)
        if now:
            self._draw(i)
            self.repaint()

    def set_wifi(self, state, now=False):
        """Icon state: True = connected, False = not, None = hidden (WiFi off).
        Drawn by the next refresh_all(), or right away with now=True."""
        self.wifi = state
        if now and self.lines:
            self._draw_icon()
            self.repaint()

    def _draw_icon(self):
        if self.wifi is None:
            self.icon.hidden = True
        else:
            self.icon.hidden = False
            if self.wifi:
                self.icon_palette[1] = WIFI_ON
                self.icon_palette.make_transparent(2)
            else:
                self.icon_palette[1] = WIFI_OFF_ARCS
                self.icon_palette[2] = WIFI_OFF_SLASH
                self.icon_palette.make_opaque(2)
        self.wifi_shown = self.wifi

    def _draw(self, i):
        text, color = self.texts[i]
        self.lines[i].text = text
        self.lines[i].color = color
        self.shown[i] = self.texts[i]

    def refresh_all(self):
        """Apply all changed lines and redraw the whole screen (if anything
        changed)."""
        if not self.lines:
            return
        changed = False
        for i in range(N_LINES):
            if self.texts[i] is not None and self.texts[i] != self.shown[i]:
                self._draw(i)
                changed = True
        if self.wifi != self.wifi_shown:
            self._draw_icon()
            changed = True
        if changed:
            self.repaint()

    def manual(self):
        """Stop automatic refreshes; from now on only refresh_all() draws."""
        if self.display is not None:
            self.display.auto_refresh = False

    def release(self):
        """Back to automatic refresh and the normal console (on shutdown)."""
        if self.display is not None:
            self.display.auto_refresh = True
            self.display.root_group = displayio.CIRCUITPYTHON_TERMINAL

    def repaint(self):
        """Redraw every pixel. Setting up the screen left parts of the boot
        console visible outside the labels (left edge, gaps between lines).
        Refilling the background did not clear them (tested); swapping the
        root group out and back in does."""
        if self.display is None:
            return
        self.display.root_group = displayio.Group()
        self.display.root_group = self.group
        self.display.refresh(target_frames_per_second=None)
