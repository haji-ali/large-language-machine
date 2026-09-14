# Python script to run on both RFID readers, broadcasting RFID tags over MQTT

import serial
import paho.mqtt.client as mqtt 
import time
import json

# Set up UHF reader
import uhf # type: ignore
import RPi.GPIO as GPIO   # type: ignore

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

is_ready = False

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("Broker session established.")
        client.subscribe("home/system/status")
    else:
        print(f"Broker connection FAILED (rc={reason_code})")

# Handle the Ready message
def on_message(client, userdata, msg):
    global is_ready
    if msg.topic == "home/system/status":
            payload = msg.payload.decode("utf-8") == "ready"
            if payload == "ready":
                if not is_ready:
                      print("Server is ready, resuming.")
                is_ready = True
            elif payload == "offline":
                if is_ready:
                    print("Server has gone offline, pausing.")
                is_ready = False

def on_disconnect(client, userdata, flags, reason_code, properties):
    global is_ready
    print(f"DISCONNECTED (rc={reason_code}) — loop thread will auto-reconnect")
    is_ready = False

# MQTT set up
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2) # type: ignore
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_message = on_message
client.reconnect_delay_set(min_delay = 1, max_delay= 30)
client.connect_async(ADDRESS, PORT, 60)
client.loop_start()
print(f"Connected to MQTT broker. Pushing data to '{TOPIC}'...")

# Main functions

def read_uhf():
    found_tags = set() # a set ignores duplicates so I don't need to script that
    uhf.serial.reset_input_buffer() # type: ignore # clear out previous reads / junk etc
    
    uhf.multiple_read()  # type: ignore # Starts reading
    start_time = time.time() # gets the current time
    while time.time() - start_time < 1.0:
        read = uhf.read_mul() # type: ignore
        if read is not None:
            tag_id = ''.join(read[8:20])
            found_tags.add(tag_id)
        else:
            # trying to find the next '0xBB' start byte in case reading got interrupted
            if uhf.serial.in_waiting > 0: # type: ignore
                uhf.serial.read(1) # type: ignore

    uhf.stop_read()  # type: ignore # Ends the reading session
    return list(found_tags)

print("Waiting for main server to be ready...")
while not is_ready:
    time.sleep(0.5)
print("Server is ready! Initializing sensors.")

try:
    while True:
        
        # Check the server is ready, hang here if not
        if not is_ready:
            time.sleep(0.5)
            continue

        tags = read_uhf()
        number_of_tags = len(tags)
        
        if tags:
            print(f"{number_of_tags} tags scanned.")
            payload = tags
        else:
            print("No tags read.")
            payload = "uhf_empty"
            
        for attempt in range(3):
            result = client.publish(TOPIC, json.dumps(payload), qos=1)
            
            # wait_for_publish blocks until QoS 1 PUBACK is received or timeout is met
            result.wait_for_publish(timeout=1.0)
            
            if result.is_published():
                print(f"Sent: {payload}")
                break
                
            print(f"Publish failed, retrying...")
            time.sleep(1)
        else:
            print("Failed to send UHF read after retries")

        time.sleep(0.5)

except KeyboardInterrupt:
    print("\nDisconnecting...")

finally:
    client.loop_stop()
    client.disconnect()