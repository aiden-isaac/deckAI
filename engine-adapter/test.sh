#!/usr/bin/env bash
set -euo pipefail
adapter_root=$(cd -- "$(dirname -- "$0")" && pwd)
forge_root=${FORGE_ROOT:-/home/aiden/Projects/forge}
forge_jar=${FORGE_JAR:-$forge_root/forge-gui-desktop/target/forge-gui-desktop-2.0.17-SNAPSHOT-jar-with-dependencies.jar}
jdk=${JDK_HOME:-/home/aiden/.local/opt/jdk-17.0.21.1+2}
classpath="$adapter_root/build/classes:$forge_jar"
bash "$adapter_root/build.sh"
"$jdk/bin/javac" --release 17 -cp "$classpath" -d "$adapter_root/build/classes" "$adapter_root"/tests/forge/spike/*.java
export ANSWER_SCHEMA=per-decision
"$jdk/bin/java" -cp "$classpath" forge.spike.ExternalDecisionBridgeTest
"$jdk/bin/java" -cp "$classpath" forge.spike.ControllerOwnershipAudit > "$adapter_root/build/controller-ownership.tsv"
cd "$forge_root/forge-gui"
"$jdk/bin/java" -Xmx1536m -cp "$classpath" forge.spike.ExternalManaPaymentTest
