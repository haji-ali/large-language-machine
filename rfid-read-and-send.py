# Python script to run on both RFID readers, broadcasting RFID tags over MQTT

from oled_091 import SSD1306
import serial           # type: ignore #import serial module
import paho.mqtt.client as mqtt
import time
import json
from os import path
import RPi.GPIO as GPIO # pyright: ignore[reportMissingModuleSource]

# Set up on-board display
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(17,GPIO.OUT)
DIR_PATH = path.abspath(path.dirname(__file__))
DefaultFont = path.join(DIR_PATH, "Tests/RFID/Fonts/GothamLight.ttf")
display = SSD1306()

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
    ser.close()  # Close port
    data = data.decode("utf-8")
    return data  # Return data

def info_print():

    # display.WhiteDisplay()
    display.DirImage(path.join(DIR_PATH, "Tests/RFID/Images/SB.png"))
    display.DrawRect()
    display.ShowImage()
    time.sleep(1)
    display.PrintText("Place your TAG", FontSize=14)
    display.ShowImage()

i = 1

while i:
    print('Read #', i)
    data = read_rfid()
    if data:
        print("Read", i, ': ', data)
        client.publish(TOPIC, json.dumps(data))
        display.PrintText("SCANNED", cords=(4, 8), FontSize=11)
        display.DrawRect()
        display.ShowImage()
    else:
        print('Read', i, ':  --------------')
        time.sleep(0.5)
    i = i + 1
