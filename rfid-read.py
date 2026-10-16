import serial
import paho.mqtt.client as mqtt
import time
import json
import socket

# MQTT variables
ADDRESS = "192.168.1.10"
PORT = 2883
KEEPALIVE = 15
TOPIC = "home/sensors/rfid"
TOPIC_STATUS = "home/system/status"
TOPIC_RESEND = "home/system/resend"
# "offline" is published by the broker (as the will) when this reader drops off
TOPIC_PRESENCE = f"home/readers/rfid@{socket.gethostname()}"

is_ready = False
# Set when the server needs the last tag again (it has just come online or asked for it)
resend_requested = False

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

# Handle the Ready message
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

# MQTT set up — connects in the background and keeps retrying, so the
# service can start before the network or the broker is up
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2) # pyright: ignore[reportPrivateImportUsage]
client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.on_message = on_message
client.will_set(TOPIC_PRESENCE, "offline", qos=1)
client.reconnect_delay_set(min_delay=1, max_delay=10)
client.connect_async(ADDRESS, PORT, KEEPALIVE)
client.loop_start()
print(f"Connecting to MQTT broker. Pushing data to '{TOPIC}'...")

print("Doing a 3-sec wait to help the RFID hardware stabilise after boot...")
time.sleep(3)

def publish_tag(tag):
    payload = [tag]

    for attempt in range(3):
        result = client.publish(TOPIC, json.dumps(payload), qos=1)
        result.wait_for_publish(timeout=2.0)  # Wait up to 2 seconds for broker ACK

        if result.is_published():
            print(f"Sent: {payload}")
            return True

        print("Publish failed or timed out, retrying...")
        time.sleep(1)

    print("Failed to send RFID read after retries")
    return False

# Open Serial immediately to initialize the hardware pins
with serial.Serial("/dev/ttyS0", baudrate=9600, timeout=1) as ser:
    i = 1

    # The card or tube currently in the slot, as far as we know. Only the most
    # recent read is kept, so a swipe made while the server is offline is sent
    # once it is back, and earlier swipes are dropped.
    last_tag = None
    send_pending = False

    ser.reset_input_buffer()
    ser.reset_output_buffer()

    # Dummy read to force out any leftover/wedged bits stuck in the pipe
    if ser.in_waiting > 0:
        ser.read(ser.in_waiting)

    print("Serial port open. Waiting for tags...")

    while True:
        waiting = ser.in_waiting

        if waiting >= 12:
            # We have at least a full 12-character tag in the buffer
            data = ser.read(12)

            if data and data != b"000000000000":
                last_tag = data.decode("utf-8", errors="ignore").strip()
                send_pending = True
                print(f"Read {i}: {last_tag}")

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

        if resend_requested:
            resend_requested = False
            if last_tag is not None:
                send_pending = True

        if send_pending and is_ready:
            send_pending = not publish_tag(last_tag)
