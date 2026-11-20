"""Sample sizes must reproduce the figures in the research report.

Reference: ".agents/tasks/research-deck-optimization-loop.md", Part 1 of "The
arithmetic, worked explicitly".
"""

from __future__ import annotations

import pytest

from harness import stats


def test_normal_quantiles_match_published_values():
    assert stats.z_for_confidence(0.95) == pytest.approx(1.959964, abs=5e-7)
    assert stats.z_for_power(0.80) == pytest.approx(0.841621, abs=5e-7)
    assert stats.z_for_power(0.95) == pytest.approx(1.644854, abs=5e-7)


def test_the_two_power_constants_are_the_reports_k_values():
    # K = (z_{1-alpha/2} + z_power)^2
    k80 = (stats.z_for_confidence(0.95) + stats.z_for_power(0.80)) ** 2
    k95 = (stats.z_for_confidence(0.95) + stats.z_for_power(0.95)) ** 2
    assert k80 == pytest.approx(7.84888, abs=5e-6)
    assert k95 == pytest.approx(12.99471, abs=5e-6)


def test_per_arm_sample_sizes_at_80_percent_power():
    # n_per_arm = K * 0.5 / delta^2 with both arms at p = 0.5.
    assert stats.sample_size_per_arm_exact(0.05) == pytest.approx(1569.776, abs=1e-3)
    assert stats.sample_size_per_arm_exact(0.03) == pytest.approx(4360.488, abs=1e-3)
    assert stats.sample_size_per_arm_exact(0.02) == pytest.approx(9811.099, abs=1e-3)

    assert stats.sample_size_per_arm(0.05) == 1570
    assert stats.sample_size_per_arm(0.03) == 4361


def test_total_sample_sizes_reproduce_the_research_table():
    # The report's 80% power column: 3,140 / 8,721 / 19,622 total games for
    # 5 / 3 / 2 pp. The last differs by one game because the report rounds
    # 19,622.2 down where this module rounds every sample size up.
    assert stats.sample_size_total(0.05) == 3140
    assert stats.sample_size_total(0.03) == 8721
    assert abs(stats.sample_size_total(0.02) - 19622) <= 1


def test_total_sample_sizes_at_95_percent_power():
    assert stats.sample_size_total(0.05, power=0.95) == 5198
    assert stats.sample_size_total(0.03, power=0.95) == 14439
    assert stats.sample_size_total(0.02, power=0.95) == 32487


def test_a_lower_base_rate_is_cheaper_than_a_win_rate_near_one_half():
    # "wins by turn 5" at p = 0.30: K * 0.42 / 0.0009 = 3,663 per arm.
    per_arm = stats.sample_size_per_arm_exact(
        0.03, baseline_rate=0.30, candidate_rate=0.30
    )
    assert per_arm == pytest.approx(3662.810, abs=1e-3)
    assert (
        stats.sample_size_per_arm(0.03, baseline_rate=0.30, candidate_rate=0.30) == 3663
    )
    assert per_arm < stats.sample_size_per_arm_exact(0.03)


def test_project_defaults_are_the_declared_ones():
    assert stats.MINIMUM_DETECTABLE_EFFECT == 0.05
    assert stats.CONFIRMATION_EFFECT == 0.03
    assert stats.DEFAULT_POWER == 0.80
    assert stats.DEFAULT_ALPHA == stats.DEFAULT_BETA == 0.05
    assert stats.DEFAULT_CONFIDENCE == 0.95
    assert stats.sample_size_total(stats.MINIMUM_DETECTABLE_EFFECT) == 3140
    assert stats.sample_size_total(stats.CONFIRMATION_EFFECT) == 8721


def test_a_non_positive_effect_is_refused():
    with pytest.raises(ValueError, match="delta must be positive"):
        stats.sample_size_total(0.0)


def test_wilson_interval_matches_the_hand_computed_value():
    # 22 wins in 44 games (a 4% matchup in a 1,100-game screen), 95%:
    #   z = 1.959964, z^2 = 3.841459, denominator = 1 + z^2/44
    #   centre = (0.5 + z^2/88) / denominator = 0.5
    #   half   = z/denominator * sqrt(0.25/44 + z^2/(4*44^2))
    z = 1.959964
    denominator = 1.0 + z * z / 44
    expected_half = (z / denominator) * (0.25 / 44 + z * z / (4 * 44 * 44)) ** 0.5
    interval = stats.wilson_interval(22, 44)
    assert expected_half == pytest.approx(0.1416, abs=1e-4)  # the report's +-15 pp
    assert interval.low == pytest.approx(0.5 - expected_half, abs=1e-7)
    assert interval.high == pytest.approx(0.5 + expected_half, abs=1e-7)


def test_wilson_interval_stays_inside_the_unit_range():
    interval = stats.wilson_interval(0, 10)
    assert interval.low == pytest.approx(0.0, abs=1e-12)
    assert interval.high < 1.0
    assert stats.wilson_interval(10, 10).high == 1.0


def test_an_interval_is_always_rendered_with_its_confidence_level():
    assert "95% CI" in str(stats.Interval(0.1, 0.2))
    assert stats.Interval(0.1, 0.3).contains(0.2)
    assert not stats.Interval(0.1, 0.3).contains(0.4)
