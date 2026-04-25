import sys
import paho.mqtt.client as mqtt  # pyright: ignore[reportMissingImports]
import json
import ollama # pyright: ignore[reportMissingImports]
import os
from animation import ascii_animate
from pathlib import Path
from rich import print
from rich.console import Console
from rich.table import Table
from time import sleep
console=Console()

# handle script being launched in debug mode (ie. `python3 large-language-machine.py debug`)
debug_mode = False
if len(sys.argv) > 1 and sys.argv[1] == "debug":
    debug_mode = True
console.print("Debug mode:", debug_mode)

# Initialise the global variables
prompt = []
model = ""
rules = []
question = ""
temperature = 0.3

uhf_sensor = False
rfid_1_sensor = False
rfid_2_sensor = False
knob_sensor = False   

# Variables for logic etc
previous_model = ""
last_response = ""

# Always want to start in test mode
test_mode = True

# Bring the tags data in from Data/database.json as a variable called tags
BASE = Path(__file__).resolve().parent
DATA_FILE = BASE / "Data" / "database.json"
with DATA_FILE.open(encoding="utf-8") as f:
    database = json.load(f)
if debug_mode:
    console.print("------------------------------------")
    console.print(database)
    console.print("------------------------------------")

# Ollama setup
secret_rules = database["setup"]["secret_rules"]

# MQTT setup
BROKER_ADDRESS = "localhost"
TOPIC_RFID = "home/sensors/rfid"
TOPIC_UHF = "home/sensors/uhf"
TOPIC_TRIGGER = "home/sensors/trigger"
TOPIC_TEMPERATURE = "home/sensors/temperature"


def animate(path: str):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    ascii_animate(data, delay=0.08)

def print_response(response):
    console.clear()
    console.print("-----------------------------------------------------")
    console.print("-----------------------------------------------------")
    console.print(response['response'])
    console.print("-----------------------------------------------------")
    console.print("-----------------------------------------------------")

def ollama_request(prompt_dict):
    global last_response
    system = secret_rules + prompt_dict["rules"]  # Make the system prompt

    payload = {
        "model": prompt_dict["model"],
        "system": system,
        "prompt": prompt_dict["question"],
        "options": {"temperature": prompt_dict["temperature"]}
    }

    try:
        response = ollama.generate(**payload)
        if debug_mode:
            console.print(payload)
        print_response(response)
        last_response = response
    except Exception as e:
        print(f"Ollama API request failed. Error: {e}")
    return

def ollama_load_model(model):
    payload = {
        "model": model,
        "system": "Respond only with the word 'ok'",
        "prompt": "Say the word 'ok'. Do not respond with anything else.",
        "options": {"temperature": "0"}
    }
    try:
        ollama.generate(**payload)
        return True
    except Exception as e:
        if debug_mode:
            console.print(f"Failed to pre-load model: {model}")
        return False


def compose_prompt(tags):
    global model, rules, question, temperature, previous_model, uhf_sensor, rfid_1_sensor, rfid_2_sensor
    
    # if UHF reader sends uhf_empty then there are no Rules present in the bucket
    # so we need to clear the whole ruleset variable
    if tags == "uhf_empty":
        rules = []
        if debug_mode:
            console.print("No UHF tags, ruleset cleared.")
        return False
    
    # ok this gets confusing but first, check if any of the received tags are Rules
    # # and if so, we want to clear the ruleset and construct it from scratch
    for tag in tags:     
        # check it's a valid tag
        tag_data = database["tags"].get(tag)
        if not tag_data or not isinstance(tag_data, dict):
            print(f"*Warning*: unregistered tag: {tag}")
            continue

        tag_type = tag_data["type"]

        if tag_type == "rule":
            if debug_mode:
                print("UHF tags received.")
            uhf_sensor = True
            rules = []

    # and now start again, iterating through each tag and mapping it to the correct property
    for tag in tags:

        # check it's a valid tag (have to do this again in case we're looking at RFIDs this time)
        tag_data = database["tags"].get(tag)
        if not tag_data or not isinstance(tag_data, dict):
            if debug_mode:
                console.print(f"*Error*: '{tag}' not found in database.")
            continue

        tag_type = tag_data["type"]
        tag_value = tag_data["value"]
        tag_display = tag_data["display"]

        if tag_type == "model":
            model = tag_value
            rfid_1_sensor = True
            
            # See if the model has changed since the last tag read or not
            # But only if there *is* a previous model, we get an error if there's no previous data
            if previous_model == "":
                if debug_mode:
                    console.print(f"(pre-loading {model})")
                ollama_load_model(model)
                previous_model = model
            else:
                if debug_mode:
                    console.print("`previous_model` contains data.")
                if model != previous_model:
                    if debug_mode:
                        console.print("`model` is not the same as `previous_model`.")
                    # Send a dummy request to pre-load this model
                    ollama_load_model(model)
                    previous_model = model
                    # do a loading animation because why not. This animation could signify loading data?
                    animate("Data/Animations/Loading_01.json")
                    # And reload the last response after the animation
                    print_response(last_response)
                    
                    if debug_mode:
                        console.print(f"Model: {tag_display}")
                else:
                    if debug_mode:
                        console.print("`model` IS the same as `previous_model`")

        elif tag_type == "rule":
            if tag_value not in rules:
                rules.append(tag_value)
            if debug_mode:
                console.print(f"Added rule: {tag_display}")

        elif tag_type == "question":
            question = tag_value
            rfid_2_sensor = True
            if debug_mode:
                console.print(f"Question is: {tag_display}")
        else:
            if debug_mode:
                console.print(f"Invalid tag: '{tag}' not found in database")

    # 2026-04-19 Pretty sure the below line was idiotic because sometimes rules will be empty!! Removed it
    ### if model and rules and question and temperature is not None:
    # sometimes temperature is 0.0 which it will think is None too, duh
    # if model and question and temperature is not None:
    # strip to basics, we only need model and question to generate a response
    if model and question is not None:
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
            console.print("Prompt updated:")
            console.print(composed_prompt)
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

