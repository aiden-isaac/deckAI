import gzip
import io
import json
from unittest.mock import patch

import pytest

from harness.scryfall import (
    ScryfallDataUnavailable, build_standard_index, download_bulk, iter_bulk_cards, load_standard,
)


CARDS = [
    {"name": "Front // Back", "card_faces": [{"name": "Front"}, {"name": "Back"}],
     "legalities": {"standard": "legal"}, "games": ["paper"]},
    {"name": "Digital", "legalities": {"standard": "legal"}, "games": ["arena"]},
    {"name": "Banned", "legalities": {"standard": "banned"}, "games": ["paper"]},
    {"name": "Goblin", "layout": "token", "legalities": {"standard": "legal"}, "games": ["paper"]},
]


def test_paper_filter_counts_cards_not_aliases():
    index = build_standard_index(CARDS)
    assert index.legal_count == 1
    assert index.total_cards == 4
    assert all(index.is_legal(n) for n in ("Front", "Back", "Front // Back"))
    assert not index.is_legal("Digital")
    assert not index.is_legal("Banned")
    assert not index.is_known("Goblin")


@pytest.mark.parametrize("suffix", ["json", "jsonl", "jsonl.gz"])
def test_bulk_formats_and_offline_cache(tmp_path, suffix):
    path = tmp_path / f"oracle-cards-20261120.{suffix}"
    payload = " \n" + json.dumps(CARDS, indent=2) if suffix == "json" else "\n".join(map(json.dumps, CARDS))
    path.write_bytes(gzip.compress(payload.encode()) if suffix.endswith("gz") else payload.encode())
    assert list(iter_bulk_cards(path)) == CARDS
    with patch("urllib.request.urlopen", side_effect=AssertionError("offline means offline")):
        index = load_standard(tmp_path, allow_network=False)
        assert index.legal_count == 1
        assert (tmp_path / "standard-legal.json").is_file()
        path.unlink()
        assert load_standard(tmp_path, allow_network=False) == index


def test_missing_or_corrupt_cache_fails_closed(tmp_path):
    with pytest.raises(ScryfallDataUnavailable, match="network use is disabled"):
        load_standard(tmp_path, allow_network=False)
    (tmp_path / "standard-legal.json").write_text("{")
    with pytest.raises(ScryfallDataUnavailable, match="invalid Scryfall cache"):
        load_standard(tmp_path, allow_network=False)


@pytest.mark.parametrize("complete", [True, False])
def test_bulk_download_is_atomic_and_rejects_short_body(tmp_path, complete):
    payload = gzip.compress("\n".join(map(json.dumps, CARDS)).encode())
    meta = {"type": "oracle_cards", "jsonl_download_uri": "https://data.scryfall.io/oracle-cards-20261120.jsonl.gz", "compressed_size": len(payload)}
    response = io.BytesIO(payload if complete else payload[:-1])
    response.headers = {"Content-Length": str(len(payload))}
    with patch("harness.scryfall._fetch_bulk_metadata", return_value=meta), patch("urllib.request.urlopen", return_value=response):
        if complete:
            path = download_bulk(tmp_path)
            assert list(iter_bulk_cards(path)) == CARDS
        else:
            with pytest.raises(ScryfallDataUnavailable, match="incomplete"):
                download_bulk(tmp_path)
            assert not list(tmp_path.iterdir())
