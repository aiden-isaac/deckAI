"""Sequential screening: hand-computed log-likelihood ratios and stopping behaviour."""

from __future__ import annotations

import itertools
import math
import random

import pytest

from harness import stats

# Hand-computed for the project default design, p0 = 0.50 vs p1 = 0.54:
#   win   contributes log(0.54/0.50) = log(1.08) = +0.0769610411361284
#   loss  contributes log(0.46/0.50) = log(0.92) = -0.0833816089390511
#   accept at log(0.95/0.05) = log(19)  = +2.9444389791664403
#   reject at log(0.05/0.95) = -log(19) = -2.9444389791664403
LLR_WIN = 0.0769610411361284
LLR_LOSS = -0.0833816089390511
THRESHOLD = 2.9444389791664403


def alternating(count: int) -> list[bool]:
    """An exactly 50/50 stream: win, loss, win, loss, ..."""
    return [index % 2 == 0 for index in range(count)]


def repeating(wins: int, losses: int, count: int) -> list[bool]:
    """A deterministic stream at rate wins/(wins+losses)."""
    block = [True] * wins + [False] * losses
    return list(itertools.islice(itertools.cycle(block), count))


def test_default_design_is_the_project_screening_design():
    design = stats.SprtDesign()
    assert (design.p0, design.p1) == (0.50, 0.54)  # bounds [0, +4 pp]
    assert design.alpha == design.beta == 0.05
    assert design.game_cap == 4000
    assert design == stats.screening_design()


def test_log_likelihood_increments_match_hand_computed_logs():
    design = stats.SprtDesign()
    assert design.llr_win == pytest.approx(LLR_WIN, abs=1e-15)
    assert design.llr_loss == pytest.approx(LLR_LOSS, abs=1e-15)
    assert design.llr_win == pytest.approx(math.log(1.08), abs=1e-15)
    assert design.llr_loss == pytest.approx(math.log(0.92), abs=1e-15)


def test_thresholds_match_hand_computed_log_odds():
    design = stats.SprtDesign()
    assert design.accept_threshold == pytest.approx(THRESHOLD, abs=1e-15)
    assert design.reject_threshold == pytest.approx(-THRESHOLD, abs=1e-15)
    assert design.accept_threshold == pytest.approx(math.log(19.0), abs=1e-15)


def test_log_likelihood_ratio_of_a_hand_computed_record():
    # 10 wins and 5 losses:
    #   10 * 0.0769610411361284 + 5 * (-0.0833816089390511) = 0.3527023666660283
    design = stats.SprtDesign()
    assert design.log_likelihood_ratio(10, 5) == pytest.approx(
        0.3527023666660283, abs=1e-15
    )
    assert design.log_likelihood_ratio(0, 0) == 0.0
    # And the ratio the run reports is the same number.
    result = stats.run_sprt(repeating(10, 5, 15), design)
    assert result.wins == 10 and result.losses == 5
    assert result.log_likelihood_ratio == pytest.approx(0.3527023666660283, abs=1e-12)


def test_an_exactly_fifty_fifty_stream_drifts_to_rejection_at_game_918():
    # Each win/loss pair moves the ratio by 0.0769610411 - 0.0833816089
    # = -0.0064205678. After 458 pairs (916 games) the ratio is -2.9406200537,
    # still inside the bounds; game 917 (a win) lifts it to -2.8636590126 and
    # game 918 (a loss) drops it to -2.9470406215, past -2.9444389792.
    result = stats.run_sprt(alternating(4000))
    assert result.decision == stats.REJECT
    assert result.observations == 918
    assert result.log_likelihood_ratio == pytest.approx(-2.9470406215, abs=1e-9)
    assert "reject threshold" in result.reason


def test_a_fifty_fifty_stream_is_inconclusive_when_the_cap_comes_first():
    # Same stream, a 500-game cap: the ratio is only at -1.6051419507 when the
    # cap arrives, so the run stops inconclusive and says so. A cap-out is
    # never an acceptance.
    design = stats.screening_design(game_cap=500)
    result = stats.run_sprt(alternating(4000), design)
    assert result.decision == stats.INCONCLUSIVE
    assert result.observations == 500
    assert result.log_likelihood_ratio == pytest.approx(-1.6051419507, abs=1e-9)
    assert "500-game cap" in result.reason
    assert result.wins == 250 and result.losses == 250


