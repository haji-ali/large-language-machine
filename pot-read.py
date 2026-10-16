from gpiozero import MCP3008 # pyright: ignore[reportMissingImports]
import paho.mqtt.client as mqtt # pyright: ignore[reportMissingImports]
import json
from time import sleep
import socket

pot = MCP3008(channel=0)

# MQTT variables
ADDRESS = "192.168.1.10"
PORT = 2883
KEEPALIVE = 15
TOPIC = "home/sensors/temperature"
TOPIC_STATUS = "home/system/status"
TOPIC_RESEND = "home/system/resend"
# "offline" is published by the broker (as the will) when this reader drops off
TOPIC_PRESENCE = f"home/readers/pot@{socket.gethostname()}"

is_ready = False
# Set when the server needs the knob position again (it has just come online or asked for it)
resend_requested = False

# Tells the main script this reader is connected, and from which address
def announce(client):
    client.publish(TOPIC_PRESENCE, client.socket().getsockname()[0], qos=1)

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("Connected to the broker.")
        client.subscribe([(TOPIC_STATUS, 1), (TOPIC_RESEND, 1)])
        announce(client)
    else:
        print(f"Broker connection FAILED! (rc={reason_code})")

def on_message(client, userdata, msg):
    global is_ready, resend_requested
    if msg.topic == TOPIC_STATUS:
            payload = msg.payload.decode("utf-8")
            if payload == "ready":
                if not is_ready:
                      print("Server is ready, resuming.")
                      resend_requested = True
                is_ready = True
            elif payload == "offline":
                if is_ready:
                    print("Server has gone offline, pausing.")
                is_ready = False
    elif msg.topic == TOPIC_RESEND:
        resend_requested = True
        announce(client)

def on_disconnect(client, userdata, flags, reason_code, properties):
    global is_ready
    print(f"DISCONNECTED (rc={reason_code}) — loop thread will auto-reconnect")
    is_ready = False

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2) # pyright: ignore[reportPrivateImportUsage]

client.on_connect = on_connect
client.on_message = on_message
client.will_set(TOPIC_PRESENCE, "offline", qos=1)
client.on_disconnect = on_disconnect
client.reconnect_delay_set(min_delay=1, max_delay=10)
client.connect_async(ADDRESS, PORT, KEEPALIVE)
client.loop_start()

last_value = None

print("Waiting for server to spin up...")
while not is_ready:
    sleep(0.5)
print("Server is ready, starting reads.")

try:
    while True:

        # Check the server is ready, hang here if not
        if not is_ready:
            sleep(0.5)
            continue

        if resend_requested:
            resend_requested = False
            last_value = None

        # Fix because I wired the pot the wrong way, now have to invert the number. Sorry x
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