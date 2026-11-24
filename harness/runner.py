"""Memory-bounded, replayable Forge BO1 batches."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

from harness.dck import parse_dck
from harness.gauntlet import load_gauntlet
from harness.stats import ResultIdentity, allocate_games
from harness.store import Journal, game_records, read_run, rebuild_index
from harness.validation import build_validator, parse_runtime_reveals


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def plan_games(candidate: str, weights: dict, games: int, seed: int) -> list[dict]:
    counts = allocate_games(weights, games)
    plan = []
    for opponent, count in counts.items():
        for index in range(count):
            seat = index % 2
            on_play = index % 4 in (0, 3)
            cell = dict(candidate=candidate, opponent=opponent, seed=seed + index,
                        seat=seat, on_play=on_play,
                        first_player_seat=seat if on_play else 1 - seat)
            if not -(2**63) <= cell["seed"] < 2**63:
                raise ValueError("seed must fit a signed Java long")
            cell["cell_id"] = _hash(json.dumps(cell, sort_keys=True).encode())[:24]
            plan.append(cell)
    return plan


def worker_count(worker_ceiling_mib: int, available_mib: int | None = None) -> int:
    if type(worker_ceiling_mib) is not int or worker_ceiling_mib <= 0:
        raise ValueError("worker ceiling must be positive measured MiB")
    if available_mib is None:
        values = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
        available_mib = int(values["MemAvailable"].split()[0]) // 1024
    count = available_mib // worker_ceiling_mib
    if count < 1:
        raise ValueError("insufficient available memory for one worker")
    return count


def _verify_engine(engine: dict) -> None:
    root = Path(engine["forge_root"])
    pin = engine["pin"]
    head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    if head != pin["patched_commit"]:
        raise ValueError("engine patched_commit drift")
    if subprocess.check_output(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"], text=True).strip():
        raise ValueError("engine tracked working tree drift")
    patches = b"".join((Path(engine["patch_root"]) / name).read_bytes() for name in pin["patch_files"])
    if _hash(patches) != pin["patch_hash"]:
        raise ValueError("engine patch_hash drift")
    if _hash(Path(pin["jar"]).read_bytes()) != pin["jar_sha256"]:
        raise ValueError("engine jar_sha256 drift")


def _verify_snapshots(header: dict) -> None:
    identity = header["identity"]
    ResultIdentity(**{field: identity[field] for field in ResultIdentity.__dataclass_fields__}).require_complete()
    for role in ("candidate", "incumbent"):
        if _hash(header["decks"][role].encode()) != identity[f"{role}_deck_hash"]:
            raise ValueError(f"{role} deck snapshot drift")
    if set(header["opponents"]) != set(identity["opponent_deck_hashes"]):
        raise ValueError("opponent deck snapshot drift")
    for name, text in header["opponents"].items():
        if _hash(text.encode()) != identity["opponent_deck_hashes"][name]:
            raise ValueError(f"opponent {name} deck snapshot drift")


def run_gauntlet(directory, candidate, incumbent, manifest, forge_root, pin_path,
                 java, worker_ceiling_mib, xmx_mib=2048, games=200,
                 seed=20261120, profiles=("Default", "Default"), clock=120) -> dict:
    """Validate and snapshot all inputs, then run fixed-seed, mirrored BO1 games."""
    if len(profiles) != 2 or any(not isinstance(p, str) or not p.strip() for p in profiles):
        raise ValueError("declare candidate and opponent AI profiles")
    if type(clock) is not int or clock <= 0:
        raise ValueError("clock must be positive integer seconds")
    if type(xmx_mib) is not int or not 0 < xmx_mib < worker_ceiling_mib:
        raise ValueError("worker ceiling must exceed the positive JVM heap")
    pin_path = Path(pin_path).resolve()
    pin = json.loads(pin_path.read_text())
    engine = dict(forge_root=str(Path(forge_root).resolve()), patch_root=str(pin_path.parent),
                  pin=pin, java=str(java), xmx_mib=xmx_mib)
    _verify_engine(engine)
    gauntlet = load_gauntlet(manifest)
    decks = {"candidate": Path(candidate).read_text(), "incumbent": Path(incumbent).read_text()}
    opponents = {item["id"]: (Path(manifest).resolve().parent / item["deck"]).read_text()
                 for item in gauntlet["opponents"]}
    validator = build_validator(forge_root, allow_network=False)
    validations = [validator.validate(parse_dck(text)) for text in [*decks.values(), *opponents.values()]]
    if any(not result.passed for result in validations):
        raise ValueError("deck validation failed: " + json.dumps([r.to_dict() for r in validations if not r.passed]))
    hashes = {name: _hash(text.encode()) for name, text in decks.items()}
    identity = asdict(ResultIdentity(pin["engine_commit"], pin["patch_hash"], hashes["candidate"],
                                    hashes["incumbent"], gauntlet["version"],
                                    json.dumps(list(profiles)), "off", clock).require_complete())
    identity.update(card_data_version=pin["card_data_version"],
                    opponent_deck_hashes={name: _hash(text.encode()) for name, text in opponents.items()},
                    profiles=list(profiles), filtered_hands=False, mulligan_rule="London")
    weights = {item["id"]: item["weight"] for item in gauntlet["opponents"]}
    header = dict(type="run", schema=1, run_id=uuid.uuid4().hex, identity=identity,
                  engine=engine, decks=decks, opponents=opponents, weights=weights,
                  validations=[r.to_dict() for r in validations],
                  worker_ceiling_mib=worker_ceiling_mib,
                  plan=plan_games(hashes["candidate"], weights, games, seed))
    with Journal(directory, header):
        pass
    return resume_run(directory)


def _record(raw: dict, cell: dict, index: int) -> dict:
    for field in ("turns", "elapsed_ms", "seed", "first_player_seat", "match_game_index", "game_index"):
        if type(raw.get(field)) is not int:
            raise ValueError(f"invalid engine field {field}: {raw!r}")
    for field in ("draw", "clock_terminated", "sideboarding", "filtered_hands"):
        if type(raw.get(field)) is not bool:
            raise ValueError(f"invalid engine field {field}: {raw!r}")
    for field in ("mulligans", "damage_by_turn_5"):
        value = raw.get(field)
        if not isinstance(value, list) or len(value) != 2 or any(type(v) is not int or v < 0 for v in value):
            raise ValueError(f"invalid engine field {field}: {raw!r}")
    for field in ("stripped", "cannot_play_well", "seats"):
        value = raw.get(field)
        if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
            raise ValueError(f"invalid engine field {field}: {raw!r}")
    winner = raw.get("winner_seat")
    if ("winner_seat" not in raw or (winner is not None and (type(winner) is not int or winner not in (0, 1)))
            or raw["draw"] != (winner is None) or (raw["clock_terminated"] and not raw["draw"])):
        raise ValueError(f"inconsistent winner/draw/clock: {raw!r}")
    if (raw["seed"] != cell["seed"] or raw["first_player_seat"] != cell["first_player_seat"]
            or raw["game_index"] != index or raw["match_game_index"] != 1
            or raw["sideboarding"] or raw["filtered_hands"] or raw.get("mulligan_rule") != "London"
            or raw["turns"] < 0 or raw["elapsed_ms"] < 0 or len(raw["seats"]) != 2
            or not isinstance(raw.get("loss_reason"), str) or not raw["loss_reason"]):
        raise ValueError(f"engine record does not match requested game: {raw!r}")
    return {**raw, **cell, "won": winner == cell["seat"] if winner is not None else False}


def _attempt(journal: Journal, header: dict, cells: list[dict], timeout: float | None = None) -> list[dict]:
    attempt = uuid.uuid4().hex
    work = journal.directory / "attempts" / attempt
    work.mkdir(parents=True)
    first = cells[0]
    candidate = work / "candidate.dck"
    opponent = work / "opponent.dck"
    candidate.write_text(header["decks"]["candidate"])
    opponent.write_text(header["opponents"][first["opponent"]])
    seeds = work / "seeds.txt"
    seeds.write_text("".join(f"{cell['seed']}\n" for cell in cells))
    output = work / "games.jsonl"
    output.touch()
    decks = [candidate, opponent] if first["seat"] == 0 else [opponent, candidate]
    profiles = header["identity"]["profiles"]
    if first["seat"] == 1:
        profiles = profiles[::-1]
    engine = header["engine"]
    prefix = engine.get("command") or [engine["java"], f"-Xmx{engine['xmx_mib']}m", "-Djava.awt.headless=true", "-jar", engine["pin"]["jar"], "sim"]
    command = [*prefix, "-d", *(deck.name for deck in decks), "-D", str(work), "-n", str(len(cells)),
               "-S", str(seeds), "-o", str(output), "-first", str(first["first_player_seat"]),
               "-a", *profiles, "-mc", "off", "-c", str(header["identity"]["game_clock_seconds"]), "-q"]
    completed = []
    process = None
    try:
        with (work / "stdout.log").open("wb") as stdout, (work / "stderr.log").open("wb") as stderr, output.open("rb") as stream:
            process = subprocess.Popen(command, cwd=Path(engine["forge_root"]) / "forge-gui", stdout=stdout, stderr=stderr)
            journal.append(dict(type="attempt", attempt=attempt, pid=process.pid,
                                cells=[cell["cell_id"] for cell in cells], command=command))
            deadline = time.monotonic() + (timeout or header["identity"]["game_clock_seconds"] + 60)
            pending = b""
            while True:
                data = stream.read()
                pending += data
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    if len(completed) >= len(cells):
                        raise ValueError("engine emitted extra game record")
                    raw = json.loads(line)
                    record = _record(raw, cells[len(completed)], len(completed) + 1)
                    record.update(type="game", attempt=attempt, identity=header["identity"])
                    journal.append(record)
                    completed.append(record)
                    deadline = time.monotonic() + (timeout or header["identity"]["game_clock_seconds"] + 60)
                if process.poll() is not None and not data:
                    if process.returncode == 0 and pending:
                        raise ValueError(f"engine emitted incomplete JSONL: {pending!r}")
                    break
                if time.monotonic() > deadline:
                    process.kill()
                    process.wait()
                    journal.append(dict(type="retry", attempt=attempt, reason="worker timeout"))
                    break
                time.sleep(0.02)
            if process.returncode:
                journal.append(dict(type="retry", attempt=attempt, reason=f"worker exit {process.returncode}"))
    except (ValueError, TypeError, KeyError) as error:
        journal.append(dict(type="discard", attempt=attempt, reason=str(error)))
        raise ValueError(f"malformed engine batch at {work}: {error}") from error
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        reveals = parse_runtime_reveals("\n".join(path.read_text(errors="replace") for path in (work / "stdout.log", work / "stderr.log") if path.exists()))
        journal.append(dict(type="reveal", attempt=attempt, stripped=list(reveals.stripped), cannot_play_well=list(reveals.cannot_play_well)))
    return completed


def _batch(journal: Journal, header: dict, cells: list[dict]) -> None:
    remaining = cells
    for retry in range(3):
        completed = _attempt(journal, header, remaining)
        done = {record["cell_id"] for record in completed}
        remaining = [cell for cell in remaining if cell["cell_id"] not in done]
        if not remaining:
            return
    raise RuntimeError(f"worker retries exhausted: {len(remaining)} unrun cells")


def resume_run(directory) -> dict:
    with Journal(directory) as journal:
        header, events = read_run(directory)
        _verify_snapshots(header)
        _verify_engine(header["engine"])
        if any(event["type"] == "discard" for event in events):
            raise ValueError("run contains malformed engine output; inspect discarded attempt")
        done = {record["cell_id"] for record in game_records(directory)}
        groups = {}
        for cell in header["plan"]:
            if cell["cell_id"] not in done:
                key = (cell["opponent"], cell["seat"], cell["first_player_seat"])
                groups.setdefault(key, []).append(cell)
        batches = [cells[start:start + 32] for cells in groups.values() for start in range(0, len(cells), 32)]
        workers = min(worker_count(header["worker_ceiling_mib"]), len(batches)) if batches else 0
        journal.append(dict(type="workers", count=workers))
        try:
            with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
                list(pool.map(lambda cells: _batch(journal, header, cells), batches))
        except BaseException as error:
            journal.append(dict(type="failed", reason=str(error)))
            raise
        journal.append(dict(type="complete", games=len(header["plan"])))
    rebuild_index(directory)
    return report_run(directory)


def report_run(directory) -> dict:
    header, events = read_run(directory)
    _verify_snapshots(header)
    records = game_records(directory)
    stripped = sorted({name for event in [*records, *events] for name in event.get("stripped", [])})
    warnings = sorted({name for event in [*records, *events] for name in event.get("cannot_play_well", [])})
    warnings += [disclosure["detail"] for result in header["validations"] for disclosure in result["disclosures"]]
    refusals = []
    if not events or events[-1]["type"] != "complete" or len(records) != len(header["plan"]):
        refusals.append("run incomplete")
    if any(event["type"] == "discard" for event in events):
        refusals.append("malformed engine batch")
    if stripped:
        refusals.append("engine stripped cards: " + ", ".join(stripped))
    if not header["validations"] or any(not result["passed"] for result in header["validations"]):
        refusals.append("deck validation failed or missing")
    return dict(run_id=header["run_id"], identity=header["identity"], games=len(records),
                wins=sum(row["won"] for row in records), draws=sum(row["draw"] for row in records),
                scorable=not refusals, refusals=refusals, warnings=warnings, records=records,
                validations=header["validations"],
                ceiling="Results measure Forge heuristic AI play; combo and control competence is limited.")


def reproduce_game(directory, cell_id) -> dict:
    header, _ = read_run(directory)
    _verify_snapshots(header)
    _verify_engine(header["engine"])
    original = next((row for row in game_records(directory) if row["cell_id"] == cell_id), None)
    if original is None:
        raise ValueError(f"unknown stored cell: {cell_id}")
    cell = next(cell for cell in header["plan"] if cell["cell_id"] == cell_id)
    replay_directory = Path(directory) / "replays" / uuid.uuid4().hex
    replay_header = {**header, "run_id": uuid.uuid4().hex, "plan": [cell]}
    with Journal(replay_directory, replay_header) as journal:
        records = _attempt(journal, header, [cell])
        if len(records) != 1:
            raise RuntimeError("replay did not complete")
        replay = records[0]
        if (original["winner_seat"], original["turns"]) != (replay["winner_seat"], replay["turns"]):
            raise ValueError("replay winner or turn count mismatch")
        journal.append(dict(type="complete", games=1))
    return dict(matched=True, cell_id=cell_id, original=original, replay=replay,
                directory=str(replay_directory))
