import serial           # type: ignore #import serial module
import paho.mqtt.client as mqtt
import time
import json

# MQTT variables
BROKER_ADDRESS = "100.85.109.22"
TOPIC = "home/sensors/rfid"

# MQTT set up
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect(BROKER_ADDRESS, 2883, 60)
print(f"Connected to MQTT broker. Pushing data to '{TOPIC}'...")

# Open the port ONCE at the start
# We add a small timeout (0.1) so it never gets stuck forever
ser = serial.Serial("/dev/ttyS0", baudrate=9600, timeout=0.1)

def poll_rfid():
    # 1. Look at the mailbox (buffer)
    # Does it have at least 12 bytes waiting?
    if ser.in_waiting >= 12:
        # 2. Read the 12 bytes
        data = ser.read(12)
        try:
            tag = data.decode("utf-8").strip()
            
            # 3. IMMEDIATELY FLUSH
            # Because it's one-shot, we clear any junk or 
            # accidental double-reads so the NEXT poll starts fresh.
            ser.reset_input_buffer()
            
            return tag
        except Exception as e:
            print(f"Read error: {e}")
            ser.reset_input_buffer()
            return None
            
    return None

# --- Main Loop ---
while True:
    print("Checking for tag...")
    tag = poll_rfid()
    
    if tag:
        print(f"Tag Detected: {tag}")
        client.publish(TOPIC, json.dumps(tag))
    else:
        # Instead of getting stuck, we just say 'Nothing here'
        print("No tag present in buffer.")
        client.publish(TOPIC, "none")
    
    # 4. Your Intermittent Delay
    # You can set this to 1, 5, or 60 seconds. 
    # The script will stay completely responsive.
    time.sleep(2)