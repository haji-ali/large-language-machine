#!/usr/bin/env python3
"""
txt2json.py – bundle all .txt files in a directory into a single JSON file.

Usage:
    python txt2json.py [--src DIR] [--out FILE] [--strip-ext] [--encoding ENC]

Examples:
    # Basic usage – read from current dir, write to texts.json
    python txt2json.py

    # Read from /path/to/txts and write to output.json
    python txt2json.py --src /path/to/txts --out output.json

    # Strip the .txt suffix from keys
    python txt2json.py --strip-ext
"""

import argparse
import json
import pathlib
import sys

def parse_args():
    parser = argparse.ArgumentParser(description="Convert many .txt files into one JSON object.")
    parser.add_argument("--src", "-s", default=".", help="Source directory (default: current directory)")
    parser.add_argument("--out", "-o", default="texts.json", help="Output JSON file (default: texts.json)")
    parser.add_argument("--strip-ext", "-x", action="store_true", help="Remove the .txt suffix from keys")
    parser.add_argument("--encoding", "-e", default="utf-8", help="File encoding (default: utf-8)")
    return parser.parse_args()

def main():
    args = parse_args()
    src_dir = pathlib.Path(args.src).resolve()

    if not src_dir.is_dir():
        print(f"Error: {src_dir} is not a directory.", file=sys.stderr)
        sys.exit(1)

    # Find all .txt files
    txt_files = sorted(src_dir.glob("*.txt"))
    if not txt_files:
        print(f"No .txt files found in {src_dir}", file=sys.stderr)
        sys.exit(1)

    json_dict = {}
    for txt_path in txt_files:
        key = txt_path.name
        if args.strip_ext and key.lower().endswith(".txt"):
            key = key[:-4]  # strip 4 characters: .txt

        # Read file content (preserve newlines)
        try:
            content = txt_path.read_text(encoding=args.encoding)
        except Exception as e:
            print(f"Error reading {txt_path}: {e}", file=sys.stderr)
            continue

        json_dict[key] = content

    # Dump to JSON
    out_path = pathlib.Path(args.out).resolve()
    try:
        out_path.write_text(json.dumps(json_dict, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"JSON written to {out_path}")
    except Exception as e:
        print(f"Error writing JSON to {out_path}: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()