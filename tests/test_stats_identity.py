"""Result identity: what may be pooled, what may be screened against, what is missing."""

from __future__ import annotations

import pytest

from harness import stats
from stats_support import records


def identity(**overrides: object) -> stats.ResultIdentity:
    base = {
        "engine_commit": "4f1c9ab0d3",
        "patch_hash": "a91b2c7",
        "candidate_deck_hash": "cand-0001",
        "incumbent_deck_hash": "inc-0000",
        "gauntlet_version": "standard-2026-11-20",
        "ai_profile": "stock",
        "sideboarding": "off",
        "game_clock_seconds": 120,
        "pilot_logic": "stock",
    }
    base.update(overrides)
    return stats.ResultIdentity(**base)


def test_identity_covers_every_declared_field():
    assert stats.IDENTITY_FIELDS == (
        "engine_commit",
        "patch_hash",
        "candidate_deck_hash",
        "incumbent_deck_hash",
        "gauntlet_version",
        "ai_profile",
        "sideboarding",
        "game_clock_seconds",
        "pilot_logic",
    )


def test_results_with_the_same_identity_pool():
    first = stats.MeasuredResult(identity(), tuple(records("boros-aggro", 10, 6)))
    second = stats.MeasuredResult(identity(), tuple(records("boros-aggro", 10, 4)))

    pooled = stats.pool_results([first, second])

    assert pooled.identity == identity()
    assert len(pooled.records) == 20
    matchups = stats.matchup_win_rates(pooled.records)
    assert matchups[0].games == 20
    assert matchups[0].wins == 10


def test_pooling_results_that_differ_only_in_ai_profile_raises_and_names_it():
    stock = stats.MeasuredResult(identity(), tuple(records("boros-aggro", 10, 6)))
    tuned = stats.MeasuredResult(
        identity(ai_profile="simulation-mc-max"), tuple(records("boros-aggro", 10, 4))
    )

    with pytest.raises(stats.IdentityMismatch) as raised:
        stats.pool_results([stock, tuned])

    assert raised.value.fields == ("ai_profile",)
    message = str(raised.value)
    assert "refusing to pool results" in message
    assert "ai_profile" in message
    assert "'stock'" in message and "'simulation-mc-max'" in message


def test_a_refusal_names_every_differing_field_not_just_the_first():
    with pytest.raises(stats.IdentityMismatch) as raised:
        stats.require_poolable(
            [
                identity(),
                identity(
                    engine_commit="0000000000",
                    pilot_logic="DonateLethal",
                    game_clock_seconds=300,
                ),
            ]
        )

    assert set(raised.value.fields) == {
        "engine_commit",
        "pilot_logic",
        "game_clock_seconds",
    }
    assert "DonateLethal" in str(raised.value)


def test_deck_specific_pilot_logic_blocks_pooling_with_a_stock_run():
    with pytest.raises(stats.IdentityMismatch, match="pilot_logic"):
        stats.require_poolable([identity(), identity(pilot_logic="DonateLethal")])


def test_a_baseline_measured_under_the_same_conditions_may_be_screened_against():
    baseline = identity(candidate_deck_hash="inc-0000")
    run = identity(candidate_deck_hash="cand-0042")
    assert stats.require_current_baseline(baseline, run) is None


def test_a_baseline_measured_under_other_conditions_is_refused():
    baseline = identity(candidate_deck_hash="inc-0000")
    for field, value in (
        ("engine_commit", "deadbeef00"),
        ("gauntlet_version", "standard-2027-02-01"),
        ("ai_profile", "simulation-mc-max"),
        ("incumbent_deck_hash", "inc-0007"),
        ("sideboarding", "bo3"),
        ("game_clock_seconds", 300),
        ("pilot_logic", "DonateLethal"),
        ("patch_hash", "ffffff0"),
    ):
        run = identity(candidate_deck_hash="cand-0042", **{field: value})
        with pytest.raises(stats.StaleBaseline) as raised:
            stats.require_current_baseline(baseline, run)
        assert raised.value.fields == (field,)
        assert "must be re-measured" in str(raised.value)


def test_the_candidate_deck_hash_is_the_one_field_a_baseline_may_differ_on():
    assert "candidate_deck_hash" not in stats.BASELINE_CURRENCY_FIELDS
    assert set(stats.BASELINE_CURRENCY_FIELDS) | {"candidate_deck_hash"} == set(
        stats.IDENTITY_FIELDS
    )


def test_an_identity_with_placeholders_cannot_reproduce_a_run():
    incomplete = identity(patch_hash="TBD", gauntlet_version="", game_clock_seconds=0)
    assert incomplete.missing_fields() == (
        "patch_hash",
        "gauntlet_version",
        "game_clock_seconds",
    )
    with pytest.raises(ValueError, match="incomplete and cannot reproduce"):
        incomplete.require_complete()


def test_a_complete_identity_states_everything_needed_to_re_run():
    complete = identity()
    assert complete.missing_fields() == ()
    assert complete.require_complete() is complete
    described = complete.describe()
    for field in stats.IDENTITY_FIELDS:
        assert field in described


def test_pooling_nothing_is_refused():
    with pytest.raises(ValueError, match="no results given"):
        stats.pool_results([])
    with pytest.raises(ValueError, match="no results given"):
        stats.require_poolable([])


def test_matching_placeholders_are_refused_at_pooling_and_screening_boundaries():
    incomplete = identity(patch_hash="TBD")
    with pytest.raises(ValueError, match="patch_hash"):
        stats.require_poolable([incomplete, incomplete])
    with pytest.raises(ValueError, match="patch_hash"):
        stats.require_current_baseline(incomplete, incomplete)


@pytest.mark.parametrize("clock", [True, float("nan"), float("inf"), "120"])
def test_non_numeric_or_non_finite_clock_is_incomplete(clock):
    with pytest.raises(ValueError, match="game_clock_seconds"):
        identity(game_clock_seconds=clock).require_complete()
