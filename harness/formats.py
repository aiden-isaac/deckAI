"""Forge's own format definitions and edition card lists.

Two files inside the pinned engine decide what Forge itself considers legal:

* ``forge-gui/res/formats/Sanctioned/<Format>.txt`` — the ``Sets:`` line (set
  codes, comma-separated) and the ``Banned:`` line (card names, semicolon-
  separated), parsed the same way ``GameFormat.Reader`` parses them.
* ``forge-gui/res/editions/*.txt`` — per-set card lists. ``CardEdition`` treats
  every section carrying collector numbers as part of the set (so a card listed
  only under ``[precon product]`` or ``[borderless]`` is still in the set), with
  ``[metadata]``, ``[tokens]``, ``[other]`` reserved and ``[conjured]`` cards
  not obtainable.

Nothing here is hardcoded: set codes and bans come from the installed files, so
a Standard rotation is picked up by re-reading the engine.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

#: Sections of an edition file that ``CardEdition`` parses as cards, minus
#: ``conjured`` (not obtainable). Mirrors ``EditionSectionWithCollectorNumbers``.
EDITION_CARD_SECTIONS = frozenset(
    {
        "cards",
        "special slot",
        "precon product",
        "borderless",
        "etched",
        "showcase",
        "full art",
        "extended art",
        "alternate art",
        "retro frame",
        "buy a box",
        "promo",
        "prerelease promo",
        "bundle",
        "box topper",
        "jumpstart",
        "rebalanced",
        "eternal",
        "scheme",
    }
)

# Translated from CardEdition.Reader.CARD_PATTERN: optional collector number,
# optional rarity letter, name, optional "@artist", optional "${params}".
_EDITION_CARD_RE = re.compile(
    r"^(?:(.?[0-9A-Z-]+\S*[A-Z]*)\s)?(?:([SCURML])\s)?([^@$]+?)(?:\s@([^$]*))?(?:\s\$\{(.+)\})?$"
)


@dataclass(frozen=True)
class Format:
    """A parsed Forge format definition."""

    name: str
    sets: tuple[str, ...]
    banned: tuple[str, ...]
    restricted: tuple[str, ...]
    effective: str | None
    source_path: Path
    source_sha256: str

    @property
    def version(self) -> str:
        """Identity of the format definition that a result was validated against."""
        return f"{self.name}@{self.source_sha256[:12]}"

    def is_set_legal(self, set_code: str) -> bool:
        if not self.sets:
            return True
        return set_code.upper() in {s.upper() for s in self.sets}


def parse_format(path: str | Path) -> Format:
    """Parse a Forge format file (e.g. ``Sanctioned/Standard.txt``)."""
    path = Path(path)
    raw = path.read_bytes()
    section: str | None = None
    fields: dict[str, str] = {}
    for line in raw.decode("utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        if text.startswith("[") and text.endswith("]"):
            section = text[1:-1].strip().casefold()
            continue
        if section != "format":
            continue
        key, sep, value = text.partition(":")
        if sep:
            fields[key.strip().casefold()] = value.strip()
    if "name" not in fields:
        raise ValueError(f"{path}: no Name: in [format] section")
    return Format(
        name=fields["name"],
        sets=_split(fields.get("sets"), ", "),
        banned=_split(fields.get("banned"), "; "),
        restricted=_split(fields.get("restricted"), "; "),
        effective=fields.get("effective"),
        source_path=path,
        source_sha256=hashlib.sha256(raw).hexdigest(),
    )


class EditionIndex:
    """Card name to set codes, over a chosen subset of Forge's editions."""

    def __init__(self, sets_by_card: dict[str, set[str]], set_codes: set[str]) -> None:
        self._sets_by_card = {
            name: frozenset(codes) for name, codes in sets_by_card.items()
        }
        self.set_codes = frozenset(set_codes)

    def __len__(self) -> int:
        return len(self._sets_by_card)

    def sets_for(self, card_name: str) -> frozenset[str]:
        from harness.cardpool import canonical_name, loose_name

        exact = self._sets_by_card.get(canonical_name(card_name))
        if exact is not None:
            return exact
        return self._sets_by_card.get(loose_name(card_name), frozenset())

    def is_legal(self, card_name: str) -> bool:
        """True when the card has a printing in one of the indexed sets."""
        return bool(self.sets_for(card_name))


def build_edition_index(
    editions_dir: str | Path, set_codes: set[str] | None = None
) -> EditionIndex:
    """Index the cards printed in ``set_codes`` (all sets when ``None``)."""
    from harness.cardpool import canonical_name, loose_name

    editions_dir = Path(editions_dir)
    if not editions_dir.is_dir():
        raise FileNotFoundError(f"editions directory not found: {editions_dir}")
    wanted = {code.upper() for code in set_codes} if set_codes else None
    sets_by_card: dict[str, set[str]] = {}
    found: set[str] = set()
    for path in sorted(editions_dir.glob("*.txt")):
        code, cards = _read_edition(path)
        if code is None:
            continue
        if wanted is not None and code.upper() not in wanted:
            continue
        found.add(code.upper())
        for name in cards:
            for alias in (name, *name.split(" // ")):
                for key in (canonical_name(alias), loose_name(alias)):
                    sets_by_card.setdefault(key, set()).add(code.upper())
    if wanted is not None and wanted - found:
        raise ValueError(f"missing Forge editions: {', '.join(sorted(wanted - found))}")
    return EditionIndex(sets_by_card, found)


def _read_edition(path: Path) -> tuple[str | None, list[str]]:
    code: str | None = None
    section: str | None = None
    names: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        if text.startswith("[") and text.endswith("]"):
            section = text[1:-1].strip().casefold()
            continue
        if section == "metadata":
            if text.startswith("Code="):
                code = text[len("Code=") :].strip()
            continue
        if section not in EDITION_CARD_SECTIONS:
            continue
        match = _EDITION_CARD_RE.match(text)
        if match is None:
            continue
        name = (match.group(3) or "").strip()
        if name:
            names.append(name)
    return code, names


def _split(value: str | None, separator: str) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(part.strip() for part in value.split(separator) if part.strip())
