# TagReader.py — WL-134 RFID reader for RP2040
# - Non-blocking poll() (no sleeps)
# - Rate limiter: MAX_READ_HZ -> refresh_ms (returns cached value inside window)
# - cache_on_fail=False (hardcoded)
# - reset_on_success=True (hardcoded)
# - Periodic reset (~3 Hz) via tiny state machine + reset-on-success
# - STX/ETX framing, XOR checksum, optional invert check
# - Robust 26-char ASCII-hex parser (BE/LE ints) + tag_key
# - De-dup repeats within repeat_ms
# - Sticky helpers: active_tag(timeout_ms), poll_active(timeout_ms)

import time, board, busio
import Settings
from components import MyDigital
from components.MySystemLog import debug, warn, error



def parser_hex_len26(body: bytes):
    try: up = body.decode("ascii").strip().upper()
    except Exception: return None
    if len(up)!=26 or any(c not in "0123456789ABCDEF" for c in up): return None
    try: id_int_be = int(up, 16)
    except Exception: id_int_be = None
    pairs = [up[i:i+2] for i in range(0, 26, 2)]; rev_hex = "".join(reversed(pairs))
    try: id_int_le = int(rev_hex, 16)
    except Exception: id_int_le = None
    return {"tag": up, "id_int_be": id_int_be, "id_int_le": id_int_le, "tag_key": up}

