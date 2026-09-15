import sys
import paho.mqtt.client as mqtt  # pyright: ignore[reportMissingImports]
import json
import ollama # pyright: ignore[reportMissingImports]
import os
import concurrent.futures
from animation import ascii_animate
from pathlib import Path
from rich import print
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.align import Align
from rich import box
from time import sleep
from playsound3 import playsound
from threading import Timer
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

is_ready = False

uhf_count = 0
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
PORT = 2883
TOPIC_RFID = "home/sensors/rfid"
TOPIC_UHF = "home/sensors/uhf"
TOPIC_TRIGGER = "home/sensors/trigger"
TOPIC_TEMPERATURE = "home/sensors/temperature"

# Timeout setup for going back to start screen
idle_timer = None
TIMEOUT_SECONDS = 60.0

# Set initial start screen animation
start_screen_animation = 0


def animate(path: str):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    ascii_animate(data, delay=0.08)
    
def play_knob_sound(knob_val):
    if 0 <= knob_val < 0.1:
        playsound("Audio/Temp/Knob/knob_0.wav", block=False)
    elif 0.1 <= knob_val < 0.2:
        playsound("Audio/Temp/Knob/knob_1.wav", block=False)
    elif 0.2 <= knob_val < 0.3:
        playsound("Audio/Temp/Knob/knob_2.wav", block=False)
    elif 0.3 <= knob_val < 0.4:
        playsound("Audio/Temp/Knob/knob_3.wav", block=False)
    elif 0.4 <= knob_val < 0.5:
        playsound("Audio/Temp/Knob/knob_4.wav", block=False)
    elif 0.5 <= knob_val < 0.6:
        playsound("Audio/Temp/Knob/knob_5.wav", block=False)
    elif 0.6 <= knob_val < 0.7:
        playsound("Audio/Temp/Knob/knob_6.wav", block=False)
    elif 0.7 <= knob_val < 0.8:
        playsound("Audio/Temp/Knob/knob_7.wav", block=False)
    elif 0.8 <= knob_val < 0.9:
        playsound("Audio/Temp/Knob/knob_8.wav", block=False)
    elif 0.9 <= knob_val < 1:
        playsound("Audio/Temp/Knob/knob_9.wav", block=False)

def print_response(response):
    response_string = response['response']
    
    response_panel = Panel(response_string, width = 44, padding=(3,2), box=box.MINIMAL, style="reverse")
    centered_response = Align(response_panel, align="center", vertical="middle")
    
    console.clear()
    console.print(centered_response, height=19)

