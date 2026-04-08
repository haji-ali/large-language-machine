# Tasks: listen on MQTT
# convert tags received into strings via their reference in json
# compile a prompt using strings
# send prompt to Ollama and print results

# Example of how Python sees tags.json (as the variable database):
# {'120304F906EA': {'type': 'model', 'value': 'qwen3:8b', 'display': 'Qwen 3', 'description': 'Qwen3 is the latest generation of large language models in Qwen series, offering a comprehensive suite of dense and mixture-of-experts (MoE) models.'}, '120304E49C6D': {'type': 'model', 'value': 'gemma3:4b', 'display': 'Gemma 3', 'description': 'The current, most capable model that runs on a single GPU.'}, '120304E49564': {'type': 'model', 'value': 'ministral-3:3b', 'display': 'Ministral 3', 'description': 'The Ministral 3 family is designed for edge deployment, capable of running on a wide range of hardware.'}, '120304F93BD7': {'type': 'model', 'value': 'phi3.5:3.8b', 'display': 'Phi 3.5', 'description': 'A lightweight AI model with 3.8 billion parameters with performance overtaking similarly and larger sized models.'}, 'e28011700000021acd079101': {'type': 'rule', 'display': "Talk like you're really really smart", 'value': 'Respond as if you were an extremely intelligent individual, with wild flourishes and verbose language, letting everyone know how smart you are.'}, 'e28069950000500a27a50a50': {'type': 'rule', 'display': "Don't say anything good about pizza", 'value': 'You hate pizza. You never say anything positive about pizza, and you like to disparage it wherever you can.'}, 'e28011700000021acd079111': {'type': 'rule', 'display': 'Respond with a poem', 'value': 'You deliver every response in the form of a rhyming poem.'}, 'e28069950000400a27a51650': {'type': 'rule', 'display': 'Talk like Super Mario', 'value': 'Always reply in the voice of Super Mario.'}, 'ee28069950000400a27a51a50': {'type': 'rule', 'display': 'Be happy', 'value': 'Your responses are EXTREMELY cheerful, smiling and cheering and whooping because you are very very happy and nothing can keep you from expressing your happiness.'}, 'e28069950000400a27a50e50': {'type': 'rule', 'display': 'Be sad', 'value': 'Your responses are VERY sad, mournful, doleful and miserable because you are very very sad and nothing can keep you from expressing your deep melancholy.'}, 'e28069950000500a27a51250': {'type': 'rule', 'display': 'Be ANGRY', 'value': "You're SUPER angry! All of your responses are dripping with rage and nothing can keep you from expressing your deep resentment."}, '0E00728ED725': {'type': 'question', 'display': 'What will the future be like?', 'value': 'What will the future be like?'}, '0E00728F3BC8': {'type': 'question', 'display': 'Is climate change real?', 'value': 'Is climate change real?'}, '4C00BD86B3C4': {'type': 'question', 'display': "What's better to eat, pizza or washing-up liquid?", 'value': "What's better to eat, pizza or washing-up liquid?"}}

import paho.mqtt.client as mqtt  # pyright: ignore[reportMissingImports]
import json
import ollama
from pathlib import Path
from rich import print

debug_mode = False

# Initialise the global prompt variables
prompt = []
model = ""
rules = []
question = ""

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
temperature = 0 # default value is 0, maybe should change this but good for debugging I guess?

# MQTT setup
BROKER_ADDRESS = "localhost"
TOPIC1 = "home/sensors/rfid"
TOPIC2 = "home/sensors/uhf"
TOPIC3 = "home/sensors/trigger"
TOPIC4 = "home/sensors/temperature"


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
        print("---------------------------------------------------------")
        print(response['response'])
        print("---------------------------------------------------------")
    except Exception as e:
        print(f"Ollama API request failed. Error: {e}")
    return


def compose_prompt(tags):
    global model, rules, question, temperature

    if tags == "uhf_empty":
        rules = []
        if debug_mode:
            print("compose_prompt(): No UHF tags, ruleset cleared.")
        return False
    
    # First step: check if any of the received tags are Rules
    # # and if so, we want to clear the ruleset and construct it from scratch   
    for tag in tags:
        
        # check it's a valid tag
        tag_data = database["tags"].get(tag)
        if not tag_data:
            print(f"compose_prompt(): '{tag}' not found in database.")
            continue

        tag_type = tag_data["type"]

        if tag_type == "rule":
            if debug_mode:
                print("UHF check: UHF tags received, emptying the `rules` variable")
            rules = []

    # and now start again, iterating through each tag and mapping it to the correct property
    for tag in tags:

        # check it's a valid tag (have to do this again in case we're looking at RFIDs this time)
        tag_data = database["tags"].get(tag)
        if not tag_data:
            print(f"compose_prompt(): '{tag}' not found in database.")
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


    if model and rules and question and temperature:
        rules_string = " ".join(rules)
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
            print('compose_prompt(): Not enough data received to put a full prompt together.')
        return False


# MQTT data handling when received
def on_message(client, userdata, msg):
    global prompt
    global temperature

    try:
        if msg.topic == TOPIC3:
            # if it's a trigger:
            payload = msg.payload.decode("utf-8").strip()
            if prompt:
                ollama_request(prompt)
            else:
                if debug_mode:
                    print("on_message(): No inference triggered because there's no prompt data.")
            return
        elif msg.topic == TOPIC4:
            # set temperature if that's what we got!
            print("received temperature data:")
            if msg.payload:
                payload = msg.payload.decode("utf-8").strip()
                print(payload)
                temperature = payload
            return
        else:
            # Try to parse as JSON for tag lists, fallback to raw string for single tags
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                data = [payload] # Treat single tag string as a list of one
            
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
