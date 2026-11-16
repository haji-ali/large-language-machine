"""Reads llm.conf, the configuration shared by every Large Language Machine script.

    import llm_config
    config = llm_config.load()
    config.ip("inference")          # an address from the MACHINES table
    config.integer("MQTT_PORT")

llm.conf is also sourced by the shell scripts, so only the part of shell syntax
that means the same in both is accepted: KEY=value lines, comments, and values
in double quotes (no $, ` or \\) or single quotes (taken literally).

Run `python3 llm_config.py` to check llm.conf and print what it contains.
"""

import ipaddress
import os
import re
import sys
from pathlib import Path

CONFIG_FILE = Path(os.environ.get("LLM_CONFIG", Path(__file__).resolve().parent / "llm.conf"))

POWER_ACTIONS = ("poweroff", "reboot", "nothing")

_ASSIGNMENT = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=(.*)")


class ConfigError(Exception):
    pass


class Machine:
    def __init__(self, name, ip, services):
        self.name = name
        self.ip = ip
        self.services = services

    def __repr__(self):
        return f"Machine({self.name!r}, {self.ip!r}, {self.services!r})"


def parse(text, source="llm.conf"):
    """Returns the KEY=value assignments in text as a dict of strings."""
    values = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        lineno = i + 1
        line = lines[i].strip()
        i += 1
        if not line or line.startswith("#"):
            continue
        match = _ASSIGNMENT.fullmatch(line)
        if not match:
            raise ConfigError(f"{source}:{lineno}: expected KEY=value, got {line!r}")
        key, rest = match.groups()

        if rest[:1] in ("'", '"'):
            quote, body = rest[0], rest[1:]
            # A quoted value can continue over several lines
            while quote not in body:
                if i >= len(lines):
                    raise ConfigError(f"{source}:{lineno}: {key} has no closing {quote}")
                body += "\n" + lines[i]
                i += 1
            value, _, after = body.partition(quote)
            after = after.strip()
            if after and not after.startswith("#"):
                raise ConfigError(f"{source}:{lineno}: unexpected {after!r} after {key}'s closing quote")
            if quote == '"' and re.search(r"[$`\\]", value):
                raise ConfigError(f"{source}:{lineno}: {key} contains $, ` or \\; use single quotes")
        else:
            value = re.split(r"\s+#", rest, maxsplit=1)[0].strip()
            if re.search(r"[\s$`\\'\"]", value):
                raise ConfigError(f"{source}:{lineno}: put {key}'s value in quotes")
        values[key] = value
    return values


class Config:
    def __init__(self, values, source="llm.conf"):
        self.values = values
        self.source = source
        self._machines = None

    def text(self, key):
        try:
            return self.values[key]
        except KeyError:
            raise ConfigError(f"{self.source} does not set {key}") from None

    def integer(self, key):
        try:
            return int(self.text(key))
        except ValueError:
            raise ConfigError(f"{self.source}: {key} should be a whole number, not {self.text(key)!r}") from None

    def number(self, key):
        try:
            return float(self.text(key))
        except ValueError:
            raise ConfigError(f"{self.source}: {key} should be a number, not {self.text(key)!r}") from None

    def choice(self, key, options):
        value = self.text(key)
        if value not in options:
            raise ConfigError(f"{self.source}: {key} should be one of {', '.join(options)}, not {value!r}")
        return value

    @property
    def machines(self):
        """The MACHINES table as a dict of Machine, in the order listed."""
        if self._machines is None:
            machines = {}
            for row in self.text("MACHINES").splitlines():
                fields = row.split("#", 1)[0].split()
                if not fields:
                    continue
                if len(fields) != 3:
                    raise ConfigError(f"{self.source}: MACHINES rows need a name, an IP address and "
                                      f"comma-separated services: {row.strip()!r}")
                name, ip, services = fields
                try:
                    ipaddress.ip_address(ip)
                except ValueError:
                    raise ConfigError(f"{self.source}: {ip!r} (machine {name}) is not an IP address") from None
                if name in machines:
                    raise ConfigError(f"{self.source}: machine {name} is listed twice in MACHINES")
                machines[name] = Machine(name, ip, services.split(","))
            self._machines = machines
        return self._machines

    def ip(self, machine):
        try:
            return self.machines[machine].ip
        except KeyError:
            raise ConfigError(f"{self.source}: MACHINES has no machine called {machine!r}") from None

    def readers(self):
        """Every machine except inference: the Raspberry Pis."""
        return [m for m in self.machines.values() if m.name != "inference"]


def load(path=CONFIG_FILE):
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigError(f"cannot read {path}: {e.strerror}") from None
    return Config(parse(text, path.name), path.name)


def check(config):
    """Reads every setting the scripts use, raising ConfigError for the first bad one."""
    for name in ("inference", "uhf", "rfid-dataset", "button-knob", "rfid-questions"):
        config.ip(name)
    for key in ("WIFI_SSID", "SSH_USER", "LLM_DIR", "VENV_DIR", "READER_PYTHON",
                "RFID_SERIAL_PORT", "UHF_SERIAL_PORT", "BROKER_SERVICE"):
        if not config.text(key):
            raise ConfigError(f"{config.source}: {key} is empty")
    ipaddress.ip_address(config.text("ROUTER_IP"))
    for key in ("MQTT_PORT", "BUTTON_PIN", "BUTTON_LED_PIN", "KNOB_ADC_CHANNEL", "UHF_ENABLE_PIN"):
        config.integer(key)
    for key in ("IDLE_TIMEOUT", "INFERENCE_TIMEOUT"):
        config.number(key)
    if not 0 <= config.integer("READER_SHUTDOWN_TIMEOUT") <= 100:
        raise ConfigError(f"{config.source}: READER_SHUTDOWN_TIMEOUT should be between 0 and 100")
    for key in ("READERS_ON_PC_POWEROFF", "READERS_ON_PC_REBOOT"):
        config.choice(key, POWER_ACTIONS)


def main():
    try:
        config = load()
        check(config)
    except ConfigError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    if "--quiet" not in sys.argv[1:]:
        for key, value in config.values.items():
            if key != "MACHINES":
                print(f"{key} = {value}")
        print("MACHINES:")
        for m in config.machines.values():
            print(f"  {m.name:<15} {m.ip:<15} {', '.join(m.services)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
