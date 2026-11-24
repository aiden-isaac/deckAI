#!/usr/bin/env python3
"""Offline integration checks for the pinned engine; writes inspectable evidence."""
import argparse
import json
from pathlib import Path
import subprocess

REQUIRED = {
    'winner_seat', 'winner', 'loss_reason', 'turns', 'elapsed_ms', 'seed',
    'seats', 'first_player_seat', 'mulligans', 'damage_by_turn_5', 'draw',
    'clock_terminated', 'match_game_index', 'game_index', 'sideboarding',
    'stripped', 'cannot_play_well', 'filtered_hands', 'mulligan_rule',
}


def run(java, jar, forge, evidence, label, seeds, first=0, decks=None, clock=120, jvm_options=()):
    seedfile = evidence / f'{label}.seeds'
    seedfile.write_text(''.join(f'{seed}\n' for seed in seeds))
    output = evidence / f'{label}.jsonl'
    assert not output.exists(), f'Refusing to append to old evidence: {output}'
    deckdir = forge / 'forge-gui/res/quest/world/zendikar/duels'
    deck_args = ['-D', str(deckdir), '-d', 'Tuktuk 3.dck', 'Slayer 3.dck'] if decks is None else ['-D', '/', '-d', *[str(p).lstrip('/') for p in decks]]
    command = [str(java), *jvm_options, '-Xmx2g', '-Djava.awt.headless=true', '-jar', str(jar),
               'sim', *deck_args, '-n', str(len(seeds)), '-S', str(seedfile),
               '-first', str(first), '-a', 'Default', 'Default', '-mc', 'off',
               '-c', str(clock), '-q', '-o', str(output)]
    (evidence / f'{label}.command.json').write_text(json.dumps(command, indent=2)+'\n')
    with (evidence / f'{label}.log').open('w') as log:
        subprocess.run(command, cwd=forge / 'forge-gui', stdout=log,
                       stderr=subprocess.STDOUT, timeout=180*len(seeds)+60, check=True)
    rows = [json.loads(line) for line in output.read_text().splitlines()]
    assert len(rows) == len(seeds)
    for index, (row, seed) in enumerate(zip(rows, seeds), 1):
        assert REQUIRED <= row.keys(), row
        assert row['seed'] == seed and row['game_index'] == index
        assert row['match_game_index'] == 1 and row['first_player_seat'] == first
        assert row['winner_seat'] in (None, 0, 1)
        assert row['draw'] == (row['winner_seat'] is None)
        assert row['loss_reason'] and row['elapsed_ms'] >= 0 and row['turns'] >= 0
        assert row['filtered_hands'] is False and row['mulligan_rule'] == 'London'
        assert len(row['mulligans']) == len(row['damage_by_turn_5']) == len(row['seats']) == 2
        assert all(isinstance(n, int) and n >= 0 for n in row['mulligans'] + row['damage_by_turn_5'])
    return rows


def verify_cli_edges(java, jar, forge, evidence):
    run(java, jar, forge, evidence, 'append', [109])
    command = json.loads((evidence / 'append.command.json').read_text())
    with (evidence / 'append-second.log').open('w') as log:
        subprocess.run(command, cwd=forge / 'forge-gui', stdout=log,
                       stderr=subprocess.STDOUT, timeout=180, check=True)
    appended = [json.loads(line) for line in (evidence / 'append.jsonl').read_text().splitlines()]
    assert len(appended) == 2 and deterministic(appended[0]) == deterministic(appended[1])
    command[command.index('-n') + 1] = '2'
    refused = evidence / 'wrong-seed-count.jsonl'
    command[command.index('-o') + 1] = str(refused)
    with (evidence / 'wrong-seed-count.log').open('w') as log:
        subprocess.run(command, cwd=forge / 'forge-gui', stdout=log,
                                stderr=subprocess.STDOUT, timeout=180)
    assert not refused.exists(), 'Invalid seed count wrote partial records'
    assert 'Seed file must contain exactly' in (evidence / 'wrong-seed-count.log').read_text()
    return {'append_preserves_existing_records': True, 'wrong_seed_count_refused_before_play': True}


def deterministic(row):
    return {key: value for key, value in row.items() if key not in ('elapsed_ms', 'game_index')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--forge', type=Path, default=Path('/home/aiden/Projects/forge'))
    parser.add_argument('--java', type=Path, default=Path('/home/aiden/.local/opt/jdk-17.0.21.1+2/bin/java'))
    parser.add_argument('--jar', type=Path)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    jar = args.jar or args.forge / 'forge-gui-desktop/target/forge-gui-desktop-2.0.17-SNAPSHOT-jar-with-dependencies.jar'
    args.evidence.mkdir(parents=True, exist_ok=True)
    seeds = list(range(101, 111))
    a = run(args.java, jar, args.forge, args.evidence, 'same-a', seeds)
    b = run(args.java, jar, args.forge, args.evidence, 'same-b', seeds)
    assert [deterministic(r) for r in a] == [deterministic(r) for r in b], 'Same-seed replay diverged'
    c = run(args.java, jar, args.forge, args.evidence, 'different', list(range(201, 211)))
    assert [(r['winner_seat'], r['turns']) for r in a] != [(r['winner_seat'], r['turns']) for r in c], 'Different seeds had no observable effect'
    replay = run(args.java, jar, args.forge, args.evidence, 'single-replay', [seeds[7]])
    assert deterministic(replay[0]) == deterministic(a[7]), 'Batch-position dependence'
    other_seat = run(args.java, jar, args.forge, args.evidence, 'first-seat-one', seeds[:5], first=1)
    assert all(r['first_player_seat'] == 1 for r in other_seat)
    assert any(sum(r['damage_by_turn_5']) for r in a)
    assert any(sum(r['mulligans']) for r in a + c + other_seat)
    assert all('Vampire Lacerator' in r['cannot_play_well'] for r in a)
    clock_rows = run(args.java, jar, args.forge, args.evidence, 'clock-zero', [55, 56], clock=0)
    assert all(r['clock_terminated'] and r['draw'] and r['winner_seat'] is None
               and r['loss_reason'] == 'Clock' for r in clock_rows), clock_rows
    clock_one = run(args.java, jar, args.forge, args.evidence, 'clock-one', [55, 56], clock=1)
    assert all(not r['clock_terminated'] or (r['draw'] and r['winner_seat'] is None)
               for r in clock_one), clock_one
    summary = {'clock_draw_invariant_verified': True, 'clock_batch_continues': True,
               'same_seed_games': len(a), 'same_seed_identical': True,
               'different_seed_outcomes_differ': True, 'isolated_replay_matches': True,
               'fixed_starting_seats_verified': [0, 1],
               'damage_nonzero': True, 'mulligans_nonzero': True,
               'runtime_ai_complaints_captured': True}
    summary.update(verify_cli_edges(args.java, jar, args.forge, args.evidence))
    (args.evidence / 'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
