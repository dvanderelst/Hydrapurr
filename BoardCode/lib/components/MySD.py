

import os
import time
import board
import storage
import sdcardio
from components import MySystemLog

MOUNT_POINT = "/sd"

# --- Pin defaults for Feather + Adalogger FeatherWing (CS = D10) ---
DEFAULT_CS = getattr(board, "D10", None)

# --- Core helpers ---

def is_mounted():
    """True iff /sd is an active filesystem mount (not just a folder)."""
    try:
        storage.getmount(MOUNT_POINT)
        return True
    except Exception:
        return False

def mount_sd_card(cs_pin=DEFAULT_CS, spi=None, baudrate=8_000_000, quiet=False):
    """
    Mount the SD card at /sd. Idempotent.
    - cs_pin: board pin object (default board.D10 for Adalogger FeatherWing)
    - spi: pass a pre-initialized SPI bus (defaults to board.SPI())
    - baudrate: SPI speed for sdcardio
    """
    if is_mounted():
        MySystemLog.debug("[SD] already mounted at /sd")
        return True

    if cs_pin is None:
        MySystemLog.error("[SD] ERROR: No CS pin (cs_pin) provided and board.D10 not available.")
        return False

    try:
        # Make sure /sd directory exists (mount will overlay it)
        try:
            os.mkdir(MOUNT_POINT)
        except OSError:
            pass

        spi = spi or board.SPI()
        sd = sdcardio.SDCard(spi, cs_pin, baudrate=baudrate)
        vfs = storage.VfsFat(sd)
        storage.mount(vfs, MOUNT_POINT)
        MySystemLog.info("[SD] mounted OK at /sd")
        return True
    except Exception as e:
        MySystemLog.error("[SD] mount failed:", repr(e))
        return False

def unmount(quiet=False):
    """Unmount /sd if mounted."""
    if not is_mounted():
        MySystemLog.info("[SD] not mounted")
        return True
    try:
        vfs = storage.getmount(MOUNT_POINT)
        storage.umount(vfs)
        MySystemLog.info("[SD] unmounted")
        return True
    except Exception as e:
        MySystemLog.error("[SD] unmount failed:", repr(e))
        return False

def remount(cs_pin=DEFAULT_CS, spi=None, baudrate=8_000_000):
    """Force unmount then mount again."""
    unmount(quiet=True)
    time.sleep(0.05)
    return mount_sd_card(cs_pin=cs_pin, spi=spi, baudrate=baudrate)

def safe_path(name):
    """Normalize a filename under /sd."""
    if not name:
        name = "test.txt"
    n = name.replace("\\", "/")
    if n.startswith(MOUNT_POINT + "/"):
        n = n[len(MOUNT_POINT) + 1 :]
    if n.startswith("/"):
        n = n[1:]
    return MOUNT_POINT + "/" + n

# --- File ops (guarded) ---

def delete(name):
    """Delete a file on /sd (only if mounted)."""
    if not is_mounted():
        print("[SD] skip delete; /sd not mounted")
        return False
    path = safe_path(name)
    try:
        os.remove(path)
        MySystemLog.info(f"[SD] deleted {path}")
        return True
    except OSError as e:
        MySystemLog.warn(f"[SD] delete failed for {path}:", repr(e))
        return False

def write_line(name, line):
    """Append one line to a file on /sd."""
    if not is_mounted():
        MySystemLog.info("[SD] skip write; /sd not mounted")
        return False
    path = safe_path(name)
    try:
        with open(path, "a") as f:
            f.write(str(line) + "\n")
        return True
    except OSError as e:
        MySystemLog.error(f"[SD] write failed for {path}:", repr(e))
        return False

def read_all(name):
    """Read all lines from a file on /sd; returns list[str] or None."""
    if not is_mounted():
        MySystemLog.info("[SD] skip read; /sd not mounted")
        return None
    path = safe_path(name)
    try:
        with open(path, "r") as f:
            return [s.rstrip("\n") for s in f.readlines()]
    except OSError as e:
        MySystemLog.error(f"[SD] read failed for {path}:", repr(e))
        return None

# --- Diagnostics ---

def ls(path=MOUNT_POINT):
    """List directory contents (pretty)."""
    if not is_mounted():
        MySystemLog.info("[SD] not mounted; nothing to list")
        return
    try:
        for name in os.listdir(path):
            full = path + "/" + name
            try:
                st = os.stat(full)
            except OSError:
                continue
            size = st[6]
            isdir = bool(st[0] & 0x4000)
            if isdir:
                sizestr = "<DIR>"
            elif size < 1000:
                sizestr = f"{size} B"
            elif size < 1_000_000:
                sizestr = f"{size/1000:.1f} KB"
            else:
                sizestr = f"{size/1_000_000:.1f} MB"
            print(f"{name + ('/' if isdir else ''):<28} {sizestr:>10}")
    except Exception as e:
        MySystemLog.error("[SD] ls failed:", repr(e))

def quick_self_test():
    """Mount, write, read back, delete — returns True on full success."""
    MySystemLog.info("[SD] quick self-test...")
    if not mount_sd_card(quiet=True):
        MySystemLog.error("[SD] self-test: mount failed")
        return False
    ok_w = write_line("sd_self_test.txt", "hello")
    ok_r = bool(read_all("sd_self_test.txt"))
    ok_d = delete("sd_self_test.txt")
    MySystemLog.info(f"[SD] self-test results: write={ok_w} read={ok_r} delete={ok_d}")
    return ok_w and ok_r and ok_d
