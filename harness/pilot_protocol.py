"""The small, shared boundary between rules decisions and external CLI pilots."""

from copy import deepcopy
import json

from jsonschema import Draft202012Validator


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")


def _no_references(schema):
    # shortcut: schema references are rejected; bundle references if an engine starts emitting them.
    if isinstance(schema, dict):
        if any(key in schema for key in ("$ref", "$dynamicRef")):
            raise ValueError("parameter schema references are unsupported")
        for value in schema.values():
            _no_references(value)
    elif isinstance(schema, list):
        for value in schema:
            _no_references(value)


def validate_decision(decision):
    """Validate the envelope; private visibility and full legality remain engine-owned."""
    fields = {"protocol_version", "game_id", "seat", "decision_id", "state_revision",
              "view", "legal_actions", "playbook_version"}
    if (not isinstance(decision, dict) or set(decision) != fields
            or type(decision.get("protocol_version")) is not int or decision["protocol_version"] != 1):
        raise ValueError("unsupported decision protocol_version")
    for field in ("game_id", "decision_id", "playbook_version"):
        _text(decision.get(field), field)
    if type(decision.get("seat")) is not int or decision["seat"] not in (0, 1):
        raise ValueError("seat must be 0 or 1")
    if type(decision.get("state_revision")) is not int or decision["state_revision"] < 0:
        raise ValueError("state_revision must be a non-negative integer")
    view = decision.get("view")
    if not isinstance(view, dict) or set(view) != {"public", "private"}:
        raise ValueError("view must contain public and private observations")
    if not all(isinstance(value, dict) for value in view.values()):
        raise ValueError("public and private observations must be objects")
    actions = decision.get("legal_actions")
    if not isinstance(actions, list) or not actions:
        raise ValueError("legal_actions must be a non-empty list")
    seen = set()
    for action in actions:
        if not isinstance(action, dict):
            raise ValueError("legal action must be an object")
        _text(action.get("action_id"), "action_id")
        _text(action.get("label"), "action label")
        if action["action_id"] in seen:
            raise ValueError("duplicate action_id")
        seen.add(action["action_id"])
        schema = action.get("parameters_schema", {"type": "object", "additionalProperties": False})
        if not isinstance(schema, dict) or schema.get("type") != "object":
            raise ValueError("parameters_schema must describe an object")
        _no_references(schema)
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as error:
            raise ValueError(f"invalid parameters_schema: {error}") from error
    try:
        json.dumps(decision, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError("decision must contain finite JSON data") from error
    return decision


def answer_schema(decision):
    """Return a structured-output envelope; validate action-specific parameters separately."""
    validate_decision(decision)
    parameters = [deepcopy(action.get("parameters_schema", {
        "type": "object", "additionalProperties": False,
    })) for action in decision["legal_actions"]]
    return {
        "type": "object",
        "properties": {
            **{field: {"type": "integer" if field in ("seat", "state_revision") else "string",
                       "enum": [decision[field]]}
               for field in ("game_id", "seat", "decision_id", "state_revision")},
            "action_id": {"type": "string", "enum": [action["action_id"] for action in decision["legal_actions"]]},
            "parameters": parameters[0] if len(parameters) == 1 else {"anyOf": parameters},
        },
        "required": ["game_id", "seat", "decision_id", "state_revision", "action_id", "parameters"],
        "additionalProperties": False,
    }


def validate_answer(decision, answer):
    """Reject malformed, cross-seat, stale and illegal-schema answers without a fallback."""
    schema = answer_schema(decision)
    try:
        json.dumps(answer, allow_nan=False)
        Draft202012Validator(schema).validate(answer)
        action = next(action for action in decision["legal_actions"] if action["action_id"] == answer["action_id"])
        parameters_schema = action.get("parameters_schema", {"type": "object", "additionalProperties": False})
        Draft202012Validator(parameters_schema).validate(answer["parameters"])
    except Exception as error:
        raise ValueError(f"invalid pilot answer: {error}") from error
    return answer
