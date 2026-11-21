#!/usr/bin/env python3
"""Apply local compatibility patches without touching the installed engine."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parent
forge = Path(sys.argv[1])
identity = json.loads((root / 'forge-identity.json').read_text())
head = subprocess.check_output(['git', '-C', str(forge), 'rev-parse', 'HEAD'], text=True).strip()
if head != identity['patched_commit']:
    raise SystemExit('Forge source identity changed; compatibility must be reviewed')
jar = Path(os.environ.get('FORGE_JAR', forge / identity['jar_relative_path']))
with jar.open('rb') as stream:
    if hashlib.file_digest(stream, 'sha256').hexdigest() != identity['jar_sha256']:
        raise SystemExit('Forge jar hash changed; compatibility must be reviewed')
for name, expected in identity['sources'].items():
    if hashlib.sha256((forge / name).read_bytes()).hexdigest() != expected:
        raise SystemExit(f'Forge source changed: {name}')
overlay = root / 'build/overlay'
if overlay.exists():
    shutil.rmtree(overlay)
shutil.copytree(root / 'upstream/forge-overlay', overlay / 'forge-overlay')
p = Path('forge-ai/src/main/java/forge/ai/ComputerUtilMana.java')
(overlay / p).parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(forge / p, overlay / p)
for patch in sorted((root / 'patches').glob('*.patch')):
    subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(patch)], cwd=overlay, check=True)
