from serial.tools import list_ports
import serial


def get_ports(print_ports=True):
    selected_ports = []
    ports = list_ports.comports()
    search_strings = ['rfcomm', 'bluetooth', 'usb', 'acm', 'com']
    for port in ports:
        device = port.device
        if any(s in device.lower() for s in search_strings):
            selected_ports.append(port)
    if print_ports:
        print("Available serial ports:")
        for index, port in enumerate(selected_ports):
            print(f"{index}: {port.device}, {port.description}")
    return selected_ports


def port_selection():
    ports = get_ports()
    port_selected = None
    while port_selected is None:
        try:
            selection = int(input("Select a port by entering its index: "))
            if 0 <= selection < len(ports):
                port_selected = ports[selection].device
            else:
                print("Invalid selection. Please try again.")
        except ValueError:
            print("Please enter a valid integer.")
    print("Selected port:", port_selected)
    return port_selected


def connect(port, baud_rate=9600, timeout=5):
    try:
        connection = serial.Serial(port, baud_rate, timeout=timeout)
        print(f"Successfully connected to {port} at {baud_rate} baud.")
        return connection
    except serial.SerialException as e:
        print(f"Failed to connect to {port}: {e}")
        return None


import time, sys


def get_data(connection, kind, timeout=1, idle_timeout=0.75, max_time=20, print_every=0.25):
    command = None
    k = kind.lower()
    if k.startswith('l'): command = 'licks*'
    if k.startswith('s'): command = 'system*'
    if command is None: return None

    try:
        connection.reset_input_buffer()
        connection.write(command.encode('utf-8'))
        print('Command sent, waiting for response...')

        response = ""
        start = time.time()
        last_activity = start
        last_print = 0.0
        total = 0

        # initial wait window to allow device to start responding
        hard_deadline = start + max_time
        soft_deadline = start + timeout

        while True:
            now = time.time()
            # hard stop
            if now >= hard_deadline: break
            # switch from initial timeout to idle-based timeout once anything arrives
            deadline = (last_activity + idle_timeout) if total > 0 else soft_deadline
            if now >= deadline: break

            available = connection.in_waiting
            if available:
                # read chunks to avoid per-line latency
                chunk = connection.read(available).decode('utf-8', errors='replace')
                response += chunk
                got = len(chunk)
                total += got
                last_activity = now

            # progress line (rate + bytes)
            if (now - last_print) >= print_every:
                elapsed = now - start
                rate = (total / elapsed) if elapsed > 0 else 0.0
                sys.stdout.write(f"\rRead {total} bytes in {elapsed:.1f}s (~{int(rate)} B/s).")
                sys.stdout.flush()
                last_print = now

            # tiny sleep to avoid busy wait
            time.sleep(0.01)

        # final newline after carriage-return updates
        print()
        if total == 0:
            print("No data received.")
            return None
        print(f"Done. Total {total} bytes. Idle {idle_timeout}s / Max {max_time}s.")
        return response.strip() if response else None

    except Exception as e:
        print(f"Error during communication: {e}")
        return None
