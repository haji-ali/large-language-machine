from gpiozero import MCP3008 # pyright: ignore[reportMissingImports]
from time import sleep

rotary_pot = MCP3008(channel=0)

try:
    while True:
        rotary_val = rotary_pot.value
        
        print(f"Rotary: {rotary_val:.2f}", end="\r")
        
        sleep(0.1)
        
except KeyboardInterrupt:
        print("\nStopping...")