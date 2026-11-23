from library import SerialUtils
from library import DataUtils
from library import ProgramUtils
from library import BluetoothUtils

use_serial = False

if use_serial:
    port = SerialUtils.port_selection()
    connection = SerialUtils.connect(port)
else:
    mac_address = BluetoothUtils.port_selection()
    connection = BluetoothUtils.connect(mac_address)

while True:
    kind = ProgramUtils.request_kind()
    data = SerialUtils.get_data(connection, kind)

    data = data.replace('*', '\n')
    data = data.split('\n')
    length = len(data)
    header = data.pop(0)
    tail1 = data.pop(-1)
    tail2 = data.pop(-1)

    try:
        data_aligned = ''
        if kind == 'system': data_aligned = DataUtils.align_system_data(data)
        if kind == 'licks': data_aligned = DataUtils.align_lick_data(data)
        #for line in data_aligned: print(line)
    except Exception as e:
        print("Error aligning data:", e)
        for line in data: print(line)

    save_data = ProgramUtils.request_save()
    if save_data:
        file_name = ProgramUtils.get_file_name(kind)
        ProgramUtils.save_data(data, file_name)

