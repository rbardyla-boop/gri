#!/usr/bin/env python3
import re
from pathlib import Path

PLACEHOLDER = re.compile(r"\[([^\]]+)\]")

def render_consent(skeleton: Path, values: dict, forbidden_tokens=()):
    text = skeleton.read_text(encoding="utf-8")
    def replace(match):
        key = match.group(1)
        value = values.get(key)
        if not isinstance(value, str) or not value or "UNRESOLVED" in value:
            raise ValueError(f"unresolved consent placeholder: {key}")
        return value
    rendered = PLACEHOLDER.sub(replace, text)
    if "UNRESOLVED" in rendered or PLACEHOLDER.search(rendered):
        raise ValueError("unresolved consent placeholder remains")
    for token in forbidden_tokens:
        if token and token in rendered:
            raise ValueError("consent contains frozen experimental stimulus")
    return rendered

if __name__ == "__main__":
    raise SystemExit("use validate_authorization.py; consent rendering needs the frozen anchor context")
