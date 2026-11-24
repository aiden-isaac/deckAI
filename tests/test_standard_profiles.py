"""Offline acceptance checks for the sourced Standard pilot profiles.

Set DECKAI_FORGE_ROOT to the pinned Forge checkout to run these checks.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path

import pytest

from harness.dck import CardEntry, build_deck, read_dck
from harness.validation import build_validator


ROOT = Path(__file__).parents[1]
PROFILE_DIRS = (
    ROOT / "decks/standard/izzet-aggro",
    ROOT / "decks/standard/landfall-aggro",
)


@pytest.fixture(scope="module")
def validator():
    forge_root = os.environ.get("DECKAI_FORGE_ROOT")
    if not forge_root:
        pytest.skip("set DECKAI_FORGE_ROOT for installed Standard profile validation")
    return build_validator(forge_root, allow_network=False)


def _section_counts(entries: list[CardEntry]) -> Counter[str]:
    return Counter({entry.name: entry.count for entry in entries})


def test_registered_profiles_pass_all_three_sources(validator):
    for directory in PROFILE_DIRS:
        manifest = json.loads((directory / "sources.json").read_text())
        deck = read_dck(directory / manifest["deck_file"])
        result = validator.validate(deck)
        assert result.passed, result.summary()
        assert (result.main_count, result.sideboard_count) == (60, 15)
        assert manifest["legality_check"]["status"].startswith("passed")
        assert manifest["legality_check"]["scryfall_bulk_file"] == validator.scryfall.bulk_file
        assert manifest["legality_check"]["format_sha256"] == validator.format.source_sha256


def test_documented_sideboard_exchanges_are_balanced_and_legal(validator):
    for directory in PROFILE_DIRS:
        manifest = json.loads((directory / "sources.json").read_text())
        deck = read_dck(directory / manifest["deck_file"])
        main = _section_counts(deck.main)
        side = _section_counts(deck.sideboard)

        for plan in manifest["sideboard_plans"]:
            incoming = {item["card"]: item["count"] for item in plan["in"]}
            outgoing = {item["card"]: item["count"] for item in plan["out"]}
            assert sum(incoming.values()) == sum(outgoing.values())
            assert all(side[name] >= count for name, count in incoming.items())
            assert all(main[name] >= count for name, count in outgoing.items())

            post_main, post_side = main.copy(), side.copy()
            post_main.subtract(outgoing)
            post_side.subtract(incoming)
            post_main.update(incoming)
            post_side.update(outgoing)
            post_main = Counter({name: count for name, count in post_main.items() if count})
            post_side = Counter({name: count for name, count in post_side.items() if count})

            postboard = build_deck(
                f"{deck.name} postboard vs {plan['opponent']}",
                [CardEntry(count, name) for name, count in post_main.items()],
                [CardEntry(count, name) for name, count in post_side.items()],
            )
            result = validator.validate(postboard)
            assert result.passed, result.summary()
            assert (result.main_count, result.sideboard_count) == (60, 15)
