"""Statistics for deciding whether one decklist is better than another.

Everything here is hand-rolled from the standard library, per decision D8 of
the ``forge-gauntlet-measurement-rig`` design: the stopping rules and the
intervals are the whole project's credibility, so they are written out in full
and unit-tested against hand-computed values rather than hidden behind a
statistics framework. ``statistics.NormalDist`` supplies the normal CDF and its
inverse; nothing outside the standard library is imported.

This module never touches the Forge engine. It consumes *game records*.

Game record shape
-----------------

A game record is a plain mapping -- one per completed game, exactly as the
runner appends it to its JSONL file. Fields this module reads:

====================  ======  =====================================================
``opponent``          str     gauntlet opponent id, e.g. ``"boros-aggro"``
``seed``              int     shuffle seed; the pairing key for paired comparison
``won``               bool    ``True`` if the deck under measurement won the game
====================  ======  =====================================================

Other fields the runner writes (``decklist``, ``seat``, ``on_play``,
``turns``, ``mulligans``, ``elapsed_ms``, ...) are ignored here, except that
``pair_on`` may name any of them as part of the pairing key.

Records for the candidate arm and for the incumbent arm are always passed as
*separate* sequences, so no field has to identify the arm.

Project defaults
----------------

Every number below comes from "The arithmetic, worked explicitly" in
``.agents/tasks/research-deck-optimization-loop.md``, and every one of them is
a keyword argument of the function that uses it -- the defaults are declared,
not baked in.

* Screening: one-sample SPRT against a frozen incumbent baseline, bounds
  ``[0, +4 pp]`` (``p0 = 0.50`` vs ``p1 = 0.54``), ``alpha = beta = 0.05``,
  capped at 4,000 games. A cap-out is *inconclusive*, never an acceptance.
* Confirmation: paired fixed-sample over shared seeds, sized for a 3 pp effect
  at 80% power (8,721 games total).
* Minimum detectable effect claimed as decision-grade: 5 pp, which needs 3,140
  games (1,570 per arm) at 80% power. Any matchup below that is diagnostic-only.
* Decisions cite the weighted aggregate. Per-matchup figures are supporting
  diagnosis and are never reported without their confidence interval.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from statistics import NormalDist, fmean, stdev

__all__ = [
    # Defaults
    "DEFAULT_ALPHA",
    "DEFAULT_BETA",
    "DEFAULT_POWER",
    "DEFAULT_CONFIDENCE",
    "BASELINE_WIN_RATE",
    "SCREENING_MARGIN",
    "SCREENING_GAME_CAP",
    "MINIMUM_DETECTABLE_EFFECT",
    "CONFIRMATION_EFFECT",
    "DEFAULT_PAIR_ON",
    # Building blocks
    "Interval",
    "z_for_confidence",
    "z_for_power",
    "wilson_interval",
    "normal_interval",
    # Sample size
    "sample_size_per_arm_exact",
    "sample_size_per_arm",
    "sample_size_total",
    # Sequential screening
    "SprtDesign",
    "SprtResult",
    "screening_design",
    "run_sprt",
    "ACCEPT",
    "REJECT",
    "INCONCLUSIVE",
    # Allocation
    "allocate_games",
    # Paired confirmation
    "ExcludedPairing",
    "PairedComparison",
    "paired_comparison",
    # Aggregation and reporting
    "MatchupWinRate",
    "MatchupEffect",
    "WeightedAggregate",
    "Decision",
    "matchup_win_rates",
    "weighted_win_rate",
    "matchup_effects",
    "weighted_effect",
    "record_decision",
    # Identity and pooling
    "ResultIdentity",
    "MeasuredResult",
    "FieldDifference",
    "IdentityMismatch",
    "StaleBaseline",
    "IDENTITY_FIELDS",
    "BASELINE_CURRENCY_FIELDS",
    "require_poolable",
    "pool_results",
    "require_current_baseline",
    # Robustness to the weighting
    "WeightingScore",
    "RobustnessReport",
    "ROBUST",
    "METAGAME_CONTINGENT",
    "rescore_under_weightings",
]


# ---------------------------------------------------------------------------
# Declared defaults
# ---------------------------------------------------------------------------

DEFAULT_ALPHA = 0.05
DEFAULT_BETA = 0.05
DEFAULT_POWER = 0.80
DEFAULT_CONFIDENCE = 0.95

#: Win rate of a frozen incumbent baseline against the gauntlet. 0.50 is the
#: worst case for variance and the value the screening bounds are stated from.
BASELINE_WIN_RATE = 0.50

#: Screening bounds are [baseline, baseline + margin]: "+4 percentage points".
SCREENING_MARGIN = 0.04
SCREENING_GAME_CAP = 4000

#: The smallest effect we claim to resolve. Samples smaller than what this
#: needs are reported as diagnostic rather than decision-grade.
MINIMUM_DETECTABLE_EFFECT = 0.05

#: Effect the paired confirmation stage is sized for.
CONFIRMATION_EFFECT = 0.03

#: Default pairing key for the paired comparison. The opponent is part of the
#: key because the same seed against two different opponents is two different
#: games, not a pair.
DEFAULT_PAIR_ON = ("opponent", "seed")

ACCEPT = "accept"
REJECT = "reject"
INCONCLUSIVE = "inconclusive"

ROBUST = "robust"
METAGAME_CONTINGENT = "metagame-contingent"

_NORMAL = NormalDist()


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------


def _check_probability(name: str, value: float) -> None:
    if not 0.0 < value < 1.0:
        raise ValueError(f"{name} must lie strictly between 0 and 1, got {value!r}")


def z_for_confidence(confidence: float = DEFAULT_CONFIDENCE) -> float:
    """Two-sided critical value ``z_{1-(1-confidence)/2}``.

    ``z_for_confidence(0.95) == 1.959963...``
    """
    _check_probability("confidence", confidence)
    return _NORMAL.inv_cdf(1.0 - (1.0 - confidence) / 2.0)


def z_for_power(power: float = DEFAULT_POWER) -> float:
    """One-sided critical value ``z_power``: ``z_for_power(0.80) == 0.841621...``"""
    _check_probability("power", power)
    return _NORMAL.inv_cdf(power)


@dataclass(frozen=True)
class Interval:
    """A confidence interval. Carried alongside every estimate this module makes."""

    low: float
    high: float
    confidence: float = DEFAULT_CONFIDENCE

    def __post_init__(self) -> None:
        if self.low > self.high:
            raise ValueError(f"interval bounds are inverted: [{self.low}, {self.high}]")
        _check_probability("confidence", self.confidence)

    @property
    def width(self) -> float:
        return self.high - self.low

    def contains(self, value: float) -> bool:
        return self.low <= value <= self.high

    def __str__(self) -> str:
        return f"[{self.low:.4f}, {self.high:.4f}] ({self.confidence:.0%} CI)"


def normal_interval(
    point: float, standard_error: float, confidence: float = DEFAULT_CONFIDENCE
) -> Interval:
    """``point +- z * standard_error``, the interval for a difference of rates."""
    if standard_error < 0.0:
        raise ValueError(f"standard error must not be negative, got {standard_error!r}")
    half = z_for_confidence(confidence) * standard_error
    return Interval(point - half, point + half, confidence)


def wilson_interval(
    wins: int, games: int, confidence: float = DEFAULT_CONFIDENCE
) -> Interval:
    """Wilson score interval for a single win rate.

    Preferred over ``p +- z*sqrt(p(1-p)/n)`` because per-matchup samples are
    small (a 4% matchup in a 1,100-game screen gets ~44 games) and the Wilson
    interval stays inside [0, 1] and keeps its coverage there.

        centre = (p + z^2/2n) / (1 + z^2/n)
        half   = z/(1 + z^2/n) * sqrt(p(1-p)/n + z^2/4n^2)
    """
    if games <= 0:
        raise ValueError("a win rate interval needs at least one game")
    if not 0 <= wins <= games:
        raise ValueError(f"wins ({wins}) must lie between 0 and games ({games})")
    z = z_for_confidence(confidence)
    p = wins / games
    denominator = 1.0 + z * z / games
    centre = (p + z * z / (2 * games)) / denominator
    half = (z / denominator) * math.sqrt(
        p * (1.0 - p) / games + z * z / (4 * games * games)
    )
    return Interval(max(0.0, centre - half), min(1.0, centre + half), confidence)


# ---------------------------------------------------------------------------
# Sample size for a fixed-sample comparison
# ---------------------------------------------------------------------------


def sample_size_per_arm_exact(
    delta: float,
    *,
    power: float = DEFAULT_POWER,
    alpha: float = DEFAULT_ALPHA,
    baseline_rate: float = 0.5,
    candidate_rate: float | None = None,
) -> float:
    """Unrounded per-arm sample size for a two-proportion, two-sided test.

        n_per_arm = (z_{1-alpha/2} + z_power)^2
                    * [p_A(1-p_A) + p_B(1-p_B)] / delta^2

    With both rates at 0.5 (the worst case for variance) the bracket is 0.5,
    so ``n_per_arm = K * 0.5 / delta^2`` with ``K = 7.848879...`` at 80% power
    and ``K = 12.994712...`` at 95% power.
    """
    if delta <= 0.0:
        raise ValueError(f"delta must be positive, got {delta!r}")
    _check_probability("baseline_rate", baseline_rate)
    _check_probability("alpha", alpha)
    rate_b = baseline_rate if candidate_rate is None else candidate_rate
    _check_probability("candidate_rate", rate_b)
    k = (z_for_confidence(1.0 - alpha) + z_for_power(power)) ** 2
    variance_sum = baseline_rate * (1.0 - baseline_rate) + rate_b * (1.0 - rate_b)
    return k * variance_sum / (delta * delta)


def sample_size_per_arm(delta: float, **kwargs: float) -> int:
    """Games needed in *each* arm, rounded up. 1,570 for a 5 pp effect at 80%."""
    return math.ceil(sample_size_per_arm_exact(delta, **kwargs))


def sample_size_total(delta: float, **kwargs: float) -> int:
    """Games needed across *both* arms, rounded up. 3,140 for 5 pp at 80% power.

    Rounded from the doubled exact figure rather than from the rounded per-arm
    figure, so the totals match the research report's table (3,140 / 8,721 /
    19,622 for 5 / 3 / 2 pp at 80% power, to within the report's own rounding
    of 19,622.2).
    """
    return math.ceil(2.0 * sample_size_per_arm_exact(delta, **kwargs))


# ---------------------------------------------------------------------------
# Sequential screening: SPRT against a frozen baseline
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SprtDesign:
    """A declared sequential test: two bounds, two error rates, and a game cap.

    The bounds are win rates for the candidate against the gauntlet: ``p0`` is
    "no better than the frozen incumbent baseline", ``p1`` is "better by the
    screening margin". Nothing about the test adapts to the data; all five
    numbers are fixed before the first game.
    """

    p0: float = BASELINE_WIN_RATE
    p1: float = BASELINE_WIN_RATE + SCREENING_MARGIN
    alpha: float = DEFAULT_ALPHA
    beta: float = DEFAULT_BETA
    game_cap: int = SCREENING_GAME_CAP

    def __post_init__(self) -> None:
        _check_probability("p0", self.p0)
        _check_probability("p1", self.p1)
        _check_probability("alpha", self.alpha)
        _check_probability("beta", self.beta)
        if self.p1 <= self.p0:
            raise ValueError(
                f"p1 ({self.p1}) must be greater than p0 ({self.p0}): the test "
                "screens for an improvement"
            )
        if self.game_cap < 1:
            raise ValueError(f"game cap must be at least 1, got {self.game_cap!r}")

    @property
    def llr_win(self) -> float:
        """Log-likelihood contribution of one win: ``log(p1/p0)``."""
        return math.log(self.p1 / self.p0)

    @property
    def llr_loss(self) -> float:
        """Log-likelihood contribution of one loss: ``log((1-p1)/(1-p0))``."""
        return math.log((1.0 - self.p1) / (1.0 - self.p0))

    @property
    def accept_threshold(self) -> float:
        """Upper stopping bound ``log((1-beta)/alpha)``; ``log(19) = 2.94444`` by default."""
        return math.log((1.0 - self.beta) / self.alpha)

    @property
    def reject_threshold(self) -> float:
        """Lower stopping bound ``log(beta/(1-alpha))``; ``-2.94444`` by default."""
        return math.log(self.beta / (1.0 - self.alpha))

    def log_likelihood_ratio(self, wins: int, losses: int) -> float:
        """``wins * log(p1/p0) + losses * log((1-p1)/(1-p0))``."""
        if wins < 0 or losses < 0:
            raise ValueError("wins and losses must not be negative")
        return wins * self.llr_win + losses * self.llr_loss

    def describe(self) -> str:
        return (
            f"SPRT p0={self.p0:.4f} vs p1={self.p1:.4f}, "
            f"alpha={self.alpha}, beta={self.beta}, cap={self.game_cap} games, "
            f"stop at {self.reject_threshold:+.5f} / {self.accept_threshold:+.5f}"
        )


def screening_design(
    *,
    baseline_rate: float = BASELINE_WIN_RATE,
    margin: float = SCREENING_MARGIN,
    alpha: float = DEFAULT_ALPHA,
    beta: float = DEFAULT_BETA,
    game_cap: int = SCREENING_GAME_CAP,
) -> SprtDesign:
    """The project's screening test: bounds ``[baseline, baseline + margin]``.

    Defaults to ``[0, +4 pp]`` against a 50% baseline, ``alpha = beta = 0.05``,
    cap 4,000 games.
    """
    if margin <= 0.0:
        raise ValueError(f"screening margin must be positive, got {margin!r}")
    if baseline_rate + margin >= 1.0:
        raise ValueError(
            f"baseline rate {baseline_rate!r} plus margin {margin!r} must stay below 1"
        )
    return SprtDesign(
        p0=baseline_rate,
        p1=baseline_rate + margin,
        alpha=alpha,
        beta=beta,
        game_cap=game_cap,
    )


@dataclass(frozen=True)
class SprtResult:
    """Outcome of a sequential screen: a decision, why it stopped, and on how much."""

    decision: str
    reason: str
    observations: int
    wins: int
    losses: int
    log_likelihood_ratio: float
    design: SprtDesign

    @property
    def win_rate(self) -> float:
        return self.wins / self.observations if self.observations else 0.0

    def summary(self) -> str:
        return (
            f"{self.decision}: {self.reason} after {self.observations} games "
            f"({self.wins}W-{self.losses}L, LLR {self.log_likelihood_ratio:+.5f}); "
            f"{self.design.describe()}"
        )


def run_sprt(
    outcomes: Iterable[bool], design: SprtDesign | None = None
) -> SprtResult:
    """Run the sequential test over a stream of win/loss outcomes.

    ``outcomes`` is consumed lazily and abandoned the moment the test decides,
    so a generator that plays games on demand stops playing them on the first
    crossing. Returns ``accept``, ``reject`` or ``inconclusive``; hitting the
    game cap is always ``inconclusive``, never an acceptance.
    """
    design = design or SprtDesign()
    wins = 0
    losses = 0
    llr = 0.0
    observations = 0

    for outcome in outcomes:
        observations += 1
        if outcome:
            wins += 1
            llr += design.llr_win
        else:
            losses += 1
            llr += design.llr_loss

        if llr >= design.accept_threshold:
            return SprtResult(
                decision=ACCEPT,
                reason=(
                    f"log-likelihood ratio crossed the accept threshold "
                    f"{design.accept_threshold:+.5f}"
                ),
                observations=observations,
                wins=wins,
                losses=losses,
                log_likelihood_ratio=llr,
                design=design,
            )
        if llr <= design.reject_threshold:
            return SprtResult(
                decision=REJECT,
                reason=(
                    f"log-likelihood ratio crossed the reject threshold "
                    f"{design.reject_threshold:+.5f}"
                ),
                observations=observations,
                wins=wins,
                losses=losses,
                log_likelihood_ratio=llr,
                design=design,
            )
        if observations >= design.game_cap:
            return SprtResult(
                decision=INCONCLUSIVE,
                reason=(
                    f"reached the {design.game_cap}-game cap without crossing "
                    "either threshold"
                ),
                observations=observations,
                wins=wins,
                losses=losses,
                log_likelihood_ratio=llr,
                design=design,
            )

    return SprtResult(
        decision=INCONCLUSIVE,
        reason=(
            f"outcome stream ended after {observations} games, short of the "
            f"{design.game_cap}-game cap, without crossing either threshold"
        ),
        observations=observations,
        wins=wins,
        losses=losses,
        log_likelihood_ratio=llr,
        design=design,
    )


# ---------------------------------------------------------------------------
# Allocation across the gauntlet
# ---------------------------------------------------------------------------


def allocate_games(
    weights: Mapping[str, float], total_games: int, *, games_per_cell: int = 2
) -> dict[str, int]:
    """Split ``total_games`` across gauntlet opponents in proportion to ``weights``.

    Allocation is proportional to metagame share, which minimises the variance
    of the weighted aggregate (the thing decisions are made on). Counts are
    issued in whole cells of ``games_per_cell`` games -- 2 by default, so every
    opponent's games split evenly into play and draw halves, which the runner
    mirrors. Remainders go to the largest fractional shares first.
    """
    if games_per_cell < 1:
        raise ValueError(f"games_per_cell must be at least 1, got {games_per_cell!r}")
    if total_games < 0:
        raise ValueError(f"total_games must not be negative, got {total_games!r}")
    if total_games % games_per_cell:
        raise ValueError(
            f"total_games ({total_games}) must be a multiple of games_per_cell "
            f"({games_per_cell}) so play and draw stay balanced"
        )
    if not weights:
        raise ValueError("a gauntlet weighting must name at least one opponent")

    normalised = _normalised_weights(weights)
    cells = total_games // games_per_cell
    exact = {name: weight * cells for name, weight in normalised.items()}
    allocated = {name: int(value) for name, value in exact.items()}

    remaining = cells - sum(allocated.values())
    by_remainder = sorted(
        exact, key=lambda name: (-(exact[name] - int(exact[name])), name)
    )
    for name in by_remainder[:remaining]:
        allocated[name] += 1

    return {name: count * games_per_cell for name, count in allocated.items()}


# ---------------------------------------------------------------------------
# Paired fixed-sample confirmation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExcludedPairing:
    """A pairing key that could not contribute, and why."""

    key: tuple[object, ...]
    reason: str
    games: int

    def __str__(self) -> str:
        return f"{self.key}: {self.reason} ({self.games} game(s) excluded)"


@dataclass(frozen=True)
class PairedComparison:
    """Candidate minus incumbent over the seeds both arms actually played."""

    effect: float
    interval: Interval
    standard_error: float
    pairs: int
    candidate_win_rate: float
    incumbent_win_rate: float
    games_used: int
    games_excluded: int
    exclusions: tuple[ExcludedPairing, ...]
    pair_on: tuple[str, ...]

    def summary(self) -> str:
        text = (
            f"win-rate difference {self.effect:+.4f} {self.interval} "
            f"over {self.pairs} paired keys ({self.games_used} games; "
            f"candidate {self.candidate_win_rate:.4f}, "
            f"incumbent {self.incumbent_win_rate:.4f})"
        )
        if self.games_excluded:
            reasons = sorted({exclusion.reason for exclusion in self.exclusions})
            text += (
                f"; excluded {self.games_excluded} unpaired game(s) across "
                f"{len(self.exclusions)} key(s): {'; '.join(reasons)}"
            )
        return text


def _pairing_key(
    record: Mapping[str, object], pair_on: Sequence[str], index: int
) -> tuple[object, ...]:
    return tuple(_require_field(record, name, index) for name in pair_on)


def _scores_by_key(
    records: Iterable[Mapping[str, object]], pair_on: Sequence[str]
) -> dict[tuple[object, ...], list[bool]]:
    scores: dict[tuple[object, ...], list[bool]] = {}
    for index, record in enumerate(records):
        key = _pairing_key(record, pair_on, index)
        scores.setdefault(key, []).append(bool(_require_field(record, "won", index)))
    return scores


def paired_comparison(
    candidate_records: Iterable[Mapping[str, object]],
    incumbent_records: Iterable[Mapping[str, object]],
    *,
    pair_on: Sequence[str] = DEFAULT_PAIR_ON,
    confidence: float = DEFAULT_CONFIDENCE,
) -> PairedComparison:
    """Paired fixed-sample comparison over the shuffle seeds the arms share.

    Pairing is verified, not assumed: only keys present in *both* arms
    contribute. Every game under a key present in only one arm is excluded and
    counted, with the reason named. Where a key holds several games in an arm
    (the mirrored play/draw pair, say), that arm's score for the key is the
    mean of them, so each key contributes exactly one difference.

    The reported effect is the mean within-key difference; its interval is the
    standard paired interval ``d_bar +- z * s_d / sqrt(n)``.
    """
    pair_on = tuple(pair_on)
    if not pair_on:
        raise ValueError("pair_on must name at least one record field")

    candidate = _scores_by_key(candidate_records, pair_on)
    incumbent = _scores_by_key(incumbent_records, pair_on)

    shared = sorted(set(candidate) & set(incumbent), key=_sortable)
    exclusions: list[ExcludedPairing] = []
    for key in sorted(set(candidate) - set(incumbent), key=_sortable):
        exclusions.append(
            ExcludedPairing(
                key=key,
                reason=f"{pair_on} present for the candidate but not the incumbent",
                games=len(candidate[key]),
            )
        )
    for key in sorted(set(incumbent) - set(candidate), key=_sortable):
        exclusions.append(
            ExcludedPairing(
                key=key,
                reason=f"{pair_on} present for the incumbent but not the candidate",
                games=len(incumbent[key]),
            )
        )

    if len(shared) < 2:
        raise ValueError(
            f"a paired comparison needs at least 2 shared pairing keys, got "
            f"{len(shared)} (excluded {len(exclusions)} unpaired key(s))"
        )

    candidate_scores = [fmean(candidate[key]) for key in shared]
    incumbent_scores = [fmean(incumbent[key]) for key in shared]
    differences = [c - i for c, i in zip(candidate_scores, incumbent_scores)]

    effect = fmean(differences)
    spread = stdev(differences)
    if spread == 0.0:
        raise ValueError(
            f"every paired difference is identical ({effect:+.4f}), so the paired "
            "formula gives a zero-width interval; that is a degenerate sample "
            "rather than certainty -- measure more seeds"
        )
    standard_error = spread / math.sqrt(len(differences))

    games_used = sum(len(candidate[key]) + len(incumbent[key]) for key in shared)
    return PairedComparison(
        effect=effect,
        interval=normal_interval(effect, standard_error, confidence),
        standard_error=standard_error,
        pairs=len(shared),
        candidate_win_rate=fmean(candidate_scores),
        incumbent_win_rate=fmean(incumbent_scores),
        games_used=games_used,
        games_excluded=sum(exclusion.games for exclusion in exclusions),
        exclusions=tuple(exclusions),
        pair_on=pair_on,
    )


# ---------------------------------------------------------------------------
# Per-matchup breakdown and weighted aggregation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MatchupWinRate:
    """One matchup's win rate, inseparable from its interval and its status.

    There is deliberately no API that hands back a bare per-matchup win rate:
    the rate, the interval and the diagnostic marker travel together, because a
    per-matchup number read without its uncertainty is the most likely way this
    project produces a confidently wrong decklist.
    """

    opponent: str
    games: int
    wins: int
    win_rate: float
    interval: Interval
    required_games: int
    diagnostic_only: bool
    minimum_detectable_effect: float
    weight: float | None = None

    def summary(self) -> str:
        share = "" if self.weight is None else f", {self.weight:.1%} of the weighting"
        status = (
            f"diagnostic only: {self.games} games cannot resolve "
            f"{self.minimum_detectable_effect:.0%}, which needs {self.required_games}"
            if self.diagnostic_only
            else "decision-grade sample"
        )
        return (
            f"{self.opponent}: win rate {self.win_rate:.4f} {self.interval} "
            f"over {self.games} games{share} -- {status}"
        )


@dataclass(frozen=True)
class MatchupEffect:
    """One matchup's candidate-minus-incumbent difference, with its interval."""

    opponent: str
    effect: float
    interval: Interval
    standard_error: float
    candidate_games: int
    incumbent_games: int
    candidate_win_rate: float
    incumbent_win_rate: float
    required_games: int
    diagnostic_only: bool
    minimum_detectable_effect: float
    weight: float | None = None

    @property
    def games(self) -> int:
        return self.candidate_games + self.incumbent_games

    def summary(self) -> str:
        share = "" if self.weight is None else f", {self.weight:.1%} of the weighting"
        status = (
            f"diagnostic only: {self.games} games cannot resolve "
            f"{self.minimum_detectable_effect:.0%}, which needs {self.required_games}"
            if self.diagnostic_only
            else "decision-grade sample"
        )
        return (
            f"{self.opponent}: difference {self.effect:+.4f} {self.interval} "
            f"over {self.games} games{share} -- {status}"
        )


