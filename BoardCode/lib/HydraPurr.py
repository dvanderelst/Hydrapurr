import board

import Settings
from components import MyDigital
from components import MyOLED
from components import MyADC
from components import MyBT
from components import MyStore
from components import MyRTC
from components import MyPixel
from components.MySystemLog import debug, info, warn, error
import time

class HydraPurr:
    def __init__(self):
        # Defines the built-in LED
        self.indicator = MyDigital(pin=board.D25, direction="output")
        # Defines the relay that controls the feeder
        self.feeder = MyDigital(pin=board.D6, direction='output')
        # Defines the OLED screen

        self.screen = MyOLED()
        self.screen.set_rotation(False)
        self.screen.auto_show = False

        # Defines the Bluetooth hardware module
        self.bluetooth = MyBT()
        # Defines the lick sensor
        self.lick = MyADC(1)
        self.lick_threshold = 2.0
        # Storing the storage files
        self.stores = {}
        # Defines the RTC for timekeeping
        self.rtc = MyRTC()
        debug("[HydraPurr] HydraPurr initialized")
        # Defines the NeoPixel for visual feedback
        self.pixel = MyPixel(num_pixels=1, brightness=0.2)
        self.pixel.toggle_colors = ['red', 'green', 'blue', 'yellow', 'cyan', 'magenta', 'white', 'off']
        self.pixel.color_index = 0

    # --- read lick ---
    def read_lick(self, binary=True):
        lick_value = self.lick.read()
        lick_threshold = self.lick_threshold
        if binary: lick_value = 1 if lick_value < lick_threshold else 0
        #debug(f'[HydraPurr] Lick value: {lick_value}, binary: {binary}')
        return lick_value

    # --- indicator LED control ---
    def indicator_on(self):
        self.indicator.write(True)
        debug('[HydraPurr] Indicator LED on')

    def indicator_off(self):
        self.indicator.write(False)
        debug('[HydraPurr] Indicator LED off')

    def indicator_toggle(self):
        self.indicator.toggle()
        debug('[HydraPurr] Indicator LED toggle')

    # --- feeder relay control ---
    def feeder_on(self):
        self.feeder.write(True)
        debug('[HydraPurr] Feeder on')

    def feeder_off(self):
        self.feeder.write(False)
        debug('[HydraPurr] Feeder off')

    def feeder_toggle(self):
        self.feeder.toggle()
        debug('[HydraPurr] Feeder toggle')

    # --- screen ---
    def write(self, text, x=0, y=0):
        self.screen.write(str(text), x, y)
        debug(f'[HydraPurr] Screen write: {text}')
    
    def write_line(self, line_nr, text):
        self.screen.write_line(line_nr, str(text))
        debug(f'[HydraPurr] Line write: {text}')
        
    def clear_screen(self):
        self.screen.clear()
        debug(f'[HydraPurr] Cleared screen')
    
    def show_screen(self):
        self.screen.show()



    # --- send bt data ---
    def bluetooth_send(self, message):
        message = str(message)
        self.bluetooth.send(message)
        debug(f'[HydraPurr] Bluetooth sent: {message}')

    def bluetooth_poll(self):
        message = self.bluetooth.poll()
        if message is not None: debug(f'[HydraPurr] Bluetooth received: {message}')
        return message

    def bluetooth_send_data(self, kind):
        # pick file
        filename = None
        if kind == "licks": filename = Settings.lick_data_filename
        if kind == "system": filename = Settings.system_log_filename
        print(kind, filename)
        if filename is None: return

        selected_storage = self.select_data_log(filename)
        it = selected_storage.iter_lines()

        lines = 0
        bytes_out = 0
        bytes_out += self.bluetooth.send(f"START,{kind}")

        for line in it:
            message = ",".join(str(x) for x in line)  # one CSV line
            sent = self.bluetooth.send(message)  # add_crlf=True appends \r\n
            bytes_out += (sent or 0)
            lines += 1
            time.sleep(0.002)

            # # every 100 lines, give receiver a chance to say STOP
            # if (lines % 100) == 0:
            #     # non-blocking check for inbound command
            #     cmd = self.bluetooth.poll()
            #     if cmd and cmd.strip().upper() == "STOP":
            #         self.bluetooth.send(f"ABORT,{kind},at_line,{lines}")
            #         debug(f"[HydraPurr] Bluetooth aborted {kind} at line {lines}")
            #         return

        # Optional: announce end
        bytes_out += self.bluetooth.send(f"END,{kind},lines,{lines},bytes,{bytes_out}")
        info(f"[HydraPurr] Bluetooth sent {kind} data: {lines} lines, {bytes_out} bytes")
        print(f"[HydraPurr] Bluetooth sent {kind} data: {lines} lines, {bytes_out} bytes")

    # --- RTC time ---
    def set_time(self, yr=None, mt=None, dy=None, hr=None, mn=None, sc=None):
        self.rtc.set_time(yr, mt, dy, hr, mn, sc)
        debug(f'[HydraPurr] Set time {(yr,mt,dy,hr,mn,sc)}')

    def get_time(self, as_string=False):
        return self.rtc.get_time(as_string=as_string, with_seconds=True)

    # --- NeoPixel ---
    def pixel_cycle(self, brightness=None):
        self.pixel.cycle(brightness)
        debug('[HydraPurr] Pixel cycle')

    def pixel_set_color(self, color_name, brightness=None):
        self.pixel.set_color(color_name, brightness)
        #debug(f'[HydraPurr] Pixel set color: {color_name} with brightness {brightness}')

    def heartbeat(self, base_color='blue'):
        self.pixel.heartbeat(base_color)
        #debug(f'[HydraPurr] Pixel heartbeat with base color: {base_color}')

    # --- data logging ---
    def create_data_log(self, filename): #alias for ease
        return self.select_data_log(filename)
    
    def select_data_log(self, filename):
        exists = filename in self.stores
        if not exists:
            self.stores[filename] = MyStore(filename, max_lines=Settings.data_log_max_lines)
        selected_storage = self.stores[filename]
        return selected_storage

    def add_data(self, filename, data):
        selected_storage = self.select_data_log(filename)
        result = selected_storage.add(data)
        return result

    def read_data_log(self, filename):
        selected_storage = self.select_data_log(filename)
        return selected_storage.read()
    
    def empty_data_log(self, filename):
        selected_storage = self.select_data_log(filename)
        selected_storage.empty()
        return selected_storage


        
        
