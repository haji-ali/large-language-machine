# Tasks: listen on MQTT
# convert tags received into strings via their reference in json
# compile a prompt using strings
# send prompt to Ollama and print results

# Example of how Python sees tags.json (as the variable tags_dict):
# {'120304F906EA': {'type': 'model', 'value': 'qwen3:8b', 'display': 'Qwen 3', 'description': 'Qwen3 is the latest generation of large language models in Qwen series, offering a comprehensive suite of dense and mixture-of-experts (MoE) models.'}, '120304E49C6D': {'type': 'model', 'value': 'gemma3:4b', 'display': 'Gemma 3', 'description': 'The current, most capable model that runs on a single GPU.'}, '120304E49564': {'type': 'model', 'value': 'ministral-3:3b', 'display': 'Ministral 3', 'description': 'The Ministral 3 family is designed for edge deployment, capable of running on a wide range of hardware.'}, '120304F93BD7': {'type': 'model', 'value': 'phi3.5:3.8b', 'display': 'Phi 3.5', 'description': 'A lightweight AI model with 3.8 billion parameters with performance overtaking similarly and larger sized models.'}, 'e28011700000021acd079101': {'type': 'rule', 'display': "Talk like you're really really smart", 'value': 'Respond as if you were an extremely intelligent individual, with wild flourishes and verbose language, letting everyone know how smart you are.'}, 'e28069950000500a27a50a50': {'type': 'rule', 'display': "Don't say anything good about pizza", 'value': 'You hate pizza. You never say anything positive about pizza, and you like to disparage it wherever you can.'}, 'e28011700000021acd079111': {'type': 'rule', 'display': 'Respond with a poem', 'value': 'You deliver every response in the form of a rhyming poem.'}, 'e28069950000400a27a51650': {'type': 'rule', 'display': 'Talk like Super Mario', 'value': 'Always reply in the voice of Super Mario.'}, 'ee28069950000400a27a51a50': {'type': 'rule', 'display': 'Be happy', 'value': 'Your responses are EXTREMELY cheerful, smiling and cheering and whooping because you are very very happy and nothing can keep you from expressing your happiness.'}, 'e28069950000400a27a50e50': {'type': 'rule', 'display': 'Be sad', 'value': 'Your responses are VERY sad, mournful, doleful and miserable because you are very very sad and nothing can keep you from expressing your deep melancholy.'}, 'e28069950000500a27a51250': {'type': 'rule', 'display': 'Be ANGRY', 'value': "You're SUPER angry! All of your responses are dripping with rage and nothing can keep you from expressing your deep resentment."}, '0E00728ED725': {'type': 'question', 'display': 'What will the future be like?', 'value': 'What will the future be like?'}, '0E00728F3BC8': {'type': 'question', 'display': 'Is climate change real?', 'value': 'Is climate change real?'}, '4C00BD86B3C4': {'type': 'question', 'display': "What's better to eat, pizza or washing-up liquid?", 'value': "What's better to eat, pizza or washing-up liquid?"}}

import paho.mqtt.client as mqtt  # pyright: ignore[reportMissingImports]
import json
import ollama # need to install on Inference machine venv!
from pathlib import Path

# Ollama setup
secret_rules = "Provide a concise response of less than 30 words. EXTREMELY IMPORTANT: Your responses will be viewed by children so must be appropriate for all ages and use clean, family-friendly language and themes."
# Initialise the prompt variables
prompt = []
model = ""
rules = []
question = ""
temperature = "0.75"

# Bring the tags data in from Data/tags.json as a variable called tags
BASE = Path(__file__).resolve().parent
DATA_FILE = BASE / "Data" / "tags.json"
with DATA_FILE.open(encoding="utf-8") as f:
    tags_dict = json.load(f)
print("----------------------------------------------")
print(tags_dict)
print("----------------------------------------------")

BROKER_ADDRESS = "localhost"
TOPIC1 = "home/sensors/rfid"
TOPIC2 = "home/sensors/uhf"

def ollama_request(prompt_dict):
    system = secret_rules + prompt_dict["rules"] # Make the system prompt

    payload = {
        "model": prompt_dict["model"],
        "system": system,
        "prompt": prompt_dict["question"],
        "options": {"temperature": prompt_dict["temperature"]}
    }

    ## Need to finish this, been using this: https://dev.to/rosgluk/integrating-ollama-with-python-rest-api-and-python-client-examples-56hk

def compose_prompt(tags):

    for tag in tags:
        try:
            type = tags_dict[tag["type"]]
        except KeyError:
            print("KeyError when finding tag in database, is it invalid?")
        if type == "model":
            model = tags_dict[tag["value"]]
            print(f"Model: {tags_dict[tag["display"]]}")
        elif type == "rule":
            rules.append(tags_dict[tag["value"]])
            print(f"Added rule: {tags_dict[tag["display"]]}")
        elif type == "question":
            question = tags_dict[tag["value"]]
            print(f"Question is: {tags_dict[tag["display"]]}")
        else:
            print("Invalid tag, not found in database")

    prompt = {"model": model, "rules": rules, "question": question, "temperature":temperature}
    return prompt

# MQTT data handling when received
def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode("utf-8")
        data = json.loads(payload)
        print(f"Received Data: {data}")

    except Exception as e:
        print(f"Error parsing message: {e}")


# Set up MQTT client
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_message = on_message

print(f"Connecting to Broker at {BROKER_ADDRESS}...")
client.connect(BROKER_ADDRESS, 2883, 60)
client.subscribe([(TOPIC1, 0), (TOPIC2, 0)])

print(f"Listening for updates on '{TOPIC1}' and '{TOPIC2}'...")

# Loop Forever
client.loop_forever()

## have made a mistake while writing this I think, I was imagining that the prompt
# would be constructed every time an MQTT message is received but actually we only
# need to re-initialise the rules list, not the others.
# So needs a process to reinitialise rules IF the message received is from the UHF reader.s