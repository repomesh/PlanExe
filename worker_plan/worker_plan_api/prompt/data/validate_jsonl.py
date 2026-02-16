"""Validate each row of simple_plan_prompts.jsonl as JSON.

Checks:
  1. Each non-empty line must be valid JSON.
  2. Line break style must be consistent across the file (LF, CRLF, etc.).

Usage:
    python validate_jsonl.py
"""
import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
JSONL_PATH = os.path.join(SCRIPT_DIR, "simple_plan_prompts.jsonl")


def check_line_breaks(path: str) -> bool:
    """Check that all line breaks use the same style. Returns True if consistent."""
    with open(path, "rb") as f:
        data = f.read()

    breaks: dict[str, list[int]] = {}
    i = 0
    line = 1
    while i < len(data):
        if data[i : i + 2] == b"\r\n":
            breaks.setdefault("CRLF", []).append(line)
            line += 1
            i += 2
        elif data[i : i + 2] == b"\n\r":
            breaks.setdefault("LFCR", []).append(line)
            line += 1
            i += 2
        elif data[i] == 0x0D:
            breaks.setdefault("CR", []).append(line)
            line += 1
            i += 1
        elif data[i] == 0x0A:
            breaks.setdefault("LF", []).append(line)
            line += 1
            i += 1
        else:
            i += 1

    if len(breaks) == 0:
        print("Line breaks: none found (single-line file).")
        return True

    if len(breaks) == 1:
        style, lines = next(iter(breaks.items()))
        print(f"Line breaks: all {style} ({len(lines)} occurrences) — consistent.")
        return True

    print("Line breaks: INCONSISTENT styles detected!")
    for style in sorted(breaks):
        lines = breaks[style]
        sample = lines[:20]
        suffix = f" ... and {len(lines) - 20} more" if len(lines) > 20 else ""
        print(f"  {style}: {len(lines)} occurrences — lines {sample}{suffix}")
    return False


def check_json(path: str) -> bool:
    """Check that every non-empty line is valid JSON. Returns True if all valid."""
    errors: list[tuple[int, str]] = []
    total = 0

    with open(path, "r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            stripped = line.rstrip("\n\r")
            if not stripped:
                continue
            total += 1
            try:
                json.loads(stripped)
            except json.JSONDecodeError as e:
                errors.append((line_number, str(e)))

    if errors:
        print(f"JSON: found {len(errors)} invalid line(s) out of {total}:")
        for line_number, msg in errors:
            print(f"  Line {line_number}: {msg}")
        return False

    print(f"JSON: all {total} lines are valid.")
    return True


def main() -> None:
    ok = True
    ok = check_line_breaks(JSONL_PATH) and ok
    ok = check_json(JSONL_PATH) and ok
    if ok:
        print("PASS")
    else:
        print("FAIL")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
