"""Index of the card scripts actually installed in the pinned Forge engine.

Forge plays a card only if a script for it exists under
``forge-gui/res/cardsfolder/<letter>/<snake_case_name>.txt``. ``Match.java``
builds the library from ``getValid().getLeft()`` and merely *reveals* the rest,
so a decklist naming an unscripted card is silently played as a smaller deck.
This index is what lets the validation gate refuse such a list before any game
runs.

Two facts about the folder shape drive the implementation:

* Multi-faced cards live in one file whose name concatenates the faces
  (``aang_swift_savior_aang_and_la_oceans_fury.txt``,
  ``skycoach_conductor_all_aboard.txt``), and each face has its own ``Name:``
  line after an ``ALTERNATE`` separator. Resolution is therefore by *face name*,
  not by filename.
* ``cardsfolder/upcoming/`` is loaded by Forge only on development builds
  (``CardStorageReader.collectCardFiles``). We exclude it by default, so a card
  that exists only there is treated as absent: the conservative choice, since a
  release build would strip it mid-game.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

#: Subdirectory Forge itself skips outside development builds.
UPCOMING_DIR = "upcoming"

_DECK_LIMIT_RE = re.compile(
    r"a deck can have (any number of|only one|up to (?P<word>\w+)) cards? named",
    re.IGNORECASE,
)
_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
_PUNCTUATION_RE = re.compile(r"[^0-9a-z]+")


def canonical_name(name: str) -> str:
    """Case-, accent- and quote-insensitive key for a card name."""
    folded = unicodedata.normalize("NFKD", name)
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    folded = folded.replace("\u2019", "'").replace("\u2018", "'")
    folded = folded.replace("\u2014", "-").replace("\u2013", "-")
    return " ".join(folded.casefold().split())


def loose_name(name: str) -> str:
    """Punctuation-free key, so ``Iroh Tea Master`` finds ``Iroh, Tea Master``."""
    return _PUNCTUATION_RE.sub(" ", canonical_name(name)).strip()


@dataclass(frozen=True)
class CardScript:
    """One installed card script.

    ``ai_flags`` are the engine's ``AI:`` directives (``AI:RemoveDeck:Random``
    means the deck builder drops the card at random because the AI plays it
    badly). ``ai_hints`` are ``SVar:AI*`` tuning lines. Both are disclosures,
    never grounds for exclusion.

    ``copy_limit`` is the limit the *card* states: ``None`` when it states none
    (the format's limit applies), ``math.inf`` for "a deck can have any number of
    cards named …", or an integer for "up to seven"/"only one".
    """

    name: str
    faces: tuple[str, ...]
    path: Path
    types: tuple[str, ...]
    ai_flags: tuple[str, ...]
    ai_hints: tuple[str, ...]
    copy_limit: int | float | None

    @property
    def is_basic_land(self) -> bool:
        lowered = [t.casefold() for t in self.types]
        return "basic" in lowered and "land" in lowered

    @property
    def removed_from_ai_decks(self) -> bool:
        return any(flag.startswith("RemoveDeck") for flag in self.ai_flags)


class AmbiguousCardName(LookupError):
    """A loose name matched more than one installed card."""

    def __init__(self, name: str, candidates: list[str]) -> None:
        super().__init__(
            f"{name!r} matches several installed cards: {', '.join(sorted(candidates))}"
        )
        self.name = name
        self.candidates = sorted(candidates)


class CardPool:
    """Name-to-script index over an installed ``cardsfolder``."""

    def __init__(self, scripts: list[CardScript], root: Path) -> None:
        self.root = root
        self.scripts = tuple(scripts)
        self._by_name: dict[str, CardScript] = {}
        self._by_loose: dict[str, list[CardScript]] = {}
        self._by_stem: dict[str, CardScript] = {}
        # A copied spell face must not shadow the standalone card with that name.
        for script in scripts:
            self._by_name.setdefault(canonical_name(script.name), script)
        for script in scripts:
            names = [script.name, *script.faces]
            if len(script.faces) > 1:
                # Scryfall-style combined name for multi-faced cards.
                names.append(" // ".join(script.faces))
            for face in names:
                self._by_name.setdefault(canonical_name(face), script)
                bucket = self._by_loose.setdefault(loose_name(face), [])
                if script not in bucket:
                    bucket.append(script)
            self._by_stem.setdefault(script.path.stem.casefold(), script)

    def __len__(self) -> int:
        return len(self.scripts)

    def __contains__(self, name: str) -> bool:
        try:
            return self.resolve(name) is not None
        except AmbiguousCardName:
            return False

    def resolve(self, name: str) -> CardScript | None:
        """Find the script for a deck entry, or ``None`` if the engine lacks it.

        Exact (normalised) face names win. A punctuation-free match is accepted
        only when it is unique; an ambiguous one raises rather than guessing.
        """
        exact = self._by_name.get(canonical_name(name))
        if exact is not None:
            return exact
        candidates = self._by_loose.get(loose_name(name), [])
        primary = [card for card in candidates if loose_name(card.name) == loose_name(name)]
        candidates = primary or candidates
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            raise AmbiguousCardName(name, [c.name for c in candidates])
        return self._by_stem.get(loose_name(name).replace(" ", "_"))

    def face_names(self) -> set[str]:
        return {face for script in self.scripts for face in script.faces}


def parse_card_script(path: Path, text: str | None = None) -> CardScript:
    """Parse one card script file into a :class:`CardScript`."""
    if text is None:
        text = path.read_text(encoding="utf-8")
    faces: list[str] = []
    types: list[str] = []
    ai_flags: list[str] = []
    ai_hints: list[str] = []
    copy_limit: int | float | None = None
    alternate_mode = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("Name:"):
            faces.append(line[len("Name:") :].strip())
        elif line.startswith("CopyFaceFrom:"):
            # Split cards whose faces are scripted in their own files name them
            # this way instead of with a Name: line (e.g. bind_liberate.txt).
            faces.append(line[len("CopyFaceFrom:") :].strip())
        elif line.startswith("AlternateMode:"):
            alternate_mode = line[len("AlternateMode:") :].strip()
        elif line.startswith("Types:"):
            types.extend(line[len("Types:") :].split())
        elif line.startswith("AI:"):
            ai_flags.append(line[len("AI:") :].strip())
        elif line.startswith("SVar:AI"):
            ai_hints.append(line[len("SVar:") :].strip())
        if "a deck can have" in line.casefold():
            copy_limit = _parse_deck_limit(line, copy_limit)
    if not faces:
        raise ValueError(f"{path}: card script names no card (no Name: or CopyFaceFrom:)")
    return CardScript(
        name=" // ".join(faces) if alternate_mode == "Split" else faces[0],
        faces=tuple(dict.fromkeys(faces)),
        path=path,
        types=tuple(types),
        ai_flags=tuple(ai_flags),
        ai_hints=tuple(ai_hints),
        copy_limit=copy_limit,
    )


def index_cardsfolder(
    root: str | Path, *, include_upcoming: bool = False
) -> CardPool:
    """Scan a ``cardsfolder`` tree and index every face of every script."""
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"cardsfolder not found: {root}")
    scripts: list[CardScript] = []
    for path in sorted(root.rglob("*.txt")):
        if not include_upcoming and UPCOMING_DIR in {
            part.casefold() for part in path.relative_to(root).parts[:-1]
        }:
            continue
        scripts.append(parse_card_script(path))
    return CardPool(scripts, root)


def _parse_deck_limit(line: str, current: int | float | None) -> int | float | None:
    match = _DECK_LIMIT_RE.search(line)
    if match is None:
        return current
    phrase = match.group(1).casefold()
    if phrase.startswith("any number"):
        return math.inf
    if phrase.startswith("only one"):
        return 1
    word = (match.group("word") or "").casefold()
    return int(word) if word.isdecimal() else _NUMBER_WORDS.get(word, current)
