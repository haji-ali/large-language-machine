# Tasks: listen on MQTT
# convert tags received into strings via their reference in json
# 

import paho.mqtt.client as mqtt
import json

BROKER_ADDRESS = "localhost"
TOPIC1 = "home/sensors/rfid"
TOPIC2 = "home/sensors/uhf"

# A function to parse data from a json

# A function to compose received data into a prompt

# This is our main function receiving the data
def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode('utf-8')
        data = json.loads(payload)
        print(f"Received Data: {data}")
        
    except Exception as e:
        print(f"Error parsing message: {e}")

# Set up MQTT client
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_message = on_message

print(f"Connecting to Broker at {BROKER_ADDRESS}...")
client.connect(BROKER_ADDRESS, 2883, 60)
client.subscribe([(TOPIC1,0), (TOPIC2,0)])

print(f"Listening for updates on '{TOPIC1}' and '{TOPIC2}'...")

# Loop Forever
client.loop_forever()