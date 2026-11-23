from HydraPurr import HydraPurr
import time

hydrapurr = HydraPurr()

counter = 1
while True:
    result = hydrapurr.bluetooth_poll()
    print(result)
    #if result == 'get':


    #hydrapurr.bluetooth_send_lick_data()
    #print(counter, result)
    
    time.sleep(0.5)
    counter = counter + 1