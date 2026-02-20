import time
import sys
sys.path.append("..")
from Library import uhf 
import RPi.GPIO as GPIO # pyright: ignore[reportMissingModuleSource]
GPIO.setmode(GPIO.BOARD)
GPIO.setwarnings(False)

GPIO.setup(7,GPIO.OUT)

GPIO.output(7,GPIO.LOW)# (LOW)Enable the module, and (HIGH) disable the module

baudrate ='115200' # default baudrate
port     ='/dev/ttyS0'

uhf = uhf.UHF(port,baudrate)

'''
Uncomment corresponding section to increase reading range,
you will have to set the region as per requirment
'''
uhf.setRegion_EU() 
#uhf.setRegion_US()

def add_to_array(item, array):
    if item not in array:
        array.append(item)
        return True
    return False

uhf.multiple_read()

results = []

i = 0

try:
    while i < 50:
        rev = uhf.read_mul()
        if rev is not None:
            epc = rev[8:20]
            epc_string = ''.join(epc)
            add_to_array(epc_string,results)
            print ("Read",i,': ',epc_string)
        else:
            print('Read',i,':  --------------')
        time.sleep(0.01)
        i = i + 1
except KeyboardInterrupt:
    uhf.stop_read()
    time.sleep(1)
    print("stop")
    
uhf.stop_read()
time.sleep(1)

print('------------------')
print(' ')

if results:
    number_of_tags = len(results)
    print('Counted',number_of_tags,'tags:',results)
else:
    print ('No tags')