class TagReader:
    def __init__(self):
        # --- Hardware (hardcoded) --------------------------------------------
        self.rx_pin, self.rst_pin, self.baudrate = board.D9, board.D11, 9600
        self.uart = busio.UART(rx=self.rx_pin, tx=None, baudrate=self.baudrate, timeout=0)
        self.rst = MyDigital(self.rst_pin, direction="output"); self.rst.write(False)
        debug(f"[RFID] init: rx={self.rx_pin} rst={self.rst_pin} baud={self.baudrate}")
        # --- Framing & parser -------------------------------------------------
        self.stx, self.etx, self.max_len = 0x02, 0x03, 64
        self.invert_required, self.parser = True, parser_hex_len26
        # --- De-dup -----------------------------------------------------------
        self.repeat_ms, self.last_tag, self.last_ms = 100, None, 0
        # --- Scheduled reset --------------------------------------------------
        self.reset_pulse_ms, self.reset_settle_ms, self.force_reset_hz = 75, 80, 3.0
        self.period_ms = int(1000/self.force_reset_hz) if self.force_reset_hz>0 else 0
        t0 = self.now_ms(); self.next_reset_ms = (t0+self.period_ms) if self.period_ms else 0
        self.rst_state, self.rst_until_ms = "idle", 0
        # --- Read-rate limiter & cache ---------------------------------------
        max_tag_read_hz = Settings.max_tag_read_hz
        self.refresh_ms = int(1000/max_tag_read_hz) if max_tag_read_hz>0 else 0
        self.last_attempt_ms, self.last_pkt = 0, None
        self.cache_on_fail = False        # hardcoded
        self.reset_on_success = True      # hardcoded
        # --- Sticky (last successful) ----------------------------------------
        self.last_success_pkt, self.last_success_ms = None, 0
        # --- Buffer -----------------------------------------------------------
        self.buf = bytearray()

    def now_ms(self): return int(time.monotonic()*1000)

    # ---- Reset state machine (non-blocking) ---------------------------------
    def tick_reset(self, now):
        if self.period_ms and self.rst_state=="idle" and now>=self.next_reset_ms:
            self.rst.write(True); self.rst_state="pulsing"; self.rst_until_ms=now+self.reset_pulse_ms; debug("[RFID] reset: assert"); return
        if self.rst_state=="pulsing" and now>=self.rst_until_ms:
            self.rst.write(False); self.rst_state="settling"; self.rst_until_ms=now+self.reset_settle_ms; debug("[RFID] reset: release; settling"); return
        if self.rst_state=="settling" and now>=self.rst_until_ms:
            self.rst_state="idle";
            if self.period_ms: self.next_reset_ms+=self.period_ms
            debug("[RFID] reset: settled"); return

    def reset_now(self):
        if self.rst_state=="idle":
            now=self.now_ms(); self.next_reset_ms=now; self.tick_reset(now)

    # ---- UART ingest --------------------------------------------------------
    def read_buf(self):
        n=getattr(self.uart,"in_waiting",0) or 0
        if not n: return
        n=min(n,self.max_len); chunk=self.uart.read(n)
        if not chunk: return
        self.buf.extend(chunk); debug(f"[RFID] read {len(chunk)}B → buf={len(self.buf)}B")
        if len(self.buf)>2*self.max_len: self.buf=self.buf[-self.max_len:]

    # ---- Manual byte scan (avoid .find() quirks) ----------------------------
    def _find_byte(self, b, start=0, stop=None):
        if not isinstance(b, int): b = b[0]
        n = len(self.buf) if stop is None else min(stop, len(self.buf))
        for k in range(start, n):
            if self.buf[k]==b: return k
        return -1

    # ---- Framing & validation -----------------------------------------------
    def validate_frame(self, frame: bytes):
        if not frame or frame[0]!=self.stx or frame[-1]!=self.etx: return None
        payload=frame[1:-1]
        if len(payload)<2: return None
        body,csum,inv=payload[:-2],payload[-2],payload[-1]
        x=0
        for bb in body: x^=bb
        x&=0xFF
        if x!=csum: warn(f"[RFID] checksum mismatch calc={x} pkt={csum}"); return None
        if self.invert_required and ((csum^inv)!=0xFF): warn(f"[RFID] checksum invert mismatch: csum={csum} inv={inv}"); return None
        return body

    def parse_body(self, body):
        if self.parser:
            try: out=self.parser(body)
            except Exception as e: error(f"[RFID] parser error: {e!r}"); return None
            if out: return out
            warn("[RFID] parser returned None"); return None
        try: txt=body.decode("ascii").strip()
        except Exception: txt=""
        return {"id_ascii": (txt or None), "tag_key": (txt or None)}

    def deduplicate(self, key):
        now=self.now_ms()
        if key==self.last_tag and (now-self.last_ms)<self.repeat_ms: return False
        self.last_tag,self.last_ms=key,now; return True

    def _reset_after_success(self, now):
        if not self.reset_on_success: return
        if self.rst_state=="idle": self.next_reset_ms=now; self.tick_reset(now)
        else: self.next_reset_ms=now

    # ---- Public API ---------------------------------------------------------
    def poll(self):
        now=self.now_ms()
        # --- Rate limiter
        if self.refresh_ms and (now - self.last_attempt_ms) < self.refresh_ms:
            return self.last_pkt
        self.last_attempt_ms = now

        self.tick_reset(now); self.read_buf()
        i=self._find_byte(self.stx)
        if i<0:
            if len(self.buf)>self.max_len: self.buf=self.buf[-self.max_len:]
            self.last_pkt=None; return None
        if (len(self.buf)-i)>self.max_len:
            warn(f"[RFID] overrun: STX at {i}, tail={len(self.buf)-i} > max_len={self.max_len} → resync")
            self.buf = bytearray(self.buf[i+1:]); self.last_pkt=None; return None
        j=self._find_byte(self.etx, i+1, i+self.max_len)
        if j<0: self.last_pkt=None; return None

        frame=bytes(self.buf[i:j+1]); self.buf = bytearray(self.buf[j+1:])
        body=self.validate_frame(frame)
        if body is None: self.last_pkt=None; return None

        pkt=self.parse_body(body)
        if pkt is None: self.last_pkt=None; return None

        pkt["raw_hex"]=body.hex().upper()
        if "tag_key" not in pkt:
            fk=pkt.get("tag") or pkt.get("id_hex") or pkt.get("id_ascii") or pkt["raw_hex"]
            pkt["tag_key"]=fk if isinstance(fk,str) else str(fk)
        if not isinstance(pkt["tag_key"],str): pkt["tag_key"]=str(pkt["tag_key"])
        pkt["time_ms"]=now

        key=pkt["tag_key"]
        if not key: self.last_pkt=None; return None
        if not self.deduplicate(key): debug(f"[RFID] duplicate suppressed: {key}"); self.last_pkt=None; return None

        debug(f"[RFID] tag: {key}")
        self.last_pkt = pkt
        self.last_success_pkt, self.last_success_ms = pkt, now
        self._reset_after_success(now)
        return pkt

    # ---- Sticky helpers -----------------------------------------------------
    def active_tag(self, timeout_ms):
        now=self.now_ms()
        return self.last_success_pkt if (self.last_success_pkt and (now - self.last_success_ms) < timeout_ms) else None

    def poll_active(self, cat_timeout_ms=None):
        if cat_timeout_ms is None: cat_timeout_ms = Settings.cat_timeout_ms
        _ = self.poll()  # may update last_success_* if we got a fresh read
        return self.active_tag(cat_timeout_ms)