@dataclass(frozen=True)
class WeightedAggregate:
    """The decision-grade figure: a weighted mean over matchups, with its interval.

    ``components`` are the per-matchup figures that fed it. They are reported
    as supporting diagnosis only; the decision cites ``value`` and ``interval``.
    """

    quantity: str
    value: float
    interval: Interval
    standard_error: float
    games: int
    weighting_name: str
    weights: tuple[tuple[str, float], ...]
    components: tuple[MatchupWinRate, ...] | tuple[MatchupEffect, ...]
    required_games: int
    diagnostic_only: bool
    minimum_detectable_effect: float

    def summary(self) -> str:
        status = (
            f"diagnostic only: {self.games} games below the {self.required_games} "
            f"needed to resolve {self.minimum_detectable_effect:.0%}"
            if self.diagnostic_only
            else "decision-grade sample"
        )
        return (
            f"weighted {self.quantity} {self.value:+.4f} {self.interval} "
            f"under weighting '{self.weighting_name}' over {self.games} games "
            f"-- {status}"
        )

    def report(self) -> str:
        """Aggregate first, then every matchup with its interval, labelled."""
        lines = [self.summary(), "supporting diagnosis (not decision-grade):"]
        lines.extend(f"  - {component.summary()}" for component in self.components)
        return "\n".join(lines)


