import serial           # type: ignore #import serial module
import paho.mqtt.client as mqtt
import time


# need this to happen continuously, see if the while statement works?

def read_rfid():
    ser = serial.Serial("/dev/ttyS0")  # Open named port
    ser.baudrate = 9600  # Set baud rate to 9600
    data = ser.read(12)  # Read 12 characters from serial port to data
    ser.close()  # Close port
    data = data.decode("utf-8")
    return data  # Return data


while i:
        print('Read #', i)
        data = read_rfid()
        if data:
             print("Read", i, ': ', data)
        else:
            print('Read', i, ':  --------------')
            time.sleep(0.5)
        i = i + 1
