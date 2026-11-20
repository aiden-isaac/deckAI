"""Synthetic game records for the statistics tests.

The shape matches the record contract documented in ``harness.stats``:
``opponent``, ``seed`` and ``won`` are the fields the statistics read.
"""

from __future__ import annotations


def records(
    opponent: str, games: int, wins: int, *, seed_start: int = 0
) -> list[dict[str, object]]:
    """``games`` records against ``opponent``, of which the first ``wins`` are wins."""
    if not 0 <= wins <= games:
        raise ValueError(f"wins ({wins}) must lie between 0 and games ({games})")
    return [
        {"opponent": opponent, "seed": seed_start + index, "won": index < wins}
        for index in range(games)
    ]
