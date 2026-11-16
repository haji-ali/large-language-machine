import paho.mqtt.client as mqtt
import json
import llm_config

config = llm_config.load()

BROKER_ADDRESS = config.ip("inference")
TOPIC = "home/sensors/trigger"

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect(BROKER_ADDRESS, config.integer("MQTT_PORT"), 60)

print(f"Connected to external broker. Pushing data to '{TOPIC}'...")

payload = ["TRIGGER"]
client.publish(TOPIC, json.dumps(payload))
print(f"Sent: {payload}")
client.disconnect()