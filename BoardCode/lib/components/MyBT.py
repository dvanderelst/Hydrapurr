import board
import busio
import time

class MyBT:
    def __init__(self, baudrate=9600, buffer_size=64, timeout=0.2, eom_char='*', add_crlf=False):
        """
        UART Bluetooth helper with optional line breaks and non-blocking receive.

        :param baudrate: UART baudrate (default 9600)
        :param buffer_size: Max bytes to read per poll
        :param timeout: Timeout for receive() in seconds
        :param eom_char: End-of-message delimiter (default '*')
        :param add_crlf: Append CRLF ('\\r\\n') after each message if True
        """
        self.uart = busio.UART(board.TX, board.RX, baudrate=baudrate)
        self.buffer_size = buffer_size
        self.eom_char = eom_char
        self._buffer = ""
        self.timeout = timeout
        self.add_crlf = add_crlf  # new flag

    # ---------- Sending ----------
    def send(self, message: str):
        """Send a string, appending EOM and optionally CRLF."""
        if not isinstance(message, str):
            raise ValueError("Message must be a string.")
        if not message.endswith(self.eom_char):
            message += self.eom_char
        if self.add_crlf:
            message += "\r\n"
        data = message.encode("utf-8")
        return self.uart.write(data)  # return bytes written

    # ---------- Non-blocking receive ----------
    def poll(self):
        """Non-blocking check for one complete message."""
        n_avail = getattr(self.uart, "in_waiting", 0) or 0
        if n_avail:
            n_read = min(n_avail, self.buffer_size)
            raw = self.uart.read(n_read)
            if raw:
                try:
                    self._buffer += raw.decode("utf-8")
                except UnicodeError:
                    self._buffer += "".join(chr(b) for b in raw if 32 <= b < 127)

        if self.eom_char in self._buffer:
            msg, remainder = self._buffer.split(self.eom_char, 1)
            self._buffer = remainder
            return msg.strip()
        return None

    def receive(self, timeout=None):
        """Wait (bounded) for a message."""
        if timeout is None:
            timeout = self.timeout
        t0 = time.monotonic()
        while True:
            msg = self.poll()
            if msg is not None:
                return msg
            if (time.monotonic() - t0) >= timeout:
                return None
            time.sleep(0.001)

    def send_and_receive(self, message, timeout=None):
        self.send(message)
        return self.receive(timeout=timeout)

    # ---------- Utilities ----------
    def clear_buffer(self):
        self._buffer = ""

    def flush_input(self):
        n_avail = getattr(self.uart, "in_waiting", 0) or 0
        if n_avail:
            _ = self.uart.read(n_avail)
