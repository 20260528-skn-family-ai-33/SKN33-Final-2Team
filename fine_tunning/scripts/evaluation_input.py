"""Load the fixed evaluation input; no inference or remote work."""
import json
from pathlib import Path

def load_case(path, index):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    if index < 0 or index >= len(rows):
        raise ValueError("case-index is outside the test dataset")
    messages = rows[index]["messages"]
    if not isinstance(messages,list) or not messages:
        raise ValueError("Expected a non-empty messages list")
    reference=messages[-1]["content"] if messages[-1]["role"]=="assistant" else None
    prompt = messages[:-1] if reference is not None else messages
    if not prompt:
        raise ValueError("Evaluation input needs a user message")
    if prompt[-1]["role"] != "user":
        raise ValueError("Prompt must end with a user message")
    return prompt, reference
