import serial
import paho.mqtt.client as mqtt
import time
import json

# MQTT variables
ADDRESS = "192.168.1.10"
TOPIC = "home/sensors/rfid"
PORT = 2883

# MQTT set up
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

try:
    client.connect(ADDRESS, PORT, 60)
    # This starts a background thread to handle reconnects and data buffers
    client.loop_start() 
    print(f"Connected to MQTT broker. Pushing data to '{TOPIC}'...")

    # Open Serial once, rather than inside the loop
    with serial.Serial("/dev/ttyS0", baudrate=9600, timeout=1) as ser:
        i = 1
        while True:
            print(f'Read #{i}')
            
            # Read 12 characters
            data = ser.read(12)
            
            if data and data != b"000000000000":
                decoded_data = data.decode("utf-8").strip()
                print(f"Read {i}: {decoded_data}")
                
                payload = [decoded_data]
                # The background loop ensures this actually reaches the broker
                client.publish(TOPIC, json.dumps(payload))
                
                # Flush to keep the buffer clean for the next physical tag swipe
                ser.reset_input_buffer()
            else:
                # Small delay to prevent CPU pinning if no data is present
                time.sleep(0.1)
            
            i += 1

except KeyboardInterrupt:
    print("\nDisconnecting...")
finally:
    client.loop_stop()
    client.disconnect()
    print("Cleanup complete.")