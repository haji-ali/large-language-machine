from gpiozero import MCP3008 # pyright: ignore[reportMissingImports]
import paho.mqtt.client as mqtt # pyright: ignore[reportMissingImports]
import json
from time import sleep

pot = MCP3008(channel=0)

# MQTT variables
ADDRESS = "100.85.109.22"
PORT = 2883
KEEPALIVE = 60
TOPIC = "home/sensors/temperature"

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect(ADDRESS, PORT, KEEPALIVE)
client.loop_start()

last_value = None

try:
    while True:
        val = pot.value
        if val != last_value:
            last_value = val
            print(f"Rotary: {val:.2f}", end="\r")

            payload = [val]
            client.publish(TOPIC, json.dumps(payload))
            print(f"Sent: {payload}")
        
        sleep(0.1)
        
except KeyboardInterrupt:
        print("\nStopping...")
        client.disconnect()