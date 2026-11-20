from dataclasses import replace

import pytest

from harness.cardpool import index_cardsfolder
from harness.dck import CardEntry, build_deck
from harness.formats import build_edition_index, parse_format
from harness.scryfall import build_standard_index
from harness.validation import (
    Check, DeckValidator, REQUIRED_CHECKS, RuntimeReveal, ValidationResult,
    merge_runtime_reveals, parse_runtime_reveals, score_run,
)


@pytest.fixture
def validator(tmp_path):
    scripts = tmp_path / "cards"
    scripts.mkdir()
    for stem, text in {
        "island": "Name:Island\nTypes:Basic Land Island",
        "good": "Name:Good, Card\nTypes:Creature",
        "bad": "Name:Banned Card\nTypes:Creature",
        "flagged": "Name:Harmless Offering\nAI:RemoveDeck:Random\nSVar:AI:True",
        "compound": "Name:Front\nTypes:Creature\nALTERNATE\nName:Back\nTypes:Creature",
        "prepared": "Name:Prepared Creature\nAlternateMode:Prepare\nALTERNATE\nCopyFaceFrom:Good, Card",
    }.items():
        (scripts / f"{stem}.txt").write_text(text)
    fmt_file = tmp_path / "Standard.txt"
    fmt_file.write_text("[format]\nName:Standard\nSets:AAA\nBanned:Banned Card\n")
    editions = tmp_path / "editions"
    editions.mkdir()
    (editions / "set.txt").write_text("[metadata]\nCode=AAA\n[cards]\n1 C Island\n2 C Good, Card\n3 C Banned Card\n4 R Harmless Offering\n5 R Front\n")
    names = ["Island", "Good, Card", "Harmless Offering", "Front", "Back"]
    scryfall = build_standard_index([
        {"name": name, "legalities": {"standard": "legal"}, "games": ["paper"]}
        for name in names
    ])
    return DeckValidator(index_cardsfolder(scripts), parse_format(fmt_file), build_edition_index(editions, {"AAA"}), scryfall)


def deck(card="Good, Card", count=4, lands=56, sideboard=None):
    return build_deck("test", [CardEntry(lands, "Island"), CardEntry(count, card)], sideboard)


def test_legal_deck_and_basic_land_exception(validator):
    result = validator.validate(deck(sideboard=[CardEntry(15, "Island")]))
    assert result.passed, result.summary()
    assert {c.name for c in result.checks} == REQUIRED_CHECKS
    assert result.to_dict()["sources"]["format"].startswith("Standard@")


@pytest.mark.parametrize(("candidate", "code", "offender"), [
    (deck("Banned Card"), "banned-card", "Banned Card"),
    (deck(count=5, lands=55), "too-many-copies", "Good, Card"),
    (deck(lands=55), "main-deck-too-small", None),
    (deck("Nonexistent Card"), "card-absent-from-pool", "Nonexistent Card"),
    (deck(sideboard=[CardEntry(16, "Island")]), "sideboard-too-large", None),
])
def test_required_rejections_name_cause(validator, candidate, code, offender):
    result = validator.validate(candidate)
    assert not result.passed
    assert any(p.code == code and p.card == offender for p in result.problems)
    assert not score_run(0.5, [result]).scorable


def test_copy_limit_combines_case_punctuation_and_faces_across_sections(validator):
    for candidate in [
        deck(sideboard=[CardEntry(1, "good card")]),
        deck("Front", sideboard=[CardEntry(1, "Back")]),
    ]:
        result = validator.validate(candidate)
        assert any(p.code == "too-many-copies" for p in result.problems), result.summary()


def test_scryfall_compound_alias_must_be_written_as_engine_name(validator):
    result = validator.validate(deck("Front // Back"))
    assert any(p.code == "noncanonical-card-name" for p in result.problems)
    assert not result.check("card-pool").passed
    assert validator.validate(deck("Front")).passed


def test_copied_spell_does_not_grant_prepared_creature_legality(validator):
    result = validator.validate(deck("Prepared Creature"))
    assert any(p.code == "card-not-in-format" for p in result.problems)


def test_disagreement_is_reported_and_refused(validator):
    validator.scryfall = replace(validator.scryfall, legal_names=frozenset({"island"}))
    result = validator.validate(deck())
    assert not result.passed
    assert result.disagreements[0].card == "Good, Card"
    assert result.disagreements[0].forge == "legal"
    assert result.disagreements[0].scryfall == "not-legal"


def test_missing_scryfall_and_extra_sections_fail(validator):
    validator.scryfall = None
    candidate = deck()
    candidate.sections["Commander"] = [CardEntry(1, "Good, Card")]
    codes = {p.code for p in validator.validate(candidate).problems}
    assert {"source-unavailable", "invalid-deck-section"} <= codes


def test_pilot_flags_are_disclosures_attached_to_score(validator):
    result = validator.validate(deck("Harmless Offering"))
    assert result.passed, result.summary()
    assert {d.kind for d in result.disclosures} == {"ai-remove-deck", "ai-hint"}
    report = score_run(0.5, [result], RuntimeReveal(cannot_play_well=("Harmless Offering",)), 10)
    assert report.scorable
    assert "AI:RemoveDeck:Random" in report.render()
    assert "Harmless Offering" in report.render()


def test_empty_or_partial_validation_records_cannot_score():
    for checks in ([], [Check("card-pool", True, "ok")]):
        result = ValidationResult("unvalidated", checks=checks)
        assert not result.passed
        assert not score_run(0.5, [result]).scorable
    assert not score_run(0.5, []).scorable


def test_runtime_strips_override_successful_preflight_and_name_card(validator):
    result = validator.validate(deck())
    reveal = parse_runtime_reveals('An unsupported card was requested: "Definitely Not A Card" from "???".\n')
    assert reveal.stripped == ("Definitely Not A Card",)
    report = score_run(0.75, [result], reveal, 20)
    assert not report.scorable
    assert report.win_rate is None
    assert "Definitely Not A Card" in report.render()
    assert "Win rate:" not in report.render()


def test_reveal_sections_and_structured_merge_preserve_all_names():
    reveal = parse_runtime_reveals("""Removed from Ai(1)'s Deck
2 Missing Card

AI can't play these cards well from Ai(1)'s Deck
=== Main ===
Harmless Offering

Game Result: ignored
""")
    combined = merge_runtime_reveals(reveal, RuntimeReveal(stripped=("Missing Card", "Another Card")))
    assert combined.stripped == ("Missing Card", "Another Card")
    assert combined.cannot_play_well == ("Harmless Offering",)
