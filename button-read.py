from gpiozero import LED, Button
import paho.mqtt.client as mqtt
import json
from signal import pause

# MQTT variables
ADDRESS = "192.168.1.10"
PORT = 2883
KEEPALIVE = 60
TOPIC = "home/sensors/trigger"

# Define the GPIO pins
button_led = LED(23)
push_button = Button(24, bounce_time=0.1)

# Set up MQTT ONCE at startup
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect(ADDRESS, PORT, KEEPALIVE)
client.loop_start() # Start the background thread
print(f"Connected to external broker. Pushing data to '{TOPIC}'...")

def button_press():
    button_led.off()
    print("button pressed!")
    
    payload = ["TRIGGER"]
    client.publish(TOPIC, json.dumps(payload))
    print(f"Sent: {payload}")

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