#!/usr/bin/env bash
#   launch-ll-machine.sh
# This script gets run by the systemd service launch-ll-machine.service
# (hopefully) in a full screen terminal window.
# The program is restarted whenever it crashes or is killed (Scripts/install.sh
# kills it to load new code). Ctrl+C exits it cleanly and drops to a shell.

VENV_ACTIVATE=~/large-language-machine/venv/bin/activate

LLM_SCRIPT=~/large-language-machine/large-language-machine.py

cd ~/large-language-machine

# Activate the virtual environment
source "$VENV_ACTIVATE"

# Tells Scripts/install.sh that this loop will restart the program
export LLM_SUPERVISED=1

while true; do
    python3 "$LLM_SCRIPT"
    status=$?
    [ "$status" -eq 0 ] && break
    echo "large-language-machine.py stopped (exit status $status), restarting in 3 seconds..."
    sleep 3
done
