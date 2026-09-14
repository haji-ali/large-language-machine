# Python script to run on both RFID readers, broadcasting RFID tags over MQTT

import serial
import paho.mqtt.client as mqtt # pyright: ignore[reportMissingImports]
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
ADDRESS = "192.168.1.10"
TOPIC = "home/sensors/uhf"
PORT = 2883

def on_connect(client, userdata, flags, reason_code, properties):
    print(f"Broker connected (rc={reason_code})")

def on_disconnect(client, userdata, flags, reason_code, properties):
    print(f"DISCONNECTED (rc={reason_code}) — auto-reconnecting")

# MQTT set up
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.reconnect_delay_set(min_delay = 1, max_delay= 30)
client.connect_async(ADDRESS, PORT, 60)
client.loop_start()
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

try:
    while True:
        tags = read_uhf()
        number_of_tags = len(tags)
        
        if tags:
            print(f"{number_of_tags} tags scanned.")
            payload = tags
            client.publish(TOPIC, json.dumps(payload))
        else:
            print("No tags read.")
            payload = "uhf_empty"
            
        for attempt in range(3):
            result = client.publish(TOPIC, json.dumps(payload), qos=1)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                print(f"Sent: {payload}")
                break
            print(f"Publish failed (rc={result.rc}), retrying...")
            time.sleep(1)
        else:
            print("Failed to send UHF read after retries")

        time.sleep(0.5)

except KeyboardInterrupt:
    print("\nDisconnecting...")

finally:
    client.loop_stop()
    client.disconnect()