def ollama_request(prompt_dict):
    global last_response
    system = secret_rules + prompt_dict["rules"]  # Make the system prompt

    payload = {
        "model": prompt_dict["model"],
        "system": system,
        "prompt": prompt_dict["question"],
        "options": {"temperature": prompt_dict["temperature"]}
    }
    
    def _generate():
        return ollama.generate(**payload)

    try:
        # bringing in this concurrent.futures thing to enable a timeout on the ollama request
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_generate)
            response = future.result(timeout=20)
            
        if debug_mode:
            console.print(payload)
        print_response(response)
        last_response = response
        
    except concurrent.futures.TimeoutError:
        if debug_mode:
            console.print("ollama_request: ERROR. Inference timed out!")
        
        playsound("Audio/Temp/Error/error.wav", block=False)
        timeout_message = {"response": "ERROR! Something went wrong. \n\nTry again, and restart the Large Language Machine if it keeps happening."}
        print_response(timeout_message)
    
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
    global model, rules, question, temperature, previous_model, uhf_count, uhf_sensor, rfid_1_sensor, rfid_2_sensor
    
    new_uhf_count = uhf_count
    
    # if UHF reader sends uhf_empty then there are no Rules present in the bucket
    # so we need to clear the whole ruleset variable
    if tags == "uhf_empty":
        uhf_count = 0
        new_uhf_count = 0
        rules = []
        if debug_mode:
            console.print("No UHF tags, ruleset cleared.")
        # really not sure why I put a "return False" here but I think it's ruining things so commenting it out
        # return False
    
    else:
        # ok this gets confusing but first, check if any of the received tags are Rules
        # # and if so, we want to clear the ruleset and construct it from scratch
        # we also want to start counting how many tags are present in this read
        for tag in tags:     
            # check it's a valid tag
            tag_data = database["tags"].get(tag)
            if not tag_data or not isinstance(tag_data, dict):
                if debug_mode:
                    console.print(f"*Warning*: unregistered tag: {tag}")
                continue

            tag_type = tag_data["type"]

            if tag_type == "rule":
                if debug_mode:
                    console.print("UHF tags received.")
                uhf_sensor = True
                rules = []
                new_uhf_count = 0

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
                        # play a sound
                        playsound("Audio/Temp/Model/model_load.wav", block=False)
                        # do a loading animation because why not. This animation could signify loading data?
                        animate("Data/Animations/Data_Loading_01.json")
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
                    # log that we've added 1 to the tag count in this read
                    new_uhf_count = new_uhf_count + 1
                if debug_mode:
                    console.print(f"Added rule: {tag_display}")

            elif tag_type == "question":
                question = tag_value
                rfid_2_sensor = True
                playsound("Audio/Temp/Questions/question_load.wav", block=False)
                if debug_mode:
                    console.print(f"Question is: {tag_display}")
            else:
                if debug_mode:
                    console.print(f"Invalid tag: '{tag}' not found in database")
    
    # Compare new tag count to old tag count and play sounds if we've added or removed tags
    if new_uhf_count > uhf_count:
        if debug_mode:
            console.print(f"Tags have been added since last read, setting uhf_count to {new_uhf_count}")
        number_of_sounds = new_uhf_count - uhf_count
        for i in range(number_of_sounds):
            playsound("Audio/Temp/Rules/Out/rule_out_1.wav", block=False)
            sleep(0.1)
        uhf_count = new_uhf_count
    elif new_uhf_count < uhf_count:
        if debug_mode:
            console.print(f"Tags have been removed since last read, setting uhf_count to {new_uhf_count}")
        number_of_sounds = uhf_count - new_uhf_count
        for i in range(number_of_sounds):
            playsound("Audio/Temp/Rules/Out/rule_out_3.wav", block=False)
            sleep(0.1)
        uhf_count = new_uhf_count
    else:
        if debug_mode:
            console.print("UHF tag count stayed the same")
        

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

def show_start_screen():
    global start_screen_animation

    console.clear()
    reset_idle_timer()
    # Select a start screen animation, and then queue up a different one for next time
    if start_screen_animation == 0:
        animate("Data/Animations/Start_Screen_00.json")
        start_screen_animation = 1
    else:
        animate("Data/Animations/Start_Screen_01.json")
        start_screen_animation = 0

    # I reckon want to put something better in here, can adjust in situ
    ready_panel = Panel("Insert a question card and press GO", width=44, padding=(3,2))
    ready_centred = Align(ready_panel, align="center", vertical="middle")

    console.print(ready_centred, height=19)

def reset_idle_timer():
    global idle_timer

    if idle_timer is not None:
        idle_timer.cancel()

    idle_timer = Timer(TIMEOUT_SECONDS, show_start_screen)
    idle_timer.start()

