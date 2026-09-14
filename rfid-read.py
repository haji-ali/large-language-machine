import serial
import paho.mqtt.client as mqtt
import time
import json

# MQTT variables
ADDRESS = "192.168.1.10"
TOPIC = "home/sensors/rfid"
PORT = 2883

def on_connect(client, userdata, flags, reason_code, properties):
    print(f"Broker connected (rc={reason_code})")

def on_disconnect(client, userdata, flags, reason_code, properties):
    print(f"DISCONNECTED (rc={reason_code}) — auto-reconnecting")

# MQTT set up — async so the service can start before the broker is up
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2) # pyright: ignore[reportPrivateImportUsage]
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.reconnect_delay_set(min_delay=1, max_delay=30)
client.connect_async(ADDRESS, PORT, 60)
client.loop_start()
print(f"Connecting to MQTT broker. Pushing data to '{TOPIC}'...")

# Open Serial once, rather than inside the loop
with serial.Serial("/dev/ttyS0", baudrate=9600, timeout=1) as ser:
    i = 1
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    while True:
        print(f'Read #{i}')

        # Read 12 characters
        data = ser.read(12)

        if data and data != b"000000000000":
            decoded_data = data.decode("utf-8").strip()
            print(f"Read {i}: {decoded_data}")

            payload = [decoded_data]

            for attempt in range(3):
                result = client.publish(TOPIC, json.dumps(payload), qos=1)
                result.wait_for_publish(timeout=2.0) # Wait up to 2 seconds for the broker ACK
                
                if result.is_published():
                    print(f"Sent: {payload}")
                    break
                    
                print("Publish failed or timed out, retrying...")
                time.sleep(1)
            else:
                print("Failed to send RFID read after retries")

            # Flush to keep the buffer clean for the next physical tag swipe
            ser.reset_input_buffer()
        else:
            # Small delay to prevent CPU pinning if no data is present
            time.sleep(0.1)

        i += 1