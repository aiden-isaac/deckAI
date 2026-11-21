"""Apply a pilot's equal-count exchange to its registered Standard deck."""
from dataclasses import replace

from .dck import with_section


def _take(entries, requested):
    if not isinstance(requested, dict) or any(
        not isinstance(name, str) or type(count) is not int or count <= 0
        for name, count in requested.items()
    ):
        raise ValueError("exchange requires card names with positive integer counts")
    remaining = requested.copy()
    kept, moved = [], []
    for entry in entries:
        count = min(entry.count, remaining.get(entry.name, 0))
        if count:
            remaining[entry.name] -= count
            moved.append(replace(entry, count=count))
        if count < entry.count:
            kept.append(replace(entry, count=entry.count - count))
    if any(remaining.values()):
        raise ValueError(f"unavailable copies: { {k:v for k,v in remaining.items() if v} }")
    return kept, moved


def exchange(deck, *, bring_in, take_out, validator):
    side, incoming = _take(deck.sideboard, bring_in)
    main, outgoing = _take(deck.main, take_out)
    if sum(bring_in.values()) != sum(take_out.values()):
        raise ValueError("sideboard exchange counts must match")
    updated = with_section(with_section(deck, "Main", main + incoming), "Sideboard", side + outgoing)
    result = validator.validate(updated)
    if not result.passed:
        raise ValueError(f"postboard deck failed validation: {result.to_dict()}")
    return updated
