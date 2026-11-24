from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

import pytest

from harness import runner
from harness.stats import ResultIdentity
from harness.store import Journal, game_records, rebuild_index


def test_plan_balances_both_dimensions_and_memory():
    plan = runner.plan_games("candidate", {"a": 1, "b": 1}, 40, 100)
    for opponent in ("a", "b"):
        cells = [cell for cell in plan if cell["opponent"] == opponent]
        assert len(cells) == 20
        assert sum(cell["on_play"] for cell in cells) == 10
        assert sum(cell["seat"] for cell in cells) == 10
        assert len({(cell["seat"], cell["on_play"]) for cell in cells}) == 4
    assert runner.worker_count(2000, 8000) == 4
    assert runner.worker_count(4000, 8000) == 2
    with pytest.raises(ValueError):
        runner.worker_count(9000, 8000)


@pytest.fixture
def fake_run(tmp_path, monkeypatch):
    script = tmp_path / "engine.py"
    script.write_text('''import json,sys,os,time
from pathlib import Path
a=sys.argv
out=Path(a[a.index('-o')+1]); seeds=Path(a[a.index('-S')+1]).read_text().splitlines()
marker=Path(__file__).with_suffix('.marker')
mode=Path(__file__).with_suffix('.mode').read_text()
first=int(a[a.index('-first')+1])
for i,seed in enumerate(seeds):
 r=dict(winner_seat=int(seed)%2,turns=8,elapsed_ms=10,seed=int(seed),first_player_seat=first,mulligans=[0,1],damage_by_turn_5=[4,8],draw=False,clock_terminated=False,match_game_index=1,game_index=i+1,loss_reason='LifeReachedZero',seats=['a','b'],sideboarding=False,filtered_hands=False,mulligan_rule='London',stripped=[],cannot_play_well=[])
 if mode=='stripped': r['stripped']=['Missing Card']
 if mode=='bad' and i==1: r.pop('stripped')
 with out.open('a') as f: f.write(json.dumps(r)+'\\n'); f.flush()
 if mode in ('crash','hang') and not marker.exists():
  marker.touch()
  with out.open('a') as f: f.write('{partial')
  if mode=='hang': time.sleep(60)
  os._exit(9)
''')
    script.with_suffix(".mode").write_text("crash")
    (tmp_path / "forge-gui").mkdir()
    text = "[metadata]\nName=test\n[Main]\n60 Mountain\n"
    digest = hashlib.sha256(text.encode()).hexdigest()
    identity = asdict(ResultIdentity("abcdef", "abc123", digest, digest, "gauntlet-v1", '["Default", "Default"]', "off", 120))
    identity.update(opponent_deck_hashes={"a": digest}, profiles=["Default", "Default"], card_data_version="card-v1")
    header = dict(type="run", run_id="test-run", identity=identity, decks={"candidate": text, "incumbent": text}, opponents={"a": text},
                  engine=dict(forge_root=str(tmp_path), command=[sys.executable, str(script)]),
                  validations=[dict(passed=True, disclosures=[])], worker_ceiling_mib=2000,
                  plan=runner.plan_games(digest, {"a": 1}, 8, 100))
    directory = tmp_path / "run"
    with Journal(directory, header):
        pass
    monkeypatch.setattr(runner, "_verify_engine", lambda engine: None)
    monkeypatch.setattr(runner, "worker_count", lambda ceiling: 1)
    return directory, header, script


def test_crash_recovers_completed_games_and_replays_and_rebuilds(fake_run):
    directory, header, script = fake_run
    report = runner.resume_run(directory)
    assert report["scorable"] and report["games"] == 8
    assert [row["seed"] for row in report["records"]] == list(range(100, 108))
    assert len({row["cell_id"] for row in report["records"]}) == 8
    assert runner.reproduce_game(directory, report["records"][0]["cell_id"])["matched"]
    def aggregate():
        with sqlite3.connect(directory / "index.sqlite3") as db:
            return db.execute("SELECT count(*),sum(won),sum(turns) FROM games").fetchone()
    before = aggregate()
    (directory / "index.sqlite3").unlink()
    assert rebuild_index(directory) == 8
    assert aggregate() == before
    with (directory / "run.jsonl").open("ab") as stream:
        stream.write(b'{torn')
    assert runner.resume_run(directory)["games"] == 8


def test_timeout_requeues_only_unfinished(fake_run, monkeypatch):
    directory, header, script = fake_run
    script.with_suffix(".mode").write_text("hang")
    attempt = runner._attempt
    monkeypatch.setattr(runner, "_attempt", lambda journal, header, cells: attempt(journal, header, cells, timeout=.15))
    assert runner.resume_run(directory)["games"] == 8


def test_malformed_batch_discarded(fake_run):
    directory, header, script = fake_run
    script.with_suffix(".mode").write_text("bad")
    with pytest.raises(ValueError, match="stripped"):
        runner.resume_run(directory)
    assert not runner.report_run(directory)["scorable"]
    assert not game_records(directory)


def test_stripped_cards_and_snapshot_drift_refused(fake_run):
    directory, header, script = fake_run
    script.with_suffix(".mode").write_text("stripped")
    report = runner.resume_run(directory)
    assert not report["scorable"]
    assert "Missing Card" in str(report["refusals"])
    path = directory / "run.jsonl"
    lines = path.read_text().splitlines()
    header["decks"]["candidate"] += "1 Island\n"
    lines[0] = json.dumps(header)
    path.write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError, match="snapshot drift"):
        runner.report_run(directory)


def test_clock_win_inconsistent(fake_run):
    directory, header, script = fake_run
    raw = dict(turns=2, elapsed_ms=1, seed=100, first_player_seat=0, match_game_index=1,game_index=1,
               draw=False,clock_terminated=True,sideboarding=False,filtered_hands=False,mulligan_rule="London",
               mulligans=[0,0],damage_by_turn_5=[0,0],stripped=[],cannot_play_well=[],seats=["a","b"],winner_seat=0,loss_reason="Clock")
    with pytest.raises(ValueError, match="inconsistent"):
        runner._record(raw, header["plan"][0], 1)
