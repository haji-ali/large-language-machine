# Python script to run on both RFID readers, broadcasting RFID tags over MQTT

import serial           # type: ignore #import serial module
import paho.mqtt.client as mqtt
import time
import json

# MQTT variables
BROKER_ADDRESS = "100.85.109.22"
TOPIC = "home/sensors/rfid"

# MQTT set up
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect(BROKER_ADDRESS, 2883, 60)
print(f"Connected to MQTT broker. Pushing data to '{TOPIC}'...")

def read_rfid():
    ser = serial.Serial("/dev/ttyS0")  # Open named port
    ser.baudrate = 9600  # Set baud rate to 9600
    data = ser.read(12)  # Read 12 characters from serial port to data
    ser.reset_input_buffer() # Flush the data (I think this is cleaner/reduces errors)
    ser.close()  # Close port
    data = data.decode("utf-8")
    return data  # Return data

i = 1

while i:
    print('Read #', i)
    data = read_rfid()
    if data:
        print("Read", i, ': ', data)
        client.publish(TOPIC, json.dumps(data))
    else:
        print('Read', i, ':  --------------')
        time.sleep(0.5)
    i = i + 1
