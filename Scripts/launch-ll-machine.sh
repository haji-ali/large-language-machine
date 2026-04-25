#!/usr/bin/env bash
#   launch-ll-machine.sh
# This script gets run by the systemd service launch-ll-machine.service
# (hopefully) in a full screen terminal window

VENV_ACTIVATE=~/large-language-machine/venv/bin/activate

LLM_SCRIPT=~/large-language-machine/large-language-machine.py

cd ~/large-language-machine

# Activate the virtual environment
source "$VENV_ACTIVATE"

# Now run the Python program
exec python3 "$LLM_SCRIPT"