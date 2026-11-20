"""Verify the fixed opponents before using them as a measuring instrument."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


def file_hash(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_gauntlet(manifest_path: str | Path) -> dict:
    """Load a frozen manifest, refusing missing, changed or escaping decks."""
    manifest_path = Path(manifest_path).resolve()
    manifest = json.loads(manifest_path.read_text())
    opponents = manifest.get("opponents")
    if not isinstance(opponents, list) or not opponents:
        raise ValueError("gauntlet must declare opponents")
    names = set()
    total_weight = 0.0
    for opponent in opponents:
        name = opponent.get("id")
        if not isinstance(name, str) or not name or name in names:
            raise ValueError(f"invalid or duplicate opponent id: {name!r}")
        names.add(name)
        relative = Path(opponent["deck"])
        deck = (manifest_path.parent / relative).resolve()
        if relative.is_absolute() or not deck.is_relative_to(manifest_path.parent):
            raise ValueError(f"opponent {name}: deck must remain inside the gauntlet")
        if not deck.is_file() or file_hash(deck) != opponent.get("sha256"):
            raise ValueError(f"opponent {name}: frozen deck drift: {relative}")
        weight = opponent.get("weight")
        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            raise ValueError(f"opponent {name}: weight must be a finite positive number")
        if not math.isfinite(weight) or weight <= 0:
            raise ValueError(f"opponent {name}: weight must be a finite positive number")
        total_weight += weight
    if not math.isfinite(total_weight):
        raise ValueError("gauntlet total weight must be finite")
    # The complete manifest is the version, including weights and deck hashes.
    return {**manifest, "version": file_hash(manifest_path)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    manifest = load_gauntlet(args.manifest)
    print(f"Verified {len(manifest['opponents'])} frozen opponents: {manifest['version']}")


if __name__ == "__main__":
    main()
