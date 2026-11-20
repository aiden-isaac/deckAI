"""Weighted aggregation, per-matchup intervals, the diagnostic marker, allocation."""

from __future__ import annotations

import pytest

from harness import stats
from stats_support import records

# A gauntlet in which one opponent carries 4% of the metagame weight.
WEIGHTS = {"boros-aggro": 0.48, "dimir-control": 0.48, "rogue-combo": 0.04}


def run_of_4000_games() -> list[dict[str, object]]:
    """1,800 games into each big matchup and 400 into the 4% one."""
    return [
        *records("boros-aggro", 1800, 990),  # 0.55
        *records("dimir-control", 1800, 810),  # 0.45
        *records("rogue-combo", 400, 360),  # 0.90
    ]


def test_a_four_percent_matchup_is_diagnostic_while_the_aggregate_is_not():
    matchups = stats.matchup_win_rates(run_of_4000_games())
    aggregate = stats.weighted_win_rate(matchups, WEIGHTS, weighting_name="mtgtop8-2026-11")

    by_opponent = {matchup.opponent: matchup for matchup in matchups}
    # 5 pp at 80% power needs 3,140 games, whether in a matchup or in total.
    assert all(matchup.required_games == 3140 for matchup in matchups)
    assert by_opponent["rogue-combo"].games == 400
    assert by_opponent["rogue-combo"].diagnostic_only is True
    assert by_opponent["boros-aggro"].diagnostic_only is True  # 1,800 < 3,140
    assert by_opponent["dimir-control"].diagnostic_only is True

    assert aggregate.games == 4000
    assert aggregate.diagnostic_only is False
    assert "diagnostic only" in by_opponent["rogue-combo"].summary()
    assert "decision-grade" in aggregate.summary()


def test_the_aggregate_is_the_weighted_mean_not_the_pooled_rate():
    matchups = stats.matchup_win_rates(run_of_4000_games())
    aggregate = stats.weighted_win_rate(matchups, WEIGHTS)

    # 0.48*0.55 + 0.48*0.45 + 0.04*0.90 = 0.516, where pooling all 4,000 games
    # would give 2,160/4,000 = 0.540.
    assert aggregate.value == pytest.approx(0.516)
    assert aggregate.quantity == "win rate"

    # Variance = sum w_i^2 * p_i(1-p_i)/n_i
    expected_variance = (
        0.48**2 * (0.55 * 0.45 / 1800)
        + 0.48**2 * (0.45 * 0.55 / 1800)
        + 0.04**2 * (0.90 * 0.10 / 400)
    )
    assert aggregate.standard_error == pytest.approx(expected_variance**0.5, abs=1e-12)
    assert aggregate.interval.low == pytest.approx(
        0.516 - 1.959964 * expected_variance**0.5, abs=1e-7
    )


def test_the_weighting_used_is_recorded_with_the_result():
    aggregate = stats.weighted_win_rate(
        stats.matchup_win_rates(run_of_4000_games()),
        WEIGHTS,
        weighting_name="mtgtop8-2026-11",
    )
    assert aggregate.weighting_name == "mtgtop8-2026-11"
    assert dict(aggregate.weights) == pytest.approx(WEIGHTS)
    assert "mtgtop8-2026-11" in aggregate.summary()


def test_weights_that_do_not_sum_to_one_are_normalised():
    matchups = stats.matchup_win_rates(run_of_4000_games())
    aggregate = stats.weighted_win_rate(
        matchups, {"boros-aggro": 12, "dimir-control": 12, "rogue-combo": 1}
    )
    assert sum(weight for _, weight in aggregate.weights) == pytest.approx(1.0)
    assert aggregate.value == pytest.approx((12 * 0.55 + 12 * 0.45 + 0.90) / 25)


def test_no_per_matchup_win_rate_is_reportable_without_its_interval():
    matchups = stats.matchup_win_rates(run_of_4000_games())
    for matchup in matchups:
        assert isinstance(matchup.interval, stats.Interval)
        assert "95% CI" in matchup.summary()

    report = stats.weighted_win_rate(matchups, WEIGHTS).report()
    assert report.splitlines()[0].startswith("weighted win rate")
    assert "supporting diagnosis (not decision-grade)" in report
    assert report.count("95% CI") == len(matchups) + 1


def test_a_matchup_with_no_declared_weight_is_refused_by_name():
    matchups = stats.matchup_win_rates(run_of_4000_games())
    with pytest.raises(ValueError, match="rogue-combo"):
        stats.weighted_win_rate(
            matchups, {"boros-aggro": 0.5, "dimir-control": 0.5}
        )


def test_a_weighted_opponent_with_no_games_is_refused_by_name():
    matchups = stats.matchup_win_rates(records("boros-aggro", 100, 55))
    with pytest.raises(ValueError, match="izzet-prowess"):
        stats.weighted_win_rate(
            matchups, {"boros-aggro": 0.9, "izzet-prowess": 0.1}
        )