def test_an_effect_inside_the_indifference_zone_runs_to_the_cap():
    # True rate 0.52, between p0 = 0.50 and p1 = 0.54: the per-game drift is
    # 0.52 * 0.0769610411 - 0.48 * 0.0833816089 = -0.0000034318, so the ratio
    # wanders near zero and the 4,000-game cap arrives first.
    result = stats.run_sprt(repeating(13, 12, 4000))
    assert result.decision == stats.INCONCLUSIVE
    assert result.observations == 4000
    assert abs(result.log_likelihood_ratio) < 1.0
    assert "4000-game cap" in result.reason


def test_a_clearly_worse_candidate_is_rejected_well_before_the_cap():
    # True rate 0.45: drift is -0.0112274 per game, so ~262 games to cross.
    result = stats.run_sprt(repeating(9, 11, 4000))
    assert result.decision == stats.REJECT
    assert result.observations == 278
    assert result.observations < 1500  # the acceptance gate's budget

    seeded = random.Random(20261120)
    sampled = stats.run_sprt(seeded.random() < 0.45 for _ in range(4000))
    assert sampled.decision == stats.REJECT
    assert sampled.observations == 249


def test_a_clearly_better_candidate_is_accepted_well_before_the_cap():
    result = stats.run_sprt(repeating(3, 2, 4000))  # true rate 0.60
    assert result.decision == stats.ACCEPT
    assert result.observations == 218
    assert "accept threshold" in result.reason

    seeded = random.Random(20261120)
    sampled = stats.run_sprt(seeded.random() < 0.54 for _ in range(4000))
    assert sampled.decision == stats.ACCEPT
    assert sampled.observations == 691


def test_the_stream_is_abandoned_as_soon_as_the_test_decides():
    played = []

    def games():
        for _ in range(4000):
            played.append(True)
            yield False

    result = stats.run_sprt(games())
    assert result.decision == stats.REJECT
    assert len(played) == result.observations == 36  # ceil(2.94444 / 0.08338)


def test_a_stream_that_ends_short_of_the_cap_is_inconclusive_and_says_so():
    result = stats.run_sprt(alternating(100))
    assert result.decision == stats.INCONCLUSIVE
    assert result.observations == 100
    assert "ended after 100 games" in result.reason
    assert "4000-game cap" in result.reason


def test_bounds_and_error_rates_are_overridable():
    # The report's wider screening bounds, 0.50 vs 0.57, kill a bad candidate
    # faster than the default 0.54 bound does.
    wide = stats.screening_design(margin=0.07)
    assert wide.p1 == pytest.approx(0.57)
    narrow_games = stats.run_sprt(repeating(9, 11, 4000)).observations
    wide_games = stats.run_sprt(repeating(9, 11, 4000), wide).observations
    assert wide_games < narrow_games

    strict = stats.screening_design(alpha=0.01, beta=0.01, baseline_rate=0.45)
    assert strict.p0 == pytest.approx(0.45) and strict.p1 == pytest.approx(0.49)
    assert strict.accept_threshold > wide.accept_threshold


def test_an_incoherent_design_is_refused():
    with pytest.raises(ValueError, match="must be greater than p0"):
        stats.SprtDesign(p0=0.54, p1=0.50)
    with pytest.raises(ValueError, match="screening margin must be positive"):
        stats.screening_design(margin=0.0)
    with pytest.raises(ValueError, match="must stay below 1"):
        stats.screening_design(baseline_rate=0.98, margin=0.04)
    with pytest.raises(ValueError, match="game cap must be at least 1"):
        stats.SprtDesign(game_cap=0)
    with pytest.raises(ValueError, match="alpha must lie strictly between 0 and 1"):
        stats.SprtDesign(alpha=0.0)


def test_the_result_summary_states_the_decision_the_evidence_and_the_design():
    summary = stats.run_sprt(alternating(4000)).summary()
    assert "reject" in summary
    assert "918 games" in summary
    assert "p0=0.5000 vs p1=0.5400" in summary
    assert "cap=4000 games" in summary
