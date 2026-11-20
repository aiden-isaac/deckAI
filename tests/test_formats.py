import pytest

from harness.formats import build_edition_index, parse_format


def test_format_parses_sets_and_bans_exactly(tmp_path):
    path = tmp_path / "Standard.txt"
    path.write_text("[format]\nName:Standard\nSets:AAA, BBB\nBanned:Bad One; Bad, Two\n")
    fmt = parse_format(path)
    assert fmt.sets == ("AAA", "BBB")
    assert fmt.banned == ("Bad One", "Bad, Two")
    assert len(fmt.source_sha256) == 64


def test_editions_include_printings_and_split_faces_but_not_tokens(tmp_path):
    (tmp_path / "set.txt").write_text("""[metadata]
Code=AAA
[cards]
1 C Push // Pull
[precon product]
2 R Precon Card @An Artist
[tokens]
3 C Token
[conjured]
4 C Conjured
""")
    index = build_edition_index(tmp_path, {"AAA"})
    assert index.sets_for("Push") == {"AAA"}
    assert index.is_legal("Push // Pull")
    assert index.is_legal("Precon Card")
    assert not index.is_legal("Token")
    assert not index.is_legal("Conjured")
    with pytest.raises(ValueError, match="missing Forge editions: BBB"):
        build_edition_index(tmp_path, {"AAA", "BBB"})
