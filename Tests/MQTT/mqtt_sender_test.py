import paho.mqtt.client as mqtt
import time
import json
import random

BROKER_ADDRESS = "100.111.176.116"
TOPIC = "home/sensors/pi_data"

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect(BROKER_ADDRESS, 1883, 60)

print(f"Connected to external broker. Pushing data to '{TOPIC}'...")

try:
    while True:
        payload = {
            "temperature": round(random.uniform(20.0, 30.0), 2),
            "humidity": round(random.uniform(40.0, 60.0), 2),
            "status": "OK"
            }
        
        client.publish(TOPIC, json.dumps(payload))
        print(f"Sent: {payload}")
        
        time.sleep(2)
        
except KeyboardInterrupt:
    print("Stopping...")
    client.disconnect()