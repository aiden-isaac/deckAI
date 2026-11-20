"""The validation gate: decide whether a decklist can be measured at all.

Forge will happily play an illegal or incomplete deck. ``Match.java`` builds the
library from ``getValid().getLeft()`` and only *reveals* the cards it could not
script, so a 60-card list naming three unimplemented cards is played as a
57-card library; simulation mode never calls ``getDeckConformanceProblem()``, so
construction rules are not checked either. Everything in this module exists to
make that impossible: a list is either validated against three independent
sources plus the construction rules, or no win rate is reported for it.

Three sources, intersected and never silently reconciled (design decision D5):

1. **Forge's format file** — what the engine will treat as legal
   (:mod:`harness.formats`).
2. **The installed cardsfolder** — what the engine can actually play
   (:mod:`harness.cardpool`).
3. **Scryfall** — what is legal in paper (:mod:`harness.scryfall`).

Where sources 1 and 3 disagree the disagreement is *reported* and the list is
refused; the gate never picks a winner. Pilot-competence flags are the opposite:
they are disclosures attached to the result, never grounds for removing a card
the user deliberately chose.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from harness.cardpool import (
    AmbiguousCardName,
    CardPool,
    CardScript,
    canonical_name,
    index_cardsfolder,
    loose_name,
)
from harness.dck import CardEntry, Deck
from harness.formats import EditionIndex, Format, build_edition_index, parse_format
from harness.scryfall import ScryfallStandard, load_standard

#: Paths of the data files inside a Forge checkout.
FORGE_CARDSFOLDER = Path("forge-gui/res/cardsfolder")
FORGE_EDITIONS = Path("forge-gui/res/editions")
FORGE_FORMATS = Path("forge-gui/res/formats")

CHECK_CARD_POOL = "card-pool"
CHECK_FORMAT_LEGALITY = "format-legality"
CHECK_SOURCE_AGREEMENT = "source-agreement"
CHECK_CONSTRUCTION = "construction-rules"
CHECK_PILOT_COMPETENCE = "pilot-competence"
REQUIRED_CHECKS = frozenset({
    CHECK_CARD_POOL, CHECK_FORMAT_LEGALITY, CHECK_SOURCE_AGREEMENT,
    CHECK_CONSTRUCTION, CHECK_PILOT_COMPETENCE,
})


@dataclass(frozen=True)
class ConstructionRules:
    """Construction rules enforced here because the engine does not enforce them."""

    min_main: int = 60
    max_sideboard: int = 15
    max_copies: int = 4


@dataclass(frozen=True)
class Check:
    """One validation check and its outcome, recorded with every run."""

    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class Problem:
    """A blocking fault: the reason a list cannot be measured."""

    code: str
    detail: str
    card: str | None = None

    def message(self) -> str:
        if self.card:
            return f"{self.code}: {self.card} — {self.detail}"
        return f"{self.code}: {self.detail}"


@dataclass(frozen=True)
class Disclosure:
    """A pilot-competence disclosure: the AI is known to play this card badly."""

    card: str
    kind: str
    flags: tuple[str, ...]
    detail: str

    def message(self) -> str:
        return f"{self.card}: {self.detail}"


@dataclass(frozen=True)
class Disagreement:
    """Forge and Scryfall disagree about a card. Reported, never resolved."""

    card: str
    forge: str
    scryfall: str
    detail: str

    def message(self) -> str:
        return (
            f"{self.card}: Forge says {self.forge}, Scryfall says {self.scryfall}"
            f" — {self.detail}"
        )


@dataclass
class ValidationResult:
    """The full record of one deck's validation."""

    deck_name: str
    checks: list[Check] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)
    disclosures: list[Disclosure] = field(default_factory=list)
    disagreements: list[Disagreement] = field(default_factory=list)
    sources: dict[str, str] = field(default_factory=dict)
    main_count: int = 0
    sideboard_count: int = 0

    @property
    def passed(self) -> bool:
        return (
            not self.problems
            and REQUIRED_CHECKS <= {check.name for check in self.checks}
            and all(check.passed for check in self.checks)
        )

    def check(self, name: str) -> Check | None:
        for item in self.checks:
            if item.name == name:
                return item
        return None

    def warnings(self) -> list[str]:
        return [disclosure.message() for disclosure in self.disclosures]

    def to_dict(self) -> dict:
        return {
            "deck_name": self.deck_name,
            "passed": self.passed,
            "main_count": self.main_count,
            "sideboard_count": self.sideboard_count,
            "checks": [asdict(check) for check in self.checks],
            "problems": [asdict(problem) for problem in self.problems],
            "disclosures": [asdict(item) for item in self.disclosures],
            "disagreements": [asdict(item) for item in self.disagreements],
            "sources": dict(self.sources),
        }

    def summary(self) -> str:
        lines = [
            f"{self.deck_name}: {'VALID' if self.passed else 'INVALID'}"
            f" ({self.main_count} main, {self.sideboard_count} sideboard)"
        ]
        for check in self.checks:
            lines.append(f"  [{'ok' if check.passed else 'FAIL'}] {check.name}: {check.detail}")
        for problem in self.problems:
            lines.append(f"  problem: {problem.message()}")
        for disagreement in self.disagreements:
            lines.append(f"  disagreement: {disagreement.message()}")
        for disclosure in self.disclosures:
            lines.append(f"  pilot-competence warning: {disclosure.message()}")
        return "\n".join(lines)


