from gpiozero import MCP3008 # pyright: ignore[reportMissingImports]
import paho.mqtt.client as mqtt # pyright: ignore[reportMissingImports]
import json
from time import sleep

pot = MCP3008(channel=0)

# MQTT variables
ADDRESS = "192.168.1.10"
PORT = 2883
KEEPALIVE = 60
TOPIC = "home/sensors/temperature"

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2) # pyright: ignore[reportPrivateImportUsage]
client.connect(ADDRESS, PORT, KEEPALIVE)
client.loop_start()

last_value = None

try:
    while True:
        # Fix because I wired the pot the wrong way – need to invert the number
        val = 1 - pot.value
        rounded_val = round(val,1)
        if rounded_val != last_value:
            last_value = rounded_val
            payload = [rounded_val]
            client.publish(TOPIC, json.dumps(payload))
            print(f"Sent: {payload}")
        
        sleep(0.1)
        
except KeyboardInterrupt:
        print("\nStopping...")
        client.disconnect()