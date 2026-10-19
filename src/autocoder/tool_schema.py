"""Small explicit benchmark tool inventories and strict argument validation."""

import json
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Search(Arguments):
    pattern: str
    path: str


class Read(Arguments):
    path: str
    start: Annotated[int, Field(ge=1)]
    end: Annotated[int, Field(ge=1)]


class Edit(Arguments):
    path: str
    old: str
    new: str
    expected_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class Check(Arguments):
    name: str


class Symbol(Arguments):
    path: str
    symbol: str


MODELS = {
    "search_text": Search,
    "read_file_range": Read,
    "apply_edit": Edit,
    "run_named_check": Check,
    "find_references": Symbol,
    "read_symbol": Symbol,
}
DESCRIPTIONS = {
    "search_text": "Find literal text under a relative project path.",
    "read_file_range": "Read a relative project file at inclusive start/end line numbers.",
    "apply_edit": "Uniquely replace old text with new text, requiring the given SHA256.",
    "run_named_check": "Run a configured named verification check; never arbitrary shell commands.",
    "find_references": "Locate references to a named symbol in a project file.",
    "read_symbol": "Read the definition of a symbol in a project file.",
}


def inventory(count: int) -> list[dict]:
    if count not in {4, 6, 12}:
        raise ValueError("Unregistered tool inventory size")
    result = [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": DESCRIPTIONS[name],
                "parameters": model.model_json_schema(),
            },
        }
        for name, model in list(MODELS.items())[: min(count, 6)]
    ]
    if count == 12:
        # Explicitly synthetic distractors, offered only in selection trials, never executed.
        for name in (
            "list_files",
            "file_metadata",
            "list_symbols",
            "git_status",
            "git_diff",
            "project_info",
        ):
            result.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": "Read-only project metadata; not source content or edits.",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "additionalProperties": False,
                        },
                    },
                }
            )
    return result


def validate_choice(message: dict, expected: dict | None, allowed: list[dict]) -> tuple[bool, bool]:
    calls = message.get("tool_calls") or []
    if expected is None:
        return not calls, not calls
    if len(calls) != 1:
        return False, False
    function = calls[0].get("function", {})
    name = function.get("name")
    if name not in {tool["function"]["name"] for tool in allowed} or name not in MODELS:
        return False, False
    try:
        arguments = function.get("arguments")
        if isinstance(arguments, str):
            arguments = json.loads(arguments)
        decoded = MODELS[name].model_validate(arguments).model_dump()
    except (ValueError, ValidationError, TypeError):
        return False, False
    if name == "read_file_range" and decoded["end"] < decoded["start"]:
        return True, False
    return True, name == expected["name"] and decoded == expected["arguments"]
