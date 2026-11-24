"""Durable run journal. SQLite is a disposable index, never the authority."""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import sqlite3
import threading


def read_run(directory: str | Path) -> tuple[dict, list[dict]]:
    path = Path(directory) / "run.jsonl"
    events = []
    with path.open("rb") as stream:
        for number, line in enumerate(stream, 1):
            if not line.endswith(b"\n"):
                break  # A killed writer can leave only the last line torn.
            try:
                events.append(json.loads(line))
            except (ValueError, UnicodeError) as error:
                raise ValueError(f"{path}:{number}: corrupt journal") from error
    if not events or events[0].get("type") != "run":
        raise ValueError(f"{path}: missing run header")
    return events[0], events[1:]


def game_records(directory: str | Path) -> list[dict]:
    header, events = read_run(directory)
    discarded = {event["attempt"] for event in events if event["type"] == "discard"}
    games = {}
    for event in events:
        if event["type"] != "game" or event["attempt"] in discarded:
            continue
        key = event["cell_id"]
        if key in games:
            raise ValueError(f"duplicate completed cell: {key}")
        games[key] = event
    return [games[cell["cell_id"]] for cell in header["plan"] if cell["cell_id"] in games]


class Journal:
    """One locked harness writer, shared safely by its worker threads."""

    def __init__(self, directory: str | Path, header: dict | None = None):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = (self.directory / ".lock").open("a")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            path = self.directory / "run.jsonl"
            if header is not None:
                self.stream = path.open("xb")
            else:
                read_run(self.directory)  # Refuse interior corruption before recovery.
                self.stream = path.open("r+b")
                end = 0
                for line in self.stream:
                    if not line.endswith(b"\n"):
                        break
                    end += len(line)
                self.stream.truncate(end)
                self.stream.seek(end)
            self.mutex = threading.Lock()
            if header is not None:
                self.append(header)
        except BaseException:
            self.lock.close()
            raise

    def append(self, event: dict) -> None:
        line = (json.dumps(event, sort_keys=True, allow_nan=False) + "\n").encode()
        with self.mutex:
            self.stream.write(line)
            self.stream.flush()
            os.fsync(self.stream.fileno())

    def close(self) -> None:
        self.stream.close()
        self.lock.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def rebuild_index(directory: str | Path, database: str | Path | None = None) -> int:
    """Replace only the derived SQLite tables, in one transaction."""
    directory = Path(directory)
    header, events = read_run(directory)
    records = game_records(directory)
    with sqlite3.connect(database or directory / "index.sqlite3") as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, header TEXT, state TEXT)")
        connection.execute("CREATE TABLE IF NOT EXISTS games (run_id TEXT, cell_id TEXT, opponent TEXT, seed INTEGER, won INTEGER, draw INTEGER, turns INTEGER, record TEXT, PRIMARY KEY(run_id, cell_id))")
        connection.execute("DELETE FROM games WHERE run_id = ?", (header["run_id"],))
        state = events[-1]["type"] if events else "incomplete"
        connection.execute("INSERT OR REPLACE INTO runs VALUES (?, ?, ?)", (header["run_id"], json.dumps(header), state))
        connection.executemany("INSERT INTO games VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [
            (header["run_id"], row["cell_id"], row["opponent"], row["seed"], row["won"], row["draw"], row["turns"], json.dumps(row))
            for row in records
        ])
    return len(records)
