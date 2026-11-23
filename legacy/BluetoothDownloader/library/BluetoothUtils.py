import bluetooth
import time
import sys

def discover_bluetooth_devices(print_devices=True):
    """
    Discover and return nearby Bluetooth devices.
    Replaces the serial port discovery function.
    """
    devices = bluetooth.discover_devices(lookup_names=True, duration=8)
    selected_devices = []

    for addr, name in devices:
        if "HC-05" in name or "hc-05" in name:
            selected_devices.append((addr, name))

    if print_devices and not selected_devices:
        print("No HC-05 devices found. Make sure the device is powered on and discoverable.")
    elif print_devices:
        print("Available Bluetooth devices:")
        for index, (addr, name) in enumerate(selected_devices):
            print(f"{index}: {name} ({addr})")

    return selected_devices

def port_selection():
    """
    Let the user select a Bluetooth device by index.
    Replaces the serial port selection function.
    """
    devices = discover_bluetooth_devices()
    if not devices:
        return None

    device_selected = None
    while device_selected is None:
        try:
            selection = int(input("Select a device by entering its index: "))
            if 0 <= selection < len(devices):
                device_selected = devices[selection]
            else:
                print("Invalid selection. Please try again.")
        except ValueError:
            print("Please enter a valid integer.")

    if device_selected:
        print(f"Selected device: {device_selected[1]} ({device_selected[0]})")
        return device_selected[0]  # Return MAC address
    return None

def connect(mac_address, baud_rate=9600, timeout=5):
    """
    Connect to a Bluetooth device using its MAC address.
    Replaces the serial connection function.
    """
    try:
        sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
        sock.connect((mac_address, 1))  # RFCOMM channel 1 (default for SPP)
        print(f"Successfully connected to {mac_address}.")
        return sock
    except Exception as e:
        print(f"Failed to connect to {mac_address}: {e}")
        return None

def get_data(connection, kind, timeout=1, idle_timeout=0.75, max_time=20, print_every=0.25):
    """
    Send a command and read the response from the Bluetooth device.
    Replaces the serial data reading function.
    """
    command_map = {
        'l': 'licks*',
        's': 'system*'
    }

    k = kind.lower()
    command = command_map.get(k[0], None) if k else None
    if command is None:
        return None

    try:
        connection.settimeout(timeout)
        connection.send(command.encode('utf-8'))
        print('Command sent, waiting for response...')

        response = ""
        start = time.time()
        last_activity = start
        last_print = 0.0
        total = 0

        hard_deadline = start + max_time
        soft_deadline = start + timeout

        while True:
            now = time.time()
            if now >= hard_deadline:
                break

            deadline = (last_activity + idle_timeout) if total > 0 else soft_deadline
            if now >= deadline:
                break

            try:
                chunk = connection.recv(1024).decode('utf-8', errors='replace')
                if chunk:
                    response += chunk
                    total += len(chunk)
                    last_activity = now
            except bluetooth.BluetoothError as e:
                if "timed out" not in str(e):
                    raise e

            if (now - last_print) >= print_every:
                elapsed = now - start
                rate = (total / elapsed) if elapsed > 0 else 0.0
                sys.stdout.write(f"\rRead {total} bytes in {elapsed:.1f}s (~{int(rate)} B/s).")
                sys.stdout.flush()
                last_print = now

            time.sleep(0.01)

        print()
        if total == 0:
            print("No data received.")
            return None

        print(f"Done. Total {total} bytes. Idle {idle_timeout}s / Max {max_time}s.")
        return response.strip() if response else None

    except Exception as e:
        print(f"Error during communication: {e}")
        return None

# # Example usage (for testing)
# if __name__ == "__main__":
#     mac_address = port_selection()
#     if mac_address:
#         connection = connect(mac_address)
#         if connection:
#             try:
#                 data = get_data(connection, "licks")
#                 if data:
#                     print("Response:", data)
#             finally:
#                 connection.close()