class DeckValidator:
    """Validates decklists against the three sources plus the construction rules."""

    def __init__(
        self,
        pool: CardPool,
        fmt: Format,
        editions: EditionIndex,
        scryfall: ScryfallStandard | None,
        rules: ConstructionRules = ConstructionRules(),
    ) -> None:
        self.pool = pool
        self.format = fmt
        self.editions = editions
        self.scryfall = scryfall
        self.rules = rules
        self._banned = {canonical_name(name) for name in fmt.banned} | {
            loose_name(name) for name in fmt.banned
        }

    def validate(self, deck: Deck) -> ValidationResult:
        result = ValidationResult(
            deck_name=deck.name or (deck.source_path.name if deck.source_path else ""),
            main_count=deck.main_count,
            sideboard_count=deck.sideboard_count,
            sources={
                "format": self.format.version,
                "cardsfolder": f"{self.pool.root}:{len(self.pool)} scripts",
                "scryfall": self.scryfall.version if self.scryfall else "unavailable",
            },
        )
        counts = _counts_by_name(deck, self.pool)
        scripts = self._check_card_pool(result, counts)
        for _section, entry in deck.all_entries():
            try:
                script = self.pool.resolve(entry.name)
            except AmbiguousCardName:
                continue
            if script and canonical_name(entry.name) not in {
                canonical_name(alias) for alias in (script.name, *script.faces)
            }:
                result.problems.append(Problem(
                    code="noncanonical-card-name", card=entry.name,
                    detail=f"use the engine card name {script.name!r} in the deck file",
                ))
                pool_check = result.check(CHECK_CARD_POOL)
                result.checks[result.checks.index(pool_check)] = Check(
                    CHECK_CARD_POOL, False, "card names must be accepted by the engine",
                )
        self._check_format_legality(result, counts)
        self._check_source_agreement(result, counts)
        self._check_construction(result, deck, counts, scripts)
        self._collect_disclosures(result, scripts)
        return result

    # -- individual checks -------------------------------------------------

    def _check_card_pool(
        self, result: ValidationResult, counts: dict[str, int]
    ) -> dict[str, CardScript]:
        scripts: dict[str, CardScript] = {}
        missing: list[str] = []
        for name in counts:
            try:
                script = self.pool.resolve(name)
            except AmbiguousCardName as exc:
                missing.append(name)
                result.problems.append(
                    Problem(
                        code="ambiguous-card-name",
                        card=name,
                        detail=str(exc),
                    )
                )
                continue
            if script is None:
                missing.append(name)
                result.problems.append(
                    Problem(
                        code="card-absent-from-pool",
                        card=name,
                        detail=(
                            "no card script installed in the pinned engine; the engine"
                            " would strip it and play a smaller library"
                        ),
                    )
                )
                continue
            scripts[name] = script
        result.checks.append(
            Check(
                name=CHECK_CARD_POOL,
                passed=not missing,
                detail=(
                    f"{len(counts) - len(missing)}/{len(counts)} card names resolved in"
                    f" {self.pool.root}"
                ),
            )
        )
        return scripts

    def _check_format_legality(
        self, result: ValidationResult, counts: dict[str, int]
    ) -> None:
        banned: list[str] = []
        off_format: list[str] = []
        for name in counts:
            verdict = self._forge_verdict(name)
            if verdict == "banned":
                banned.append(name)
                result.problems.append(
                    Problem(
                        code="banned-card",
                        card=name,
                        detail=f"on the {self.format.name} ban list ({self.format.version})",
                    )
                )
            elif verdict == "not-in-format":
                off_format.append(name)
                result.problems.append(
                    Problem(
                        code="card-not-in-format",
                        card=name,
                        detail=(
                            f"no printing in the {self.format.name} sets"
                            f" ({', '.join(self.format.sets)})"
                        ),
                    )
                )
        result.checks.append(
            Check(
                name=CHECK_FORMAT_LEGALITY,
                passed=not banned and not off_format,
                detail=(
                    f"{self.format.name} {self.format.version}:"
                    f" {len(banned)} banned, {len(off_format)} outside the legal sets"
                ),
            )
        )

    def _check_source_agreement(
        self, result: ValidationResult, counts: dict[str, int]
    ) -> None:
        if self.scryfall is None:
            result.checks.append(
                Check(
                    name=CHECK_SOURCE_AGREEMENT,
                    passed=False,
                    detail="Scryfall data unavailable; paper legality unverified",
                )
            )
            result.problems.append(
                Problem(
                    code="source-unavailable",
                    detail=(
                        "Scryfall Standard data is not loaded, so paper legality cannot"
                        " be cross-checked"
                    ),
                )
            )
            return
        for name in counts:
            forge_verdict = self._forge_verdict(name)
            forge_legal = forge_verdict == "legal"
            if not self.scryfall.is_known(name):
                scryfall_verdict = "unknown"
            else:
                scryfall_verdict = "legal" if self.scryfall.is_legal(name) else "not-legal"
            if forge_legal == (scryfall_verdict == "legal"):
                continue
            disagreement = Disagreement(
                card=name,
                forge=forge_verdict,
                scryfall=scryfall_verdict,
                detail=(
                    "the two legality sources do not agree; resolve it by hand rather"
                    " than measuring the list"
                ),
            )
            result.disagreements.append(disagreement)
            result.problems.append(
                Problem(
                    code="source-disagreement",
                    card=name,
                    detail=disagreement.message(),
                )
            )
        result.checks.append(
            Check(
                name=CHECK_SOURCE_AGREEMENT,
                passed=not result.disagreements,
                detail=(
                    f"Forge {self.format.version} vs {self.scryfall.version}:"
                    f" {len(result.disagreements)} disagreement(s)"
                ),
            )
        )

    def _check_construction(
        self,
        result: ValidationResult,
        deck: Deck,
        counts: dict[str, int],
        scripts: dict[str, CardScript],
    ) -> None:
        faults: list[str] = []
        for section, entries in deck.sections.items():
            if entries and section not in {"Main", "Sideboard"}:
                faults.append(f"unsupported section {section}")
                result.problems.append(Problem(
                    code="invalid-deck-section",
                    detail=f"{self.format.name} decks cannot contain a {section} section",
                ))
        if deck.main_count < self.rules.min_main:
            faults.append("main deck too small")
            result.problems.append(
                Problem(
                    code="main-deck-too-small",
                    detail=(
                        f"main deck has {deck.main_count} cards, the format requires at"
                        f" least {self.rules.min_main}"
                    ),
                )
            )
        if deck.sideboard_count > self.rules.max_sideboard:
            faults.append("sideboard too large")
            result.problems.append(
                Problem(
                    code="sideboard-too-large",
                    detail=(
                        f"sideboard has {deck.sideboard_count} cards, the format allows at"
                        f" most {self.rules.max_sideboard}"
                    ),
                )
            )
        for name, count in counts.items():
            limit = self._copy_limit(scripts.get(name))
            if limit is not None and count > limit:
                faults.append(f"{name} x{count}")
                result.problems.append(
                    Problem(
                        code="too-many-copies",
                        card=name,
                        detail=f"{count} copies, limit is {limit}",
                    )
                )
        result.checks.append(
            Check(
                name=CHECK_CONSTRUCTION,
                passed=not faults,
                detail=(
                    f"main {deck.main_count}/>={self.rules.min_main},"
                    f" sideboard {deck.sideboard_count}/<={self.rules.max_sideboard},"
                    f" copy limit {self.rules.max_copies}"
                    f" (basic lands exempt): {len(faults)} fault(s)"
                ),
            )
        )

    def _collect_disclosures(
        self, result: ValidationResult, scripts: dict[str, CardScript]
    ) -> None:
        for name, script in scripts.items():
            if script.ai_flags:
                result.disclosures.append(
                    Disclosure(
                        card=script.name,
                        kind="ai-remove-deck",
                        flags=script.ai_flags,
                        detail=(
                            "the engine flags this card as one its AI plays badly"
                            f" ({', '.join('AI:' + flag for flag in script.ai_flags)})"
                        ),
                    )
                )
            if script.ai_hints:
                result.disclosures.append(
                    Disclosure(
                        card=script.name,
                        kind="ai-hint",
                        flags=script.ai_hints,
                        detail=(
                            "the card script carries AI tuning hints, so pilot play"
                            f" depends on them ({', '.join('SVar:' + h for h in script.ai_hints)})"
                        ),
                    )
                )
        result.checks.append(
            Check(
                name=CHECK_PILOT_COMPETENCE,
                passed=True,
                detail=(
                    f"{len(result.disclosures)} card(s) carry AI competence flags;"
                    " disclosed, not removed"
                ),
            )
        )

    # -- helpers -----------------------------------------------------------

    def _forge_verdict(self, name: str) -> str:
        try:
            script = self.pool.resolve(name)
        except AmbiguousCardName:
            script = None
        # CopyFaceFrom spells can be legal without making their prepared creature legal.
        name = script.name if script else name
        if canonical_name(name) in self._banned or loose_name(name) in self._banned:
            return "banned"
        return "legal" if self.editions.is_legal(name) else "not-in-format"

    def _copy_limit(self, script: CardScript | None) -> int | None:
        """Effective copy limit, or ``None`` when any number of copies is allowed."""
        if script is None:
            return self.rules.max_copies
        if script.is_basic_land or script.copy_limit == math.inf:
            return None
        if script.copy_limit is None:
            return self.rules.max_copies
        return int(script.copy_limit)


