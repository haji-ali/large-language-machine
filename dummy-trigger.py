import paho.mqtt.client as mqtt
import json

BROKER_ADDRESS = "192.168.1.10"
TOPIC = "home/sensors/trigger"

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect(BROKER_ADDRESS, 2883, 60)

print(f"Connected to external broker. Pushing data to '{TOPIC}'...")

payload = ["TRIGGER"]
client.publish(TOPIC, json.dumps(payload))
print(f"Sent: {payload}")
client.disconnect()