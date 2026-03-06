# Run this script to set the time and date on the logger

from HydraPurr import HydraPurr
hp = HydraPurr()

# To skip setting fields, set the field to None
yr=2025
mt=10
dy=6
hr=14
mn=26
sc=00

print(hr, mn, sc)

input('press enter to set time')

hp.set_time(yr=yr, mt=mt, dy=dy, hr=hr, mn=mn, sc=sc)
line1 = " Current time (string):" + str(hp.get_time(as_string=True))
line2 = " Current time (dict):" + str(hp.get_time(as_string=False))
print(line1)
print(line2)