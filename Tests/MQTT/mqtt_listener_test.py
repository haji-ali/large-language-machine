import paho.mqtt.client as mqtt
import json

# 1. Configuration
BROKER_ADDRESS = "localhost"
TOPIC1 = "home/sensors/rfid"
TOPIC2 = "home/sensors/uhf"

# 2. The Callback Function (What to do when data arrives)
def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode('utf-8')
        data = json.loads(payload)
        print(f"Received Data: {data}")
        
    except Exception as e:
        print(f"Error parsing message: {e}")

# 3. Setup the Client
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_message = on_message

print(f"Connecting to Broker at {BROKER_ADDRESS}...")
client.connect(BROKER_ADDRESS, 2883, 60)

# 4. Subscribe to the topics
client.subscribe([(TOPIC1,0), (TOPIC2,0)])
print(f"Listening for updates on '{TOPIC1}' and '{TOPIC2}'...")

# 5. Loop Forever (Handles network reconnects automatically)
client.loop_forever()