def matchup_win_rates(
    records: Iterable[Mapping[str, object]],
    *,
    minimum_detectable_effect: float = MINIMUM_DETECTABLE_EFFECT,
    power: float = DEFAULT_POWER,
    alpha: float = DEFAULT_ALPHA,
    confidence: float = DEFAULT_CONFIDENCE,
) -> tuple[MatchupWinRate, ...]:
    """Break a single arm's games down by opponent, each with a Wilson interval.

    A matchup is marked diagnostic-only when its own game count falls below
    what the declared minimum detectable effect needs -- 3,140 games for 5 pp
    at 80% power. Under proportional allocation that is nearly every matchup in
    a screening run, which is the point: they are there to show the LLM where
    to look, not to decide anything.
    """
    required = sample_size_total(
        minimum_detectable_effect, power=power, alpha=alpha
    )
    grouped = _wins_by_opponent(records)
    if not grouped:
        raise ValueError("no game records to break down by matchup")

    matchups = []
    for opponent in sorted(grouped):
        results = grouped[opponent]
        games = len(results)
        wins = sum(1 for won in results if won)
        matchups.append(
            MatchupWinRate(
                opponent=opponent,
                games=games,
                wins=wins,
                win_rate=wins / games,
                interval=wilson_interval(wins, games, confidence),
                required_games=required,
                diagnostic_only=games < required,
                minimum_detectable_effect=minimum_detectable_effect,
            )
        )
    return tuple(matchups)


