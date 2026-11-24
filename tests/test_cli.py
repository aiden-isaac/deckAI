import json

from harness import cli


def test_run_passes_declared_inputs_to_runner(monkeypatch, capsys):
    seen = {}

    def run(*args, **kwargs):
        seen["args"] = args
        seen["kwargs"] = kwargs
        return {"games": 200, "wins": 100, "draws": 2, "scorable": True}

    monkeypatch.setattr(cli.runner, "run_gauntlet", run)
    status = cli.main([
        "run", "runs/new", "--candidate", "candidate.dck", "--incumbent", "base.dck",
        "--manifest", "field.json", "--forge-root", "/forge", "--pin", "pin.json",
        "--java", "/jdk/bin/java", "--worker-ceiling-mib", "4096",
        "--candidate-profile", "Default", "--opponent-profile", "Experimental",
    ])
    assert status == 0
    assert seen["args"] == ("runs/new", "candidate.dck", "base.dck", "field.json", "/forge", "pin.json", "/jdk/bin/java", 4096)
    assert seen["kwargs"] == {
        "xmx_mib": 2048, "games": 200, "seed": 20261120,
        "profiles": ("Default", "Experimental"), "clock": 120,
    }
    assert json.loads(capsys.readouterr().out)["games"] == 200


def test_resume_report_and_replay_dispatch(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(cli.runner, "resume_run", lambda path: calls.append(("resume", path)) or {"scorable": False})
    monkeypatch.setattr(cli.runner, "report_run", lambda path: calls.append(("report", path)) or {"games": 2})
    monkeypatch.setattr(cli.runner, "reproduce_game", lambda path, cell: calls.append(("replay", path, cell)) or {"matched": True})
    for command, expected in [
        (["resume", "runs/a"], {"scorable": False}),
        (["report", "runs/a"], {"games": 2}),
        (["replay", "runs/a", "cell-1"], {"matched": True}),
    ]:
        assert cli.main(command) == 0
        assert json.loads(capsys.readouterr().out) == expected
    assert calls == [("resume", "runs/a"), ("report", "runs/a"), ("replay", "runs/a", "cell-1")]


def test_rebuild_dispatch_and_runner_refusal_is_nonzero(monkeypatch, capsys):
    monkeypatch.setattr(cli.store, "rebuild_index", lambda path: 7)
    assert cli.main(["rebuild", "runs/a"]) == 0
    assert json.loads(capsys.readouterr().out) == {"indexed_games": 7}

    monkeypatch.setattr(cli.runner, "report_run", lambda path: (_ for _ in ()).throw(ValueError("engine patch_hash drift")))
    assert cli.main(["report", "runs/a"]) == 1
    assert json.loads(capsys.readouterr().out) == {"error": "engine patch_hash drift"}
