import serial
import paho.mqtt.client as mqtt
import time
import json

# MQTT variables
ADDRESS = "192.168.1.10"
TOPIC = "home/sensors/rfid"
PORT = 2883

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
            payload = msg.payload.decode("utf-8")
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
    print(f"DISCONNECTED (rc={reason_code}) — loop thread will auto-reconnect")
    is_ready = False

# MQTT set up — async so the service can start before the broker is up
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2) # pyright: ignore[reportPrivateImportUsage]
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_message = on_message
client.reconnect_delay_set(min_delay=1, max_delay=30)
client.connect_async(ADDRESS, PORT, 60)
client.loop_start()
print(f"Connecting to MQTT broker. Pushing data to '{TOPIC}'...")

# Open Serial immediately to initialize the hardware pins
with serial.Serial("/dev/ttyS0", baudrate=9600, timeout=1) as ser:
    i = 1
    # Give the serial port a brief moment to settle on cold boot, then flush
    time.sleep(1)
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    
    print("Serial port open. Waiting for server to be ready...")

    while True:
        # Check the server is ready
        if not is_ready:
            # If a user swipes while offline, silently flush it so it isn't 
            # stored and accidentally sent the moment the server comes online.
            if ser.in_waiting > 0:
                ser.reset_input_buffer()
            time.sleep(0.5)
            continue
        
        waiting = ser.in_waiting

        if waiting >= 12:
            # We have at least a full 12-character tag in the buffer
            data = ser.read(12)

            if data and data != b"000000000000":
                decoded_data = data.decode("utf-8", errors="ignore").strip()
                print(f"Read {i}: {decoded_data}")

                payload = [decoded_data]

                for attempt in range(3):
                    result = client.publish(TOPIC, json.dumps(payload), qos=1)
                    result.wait_for_publish(timeout=2.0)  # Wait up to 2 seconds for broker ACK
                    
                    if result.is_published():
                        print(f"Sent: {payload}")
                        break
                        
                    print("Publish failed or timed out, retrying...")
                    time.sleep(1)
                else:
                    print("Failed to send RFID read after retries")

            # Clear out any trailing bytes to prevent framing desync on the next swipe
            ser.reset_input_buffer()
            i += 1

        elif waiting > 0:
            # Bytes exist, but fewer than 12.
            # Allow a short delay to see if the rest of the 12-byte payload is mid-transmission
            time.sleep(0.1)
            if ser.in_waiting < 12:
                # Still incomplete. This is boot noise/partial byte drift; discard it.
                ser.reset_input_buffer()

        else:
            # No data waiting; idle briefly to prevent pinning CPU core
            time.sleep(0.1)