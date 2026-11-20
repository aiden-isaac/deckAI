"""Scryfall's view of Standard legality and paper availability.

This is the third validation source (design decision D5): Forge's format file
says what the engine will do, the cardsfolder index says what it can play, and
Scryfall says what is legal in paper — which is what the user's money buys.

Only the stdlib is used (``urllib`` plus ``gzip``), and the bulk file is cached
under ``cache/scryfall/`` so later runs are offline. The bulk feed is one card
object per Oracle id; a card is counted legal when *any* entry bearing its name
(whole card or a single face of a multi-faced card) is ``legalities.standard ==
"legal"`` and available in paper. That face-level indexing is what makes
``Skycoach Conductor`` resolvable even though Scryfall names the card
``Skycoach Conductor // All Aboard``.
"""

from __future__ import annotations

import gzip
import json
import shutil
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

BULK_INDEX_URL = "https://api.scryfall.com/bulk-data"
BULK_TYPE = "oracle_cards"
USER_AGENT = "deckAI/0.1 (local measurement harness)"
DEFAULT_CACHE_DIR = Path("cache/scryfall")

#: Layouts that are not playable cards; they carry card names but never a legality.
NON_CARD_LAYOUTS = frozenset(
    {
        "art_series",
        "token",
        "double_faced_token",
        "emblem",
        "scheme",
        "planar",
        "vanguard",
        "sticker",
        "augment",
        "host",
    }
)


class ScryfallDataUnavailable(RuntimeError):
    """No cached Scryfall data and no network access to fetch it."""


@dataclass(frozen=True)
class ScryfallStandard:
    """Names Scryfall reports as Standard-legal and paper-available."""

    legal_names: frozenset[str]
    known_names: frozenset[str]
    updated_at: str
    bulk_file: str
    legal_count: int
    total_cards: int

    @property
    def version(self) -> str:
        return f"scryfall:{BULK_TYPE}@{self.updated_at}"

    def is_legal(self, card_name: str) -> bool:
        from harness.cardpool import canonical_name, loose_name

        return (
            canonical_name(card_name) in self.legal_names
            or loose_name(card_name) in self.legal_names
        )

    def is_known(self, card_name: str) -> bool:
        """Whether Scryfall has heard of the card at all."""
        from harness.cardpool import canonical_name, loose_name

        return (
            canonical_name(card_name) in self.known_names
            or loose_name(card_name) in self.known_names
        )

    def to_json(self) -> str:
        return json.dumps(
            {
                "updated_at": self.updated_at,
                "bulk_file": self.bulk_file,
                "legal_count": self.legal_count,
                "total_cards": self.total_cards,
                "legal_names": sorted(self.legal_names),
                "known_names": sorted(self.known_names),
            }
        )

    @classmethod
    def from_json(cls, text: str) -> "ScryfallStandard":
        data = json.loads(text)
        return cls(
            legal_names=frozenset(data["legal_names"]),
            known_names=frozenset(data["known_names"]),
            updated_at=data["updated_at"],
            bulk_file=data["bulk_file"],
            legal_count=data["legal_count"],
            total_cards=data["total_cards"],
        )


def build_standard_index(
    cards: Iterable[dict], *, updated_at: str = "unknown", bulk_file: str = "in-memory"
) -> ScryfallStandard:
    """Fold raw Scryfall card objects into the Standard-legal name index."""
    from harness.cardpool import canonical_name, loose_name

    legal: set[str] = set()
    known: set[str] = set()
    total = 0
    legal_cards = 0
    for card in cards:
        total += 1
        layout = card.get("layout", "normal")
        if layout in NON_CARD_LAYOUTS:
            continue
        names = _names_of(card)
        for name in names:
            known.add(canonical_name(name))
            known.add(loose_name(name))
        standard = (card.get("legalities") or {}).get("standard")
        in_paper = "paper" in (card.get("games") or [])
        if standard == "legal" and in_paper:
            legal_cards += 1
            for name in names:
                legal.add(canonical_name(name))
                legal.add(loose_name(name))
    return ScryfallStandard(
        legal_names=frozenset(legal),
        known_names=frozenset(known),
        updated_at=updated_at,
        bulk_file=bulk_file,
        legal_count=legal_cards,
        total_cards=total,
    )