def build_validator(
    forge_root: str | Path,
    format_name: str = "Standard",
    *,
    cache_dir: str | Path = "cache/scryfall",
    allow_network: bool = True,
    rules: ConstructionRules = ConstructionRules(),
) -> DeckValidator:
    """Assemble a validator from a Forge checkout plus the cached Scryfall data."""
    forge_root = Path(forge_root)
    fmt = parse_format(forge_root / FORGE_FORMATS / "Sanctioned" / f"{format_name}.txt")
    pool = index_cardsfolder(forge_root / FORGE_CARDSFOLDER)
    editions = build_edition_index(forge_root / FORGE_EDITIONS, set(fmt.sets))
    scryfall = load_standard(cache_dir, allow_network=allow_network)
    return DeckValidator(pool, fmt, editions, scryfall, rules)


# -- runtime reveals -------------------------------------------------------

#: ``CardPool.add`` prints this to stderr when a deck names a card the engine has
#: no script for; the card then becomes an "unsupported" placeholder that
#: ``Match.java`` strips from the library before the first draw.
_UNSUPPORTED_RE = re.compile(
    r'An unsupported card was requested:\s*"(?P<name>[^"]+)"\s*from\s*"(?P<set>[^"]*)"'
)
#: Headers of the engine's two game-start reveals (``GameAction.revealUnsupported``
#: and ``revealUnplayableByAI``, rendered via ``lblActionFromPlayerDeck``).
_REMOVED_HEADER_RE = re.compile(r"^Removed from .* Deck\s*$")
_CANT_PLAY_HEADER_RE = re.compile(r"^AI can.?t play these cards well from .* Deck\s*$")
_SECTION_HEADER_RE = re.compile(r"^=+\s*.*\s*=+$")
_COUNT_PREFIX_RE = re.compile(r"^(\d+)\s+(?:x\s+)?")


