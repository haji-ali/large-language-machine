# Powers the Raspberry Pi readers off, or reboots them, over MQTT.
#
#   reader-power.py listen             on each Pi (reader-power.service): carries
#                                      out the commands below
#   reader-power.py poweroff|reboot    tells every Pi to power off or reboot now;
#                                      poweroff waits until they have gone
#   reader-power.py pc-shutdown        on inference (shutdown-readers.service, as
#                                      the PC shuts down): does what
#                                      READERS_ON_PC_POWEROFF or
#                                      READERS_ON_PC_REBOOT in llm.conf says
#
# A Pi that has powered off stays off until its power is switched off and on.

import subprocess
import sys
import time
import paho.mqtt.client as mqtt # pyright: ignore[reportMissingImports]
import llm_config

config = llm_config.load()

PORT = config.integer("MQTT_PORT")
KEEPALIVE = 15
TOPIC_POWER = "home/system/power"
COMMANDS = ("poweroff", "reboot")
# After a Pi stops answering pings it still has to unmount its filesystems
HALT_GRACE = 5


def listen():
    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            client.subscribe(TOPIC_POWER, qos=1)
            print(f"Connected to the broker, waiting for commands on '{TOPIC_POWER}'.")
        else:
            print(f"Broker connection FAILED (rc={reason_code})")

    def on_message(client, userdata, msg):
        command = msg.payload.decode("utf-8", errors="replace").strip()
        # A retained command would power the Pi off again every time it boots
        if msg.retain:
            print(f"Ignoring retained command {command!r}.")
        elif command in COMMANDS:
            print(f"Received {command}, carrying it out.")
            subprocess.run(["systemctl", command], check=False)
        else:
            print(f"Ignoring unknown command {command!r}.")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2) # pyright: ignore[reportPrivateImportUsage]
    client.on_connect = on_connect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=10)
    # Connects in the background and keeps retrying, so the service can start
    # before the network or the broker is up
    client.connect_async(config.ip("inference"), PORT, KEEPALIVE)
    client.loop_forever(retry_first_connection=True)


def answers_ping(ips):
    """The subset of ips that answer a ping within a second."""
    timeout = ["-t", "1"] if sys.platform == "darwin" else ["-W", "1"]
    pings = {ip: subprocess.Popen(["ping", "-c", "1", *timeout, ip],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
             for ip in ips}
    return {ip for ip, p in pings.items() if p.wait() == 0}


def send(command, broker):
    """Sends command to every reader. For poweroff, waits until they stop answering pings."""
    readers = config.readers()
    up = answers_ping([m.ip for m in readers])
    for m in readers:
        print(f"{m.name} ({m.ip}): {'up' if m.ip in up else 'not answering, skipping'}")
    if not up:
        return 0

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2) # pyright: ignore[reportPrivateImportUsage]
    try:
        client.connect(broker, PORT, KEEPALIVE)
    except OSError as e:
        print(f"ERROR: cannot connect to the broker at {broker}:{PORT}: {e}")
        return 1
    client.loop_start()
    info = client.publish(TOPIC_POWER, command, qos=1)
    info.wait_for_publish(timeout=5)
    client.disconnect()
    client.loop_stop()
    if not info.is_published():
        print("ERROR: the broker did not acknowledge the command")
        return 1
    print(f"Sent {command} to the readers.")
    if command != "poweroff":
        return 0

    timeout = config.integer("READER_SHUTDOWN_TIMEOUT")
    start = time.monotonic()
    while up and time.monotonic() - start < timeout:
        still = answers_ping(up)
        for m in readers:
            if m.ip in up and m.ip not in still:
                print(f"{m.name} has shut down ({time.monotonic() - start:.0f} s).")
        up = still
        if up:
            time.sleep(1)
    if up:
        names = ", ".join(m.name for m in readers if m.ip in up)
        print(f"WARNING: still answering after {timeout} s: {names}")
        return 1
    time.sleep(HALT_GRACE)
    print("All readers have shut down.")
    return 0


def pc_shutdown():
    """Run as inference stops: acts only if the whole PC is powering off or rebooting."""
    jobs = subprocess.run(["systemctl", "list-jobs", "--no-legend"],
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True).stdout
    if "poweroff.target" in jobs or "halt.target" in jobs:
        setting = "READERS_ON_PC_POWEROFF"
    elif "reboot.target" in jobs or "kexec.target" in jobs:
        setting = "READERS_ON_PC_REBOOT"
    else:
        print("inference is not shutting down (the service was just stopped), leaving the readers alone.")
        return 0
    action = config.choice(setting, llm_config.POWER_ACTIONS)
    print(f"inference is shutting down; {setting} is {action}.")
    if action == "nothing":
        return 0
    # The broker runs on this machine
    return send(action, "localhost")


def main():
    mode = sys.argv[1] if len(sys.argv) == 2 else None
    if mode == "listen":
        listen()
    elif mode in COMMANDS:
        return send(mode, config.ip("inference"))
    elif mode == "pc-shutdown":
        return pc_shutdown()
    else:
        print(f"usage: {sys.argv[0]} listen | poweroff | reboot | pc-shutdown", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
