from gpiozero import LED, Button  # pyright: ignore[reportMissingImports]
import paho.mqtt.client as mqtt
import json
from signal import pause

# MQTT variables
BROKER_ADDRESS = "100.85.109.22"
TOPIC = "home/sensors/trigger"
PORT = 2883

# Define the GPIO pins
button_led = LED(23)    # Connected to GPIO 23 (Pin 16)
push_button = Button(24, bounce_time=0.1)  # Connected to GPIO 24 (Pin 18) and bounce_time stops it firing tonnes of messages


def button_press():
    button_led.off()
    print("button pressed!")
    
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(BROKER_ADDRESS, 2883, 60)

    print(f"Connected to external broker. Pushing data to '{TOPIC}'...")

    payload = ["TRIGGER"]
    client.publish(TOPIC, json.dumps(payload))
    print(f"Sent: {payload}")
    client.disconnect()
    

def button_release():
    button_led.on()


push_button.when_pressed = button_press
push_button.when_released = button_release

print("Waiting.")

# Keep the script running
pause()
