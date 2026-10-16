from gpiozero import LED, Button
import paho.mqtt.client as mqtt
import json
import socket
import time
import threading
from signal import pause

# MQTT variables
ADDRESS = "192.168.1.10"
PORT = 2883
KEEPALIVE = 15
TOPIC = "home/sensors/trigger"
TOPIC_STATUS = "home/system/status"
TOPIC_RESEND = "home/system/resend"
# "offline" is published by the broker (as the will) when this reader drops off
TOPIC_PRESENCE = f"home/readers/button@{socket.gethostname()}"

# Define the GPIO pins
button_led = LED(23)
push_button = Button(24, bounce_time=0.1)

is_ready = False

def button_flash(number_of_flashes, speed):
    for i in range(number_of_flashes):
        button_led.toggle()
        time.sleep(speed)

def flash_and_evaluate():
    button_flash(4, 0.15)
    if is_ready:
        button_led.on()
    else:
        button_led.off()

# Tells the main script this reader is connected, and from which address
def announce(client):
    client.publish(TOPIC_PRESENCE, client.socket().getsockname()[0], qos=1)

def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("Broker session established.")
        client.subscribe([(TOPIC_STATUS, 1), (TOPIC_RESEND, 1)])
        announce(client)
    else:
        print(f"Broker connection FAILED (rc={reason_code})")

# Handle the Ready or Busy message
def on_message(client, userdata, msg):
    global is_ready
    if msg.topic == TOPIC_RESEND:
        announce(client)
    elif msg.topic == TOPIC_STATUS:
            payload = msg.payload.decode("utf-8")
            if payload == "ready":
                if not is_ready:
                      print("Server is ready, resuming.")
                is_ready = True
                button_led.on()

            elif payload == "busy":
                is_ready = False
                threading.Thread(target=flash_and_evaluate).start()

            elif payload == "offline":
                if is_ready:
                    print("Server has gone offline, pausing.")
                is_ready = False
                button_led.off()

def on_disconnect(client, userdata, flags, reason_code, properties):
    global is_ready
    print(f"DISCONNECTED (rc={reason_code}) — no button triggers now.")
    is_ready = False
    button_led.off()

# Set up MQTT ONCE at startup
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2) # pyright: ignore[reportPrivateImportUsage]
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_message = on_message
client.will_set(TOPIC_PRESENCE, "offline", qos=1)
client.reconnect_delay_set(min_delay=1, max_delay=10)

# Connects in the background and keeps retrying, so the service can start
# before the network or the broker is up
client.connect_async(ADDRESS, PORT, KEEPALIVE)
client.loop_start() # Start the background thread
print(f"Connecting to external broker. Pushing data to '{TOPIC}'...")

print("Waiting for main server to be ready...")
while not is_ready:
    button_flash(2, 0.5)
    button_flash(6, 0.1)

if is_ready:
    button_led.on()
print("Server is ready! Initialising sensors.")

def button_press():
    global is_ready

    if is_ready:

        is_ready = False
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

    else:
        print("Button press ignored, server isn't ready.")

def button_release():
    pass

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