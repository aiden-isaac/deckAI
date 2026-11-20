"""Re-scoring an accepted decision under alternative gauntlet weightings."""

from __future__ import annotations

import pytest

from harness import stats
from stats_support import records

# Three declared weightings over the same two matchups. The candidate beats
# the aggro deck and loses to the control deck, so which one the metagame is
# made of decides whether the change helps.
AGGRO_HEAVY = {"boros-aggro": 0.70, "dimir-control": 0.30}
EVEN = {"boros-aggro": 0.50, "dimir-control": 0.50}
CONTROL_HEAVY = {"boros-aggro": 0.30, "dimir-control": 0.70}

WEIGHTINGS = {
    "mtgtop8-2026-11": AGGRO_HEAVY,
    "even": EVEN,
    "control-heavy": CONTROL_HEAVY,
}


def reversing_effects() -> tuple[stats.MatchupEffect, ...]:
    """+10 pp against the aggro deck, -10 pp against the control deck."""
    candidate = [
        *records("boros-aggro", 1000, 600),
        *records("dimir-control", 1000, 400),
    ]
    incumbent = [
        *records("boros-aggro", 1000, 500),
        *records("dimir-control", 1000, 500),
    ]
    return stats.matchup_effects(candidate, incumbent)


def robust_effects() -> tuple[stats.MatchupEffect, ...]:
    """+10 pp against the aggro deck, +4 pp against the control deck."""
    candidate = [
        *records("boros-aggro", 1000, 600),
        *records("dimir-control", 1000, 540),
    ]
    incumbent = [
        *records("boros-aggro", 1000, 500),
        *records("dimir-control", 1000, 500),
    ]
    return stats.matchup_effects(candidate, incumbent)


def test_a_result_that_reverses_under_another_weighting_is_metagame_contingent():
    report = stats.rescore_under_weightings(
        reversing_effects(), WEIGHTINGS, primary="mtgtop8-2026-11"
    )

    assert report.verdict == stats.METAGAME_CONTINGENT
    assert report.metagame_contingent is True
    # 0.70*(+0.10) + 0.30*(-0.10) = +0.04 under the primary weighting,
    # 0.30*(+0.10) + 0.70*(-0.10) = -0.04 under the control-heavy one.
    scores = {score.name: score.value for score in report.scores}
    assert scores["mtgtop8-2026-11"] == pytest.approx(+0.04)
    assert scores["control-heavy"] == pytest.approx(-0.04)
    assert scores["even"] == pytest.approx(0.0)

    assert report.helps_under == ("mtgtop8-2026-11",)
    assert report.hurts_under == ("control-heavy",)
    assert report.neutral_under == ("even",)
    summary = report.summary()
    assert "metagame-contingent" in summary
    assert "not an improvement" in summary
    assert "control-heavy" in summary


def test_a_change_that_keeps_its_direction_everywhere_is_reported_as_robust():
    report = stats.rescore_under_weightings(
        robust_effects(), WEIGHTINGS, primary="mtgtop8-2026-11"
    )

    assert report.verdict == stats.ROBUST
    assert report.metagame_contingent is False
    assert set(report.helps_under) == set(WEIGHTINGS)
    assert report.hurts_under == ()
    assert "robust to the 3 tested weightings" in report.summary()


def test_every_re_scored_weighting_reports_its_own_interval():
    report = stats.rescore_under_weightings(
        reversing_effects(), WEIGHTINGS, primary="mtgtop8-2026-11"
    )
    for score in report.scores:
        assert score.aggregate.quantity == "win-rate difference"
        assert score.aggregate.weighting_name == score.name
        assert score.aggregate.interval.contains(score.value)
        assert "95% CI" in score.summary()
    assert report.report().count("95% CI") >= 3


def test_the_primary_weighting_is_reported_first_and_named():
    report = stats.rescore_under_weightings(
        robust_effects(), WEIGHTINGS, primary="even"
    )
    assert report.primary == "even"
    assert report.scores[0].name == "even"
    assert [score.name for score in report.scores[1:]] == [
        "control-heavy",
        "mtgtop8-2026-11",
    ]


def test_at_least_two_alternative_weightings_are_required():
    with pytest.raises(ValueError, match="at least 2 alternative weighting"):
        stats.rescore_under_weightings(
            robust_effects(),
            {"mtgtop8-2026-11": AGGRO_HEAVY, "even": EVEN},
            primary="mtgtop8-2026-11",
        )


def test_the_primary_weighting_must_be_one_of_the_declared_ones():
    with pytest.raises(ValueError, match="is not among the declared weightings"):
        stats.rescore_under_weightings(
            robust_effects(), WEIGHTINGS, primary="pioneer-2026"
        )


def test_a_metagame_contingent_decision_carries_its_robustness_report():
    effects = reversing_effects()
    report = stats.rescore_under_weightings(
        effects, WEIGHTINGS, primary="mtgtop8-2026-11"
    )
    aggregate = stats.weighted_effect(
        effects, AGGRO_HEAVY, weighting_name="mtgtop8-2026-11"
    )

    decision = stats.record_decision(stats.ACCEPT, aggregate, robustness=report)

    assert decision.robustness is report
    assert "metagame-contingent" in decision.summary()