@dataclass(frozen=True)
class RuntimeReveal:
    """What the engine said about a deck at game start."""

    stripped: tuple[str, ...] = ()
    cannot_play_well: tuple[str, ...] = ()
    lines: tuple[str, ...] = ()

    @property
    def has_strips(self) -> bool:
        return bool(self.stripped)


def parse_runtime_reveals(text: str) -> RuntimeReveal:
    """Extract stripped and cannot-play-well cards from engine output.

    Stripped cards make a run unscorable: the games were played with a smaller
    library than the decklist describes. Cannot-play-well cards are disclosures.
    """
    stripped: list[str] = []
    cannot_play: list[str] = []
    matched: list[str] = []
    collecting: list[str] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        unsupported = _UNSUPPORTED_RE.search(line)
        if unsupported:
            _append_unique(stripped, unsupported.group("name"))
            matched.append(line)
            collecting = None
            continue
        if _REMOVED_HEADER_RE.match(line):
            collecting = stripped
            matched.append(line)
            continue
        if _CANT_PLAY_HEADER_RE.match(line):
            collecting = cannot_play
            matched.append(line)
            continue
        if collecting is None:
            continue
        if not line:
            collecting = None
            continue
        if _SECTION_HEADER_RE.match(line):
            matched.append(line)
            continue
        _append_unique(collecting, _COUNT_PREFIX_RE.sub("", line))
        matched.append(line)
    return RuntimeReveal(
        stripped=tuple(stripped),
        cannot_play_well=tuple(cannot_play),
        lines=tuple(matched),
    )


