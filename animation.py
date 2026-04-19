import json
import os
import time
from typing import Any

def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")

def ascii_animate(obj: Any, delay: float = 1.0) -> None:
    """
    Recursively walk a JSON‑like structure (dict / list) and print every
    scalar value (i.e., not a dict or list).

    Parameters
    ----------
    obj : Any
        The JSON data to traverse.
    delay : float
        Seconds to pause after each printed value (default 1.0).
    """
    if isinstance(obj, dict):
        for value in obj.values():
            ascii_animate(value, delay)
    elif isinstance(obj, list):
        for item in obj:
            ascii_animate(item, delay)
    else:
        clear_screen()
        print(obj)
        time.sleep(delay)

# ---- CLI helper (kept only for running as a script) ----
def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)

def _main() -> None:
    import argparse, sys
    parser = argparse.ArgumentParser(
        description="Display each scalar value in a JSON file, one at a time."
    )
    parser.add_argument("json_file", help="Path to the JSON file.")
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Seconds to pause between values (default 1.0)",
    )
    args = parser.parse_args()

    try:
        data = _load_json(args.json_file)
    except Exception as exc:
        print(f"Error reading JSON file: {exc}", file=sys.stderr)
        sys.exit(1)

    ascii_animate(data, delay=args.delay)
    print("\nAll values displayed.")

if __name__ == "__main__":
    _main()