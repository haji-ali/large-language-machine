# Python script to run on both RFID readers, broadcasting RFID tags over MQTT

import serial           # type: ignore #import serial module
import paho.mqtt.client as mqtt
import time
import json

# Set up UHF reader
import uhf
import RPi.GPIO as GPIO # pyright: ignore[reportMissingModuleSource]

GPIO.setmode(GPIO.BOARD)
GPIO.setwarnings(False)
GPIO.setup(7,GPIO.OUT)
GPIO.output(7,GPIO.LOW)

baudrate = '115200'
port = '/dev/ttyAMA0'
uhf = uhf.UHF(port,baudrate)

# MQTT variables
BROKER_ADDRESS = "100.85.109.22"
TOPIC = "home/sensors/uhf"

# MQTT set up
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect(BROKER_ADDRESS, 2883, 60)
print(f"Connected to MQTT broker. Pushing data to '{TOPIC}'...")

def read_uhf():
    ser = serial.Serial("/dev/ttyS0")  # Open named port
    ser.baudrate = 9600  # Set baud rate to 9600
    data = ser.read(12)  # Read 12 characters from serial port to data
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
