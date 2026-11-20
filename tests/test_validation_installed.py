"""Opt-in checks against the actual pinned checkout and downloaded bulk cache.

DECKAI_FORGE_ROOT=/path/to/forge uv run pytest tests/test_validation_installed.py
"""
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from harness.dck import CardEntry, build_deck
from harness.scryfall import iter_bulk_cards, load_standard
from harness.validation import build_validator


CORE_NAMES = (
    "Kobayashi Maru Scenario", "The Naked Time", "Iroh Tea Master",
    "United Battlefront", "Harmless Offering", "Shiko Paragon of the Way",
    "Stiltzkin Moogle Merchant", "Aang's Iceberg", "Solitary Cell", "Seam Rip",
    "Skycoach Conductor", "Aang Swift Savior",
    "Skycoach Conductor // All Aboard",
    "Aang, Swift Savior // Aang and La, Ocean's Fury",
)


@pytest.fixture(scope="module")
def installed():
    root = os.environ.get("DECKAI_FORGE_ROOT")
    if not root:
        pytest.skip("set DECKAI_FORGE_ROOT for installed-pool verification")
    with patch("urllib.request.urlopen", side_effect=AssertionError("must use offline cache")):
        yield build_validator(root, allow_network=False)


@pytest.mark.parametrize("name", CORE_NAMES)
def test_core_cards_pass_all_three_sources(installed, name):
    script = installed.pool.resolve(name)
    assert script is not None
    result = installed.validate(build_deck("core verification", [CardEntry(59, "Island"), CardEntry(1, script.name)]))
    assert result.passed, result.summary()


def test_bans_match_pinned_file_and_flags_are_disclosed(installed):
    raw = installed.format.source_path.read_text()
    names = next(line.partition(":")[2] for line in raw.splitlines() if line.startswith("Banned:"))
    assert installed.format.banned == tuple(name.strip() for name in names.split(";"))
    assert "RemoveDeck:Random" in installed.pool.resolve("Harmless Offering").ai_flags
    assert not installed.pool.resolve("Kobayashi Maru Scenario").ai_flags
    assert not installed.pool.resolve("Kobayashi Maru Scenario").ai_hints


def test_real_bulk_filter_count_and_offline_reuse(installed):
    index = installed.scryfall
    path = Path("cache/scryfall") / index.bulk_file
    assert path.is_file(), "the real bulk file must be retained, not just a hand-written index"
    raw_count = sum(
        card.get("legalities", {}).get("standard") == "legal" and "paper" in card.get("games", [])
        for card in iter_bulk_cards(path)
    )
    assert raw_count > 0
    assert index.legal_count == raw_count
    with patch("urllib.request.urlopen", side_effect=AssertionError("must use offline cache")):
        assert load_standard(allow_network=False) == index


def test_full_bulk_paper_standard_pool_cross_validation(installed):
    path = Path("cache/scryfall") / installed.scryfall.bulk_file
    verified = 0
    for card in iter_bulk_cards(path):
        if card.get("legalities", {}).get("standard") != "legal" or "paper" not in card.get("games", []):
            continue
        name = card["name"]
        script = installed.pool.resolve(name)
        assert script is not None, name
        result = installed.validate(build_deck("pool cross-check", [CardEntry(59, "Island"), CardEntry(1, script.name)]))
        assert result.passed, result.summary()
        verified += 1
    assert verified == installed.scryfall.legal_count
