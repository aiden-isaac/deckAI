import math

import pytest

from harness.cardpool import AmbiguousCardName, index_cardsfolder, parse_card_script


def test_compound_script_is_indexed_by_faces_not_filename(tmp_path):
    (tmp_path / "compound.txt").write_text("Name:Aang, Swift Savior\nTypes:Creature\nALTERNATE\nName:Aang and La, Ocean's Fury\n")
    upcoming = tmp_path / "upcoming"
    upcoming.mkdir()
    (upcoming / "future.txt").write_text("Name:Future\n")
    pool = index_cardsfolder(tmp_path)
    front = pool.resolve("Aang Swift Savior")
    assert front is not None
    assert pool.resolve("Aang and La, Ocean's Fury") is front
    assert pool.resolve("Aang, Swift Savior // Aang and La, Ocean's Fury") is front
    assert pool.resolve("Future") is None
    assert index_cardsfolder(tmp_path, include_upcoming=True).resolve("Future")


def test_loose_ambiguity_refuses_to_guess(tmp_path):
    (tmp_path / "one.txt").write_text("Name:One, Two\n")
    (tmp_path / "two.txt").write_text("Name:One-Two\n")
    pool = index_cardsfolder(tmp_path)
    assert pool.resolve("One, Two").name == "One, Two"
    with pytest.raises(AmbiguousCardName):
        pool.resolve("One Two")


def test_primary_card_beats_copied_face_and_split_name_matches_forge(tmp_path):
    (tmp_path / "a.txt").write_text("Name:Prepared Creature\nAlternateMode:Prepare\nALTERNATE\nCopyFaceFrom:Spell\n")
    (tmp_path / "z.txt").write_text("Name:Spell\nTypes:Sorcery\n")
    (tmp_path / "split.txt").write_text("Name:Push\nAlternateMode:Split\nALTERNATE\nName:Pull\n")
    pool = index_cardsfolder(tmp_path)
    assert pool.resolve("Spell").name == "Spell"
    assert pool.resolve("Push").name == "Push // Pull"


@pytest.mark.parametrize(("text", "limit"), [
    ("A deck can have any number of cards named Test.", math.inf),
    ("A deck can have up to seven cards named Test.", 7),
    ("A deck can have only one card named Test.", 1),
])
def test_script_copy_exceptions_and_flags(tmp_path, text, limit):
    script = parse_card_script(tmp_path / "test.txt", f"Name:Test\nTypes:Basic Land\nAI:RemoveDeck:Random\nSVar:AI:True\nOracle:{text}\n")
    assert script.is_basic_land
    assert script.copy_limit == limit
    assert script.ai_flags == ("RemoveDeck:Random",)
    assert script.ai_hints == ("AI:True",)