def weighted_win_rate(
    matchups: Sequence[MatchupWinRate],
    weights: Mapping[str, float],
    *,
    weighting_name: str = "declared",
    confidence: float = DEFAULT_CONFIDENCE,
    minimum_detectable_effect: float = MINIMUM_DETECTABLE_EFFECT,
    power: float = DEFAULT_POWER,
    alpha: float = DEFAULT_ALPHA,
) -> WeightedAggregate:
    """Stratified estimate ``sum(w_i * p_i)`` with variance ``sum(w_i^2 p_i(1-p_i)/n_i)``.

    The weighting is recorded on the result, because an aggregate win rate is a
    property of the gauntlet weighting as much as of the deck.
    """
    if not matchups:
        raise ValueError("a weighted aggregate needs at least one matchup")
    normalised = _normalised_weights(weights, {m.opponent for m in matchups})

    value = 0.0
    variance = 0.0
    weighted: list[MatchupWinRate] = []
    for matchup in matchups:
        weight = normalised[matchup.opponent]
        value += weight * matchup.win_rate
        variance += (
            weight
            * weight
            * matchup.win_rate
            * (1.0 - matchup.win_rate)
            / matchup.games
        )
        weighted.append(replace(matchup, weight=weight))

    games = sum(matchup.games for matchup in matchups)
    required = sample_size_total(minimum_detectable_effect, power=power, alpha=alpha)
    standard_error = math.sqrt(variance)
    return WeightedAggregate(
        quantity="win rate",
        value=value,
        interval=normal_interval(value, standard_error, confidence),
        standard_error=standard_error,
        games=games,
        weighting_name=weighting_name,
        weights=tuple(sorted(normalised.items())),
        components=tuple(weighted),
        required_games=required,
        diagnostic_only=games < required,
        minimum_detectable_effect=minimum_detectable_effect,
    )


