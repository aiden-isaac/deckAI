from copy import deepcopy

import pytest

from harness.pilot_protocol import answer_schema, validate_answer, validate_decision


@pytest.fixture
def decision():
    return dict(protocol_version=1, game_id="g", seat=0, decision_id="d1", state_revision=3,
                view={"public": {}, "private": {}}, playbook_version="v0", legal_actions=[
                    {"action_id": "cast", "label": "Cast", "parameters_schema": {
                        "type": "object", "properties": {"target": {"enum": ["a", "b"]}},
                        "required": ["target"], "additionalProperties": False}},
                    {"action_id": "pass", "label": "Pass"}])


def answer(**updates):
    return dict(game_id="g", seat=0, decision_id="d1", state_revision=3,
                action_id="cast", parameters={"target": "a"}, **updates)


def test_valid_answer_preserves_requested_action(decision):
    value = answer()
    assert validate_answer(decision, value) is value
    assert answer_schema(decision)["additionalProperties"] is False


@pytest.mark.parametrize("field,value", [("seat", 1), ("state_revision", 2),
    ("decision_id", "old"), ("game_id", "other"), ("action_id", "not-offered"),
    ("parameters", {"target": "hidden"})])
def test_invalid_identity_or_parameters_never_default(decision, field, value):
    response = answer()
    response[field] = value
    with pytest.raises(ValueError, match="invalid pilot answer"):
        validate_answer(decision, response)


def test_parameter_schema_is_bound_to_selected_action(decision):
    response = answer()
    response["action_id"] = "pass"
    with pytest.raises(ValueError, match="invalid pilot answer"):
        validate_answer(decision, response)


@pytest.mark.parametrize("field,value", [("seat", True), ("state_revision", -1),
    ("protocol_version", 2), ("protocol_version", True), ("legal_actions", []), ("playbook_version", "")])
def test_invalid_decision_is_refused(decision, field, value):
    decision[field] = value
    with pytest.raises(ValueError):
        validate_decision(decision)


def test_duplicate_actions_and_reference_schemas_are_refused(decision):
    decision["legal_actions"].append(deepcopy(decision["legal_actions"][0]))
    with pytest.raises(ValueError, match="duplicate"):
        validate_decision(decision)
    decision["legal_actions"].pop()
    decision["legal_actions"][0]["parameters_schema"]["$ref"] = "https://example.org/schema"
    with pytest.raises(ValueError, match="references"):
        validate_decision(decision)


def test_unexpected_envelope_data_is_not_sent_to_a_pilot(decision):
    decision["referee_private_state"] = {"opponent_hand": ["hidden"]}
    with pytest.raises(ValueError):
        validate_decision(decision)
