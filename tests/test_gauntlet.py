import hashlib
import json
from pathlib import Path

import pytest

from harness.gauntlet import load_gauntlet
from harness.dck import read_dck


def make_manifest(tmp_path):
    deck = tmp_path / "opponent.dck"
    deck.write_text("[Main]\n60 Mountain\n")
    opponent = {"id": "red", "deck": deck.name, "weight": 1,
                "sha256": hashlib.sha256(deck.read_bytes()).hexdigest()}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"opponents": [opponent]}))
    return path, deck, opponent


def test_frozen_gauntlet_detects_deck_drift(tmp_path):
    manifest, deck, _ = make_manifest(tmp_path)
    assert load_gauntlet(manifest)["version"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
    deck.write_text("[Main]\n59 Mountain\n")
    with pytest.raises(ValueError, match="red: frozen deck drift"):
        load_gauntlet(manifest)


@pytest.mark.parametrize("weight", [0, -1, True, float("nan"), float("inf"), "1"])
def test_invalid_weight_is_refused(tmp_path, weight):
    manifest, _, opponent = make_manifest(tmp_path)
    opponent["weight"] = weight
    manifest.write_text(json.dumps({"opponents": [opponent]}))
    with pytest.raises(ValueError, match="weight"):
        load_gauntlet(manifest)


def test_deck_outside_gauntlet_is_refused(tmp_path):
    manifest, _, opponent = make_manifest(tmp_path)
    opponent["deck"] = "../opponent.dck"
    manifest.write_text(json.dumps({"opponents": [opponent]}))
    with pytest.raises(ValueError, match="inside the gauntlet"):
        load_gauntlet(manifest)


def test_duplicate_opponent_is_refused(tmp_path):
    manifest, _, opponent = make_manifest(tmp_path)
    manifest.write_text(json.dumps({"opponents": [opponent, opponent]}))
    with pytest.raises(ValueError, match="duplicate"):
        load_gauntlet(manifest)


def test_acceptance_fixtures_change_only_four_lands_for_four_spells():
    root = Path(__file__).resolve().parents[1]
    healthy = read_dck(root / "decks/acceptance/healthy.dck")
    crippled = read_dck(root / "decks/acceptance/crippled.dck")
    assert healthy.main_count == crippled.main_count == 60
    before = {entry.name: entry.count for entry in healthy.main}
    after = {entry.name: entry.count for entry in crippled.main}
    differences = {name: after.get(name, 0) - before.get(name, 0)
                   for name in before.keys() | after.keys()
                   if before.get(name, 0) != after.get(name, 0)}
    assert differences == {"Mountain": -4, "Kellan, Planar Trailblazer": 4}
    assert before["Mountain"] == 24
    assert after["Mountain"] == 20
    assert len(load_gauntlet(root / "gauntlets/acceptance/manifest.json")["opponents"]) == 3