def matchup_effects(
    candidate_records: Iterable[Mapping[str, object]],
    incumbent_records: Iterable[Mapping[str, object]],
    *,
    minimum_detectable_effect: float = MINIMUM_DETECTABLE_EFFECT,
    power: float = DEFAULT_POWER,
    alpha: float = DEFAULT_ALPHA,
    confidence: float = DEFAULT_CONFIDENCE,
) -> tuple[MatchupEffect, ...]:
    """Per-matchup candidate-minus-incumbent differences, each with its interval.

    Both arms must have played every matchup; a matchup present in only one arm
    has no difference to report and is refused rather than silently dropped.
    """
    candidate = _wins_by_opponent(candidate_records)
    incumbent = _wins_by_opponent(incumbent_records)
    only_candidate = sorted(set(candidate) - set(incumbent))
    only_incumbent = sorted(set(incumbent) - set(candidate))
    if only_candidate or only_incumbent:
        raise ValueError(
            "both arms must play the same matchups; "
            f"candidate-only: {only_candidate}, incumbent-only: {only_incumbent}"
        )
    if not candidate:
        raise ValueError("no game records to break down by matchup")

    required = sample_size_total(minimum_detectable_effect, power=power, alpha=alpha)
    effects = []
    for opponent in sorted(candidate):
        c_results, i_results = candidate[opponent], incumbent[opponent]
        c_games, i_games = len(c_results), len(i_results)
        c_rate = sum(1 for won in c_results if won) / c_games
        i_rate = sum(1 for won in i_results if won) / i_games
        effect = c_rate - i_rate
        standard_error = math.sqrt(
            c_rate * (1.0 - c_rate) / c_games + i_rate * (1.0 - i_rate) / i_games
        )
        effects.append(
            MatchupEffect(
                opponent=opponent,
                effect=effect,
                interval=normal_interval(effect, standard_error, confidence),
                standard_error=standard_error,
                candidate_games=c_games,
                incumbent_games=i_games,
                candidate_win_rate=c_rate,
                incumbent_win_rate=i_rate,
                required_games=required,
                diagnostic_only=c_games + i_games < required,
                minimum_detectable_effect=minimum_detectable_effect,
            )
        )
    return tuple(effects)


