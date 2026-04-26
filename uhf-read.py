# Python script to run on both RFID readers, broadcasting RFID tags over MQTT

import serial # type: ignore #import serial module
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

# Main functions

def read_uhf():
    found_tags = set() # a set ignores duplicates so I don't need to script that
    uhf.serial.reset_input_buffer() # clear out previous reads / junk etc
    
    uhf.multiple_read()  # Starts reading
    start_time = time.time() # gets the current time
    while time.time() - start_time < 1.0:
        read = uhf.read_mul()
        if read is not None:
            tag_id = ''.join(read[8:20])
            found_tags.add(tag_id)
        else:
            # trying to find the next '0xBB' start byte in case reading got interrupted
            if uhf.serial.in_waiting > 0:
                uhf.serial.read(1)

    uhf.stop_read()  # Ends the reading session
    return list(found_tags)

while True:
    tags = read_uhf()
    number_of_tags = len(tags)
    
    if tags:
        print(f"{number_of_tags} tags scanned.")
        # print(f"Tags: {tags}")
        payload = tags
        client.publish(TOPIC, json.dumps(payload))
    else:
        print("No tags read.")
        payload = "uhf_empty"
        client.publish(TOPIC, json.dumps(payload))
    time.sleep(0.5)