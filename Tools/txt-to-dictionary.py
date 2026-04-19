#!/usr/bin/env python3
"""
load_txt_files.py

Load all *.txt files in a folder into a single dictionary.

Usage
-----
    python load_txt_files.py /path/to/txt/folder [--parse] [--sep SEPARATOR]

Options
-------
--parse          : Treat each file as a key/value list and build a nested dict.
--sep SEPARATOR  : Character(s) that separate key and value inside each line
                   (default is ':').
"""

import argparse
import pathlib
import sys
from typing import Dict, Any


def load_txt_files_to_dict(
    folder_path: pathlib.Path,
    parse: bool = False,
    separator: str = ":",
) -> Dict[str, Any]:
    """
    Walk through `folder_path`, find all *.txt files, and return a dictionary.

    Parameters
    ----------
    folder_path : pathlib.Path
        Path to the directory that contains the .txt files.
    parse : bool, optional
        If True, treat each file as a key/value list.  Each line must contain
        `separator`.  Lines that are empty or start with `#` are ignored.
    separator : str, optional
        The string that separates keys and values inside each line when
        `parse=True`.

    Returns
    -------
    dict
        Mapping from file‑stem (file name without extension) to either:
        * the raw file text (str) if parse=False, or
        * a nested dict of key/value pairs if parse=True.
    """
    result: Dict[str, Any] = {}

    for txt_file in folder_path.glob("*.txt"):
        # Read the file content
        try:
            txt_file_text = txt_file.read_text(encoding="utf-8")
        except Exception as exc:
            print(f"⚠️  Could not read {txt_file}: {exc}", file=sys.stderr)
            continue

        key = txt_file.stem  # file name without the extension

        if parse:
            nested: Dict[str, str] = {}
            for line_number, line in enumerate(txt_file_text.splitlines(), start=1):
                stripped = line.strip()

                # Skip empty lines and comments
                if not stripped or stripped.startswith("#"):
                    continue

                if separator not in stripped:
                    print(
                        f"⚠️  Skipping line {line_number} in {txt_file} – "
                        f"no separator '{separator}' found.",
                        file=sys.stderr,
                    )
                    continue

                k, v = stripped.split(separator, 1)
                nested[k.strip()] = v.strip()

            result[key] = nested
        else:
            result[key] = txt_file_text

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert all .txt files in a folder into a single dictionary."
    )
    parser.add_argument(
        "folder",
        type=pathlib.Path,
        help="Path to the folder containing the .txt files",
    )
    parser.add_argument(
        "--parse",
        action="store_true",
        help="Treat each file as a key/value list instead of raw text.",
    )
    parser.add_argument(
        "--sep",
        default=":",
        help="Separator between key and value when parsing (default: ':').",
    )
    args = parser.parse_args()

    if not args.folder.is_dir():
        print(f"❌ {args.folder!s} is not a directory.", file=sys.stderr)
        sys.exit(1)

    data = load_txt_files_to_dict(args.folder, parse=args.parse, separator=args.sep)

    # Pretty‑print the resulting dictionary
    import json

    print(json.dumps(data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()