def weighted_effect(
    effects: Sequence[MatchupEffect],
    weights: Mapping[str, float],
    *,
    weighting_name: str = "declared",
    confidence: float = DEFAULT_CONFIDENCE,
    minimum_detectable_effect: float = MINIMUM_DETECTABLE_EFFECT,
    power: float = DEFAULT_POWER,
    alpha: float = DEFAULT_ALPHA,
) -> WeightedAggregate:
    """Stratified estimate of the win-rate difference: ``sum(w_i * d_i)``."""
    if not effects:
        raise ValueError("a weighted aggregate needs at least one matchup")
    normalised = _normalised_weights(weights, {e.opponent for e in effects})

    value = 0.0
    variance = 0.0
    weighted: list[MatchupEffect] = []
    for effect in effects:
        weight = normalised[effect.opponent]
        value += weight * effect.effect
        variance += weight * weight * effect.standard_error**2
        weighted.append(replace(effect, weight=weight))

    games = sum(effect.games for effect in effects)
    required = sample_size_total(minimum_detectable_effect, power=power, alpha=alpha)
    standard_error = math.sqrt(variance)
    return WeightedAggregate(
        quantity="win-rate difference",
        value=value,
        interval=normal_interval(value, standard_error, confidence),
        standard_error=standard_error,
        games=games,
        weighting_name=weighting_name,
        weights=tuple(sorted(normalised.items())),
        components=tuple(weighted),
        required_games=required,
        diagnostic_only=games < required,
        minimum_detectable_effect=minimum_detectable_effect,
    )


# ---------------------------------------------------------------------------
# Recording a decision
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Decision:
    """An accept/reject/inconclusive record that cites the weighted aggregate."""

    outcome: str
    cited_aggregate: WeightedAggregate
    supporting_matchups: tuple[MatchupWinRate, ...] | tuple[MatchupEffect, ...]
    identity: "ResultIdentity | None" = None
    screening: SprtResult | None = None
    confirmation: PairedComparison | None = None
    robustness: "RobustnessReport | None" = None

    def summary(self) -> str:
        lines = [
            f"{self.outcome}, citing the weighted aggregate: "
            f"{self.cited_aggregate.summary()}"
        ]
        if self.screening is not None:
            lines.append(f"screen: {self.screening.summary()}")
        if self.confirmation is not None:
            lines.append(f"confirmation: {self.confirmation.summary()}")
        if self.robustness is not None:
            lines.append(f"robustness: {self.robustness.summary()}")
        if self.identity is not None:
            lines.append(f"identity: {self.identity.describe()}")
        lines.append("supporting diagnosis (not decision-grade):")
        lines.extend(f"  - {matchup.summary()}" for matchup in self.supporting_matchups)
        return "\n".join(lines)


def record_decision(
    outcome: str,
    aggregate: WeightedAggregate,
    *,
    identity: "ResultIdentity | None" = None,
    screening: SprtResult | None = None,
    confirmation: PairedComparison | None = None,
    robustness: "RobustnessReport | None" = None,
) -> Decision:
    """Record a decision against the weighted aggregate.

    The aggregate is mandatory and typed: a decision cannot be recorded against
    a per-matchup figure, which is the one thing per-matchup numbers must never
    be used for.
    """
    if outcome not in (ACCEPT, REJECT, INCONCLUSIVE):
        raise ValueError(
            f"outcome must be one of {ACCEPT!r}, {REJECT!r}, {INCONCLUSIVE!r}, "
            f"got {outcome!r}"
        )
    if not isinstance(aggregate, WeightedAggregate):
        raise TypeError(
            "a decision must cite a weighted aggregate, not a per-matchup "
            f"figure; got {type(aggregate).__name__}"
        )
    return Decision(
        outcome=outcome,
        cited_aggregate=aggregate,
        supporting_matchups=aggregate.components,
        identity=identity,
        screening=screening,
        confirmation=confirmation,
        robustness=robustness,
    )


