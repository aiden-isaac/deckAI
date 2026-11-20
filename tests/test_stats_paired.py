"""Paired confirmation over shared shuffle seeds, and the exclusion of unpaired games."""

from __future__ import annotations

import pytest

from harness import stats


def game(opponent: str, seed: int, won: bool, **extra: object) -> dict[str, object]:
    return {"opponent": opponent, "seed": seed, "won": won, **extra}


def test_a_known_effect_is_recovered_inside_its_interval():
    # 400 shared seeds. The incumbent wins the even seeds (50%). The candidate
    # wins everything the incumbent wins, plus one seed in every 20 (+5 pp).
    candidate = []
    incumbent = []
    for seed in range(400):
        incumbent_won = seed % 2 == 0
        candidate_won = incumbent_won or seed % 20 == 1
        incumbent.append(game("boros-aggro", seed, incumbent_won))
        candidate.append(game("boros-aggro", seed, candidate_won))

    result = stats.paired_comparison(candidate, incumbent)

    assert result.pairs == 400
    assert result.games_used == 800
    assert result.games_excluded == 0
    assert result.candidate_win_rate == pytest.approx(0.55)
    assert result.incumbent_win_rate == pytest.approx(0.50)
    assert result.effect == pytest.approx(0.05)

    # Per-seed differences: 20 of +1 and 380 of 0, so
    #   s_d = sqrt((380*0.05^2 + 20*0.95^2) / 399) = 0.2182179
    #   SE  = s_d / sqrt(400) = 0.0109109
    #   CI  = 0.05 +- 1.959964 * 0.0109109 = [0.0286151, 0.0713849]
    assert result.standard_error == pytest.approx(0.0109109, abs=1e-7)
    assert result.interval.low == pytest.approx(0.0286151, abs=1e-6)
    assert result.interval.high == pytest.approx(0.0713849, abs=1e-6)
    assert result.interval.contains(0.05)
    assert not result.interval.contains(0.0)  # the effect is resolved


def test_a_known_null_effect_has_an_interval_containing_zero():
    # Identical arms: every within-pair difference is 0, which the paired
    # formula can only describe as a zero-width interval. That is a degenerate
    # sample rather than certainty, so it is refused.
    candidate = [game("boros-aggro", seed, seed % 2 == 0) for seed in range(400)]
    incumbent = [game("boros-aggro", seed, seed % 2 == 0) for seed in range(400)]
    with pytest.raises(ValueError, match="degenerate sample"):
        stats.paired_comparison(candidate, incumbent)

    # One seed flipped each way: effect 0, interval straddles 0.
    candidate[3] = game("boros-aggro", 3, True)
    candidate[4] = game("boros-aggro", 4, False)
    result = stats.paired_comparison(candidate, incumbent)
    assert result.effect == pytest.approx(0.0)
    assert result.interval.width > 0.0
    assert result.interval.contains(0.0)


def test_only_seeds_present_for_both_decklists_contribute():
    # The candidate wins seeds 3 and 4 but not 5; the incumbent loses them all.
    candidate = [
        game("boros-aggro", seed, seed != 5) for seed in (1, 2, 3, 4, 5)
    ]
    incumbent = [game("boros-aggro", seed, False) for seed in (3, 4, 5, 6, 7, 8)]

    result = stats.paired_comparison(candidate, incumbent)

    assert result.pairs == 3  # seeds 3, 4, 5
    assert result.games_used == 6
    assert result.effect == pytest.approx(2 / 3)
    assert result.candidate_win_rate == pytest.approx(2 / 3)
    assert result.incumbent_win_rate == pytest.approx(0.0)


def test_unpaired_games_are_counted_and_the_reason_is_named():
    candidate = [
        game("boros-aggro", seed, seed != 5) for seed in (1, 2, 3, 4, 5)
    ]
    incumbent = [game("boros-aggro", seed, False) for seed in (3, 4, 5, 6, 7, 8)]

    result = stats.paired_comparison(candidate, incumbent)

    assert result.games_excluded == 5  # seeds 1, 2 and 6, 7, 8
    excluded_keys = {exclusion.key for exclusion in result.exclusions}
    assert excluded_keys == {
        ("boros-aggro", 1),
        ("boros-aggro", 2),
        ("boros-aggro", 6),
        ("boros-aggro", 7),
        ("boros-aggro", 8),
    }
    reasons = {exclusion.reason for exclusion in result.exclusions}
    assert any("candidate but not the incumbent" in reason for reason in reasons)
    assert any("incumbent but not the candidate" in reason for reason in reasons)
    assert "excluded 5 unpaired game(s)" in result.summary()


def test_the_same_seed_against_a_different_opponent_is_not_a_pair():
    candidate = [game("boros-aggro", seed, True) for seed in range(10)]
    incumbent = [game("dimir-control", seed, False) for seed in range(10)]

    with pytest.raises(ValueError, match="at least 2 shared pairing keys"):
        stats.paired_comparison(candidate, incumbent)


def test_several_games_under_one_key_average_into_a_single_difference():
    # The mirrored play/draw pair under one seed is one paired observation, not
    # two: the candidate wins on the play and loses on the draw, scoring 0.5.
    candidate = []
    incumbent = []
    for seed in range(20):
        candidate.append(game("boros-aggro", seed, True, on_play=True))
        candidate.append(game("boros-aggro", seed, seed % 2 == 0, on_play=False))
        incumbent.append(game("boros-aggro", seed, True, on_play=True))
        incumbent.append(game("boros-aggro", seed, False, on_play=False))

    result = stats.paired_comparison(candidate, incumbent)

    assert result.pairs == 20
    assert result.games_used == 80
    assert result.candidate_win_rate == pytest.approx(0.75)
    assert result.incumbent_win_rate == pytest.approx(0.50)
    assert result.effect == pytest.approx(0.25)


def test_the_pairing_key_is_declared_and_overridable():
    candidate = [
        game("boros-aggro", seed, seed != 0, on_play=seed % 2 == 0)
        for seed in range(20)
    ]
    incumbent = [
        game("boros-aggro", seed, seed == 0, on_play=seed % 2 == 0)
        for seed in range(20)
    ]

    strict = stats.paired_comparison(
        candidate, incumbent, pair_on=("opponent", "seed", "on_play")
    )
    assert strict.pairs == 20
    assert strict.pair_on == ("opponent", "seed", "on_play")

    loose = stats.paired_comparison(candidate, incumbent, pair_on=("seed",))
    assert loose.pairs == 20
    assert loose.pair_on == ("seed",)


def test_a_record_missing_a_pairing_field_is_refused_by_name():
    candidate = [{"opponent": "boros-aggro", "won": True} for _ in range(4)]
    incumbent = [game("boros-aggro", seed, False) for seed in range(4)]

    with pytest.raises(ValueError, match="missing the required field 'seed'"):
        stats.paired_comparison(candidate, incumbent)


def test_a_confirmation_reports_an_effect_with_an_interval_not_a_bare_win_rate():
    candidate = [game("boros-aggro", seed, seed % 4 != 0) for seed in range(200)]
    incumbent = [game("boros-aggro", seed, seed % 2 == 0) for seed in range(200)]

    summary = stats.paired_comparison(candidate, incumbent).summary()

    assert "win-rate difference" in summary
    assert "95% CI" in summary


def test_the_confirmation_stage_sample_size_is_the_declared_one():
    assert stats.sample_size_total(stats.CONFIRMATION_EFFECT) == 8721
