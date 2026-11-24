"""Command line entry points for starting and inspecting a measurement run."""

from __future__ import annotations

import argparse
import json

from harness import runner, store


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="deckai", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="validate and run a gauntlet")
    run.add_argument("directory")
    run.add_argument("--candidate", required=True)
    run.add_argument("--incumbent", required=True)
    run.add_argument("--manifest", required=True)
    run.add_argument("--forge-root", required=True)
    run.add_argument("--pin", required=True)
    run.add_argument("--java", required=True)
    run.add_argument("--worker-ceiling-mib", required=True, type=int)
    run.add_argument("--xmx-mib", type=int, default=2048)
    run.add_argument("--games", type=int, default=200)
    run.add_argument("--seed", type=int, default=20261120)
    run.add_argument("--candidate-profile", default="Default")
    run.add_argument("--opponent-profile", default="Default")
    run.add_argument("--clock", type=int, default=120)

    for name, help_text in (("resume", "resume an incomplete run"), ("report", "report a run"), ("rebuild", "rebuild the run's SQLite index")):
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument("directory")

    replay = commands.add_parser("replay", help="reproduce one recorded game")
    replay.add_argument("directory")
    replay.add_argument("cell_id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "run":
            result = runner.run_gauntlet(
                args.directory, args.candidate, args.incumbent, args.manifest,
                args.forge_root, args.pin, args.java, args.worker_ceiling_mib,
                xmx_mib=args.xmx_mib, games=args.games, seed=args.seed,
                profiles=(args.candidate_profile, args.opponent_profile), clock=args.clock,
            )
        elif args.command == "resume":
            result = runner.resume_run(args.directory)
        elif args.command == "report":
            result = runner.report_run(args.directory)
        elif args.command == "replay":
            result = runner.reproduce_game(args.directory, args.cell_id)
        else:
            result = {"indexed_games": store.rebuild_index(args.directory)}
    except (OSError, ValueError, RuntimeError) as error:
        _print({"error": str(error)})
        return 1
    _print(result)
    return 0


def _print(value: dict) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    raise SystemExit(main())
