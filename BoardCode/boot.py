import supervisor
import storage

if not supervisor.runtime.usb_connected:
    storage.remount("/", readonly=False)