def test_a_negative_weight_is_refused():
    matchups = stats.matchup_win_rates(records("boros-aggro", 100, 55))
    with pytest.raises(ValueError, match="must be positive"):
        stats.weighted_win_rate(matchups, {"boros-aggro": -1.0})


def test_the_minimum_detectable_effect_is_overridable():
    matchups = stats.matchup_win_rates(
        records("rogue-combo", 400, 360), minimum_detectable_effect=0.20
    )
    # 20 pp at 80% power needs only ceil(2 * 7.848879 * 0.5 / 0.04) = 197 games.
    assert matchups[0].required_games == 197
    assert matchups[0].diagnostic_only is False


def test_matchup_effects_report_the_difference_per_matchup_with_intervals():
    candidate = [*records("boros-aggro", 1000, 550), *records("dimir-control", 1000, 400)]
    incumbent = [*records("boros-aggro", 1000, 500), *records("dimir-control", 1000, 500)]

    effects = {effect.opponent: effect for effect in stats.matchup_effects(candidate, incumbent)}

    assert effects["boros-aggro"].effect == pytest.approx(0.05)
    assert effects["dimir-control"].effect == pytest.approx(-0.10)
    expected_se = (0.55 * 0.45 / 1000 + 0.50 * 0.50 / 1000) ** 0.5
    assert effects["boros-aggro"].standard_error == pytest.approx(expected_se, abs=1e-12)
    assert effects["boros-aggro"].interval.contains(0.05)
    assert effects["boros-aggro"].games == 2000
    assert effects["boros-aggro"].diagnostic_only is True  # 2,000 < 3,140
    assert "95% CI" in effects["dimir-control"].summary()


def test_matchup_effects_refuse_arms_that_played_different_matchups():
    candidate = [*records("boros-aggro", 10, 5), *records("rogue-combo", 10, 5)]
    incumbent = records("boros-aggro", 10, 5)
    with pytest.raises(ValueError, match="rogue-combo"):
        stats.matchup_effects(candidate, incumbent)


def test_a_decision_cites_the_weighted_aggregate():
    matchups = stats.matchup_win_rates(run_of_4000_games())
    aggregate = stats.weighted_win_rate(matchups, WEIGHTS, weighting_name="mtgtop8-2026-11")
    screen = stats.run_sprt([True, False] * 200)

    decision = stats.record_decision(stats.ACCEPT, aggregate, screening=screen)

    assert decision.outcome == stats.ACCEPT
    assert decision.cited_aggregate is aggregate
    assert decision.supporting_matchups == aggregate.components
    summary = decision.summary()
    assert "citing the weighted aggregate" in summary
    assert "supporting diagnosis (not decision-grade)" in summary


def test_a_decision_cannot_be_recorded_against_a_per_matchup_figure():
    matchups = stats.matchup_win_rates(run_of_4000_games())
    with pytest.raises(TypeError, match="must cite a weighted aggregate"):
        stats.record_decision(stats.ACCEPT, matchups[0])
    with pytest.raises(ValueError, match="outcome must be one of"):
        stats.record_decision(
            "looks good", stats.weighted_win_rate(matchups, WEIGHTS)
        )


def test_allocation_follows_the_declared_weighting_within_rounding():
    weights = {
        "boros-aggro": 0.30,
        "mardu-aggro": 0.26,
        "dimir-control": 0.20,
        "selesnya-aggro": 0.20,
        "rogue-combo": 0.04,
    }
    allocation = stats.allocate_games(weights, 1100)

    assert sum(allocation.values()) == 1100
    for opponent, weight in weights.items():
        share = allocation[opponent] / 1100
        assert share == pytest.approx(weight, abs=2 / 1100)
    # Every count is even, so the runner can mirror play and draw halves.
    assert all(count % 2 == 0 for count in allocation.values())
    # The 4% matchup gets 44 of the 1,100 screening games: the research's
    # "standard error 7.5 pp, 95% CI +-15 pp" case.
    assert allocation["rogue-combo"] == 44


def test_allocation_refuses_a_total_that_cannot_balance_play_and_draw():
    with pytest.raises(ValueError, match="multiple of games_per_cell"):
        stats.allocate_games({"boros-aggro": 1.0}, 101)
    with pytest.raises(ValueError, match="at least one opponent"):
        stats.allocate_games({}, 100)


def test_allocation_cell_size_is_overridable():
    # Four cells per opponent: play/draw crossed with both seat orders.
    allocation = stats.allocate_games(
        {"boros-aggro": 0.5, "dimir-control": 0.5}, 1000, games_per_cell=4
    )
    assert allocation == {"boros-aggro": 500, "dimir-control": 500}
    assert all(count % 4 == 0 for count in allocation.values())