def merge_runtime_reveals(*reveals: RuntimeReveal) -> RuntimeReveal:
    """Combine output streams and structured per-game reveals without losing names."""
    return RuntimeReveal(**{
        field: tuple(dict.fromkeys(value for reveal in reveals for value in getattr(reveal, field)))
        for field in ("stripped", "cannot_play_well", "lines")
    })


# -- withholding a score ---------------------------------------------------


@dataclass(frozen=True)
class ScoreReport:
    """A win rate, or the reason there is no win rate.

    Pilot-competence warnings travel with the number: they are rendered in the
    same block as the win rate, never in a separate log.
    """

    scorable: bool
    win_rate: float | None
    games: int | None
    refusals: tuple[str, ...]
    warnings: tuple[str, ...]
    validations: tuple[dict, ...]

    def render(self) -> str:
        lines: list[str] = []
        if self.scorable and self.win_rate is not None:
            games = f" over {self.games} games" if self.games else ""
            lines.append(f"Win rate: {self.win_rate * 100:.1f}%{games}")
        else:
            lines.append("No win rate: run is unscorable")
            for refusal in self.refusals:
                lines.append(f"  reason: {refusal}")
        for warning in self.warnings:
            lines.append(f"  pilot-competence warning: {warning}")
        for record in self.validations:
            states = ", ".join(
                f"{check['name']}={'pass' if check['passed'] else 'fail'}"
                for check in record["checks"]
            )
            lines.append(f"  validation [{record['deck_name']}]: {states or 'no checks ran'}")
        if not self.validations:
            lines.append("  validation: none ran — this run is unvalidated")
        return "\n".join(lines)


def score_run(
    win_rate: float | None,
    validations: list[ValidationResult],
    reveal: RuntimeReveal | None = None,
    games: int | None = None,
) -> ScoreReport:
    """Report a win rate only for a validated run with no runtime strips."""
    refusals: list[str] = []
    warnings: list[str] = []
    if not validations:
        refusals.append(
            "no validation record for this run; an unvalidated run cannot be scored"
        )
    for validation in validations:
        if not validation.passed:
            reasons = "; ".join(problem.message() for problem in validation.problems)
            failed = ", ".join(
                check.name for check in validation.checks if not check.passed
            )
            missing = REQUIRED_CHECKS - {check.name for check in validation.checks}
            if missing:
                failed += f"; missing checks: {', '.join(sorted(missing))}"
            refusals.append(
                f"deck {validation.deck_name!r} failed validation"
                f" ({failed or 'unknown check'}): {reasons}"
            )
        warnings.extend(validation.warnings())
    if reveal is not None:
        if reveal.stripped:
            refusals.append(
                "the engine stripped cards from a deck at game start: "
                + ", ".join(reveal.stripped)
            )
        for card in reveal.cannot_play_well:
            warnings.append(f"{card}: the engine reported its AI cannot play this well")
    if win_rate is None:
        refusals.append("no win rate was computed for this run")
    scorable = not refusals
    return ScoreReport(
        scorable=scorable,
        win_rate=win_rate if scorable else None,
        games=games,
        refusals=tuple(refusals),
        warnings=tuple(dict.fromkeys(warnings)),
        validations=tuple(validation.to_dict() for validation in validations),
    )


def _counts_by_name(deck: Deck, pool: CardPool) -> dict[str, int]:
    """Copies per card across main deck and sideboard (the limit spans both)."""
    counts: dict[str, int] = {}
    entry: CardEntry
    for _section, entry in deck.all_entries():
        try:
            script = pool.resolve(entry.name)
        except AmbiguousCardName:
            script = None
        name = script.name if script else entry.name
        counts[name] = counts.get(name, 0) + entry.count
    return counts


def _append_unique(target: list[str], value: str) -> None:
    value = value.strip()
    if value and value not in target:
        target.append(value)