def startup_checks(client, userdata, msg):
    global prompt, temperature, uhf_sensor, rfid_1_sensor, rfid_2_sensor, knob_sensor, test_mode, is_ready
    
    def test_update():
        console.clear()
        console.print(" ")
        console.print(" ")
        console.print("[bold]LARGE LANGUAGE MACHINE[/bold]", justify="center")
        console.print("Startup Test Sequence", justify="center")
        console.print(" ")
        console.print(" ")
        if is_ready:
            startup_table = Table(title="Network: ✅ ONLINE", show_lines=True, width=53)
        else:
            startup_table = Table(title="Network: ❌ OFFLINE", show_lines=True, width=53)
        startup_table.add_column("Status", justify="center")
        startup_table.add_column("Sensor", justify="center")
        startup_table.add_column("Data", justify="center")
        if uhf_sensor:
            startup_table.add_row("✅", "Rule ball reader", f"{uhf_count}")
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
            console.print(startup_table)
            console.print("[bold]All checks passed[/bold]", justify="center")
            console.print("[blink]PRESS BUTTON TO CONTINUE[/blink]", justify="center")
        else:
            console.print(startup_table)
        
    test_update()
    
    try:
        # Extract the payload immediately so it's available everywhere
        raw_payload = msg.payload.decode("utf-8").strip()

        if msg.topic == TOPIC_TRIGGER:
            console.clear()
            ready_panel = Panel("READY. PRESS BUTTON TO START", width = 44, padding=(3,2))
            ready_centered = Align(ready_panel, align="center", vertical="middle")
            
            test_mode = False
            
            console.print(ready_centered, height=19)
        
        elif msg.topic == TOPIC_TEMPERATURE:
            try:
                temp_data = json.loads(raw_payload)
                # not sure if the temperature data is coming thorugh as a string or float? trying to force a conversion here
                if isinstance(temp_data, list):
                    temperature = float(temp_data[0])
                else:
                    temperature = float(temp_data)
                knob_sensor = True
                # play sound matching knob value
                play_knob_sound(temperature)
                
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
    global is_ready
    
    try:
        # Extract the payload immediately so it's available everywhere
        raw_payload = msg.payload.decode("utf-8").strip()
        
        if debug_mode:
            console.print(f"Topic: {msg.topic} | Raw Payload: {raw_payload}")

        if msg.topic == TOPIC_TRIGGER:
            
            if prompt:
                # Let the button know we're busy so the light switches off
                client.publish("home/system/status", "busy", qos=1, retain=True)

                responding_sound = playsound("Audio/Temp/Response/responding.wav", block=False)
                animate("Data/Animations/Loading_01.json")

                # Starting the reset timer! Putting it here so it can catch failed inferences and reset if we're just left hanging
                reset_idle_timer()
                ollama_request(prompt)
                responding_sound.stop()
                playsound("Audio/Temp/Response/response.wav", block=False)

                # Broadcast ready state again
                client.publish("home/system/status", "ready", qos=1, retain=True)

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
                # not sure if the temperature data is coming thorugh as a string or float? trying to force a conversion here
                if isinstance(temp_data, list):
                    temperature = float(temp_data[0])
                else:
                    temperature = float(temp_data)
                # play sound matching knob value
                play_knob_sound(temperature)
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
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2) # pyright: ignore[reportPrivateImportUsage]

# Sending out a 'ready' message
def on_server_connect(client, userdata, flags, reason_code, properties):
    global is_ready

    if reason_code ==0:
        console.print("Connected to broker, sending out Ready state retained message.")
        client.publish("home/system/status", "ready", qos=1, retain=True)
        is_ready = True

client.on_connect = on_server_connect

# "Last will and testament" message if the script crashes:
client.will_set("home/system/status", payload="offline", qos=1, retain=True)

console.print(f"Connecting to Broker at {BROKER_ADDRESS}...")
client.connect(BROKER_ADDRESS, PORT, 60)
client.subscribe([(TOPIC_RFID, 0), (TOPIC_UHF, 0), (TOPIC_TRIGGER, 0), (TOPIC_TEMPERATURE, 0)])

console.print(f"Listening for updates on '{TOPIC_RFID}', '{TOPIC_UHF}', {TOPIC_TRIGGER} and '{TOPIC_TEMPERATURE}'...")

def on_message(client, userdata, msg):
    if test_mode:
        startup_checks(client, userdata, msg)
    else:
        main_message_handler(client, userdata, msg)

client.on_message = on_message
try:
    client.loop_forever()
except KeyboardInterrupt:
    console.print("\nShutting down. Broadcasting offline state.")
    client.publish("home/system/status", "offline", qos=1, retain=True)
    client.disconnect()