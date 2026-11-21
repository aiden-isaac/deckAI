#!/usr/bin/env bash
set -euo pipefail
adapter_root=$(cd -- "$(dirname -- "$0")" && pwd)
forge_root=${FORGE_ROOT:-/home/aiden/Projects/forge}
forge_jar=${FORGE_JAR:-$forge_root/forge-gui-desktop/target/forge-gui-desktop-2.0.17-SNAPSHOT-jar-with-dependencies.jar}
javac_path=${JAVAC:-/home/aiden/.local/opt/jdk-17.0.21.1+2/bin/javac}
python "$adapter_root/fetch-source.py"
python "$adapter_root/prepare-overlay.py" "$forge_root"
mkdir -p "$adapter_root/build/classes"
find "$adapter_root/build/overlay" "$adapter_root/src" -name '*.java' -print > "$adapter_root/build/sources.txt"
"$javac_path" --release 17 -cp "$forge_jar" -d "$adapter_root/build/classes" @"$adapter_root/build/sources.txt"
