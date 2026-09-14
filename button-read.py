from gpiozero import LED, Button
import paho.mqtt.client as mqtt
import json
import time
from signal import pause

# MQTT variables
ADDRESS = "192.168.1.10"
PORT = 2883
KEEPALIVE = 60
TOPIC = "home/sensors/trigger"

# Define the GPIO pins
button_led = LED(23)
push_button = Button(24, bounce_time=0.1)

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
    print(f"DISCONNECTED (rc={reason_code}) — no button triggers now.")
    is_ready = False

# Set up MQTT ONCE at startup
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2) # pyright: ignore[reportPrivateImportUsage]
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_message = on_message
client.reconnect_delay_set(min_delay=1, max_delay=30)
client.connect_async(ADDRESS, PORT, KEEPALIVE)

client.loop_start() # Start the background thread
print(f"Connected to external broker. Pushing data to '{TOPIC}'...")

print("Waiting for main server to be ready...")
while not is_ready:
    time.sleep(0.5)
print("Server is ready! Initializing sensors.")

def button_press():

    if not is_ready:
        print("Button press ignored, server isn't ready.")
        return

    button_led.off()
    print("button pressed!")
    
    payload = ["TRIGGER"]

    for attempt in range(3):
        result = client.publish(TOPIC, json.dumps(payload))
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"Sent: {payload}")
            break
        print(f"Publish failed (rc={result.rc}), retrying.")
        time.sleep(1)
    else:
        print("WARNING: failed to send TRIGGER after retries")

def button_release():
    button_led.on()

push_button.when_pressed = button_press
push_button.when_released = button_release

print("Waiting.")

try:
    pause()
except KeyboardInterrupt:
    print("\nDisconnecting...")
finally:
    client.loop_stop()
    client.disconnect()