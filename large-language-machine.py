import sys
import paho.mqtt.client as mqtt  # pyright: ignore[reportMissingImports]
import json
import ollama
import os
from animation import ascii_animate
from pathlib import Path
from rich import print
from time import sleep

# handle script being launched in debug mode (ie. `python3 large-language-machine.py debug`)
debug_mode = False
if len(sys.argv) > 1 and sys.argv[1] == "debug":
    debug_mode = True
print("Debug mode:", debug_mode)

# Initialise the global prompt variables
prompt = []
model = ""
rules = []
question = ""
temperature = 0.3

# Bring the tags data in from Data/database.json as a variable called tags
BASE = Path(__file__).resolve().parent
DATA_FILE = BASE / "Data" / "database.json"
with DATA_FILE.open(encoding="utf-8") as f:
    database = json.load(f)
if debug_mode:
    print("----------------------------------------------")
    print(database)
    print("----------------------------------------------")

# Ollama setup
secret_rules = database["setup"]["secret_rules"]

# MQTT setup
BROKER_ADDRESS = "localhost"
TOPIC1 = "home/sensors/rfid"
TOPIC2 = "home/sensors/uhf"
TOPIC3 = "home/sensors/trigger"
TOPIC4 = "home/sensors/temperature"

def animate(path: str):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    ascii_animate(data, delay=0.08)

def ollama_request(prompt_dict):
    system = secret_rules + prompt_dict["rules"]  # Make the system prompt

    payload = {
        "model": prompt_dict["model"],
        "system": system,
        "prompt": prompt_dict["question"],
        "options": {"temperature": prompt_dict["temperature"]},
    }

    try:
        response = ollama.generate(**payload)
        if debug_mode:
            print(payload)
        os.system('clear')
        print("---------------------------------------------------------")
        print("---------------------------------------------------------")
        print("---------------------------------------------------------")
        print("---------------------------------------------------------")
        print("---------------------------------------------------------")
        print("---------------------------------------------------------")
        print("---------------------------------------------------------")
        print("---------------------------------------------------------")
        print("---------------------------------------------------------")
        print("---------------------------------------------------------")
        print("---------------------------------------------------------")
        print("---------------------------------------------------------")
        print("---------------------------------------------------------")
        print("---------------------------------------------------------")
        print("---------------------------------------------------------")
        print("---------------------------------------------------------")
        print("---------------------------------------------------------")
        print("---------------------------------------------------------")
        print("---------------------------------------------------------")
        print("---------------------------------------------------------")
        print("---------------------------------------------------------")
        print("---------------------------------------------------------")
        print("---------------------------------------------------------")
        print("---------------------------------------------------------")
        print("---------------------------------------------------------")
        print("---------------------------------------------------------")
        print("---------------------------------------------------------")
        print("---------------------------------------------------------")
        print("---------------------------------------------------------")
        print("---------------------------------------------------------")
        sleep(0.2)
        os.system('clear')
        print("---------------------------------------------------------")
        print(response['response'])
        print("---------------------------------------------------------")
    except Exception as e:
        print(f"Ollama API request failed. Error: {e}")
    return


def compose_prompt(tags):
    global model, rules, question, temperature
    
    # if UHF reader sends uhf_empty then there are no Rules present in the bucket
    # so we need to clear the whole ruleset variable

    if tags == "uhf_empty":
        rules = []
        if debug_mode:
            print("No UHF tags, ruleset cleared.")
        return False
    
    # ok this gets confusing but first, check if any of the received tags are Rules
    # # and if so, we want to clear the ruleset and construct it from scratch
    for tag in tags:
        
        # check it's a valid tag
        tag_data = database["tags"].get(tag)
        if not tag_data:
            print(f"*Warning*: unregistered tag: {tag}")
            continue

        tag_type = tag_data["type"]

        if tag_type == "rule":
            if debug_mode:
                print("UHF tags received.")
            rules = []

    # and now start again, iterating through each tag and mapping it to the correct property
    for tag in tags:

        # check it's a valid tag (have to do this again in case we're looking at RFIDs this time)
        tag_data = database["tags"].get(tag)
        if not tag_data:
            if debug_mode:
                print(f"*Error*: '{tag}' not found in database.")
            continue

        tag_type = tag_data["type"]
        tag_value = tag_data["value"]
        tag_display = tag_data["display"]

        if tag_type == "model":
            model = tag_value
            if debug_mode:
                print(f"Model: {tag_display}")

        elif tag_type == "rule":
            if tag_value not in rules:
                rules.append(tag_value)
            if debug_mode:
                print(f"Added rule: {tag_display}")

        elif tag_type == "question":
            question = tag_value
            if debug_mode:
                print(f"Question is: {tag_display}")
        else:
            if debug_mode:
                print(f"Invalid tag: '{tag}' not found in database")

    # 2026-04-19 Pretty sure the below line was idiotic because sometimes rules will be empty!! Removed it
    ### if model and rules and question and temperature is not None:
    if model and question and temperature is not None:
        if rules is not None:
            rules_string = " ".join(rules)
        else:
            rules_string = ""
            
        composed_prompt = {
            "model": model,
            "rules": rules_string,
            "question": question,
            "temperature": temperature,
        }
        if debug_mode:
            print("Prompt updated:")
            print(composed_prompt)
        return composed_prompt
    else:
        if debug_mode:
            if model is None:
                print('Incomplete prompt: no model')
            if question is None:
                print('Incomplete prompt: no question')
            if temperature is None:
                print('Incomplete prompt: no temperature')
        return False


# MQTT data handling when received
def on_message(client, userdata, msg):
    global prompt
    global temperature
    
    try:
        # Extract the payload immediately so it's available everywhere
        raw_payload = msg.payload.decode("utf-8").strip()
        
        if debug_mode:
            print(f"Topic: {msg.topic} | Raw Payload: {raw_payload}")

        if msg.topic == TOPIC3:
            # if it's a trigger:
            if prompt:
                animate("Data/Animations/Loading_01.json")
                ollama_request(prompt)
            else:
                if debug_mode:
                    print("on_message(): No inference triggered because there's no prompt data.")
            return
        
        elif msg.topic == TOPIC4:
            # set temperature if that's what we got!
            if debug_mode:
                print(f"received temperature data: {raw_payload}")
            try:
                temp_data = json.loads(raw_payload)
                temperature = temp_data[0] if isinstance(temp_data, list) else float(temp_data)
            except (json.JSONDecodeError, ValueError, IndexError):
                temperature = 0.8
            return
        else:
            # Try to parse as JSON for tag lists, fallback to raw string for single tags
            try:
                data = json.loads(raw_payload)
            except json.JSONDecodeError:
                data = [raw_payload] # Treat single tag string as a list of one
            
            if debug_mode:
                print(f"Received Data: {data}")
            
            new_prompt = compose_prompt(data)
            if new_prompt:
                prompt = new_prompt

    except Exception as e:
        print(f"on_message(): Error parsing message: {e}")


# Set up MQTT client
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_message = on_message

print(f"Connecting to Broker at {BROKER_ADDRESS}...")
client.connect(BROKER_ADDRESS, 2883, 60)
client.subscribe([(TOPIC1, 0), (TOPIC2, 0), (TOPIC3, 0), (TOPIC4, 0)])

print(f"Listening for updates on '{TOPIC1}', '{TOPIC2}', {TOPIC3} and '{TOPIC4}'...")

# Loop Forever
client.loop_forever()
