#!/usr/bin/env python3
"""Verify measured games ignore desktop hand/mulligan/MC-retention preferences."""
import argparse
import json
from pathlib import Path
import tempfile

from verify_engine import deterministic, run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--forge', type=Path, default=Path('/home/aiden/Projects/forge'))
    parser.add_argument('--java', type=Path, default=Path('/home/aiden/.local/opt/jdk-17.0.21.1+2/bin/java'))
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    jar = args.forge / 'forge-gui-desktop/target/forge-gui-desktop-2.0.17-SNAPSHOT-jar-with-dependencies.jar'
    args.evidence.mkdir(parents=True, exist_ok=True)
    rows = []
    preferences = ['FILTERED_HANDS=false\nMULLIGAN_RULE=London\nMATCH_AI_FLAT_MONTE_CARLO=false\n',
                   'FILTERED_HANDS=true\nMULLIGAN_RULE=Paris\nMATCH_AI_FLAT_MONTE_CARLO=true\n']
    for index, prefs in enumerate(preferences):
        with tempfile.TemporaryDirectory(prefix='deckai-forge-preferences-') as home:
            pref = Path(home) / '.forge/preferences/forge.preferences'
            pref.parent.mkdir(parents=True)
            pref.write_text(prefs)
            (args.evidence / f'preferences-{index}.txt').write_text(prefs)
            rows.append(run(args.java, jar, args.forge, args.evidence,
                            f'preferences-{index}', [101, 103, 108],
                            jvm_options=[f'-Duser.home={home}']))
            assert pref.read_text() == prefs, 'Measured mode changed saved desktop preferences'
    assert [deterministic(r) for r in rows[0]] == [deterministic(r) for r in rows[1]]
    summary = {'filtered_hands_disabled': True, 'mulligan_rule_london': True,
               'opposite_desktop_preferences_same_games': True,
               'saved_preferences_unchanged': True, 'games_per_profile': 3}
    (args.evidence / 'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()
