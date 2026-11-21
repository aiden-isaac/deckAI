from types import SimpleNamespace
import pytest
from harness.dck import parse_dck
from harness.sideboard import exchange


@pytest.fixture
def deck():
    return parse_dck("[Main]\n1 A|X\n2 A|Y\n[Sideboard]\n2 B|Z")


class Validator:
    def validate(self, deck):
        assert deck.main_count == 3 and deck.sideboard_count == 2
        return SimpleNamespace(passed=True)


def test_exchange_preserves_registered_printings_and_input(deck):
    updated = exchange(deck, bring_in={"B": 2}, take_out={"A": 2}, validator=Validator())
    assert [c.render() for c in updated.main] == ["1 A|Y", "2 B|Z"]
    assert [c.render() for c in updated.sideboard] == ["1 A|X", "1 A|Y"]
    assert deck.sideboard[0].render() == "2 B|Z"


@pytest.mark.parametrize("incoming,outgoing", [({"B":3},{"A":3}), ({"B":True},{"A":1}), ({"B":1},{}), ({"C":1},{"A":1})])
def test_invalid_exchange(deck, incoming, outgoing):
    with pytest.raises(ValueError):
        exchange(deck, bring_in=incoming, take_out=outgoing, validator=Validator())
