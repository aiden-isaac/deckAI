import pytest

from harness.dck import CardEntry, DckError, normalise_dck, parse_dck, read_dck, save_dck, write_dck


NORMALISED = """[metadata]
Name=Handwritten 60+15

[Main]
24 Mountain|FDN|1
4 Monastery Swiftspear
4 Burst Lightning
4 Lightning Strike
4 Shock
4 Abrade
4 Screaming Nemesis
4 Emberheart Challenger
4 Hired Claw
4 Manifold Mouse

[Sideboard]
4 Lithomantic Barrage
4 Torch the Tower
4 Witchstalker Frenzy
3 Obliterating Bolt
"""


def test_handwritten_60_plus_15_round_trip(tmp_path):
    deck = parse_dck(NORMALISED)
    assert (deck.main_count, deck.sideboard_count) == (60, 15)
    assert write_dck(deck) == NORMALISED
    path = save_dck(deck, tmp_path / "list.dck")
    assert write_dck(read_dck(path)) == NORMALISED
    assert normalise_dck(NORMALISED.replace("24 Mountain", "24\t Mountain")) == NORMALISED


@pytest.mark.parametrize("line", ["0 Mountain", "-4 Shock", "X Shock", "4", "4 |FDN", "1 Shock|A|1|extra"])
def test_malformed_entry_rejected(line):
    with pytest.raises(DckError):
        parse_dck("[Main]\n" + line)


@pytest.mark.parametrize("count", [0, -1, 1.5, True])
def test_programmatic_entries_also_require_positive_integer_count(count):
    with pytest.raises(DckError):
        CardEntry(count, "Shock")
