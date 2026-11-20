"""Read and write Forge ``.dck`` deck files.

A ``.dck`` file is an INI-like list of sections. ``[metadata]`` holds ``Key=Value``
lines; every other section holds deck entries of the form
``<count> <card name>[|<set code>[|<art index>]]``.

Normalisation here means: a canonical rendering (``[metadata]`` first, one blank
line between sections, entries in the order they were written, ``Key=Value`` and
``count name|SET|art`` spacing fixed). Reading a file and writing it back
reproduces the same bytes for any file already in that form, so a round-trip test
is a real check rather than a tautology.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

METADATA_SECTION = "metadata"

# Forge's own section spellings. Parsing is case-insensitive; writing uses these.
CANONICAL_SECTIONS = (
    METADATA_SECTION,
    "Avatar",
    "Commander",
    "Main",
    "Sideboard",
    "Planes",
    "Schemes",
    "Conspiracy",
    "Dungeon",
    "Attractions",
    "Contraptions",
)
_CANONICAL_BY_KEY = {name.lower(): name for name in CANONICAL_SECTIONS}


class DckError(ValueError):
    """A ``.dck`` file could not be parsed."""


@dataclass(frozen=True)
class CardEntry:
    """One deck line: a count, a card name, and an optional pinned printing."""

    count: int
    name: str
    set_code: str | None = None
    art_index: str | None = None

    def __post_init__(self) -> None:
        if type(self.count) is not int or self.count <= 0:
            raise DckError(f"{self.name!r}: count must be a positive integer")
        if not self.name.strip() or any(c in self.name for c in "\r\n|"):
            raise DckError(f"invalid card name: {self.name!r}")

    def render(self) -> str:
        parts = [self.name]
        if self.set_code:
            parts.append(self.set_code)
            if self.art_index:
                parts.append(self.art_index)
        return f"{self.count} {'|'.join(parts)}"


@dataclass
class Deck:
    """A parsed deck: metadata plus card entries per section."""

    name: str = ""
    metadata: dict[str, str] = field(default_factory=dict)
    sections: dict[str, list[CardEntry]] = field(default_factory=dict)
    source_path: Path | None = None

    @property
    def main(self) -> list[CardEntry]:
        return self.sections.get("Main", [])

    @property
    def sideboard(self) -> list[CardEntry]:
        return self.sections.get("Sideboard", [])

    def count(self, section: str) -> int:
        return sum(entry.count for entry in self.sections.get(section, []))

    @property
    def main_count(self) -> int:
        return self.count("Main")

    @property
    def sideboard_count(self) -> int:
        return self.count("Sideboard")

    def all_entries(self) -> list[tuple[str, CardEntry]]:
        """Every entry as ``(section, entry)``, in canonical section order."""
        return [
            (section, entry)
            for section in _ordered_sections(self.sections)
            for entry in self.sections[section]
        ]


def parse_dck(text: str, *, source_path: Path | None = None) -> Deck:
    """Parse ``.dck`` text. Unknown sections are preserved as-is."""
    deck = Deck(source_path=source_path)
    section: str | None = None
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = _canonical_section(line[1:-1].strip())
            if section != METADATA_SECTION:
                deck.sections.setdefault(section, [])
            continue
        if section is None:
            raise DckError(f"line {lineno}: content before any section header: {raw!r}")
        if section == METADATA_SECTION:
            key, sep, value = line.partition("=")
            if not sep:
                raise DckError(f"line {lineno}: metadata line without '=': {raw!r}")
            key = key.strip()
            deck.metadata[key] = value.strip()
            if key.lower() == "name":
                deck.name = value.strip()
            continue
        deck.sections[section].append(_parse_entry(line, lineno))
    return deck


def read_dck(path: str | Path) -> Deck:
    path = Path(path)
    return parse_dck(path.read_text(encoding="utf-8"), source_path=path)


def write_dck(deck: Deck) -> str:
    """Render a deck in canonical form (the normalisation used for round-trips)."""
    blocks: list[str] = []
    metadata = dict(deck.metadata)
    if deck.name and not any(key.lower() == "name" for key in metadata):
        metadata = {"Name": deck.name, **metadata}
    if metadata:
        lines = [f"[{METADATA_SECTION}]"]
        lines += [f"{key}={value}" for key, value in metadata.items()]
        blocks.append("\n".join(lines))
    for section in _ordered_sections(deck.sections):
        lines = [f"[{section}]"]
        lines += [entry.render() for entry in deck.sections[section]]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n"


def save_dck(deck: Deck, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(write_dck(deck), encoding="utf-8")
    return path


def normalise_dck(text: str) -> str:
    """Canonical rendering of arbitrary ``.dck`` text."""
    return write_dck(parse_dck(text))


def build_deck(
    name: str,
    main: list[CardEntry],
    sideboard: list[CardEntry] | None = None,
    **metadata: str,
) -> Deck:
    """Build a deck in memory (used by tests and deck authoring tools)."""
    sections: dict[str, list[CardEntry]] = {"Main": list(main)}
    if sideboard is not None:
        sections["Sideboard"] = list(sideboard)
    return Deck(name=name, metadata={"Name": name, **metadata}, sections=sections)


def with_section(deck: Deck, section: str, entries: list[CardEntry]) -> Deck:
    """Return a copy of ``deck`` with one section replaced."""
    sections = {key: list(value) for key, value in deck.sections.items()}
    sections[_canonical_section(section)] = list(entries)
    return replace(deck, sections=sections)


def _parse_entry(line: str, lineno: int) -> CardEntry:
    parts = line.split(maxsplit=1)
    if len(parts) != 2:
        raise DckError(f"line {lineno}: deck line without a count: {line!r}")
    count_text, remainder = parts
    try:
        count = int(count_text)
    except ValueError as exc:
        raise DckError(f"line {lineno}: non-numeric count in {line!r}") from exc
    fields = [part.strip() for part in remainder.split("|")]
    if len(fields) > 3:
        raise DckError(f"line {lineno}: too many printing fields: {line!r}")
    name = fields[0]
    if not name:
        raise DckError(f"line {lineno}: deck line without a card name: {line!r}")
    set_code = fields[1] if len(fields) > 1 and fields[1] else None
    art_index = fields[2] if len(fields) > 2 and fields[2] else None
    return CardEntry(count=count, name=name, set_code=set_code, art_index=art_index)


def _canonical_section(name: str) -> str:
    return _CANONICAL_BY_KEY.get(name.lower(), name)


def _ordered_sections(sections: dict[str, list[CardEntry]]) -> list[str]:
    known = [s for s in CANONICAL_SECTIONS if s != METADATA_SECTION and s in sections]
    extra = [s for s in sections if s not in CANONICAL_SECTIONS]
    return known + extra