# ---------------------------------------------------------------------------
# Result identity and poolability
# ---------------------------------------------------------------------------

IDENTITY_FIELDS = (
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

#: Fields a frozen baseline must still match for a screen to be run against it.
#: The candidate's own decklist hash is excluded -- it differs by construction.
BASELINE_CURRENCY_FIELDS = tuple(
    name for name in IDENTITY_FIELDS if name != "candidate_deck_hash"
)

_PLACEHOLDERS = frozenset(
    {"", "?", "tbd", "todo", "none", "null", "unknown", "placeholder"}
)


@dataclass(frozen=True)
class FieldDifference:
    """One identity field on which two results disagree."""

    field: str
    left: object
    right: object

    def __str__(self) -> str:
        return f"{self.field} ({self.left!r} vs {self.right!r})"


class IdentityMismatch(ValueError):
    """Raised when results whose identities differ are asked to be pooled."""

    def __init__(
        self, differences: Sequence[FieldDifference], action: str = "pool results"
    ) -> None:
        self.differences = tuple(differences)
        self.fields = tuple(difference.field for difference in self.differences)
        detail = "; ".join(str(difference) for difference in self.differences)
        super().__init__(
            f"refusing to {action}: identity fields differ: {detail}"
        )


class StaleBaseline(ValueError):
    """Raised when a screen is requested against a baseline that must be re-measured."""

    def __init__(self, differences: Sequence[FieldDifference]) -> None:
        self.differences = tuple(differences)
        self.fields = tuple(difference.field for difference in self.differences)
        detail = "; ".join(str(difference) for difference in self.differences)
        super().__init__(
            "refusing to screen against this baseline: it was measured under a "
            f"different identity and must be re-measured: {detail}"
        )


@dataclass(frozen=True)
class ResultIdentity:
    """Everything needed to re-run a result, and to decide whether it may be pooled.

    Two results may be pooled only when every one of these fields matches. The
    fields are exactly those that change what a game means: the engine, the
    patches, the two decklists, the gauntlet, the AI profile, whether
    sideboarding happened, the per-game clock, and any deck-specific pilot logic.
    """

    engine_commit: str
    patch_hash: str
    candidate_deck_hash: str
    incumbent_deck_hash: str
    gauntlet_version: str
    ai_profile: str
    sideboarding: str
    game_clock_seconds: int
    pilot_logic: str = "stock"

    def differences(
        self, other: "ResultIdentity", fields: Sequence[str] = IDENTITY_FIELDS
    ) -> tuple[FieldDifference, ...]:
        """Identity fields on which this result and ``other`` disagree."""
        return tuple(
            FieldDifference(name, getattr(self, name), getattr(other, name))
            for name in fields
            if getattr(self, name) != getattr(other, name)
        )

    def missing_fields(self) -> tuple[str, ...]:
        """Fields left empty or filled with a placeholder, which blocks reproduction."""
        missing = []
        for name in IDENTITY_FIELDS:
            value = getattr(self, name)
            if value is None:
                missing.append(name)
            elif isinstance(value, str) and value.strip().lower() in _PLACEHOLDERS:
                missing.append(name)
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                if value <= 0:
                    missing.append(name)
        return tuple(missing)

    def require_complete(self) -> "ResultIdentity":
        """Return self, or raise if any field would stop someone reproducing the run."""
        missing = self.missing_fields()
        if missing:
            raise ValueError(
                "result identity is incomplete and cannot reproduce the run; "
                f"unset or placeholder fields: {', '.join(missing)}"
            )
        return self

    def describe(self) -> str:
        return ", ".join(f"{name}={getattr(self, name)!r}" for name in IDENTITY_FIELDS)


@dataclass(frozen=True)
class MeasuredResult:
    """An identity stamp and the game records measured under it."""

    identity: ResultIdentity
    records: tuple[Mapping[str, object], ...]


def require_poolable(
    identities: Sequence[ResultIdentity], *, action: str = "pool results"
) -> ResultIdentity:
    """Return the shared identity, or raise ``IdentityMismatch`` naming the differences.

    Every identity is compared against the first, and *all* differing fields
    are named -- a refusal that names one field at a time wastes a run.
    """
    if not identities:
        raise ValueError("nothing to pool: no results given")
    reference = identities[0]
    differences: list[FieldDifference] = []
    seen: set[tuple[str, object, object]] = set()
    for identity in identities[1:]:
        for difference in reference.differences(identity):
            marker = (difference.field, repr(difference.left), repr(difference.right))
            if marker not in seen:
                seen.add(marker)
                differences.append(difference)
    if differences:
        raise IdentityMismatch(differences, action=action)
    return reference


def pool_results(results: Sequence[MeasuredResult]) -> MeasuredResult:
    """Pool game records across results, refusing any identity mismatch."""
    if not results:
        raise ValueError("nothing to pool: no results given")
    identity = require_poolable([result.identity for result in results])
    records: list[Mapping[str, object]] = []
    for result in results:
        records.extend(result.records)
    return MeasuredResult(identity=identity, records=tuple(records))


def require_current_baseline(
    baseline: ResultIdentity, candidate_run: ResultIdentity
) -> None:
    """Refuse to screen a candidate against a baseline measured under other conditions.

    The candidate's own decklist hash is expected to differ; everything else --
    engine pin, patches, the incumbent decklist, gauntlet, AI profile,
    sideboarding, clock, pilot logic -- must match, or the baseline has to be
    re-measured before it can be screened against.
    """
    differences = baseline.differences(candidate_run, BASELINE_CURRENCY_FIELDS)
    if differences:
        raise StaleBaseline(differences)


# ---------------------------------------------------------------------------
# Robustness of a decision to the gauntlet weighting
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WeightingScore:
    """A decision re-scored under one named weighting."""

    name: str
    aggregate: WeightedAggregate

    @property
    def value(self) -> float:
        return self.aggregate.value

    @property
    def direction(self) -> int:
        """+1 if the change helps under this weighting, -1 if it hurts, 0 if flat."""
        if self.aggregate.value > 0.0:
            return 1
        if self.aggregate.value < 0.0:
            return -1
        return 0

    def summary(self) -> str:
        return f"{self.name}: {self.aggregate.summary()}"


@dataclass(frozen=True)
class RobustnessReport:
    """Whether a decision survives re-weighting, and where it helps and hurts."""

    verdict: str
    primary: str
    scores: tuple[WeightingScore, ...]
    helps_under: tuple[str, ...]
    hurts_under: tuple[str, ...]
    neutral_under: tuple[str, ...]

    @property
    def metagame_contingent(self) -> bool:
        return self.verdict == METAGAME_CONTINGENT

    def summary(self) -> str:
        if self.metagame_contingent:
            headline = (
                "metagame-contingent: the measured advantage reverses under a "
                "declared weighting, so this is not an improvement"
            )
        else:
            headline = (
                f"robust to the {len(self.scores)} tested weightings: the "
                "direction holds under every one"
            )
        return (
            f"{headline}; helps under {list(self.helps_under)}, "
            f"hurts under {list(self.hurts_under)}, "
            f"flat under {list(self.neutral_under)} "
            f"(primary weighting '{self.primary}')"
        )

    def report(self) -> str:
        return "\n".join(
            [self.summary(), *(f"  - {score.summary()}" for score in self.scores)]
        )


def rescore_under_weightings(
    effects: Sequence[MatchupEffect],
    weightings: Mapping[str, Mapping[str, float]],
    *,
    primary: str,
    confidence: float = DEFAULT_CONFIDENCE,
    minimum_alternatives: int = 2,
    minimum_detectable_effect: float = MINIMUM_DETECTABLE_EFFECT,
    power: float = DEFAULT_POWER,
    alpha: float = DEFAULT_ALPHA,
) -> RobustnessReport:
    """Re-score the same measured matchups under every declared weighting.

    The per-matchup differences do not change; only the weights do. If the sign
    of the weighted difference under any declared weighting is opposite to the
    sign under ``primary``, the change is reported as metagame-contingent
    rather than as an improvement.

    At least ``minimum_alternatives`` weightings beyond the primary are
    required, per the spec's "at least two alternative gauntlet weightings".
    """
    if primary not in weightings:
        raise ValueError(
            f"primary weighting {primary!r} is not among the declared weightings "
            f"{sorted(weightings)}"
        )
    alternatives = [name for name in weightings if name != primary]
    if len(alternatives) < minimum_alternatives:
        raise ValueError(
            f"re-scoring needs at least {minimum_alternatives} alternative "
            f"weighting(s) besides {primary!r}, got {len(alternatives)}"
        )

    scores = tuple(
        WeightingScore(
            name=name,
            aggregate=weighted_effect(
                effects,
                weightings[name],
                weighting_name=name,
                confidence=confidence,
                minimum_detectable_effect=minimum_detectable_effect,
                power=power,
                alpha=alpha,
            ),
        )
        for name in [primary, *sorted(alternatives)]
    )

    primary_direction = scores[0].direction
    reversed_somewhere = any(
        score.direction == -primary_direction and score.direction != 0
        for score in scores[1:]
    )
    return RobustnessReport(
        verdict=METAGAME_CONTINGENT if reversed_somewhere else ROBUST,
        primary=primary,
        scores=scores,
        helps_under=tuple(score.name for score in scores if score.direction > 0),
        hurts_under=tuple(score.name for score in scores if score.direction < 0),
        neutral_under=tuple(score.name for score in scores if score.direction == 0),
    )


# ---------------------------------------------------------------------------
# Record plumbing
# ---------------------------------------------------------------------------


def _require_field(
    record: Mapping[str, object], name: str, index: int
) -> object:
    try:
        return record[name]
    except (KeyError, TypeError):
        raise ValueError(
            f"game record {index} is missing the required field {name!r}: {record!r}"
        ) from None


def _wins_by_opponent(
    records: Iterable[Mapping[str, object]],
) -> dict[str, list[bool]]:
    grouped: dict[str, list[bool]] = {}
    for index, record in enumerate(records):
        opponent = str(_require_field(record, "opponent", index))
        grouped.setdefault(opponent, []).append(
            bool(_require_field(record, "won", index))
        )
    return grouped


def _normalised_weights(
    weights: Mapping[str, float], opponents: Iterable[str] | None = None
) -> dict[str, float]:
    if not weights:
        raise ValueError("a gauntlet weighting must name at least one opponent")
    for name, weight in weights.items():
        if weight <= 0.0:
            raise ValueError(
                f"weight for {name!r} must be positive, got {weight!r}; drop the "
                "opponent from the weighting instead"
            )
    if opponents is not None:
        measured = set(opponents)
        declared = set(weights)
        missing = sorted(measured - declared)
        unmeasured = sorted(declared - measured)
        if missing or unmeasured:
            raise ValueError(
                "the declared weighting does not match the measured matchups; "
                f"measured with no declared weight: {missing}; "
                f"weighted but not measured: {unmeasured}"
            )
    total = sum(weights.values())
    return {name: weight / total for name, weight in weights.items()}


def _sortable(key: tuple[object, ...]) -> tuple[str, ...]:
    """Stable ordering for pairing keys of mixed types (ints, strings, bools)."""
    return tuple(f"{type(part).__name__}:{part!r}" for part in key)
