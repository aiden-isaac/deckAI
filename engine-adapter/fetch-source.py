#!/usr/bin/env python3
"""Fetch only hash-pinned overlay files, reusing verified local bytes."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parent

def main():
    pin = json.loads((ROOT / 'source-pin.json').read_text())
    def fetch(item):
        path, expected = item
        target = ROOT / 'upstream' / path
        if target.exists():
            data = target.read_bytes()
        else:
            data = urllib.request.urlopen(
                f"https://raw.githubusercontent.com/lumlaolao/spike-eval/{pin['commit']}/{path}",
                timeout=90).read()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f'Pinned source hash mismatch: {path}')
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(fetch, pin['files'].items()))
    print(f"Verified {len(pin['files'])} pinned source files")

if __name__ == '__main__':
    main()
