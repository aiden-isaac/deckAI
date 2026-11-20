# Building and running the pinned Forge engine

Forge lives at `/home/aiden/Projects/forge`; the upstream pin and exact local artifact identity live in `forge-patches/PIN.md` and `forge-patches/identity.json`. The upstream snapshot is `2.0.17-SNAPSHOT`, compiled for Java 17. There is no locally available upstream tag in the original shallow clone.

The interrupted session installed Maven 3.9.9 and Eclipse Temurin 17.0.21.1+2 under `~/.local/opt`. It successfully built on Java 27 first while downloading dependencies (Maven reported **21m27s**; `forge-probe-build-jdk27.log`). Java 27 was not rejected by the build. We use Java 17 to match the declared compiler target and keep the system Java unchanged. The subsequent clean Java 17 build took **55.954 seconds wall time**, from 2026-11-20 21:43:21 to 21:44:17 +08:00 (`forge-first-build.log`). That time excludes dependency downloads already completed by the probe and the toolchain downloads.

Run from a fresh shell:

```sh
export JAVA_HOME=/home/aiden/.local/opt/jdk-17.0.21.1+2
export PATH="$JAVA_HOME/bin:/home/aiden/.local/opt/apache-maven-3.9.9/bin:$PATH"
mvn -version
java -version
cd /home/aiden/Projects/forge
mvn -B clean install -DskipTests -pl forge-gui-desktop -am
```

For a rebuild with the populated dependency cache, add `-o` for offline mode. The repository's `.mvn/maven.config` supplies its existing Maven settings; do not replace it. The runnable assembly is:

`/home/aiden/Projects/forge/forge-gui-desktop/target/forge-gui-desktop-2.0.17-SNAPSHOT-jar-with-dependencies.jar`

Forge needs the working directory `forge-gui` to find its `res` directory. A fresh shell can run this smoke test without changing any system configuration:

```sh
cd /home/aiden/Projects/forge/forge-gui
/home/aiden/.local/opt/jdk-17.0.21.1+2/bin/java -Xmx2g -Djava.awt.headless=true \
  -jar ../forge-gui-desktop/target/forge-gui-desktop-2.0.17-SNAPSHOT-jar-with-dependencies.jar \
  sim -D "$PWD/res/quest/world/zendikar/duels" \
  -d 'Tuktuk 3.dck' 'Slayer 3.dck' -n 1 -q
```

Those two upstream sample decks are `/home/aiden/Projects/forge/forge-gui/res/quest/world/zendikar/duels/Tuktuk 3.dck` and `Slayer 3.dck` in the same directory. The unpatched smoke test printed `Game Result: Game 1 ended in 2073 ms. Ai(2)-Slayer 3 has won!`; its complete output is `docs/engine-verification/verify-smoke-run.txt`. It is a headless engine smoke test, not a Standard legality test.