def startup_checks(client, userdata, msg):
    global prompt, temperature, uhf_sensor, rfid_1_sensor, rfid_2_sensor, knob_sensor, test_mode
    
    def test_update():
        console.clear()
        console.print(" ")
        console.print(" ")
        console.print("[bold]LARGE LANGUAGE MACHINE[/bold]", justify="center")
        console.print("Startup Test Sequence", justify="center")
        console.print(" ")
        console.print(" ")
        startup_table = Table(title="Sensor status", show_lines=True, width=53)
        startup_table.add_column("Status", justify="center")
        startup_table.add_column("Sensor", justify="center")
        startup_table.add_column("Data", justify="center")
        if uhf_sensor:
            startup_table.add_row("✅", "Rule ball reader", "")
        else:
            startup_table.add_row("❌", "Rule ball reader", "")
        if rfid_1_sensor:
            startup_table.add_row("✅", "Dataset tube reader", "")
        else:
            startup_table.add_row("❌", "Dataset tube reader", "")
        if rfid_2_sensor:
            startup_table.add_row("✅", "Question cards reader", "")
        else:
            startup_table.add_row("❌", "Question cards reader", "")
        if knob_sensor:
            startup_table.add_row(f"✅", "Temperature knob", f"{temperature}")
        else:
            startup_table.add_row("❌", "Temperature knob", f"{temperature}")
        if uhf_sensor and rfid_1_sensor and rfid_2_sensor and knob_sensor:
            startup_status = Table(title=None, width=53)
            startup_status.add_column()
            startup_status.add_row("[bold]All checks passed[/bold]")
            startup_status.add_row("[blink]PRESS BUTTON TO START[/blink]")
            console.print(startup_table)
            console.print(startup_status)
        else: 
            console.print(startup_table)
    test_update()
    
    try:
        # Extract the payload immediately so it's available everywhere
        raw_payload = msg.payload.decode("utf-8").strip()

        if msg.topic == TOPIC_TRIGGER:
            console.clear()
            # animate("Data/Animations/Loading_01.json")
            console.print(" ")
            console.print(" ")
            console.print("Press button again to start")
            test_mode = False
        
        elif msg.topic == TOPIC_TEMPERATURE:
            try:
                temp_data = json.loads(raw_payload)
                temperature = temp_data[0] if isinstance(temp_data, list) else float(temp_data)
                knob_sensor = True
            except (json.JSONDecodeError, ValueError, IndexError):
                temperature = 0.8
                test_update()
            return
        else:
            # Try to parse as JSON for tag lists, fallback to raw string for single tags
            try:
                data = json.loads(raw_payload)
            except json.JSONDecodeError:
                data = [raw_payload] # Treat single tag string as a list of one
            
            if debug_mode:
                console.print(f"Received Data: {data}")
            
            new_prompt = compose_prompt(data)
            test_update()
            if new_prompt:
                prompt = new_prompt

    except Exception as e:
        console.print(f"Warning: Error parsing message: {e}")
    

def main_message_handler(client, userdata, msg):
    global prompt
    global temperature
    
    try:
        # Extract the payload immediately so it's available everywhere
        raw_payload = msg.payload.decode("utf-8").strip()
        
        if debug_mode:
            console.print(f"Topic: {msg.topic} | Raw Payload: {raw_payload}")

        if msg.topic == TOPIC_TRIGGER:
            
            if prompt:
                animate("Data/Animations/Loading_01.json")
                ollama_request(prompt)
            else:
                if debug_mode:
                    console.print("TW No inference triggered because there's no prompt data.")
            return
        
        elif msg.topic == TOPIC_TEMPERATURE:
            # set temperature if that's what we got!
            if debug_mode:
                console.print(f"received temperature data: {raw_payload}")
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
                console.print(f"Received Data: {data}")
            
            new_prompt = compose_prompt(data)
            if new_prompt:
                prompt = new_prompt

    except Exception as e:
        console.print(f"Warning: Error parsing message: {e}")


# Set up MQTT client
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)


console.print(f"Connecting to Broker at {BROKER_ADDRESS}...")
client.connect(BROKER_ADDRESS, 2883, 60)
client.subscribe([(TOPIC_RFID, 0), (TOPIC_UHF, 0), (TOPIC_TRIGGER, 0), (TOPIC_TEMPERATURE, 0)])

console.print(f"Listening for updates on '{TOPIC_RFID}', '{TOPIC_UHF}', {TOPIC_TRIGGER} and '{TOPIC_TEMPERATURE}'...")

def on_message(client, userdata, msg):
    if test_mode:
        startup_checks(client, userdata, msg)
    else:
        main_message_handler(client, userdata, msg)

client.on_message = on_message
client.loop_forever()