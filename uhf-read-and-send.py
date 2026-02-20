# Python script to run on both RFID readers, broadcasting RFID tags over MQTT

import serial           # type: ignore #import serial module
import paho.mqtt.client as mqtt
import time
import json

# Set up UHF reader
import uhf
import RPi.GPIO as GPIO  # pyright: ignore[reportMissingModuleSource]

GPIO.setmode(GPIO.BOARD)
GPIO.setwarnings(False)
GPIO.setup(7, GPIO.OUT)
GPIO.output(7, GPIO.LOW)

baudrate = '115200'
port = '/dev/ttyAMA0'
uhf = uhf.UHF(port, baudrate)
uhf.setRegion_EU()

# MQTT variables
BROKER_ADDRESS = "100.85.109.22"
TOPIC = "home/sensors/uhf"

# MQTT set up
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect(BROKER_ADDRESS, 2883, 60)
print(f"Connected to MQTT broker. Pushing data to '{TOPIC}'...")

# Functions


def add_to_array(item, array):
    if item not in array:
        array.append(item)
        return True
    return False


def read_uhf():
    uhf.multiple_read()  # Starts reading
    data = []
    read_iterations = 0

    # So we run 100 reads in succession and add all of them to an array
    # If tags are duplicates they don't get added in add_to_array()
    try:
        while read_iterations < 200:
            read = uhf.read_mul()
            if read is not None:
                tag = read[8:20]
                tag_string = ''.join(tag)
                add_to_array(tag_string, data)
                # print("Read", i, ': ', tag_string)
            # else:
                # print('Read', i, ':  --------------')
            time.sleep(0.01)
            read_iterations = read_iterations + 1
    except KeyboardInterrupt:
        uhf.stop_read()
        time.sleep(1)
        print("stop")

    uhf.stop_read()  # Ends the reading session
    if data:
        number_of_tags = len(data)
        print('Counted',number_of_tags,'tags.')
        return data
    else:
        return False

i = 1

while i:
    print('Read #', i)
    data = read_uhf()
    if data:
        # print("Read", i, ': ', data)
        print ('Read #',i,'published.')
        client.publish(TOPIC, json.dumps(data)) # publish over MQTT
    else:
        print('Read', i, ' No tags found')
    
    time.sleep(1) # time to wait before reading again
    
    i = i + 1