def load_standard(
    cache_dir: str | Path = DEFAULT_CACHE_DIR, *, allow_network: bool = True
) -> ScryfallStandard:
    """Load the Standard index, downloading the bulk file only if needed."""
    cache_dir = Path(cache_dir)
    filtered = cache_dir / "standard-legal.json"
    if filtered.is_file():
        try:
            return ScryfallStandard.from_json(filtered.read_text(encoding="utf-8"))
        except (ValueError, KeyError, TypeError) as exc:
            raise ScryfallDataUnavailable(f"invalid Scryfall cache {filtered}: {exc}") from exc
    bulk = _newest_bulk_file(cache_dir)
    if bulk is None:
        if not allow_network:
            raise ScryfallDataUnavailable(
                f"no Scryfall bulk data under {cache_dir} and network use is disabled"
            )
        bulk = download_bulk(cache_dir)
    index = build_standard_index(
        iter_bulk_cards(bulk),
        updated_at=_updated_at_from_filename(bulk.name),
        bulk_file=bulk.name,
    )
    filtered.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=cache_dir, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(index.to_json())
            handle.close()
            temporary.replace(filtered)
        finally:
            temporary.unlink(missing_ok=True)
    return index


def download_bulk(cache_dir: str | Path = DEFAULT_CACHE_DIR) -> Path:
    """Download the ``oracle_cards`` bulk file into the cache and return its path."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    meta = _fetch_bulk_metadata()
    url = meta.get("jsonl_download_uri") or meta["download_uri"]
    dest = cache_dir / url.rsplit("/", 1)[-1]
    if dest.is_file():
        return dest
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"}
    )
    with tempfile.NamedTemporaryFile(dir=cache_dir, suffix=".part", delete=False) as handle:
        partial = Path(handle.name)
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                shutil.copyfileobj(response, handle, 1 << 16)
                expected = response.headers.get("Content-Length")
            handle.close()
            expected = expected or (meta.get("compressed_size") if url.endswith(".gz") else None)
            if expected is not None and partial.stat().st_size != int(expected):
                raise ScryfallDataUnavailable(f"incomplete Scryfall download: {url}")
            partial.replace(dest)
        finally:
            partial.unlink(missing_ok=True)
    return dest


def iter_bulk_cards(path: str | Path) -> Iterator[dict]:
    """Yield card objects from a bulk file (JSONL or JSON array, gzipped or not)."""
    path = Path(path)
    opener = gzip.open if path.name.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as handle:  # type: ignore[operator]
        first = handle.read(1)
        while first and first.isspace():
            first = handle.read(1)
        handle.seek(0)
        if first == "[":
            yield from json.load(handle)
            return
        for line in handle:
            text = line.strip().rstrip(",")
            if not text or text in "[]":
                continue
            yield json.loads(text)


def _names_of(card: dict) -> list[str]:
    names = []
    whole = card.get("name")
    if whole:
        names.append(whole)
    for face in card.get("card_faces") or []:
        face_name = face.get("name")
        if face_name:
            names.append(face_name)
    return names


def _fetch_bulk_metadata() -> dict:
    request = urllib.request.Request(
        BULK_INDEX_URL,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.load(response)
    for entry in payload["data"]:
        if entry.get("type") == BULK_TYPE:
            return entry
    raise ScryfallDataUnavailable(f"bulk data has no {BULK_TYPE} entry")


def _newest_bulk_file(cache_dir: Path) -> Path | None:
    candidates = sorted(cache_dir.glob("oracle-cards-*.json*"))
    candidates = [p for p in candidates if not p.name.endswith(".part")]
    return candidates[-1] if candidates else None


def _updated_at_from_filename(name: str) -> str:
    stamp = name.removeprefix("oracle-cards-").split(".", 1)[0]
    return stamp or "unknown"
