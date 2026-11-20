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
mvn -U -B clean install -DskipTests -pl forge-gui-desktop -am
```

For a rebuild with the populated dependency cache, replace `-U` with `-o` for offline mode. The repository's `.mvn/maven.config` supplies its existing Maven settings; do not replace it. The runnable assembly is:

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

## Measurement CLI and record contract

From `forge-gui`, use one homogeneous deck order and starting seat per batch:

```sh
engine_run_dir=$(mktemp -d /tmp/deckai-engine-example.XXXXXX)
seq 101 110 > "$engine_run_dir/seeds.txt"
/home/aiden/.local/opt/jdk-17.0.21.1+2/bin/java -Xmx2g -Djava.awt.headless=true \
  -jar ../forge-gui-desktop/target/forge-gui-desktop-2.0.17-SNAPSHOT-jar-with-dependencies.jar \
  sim -D / \
  -d home/aiden/Projects/deckAI/decks/acceptance/healthy.dck \
     home/aiden/Projects/deckAI/gauntlets/acceptance/green-elves.dck \
  -n 10 -S "$engine_run_dir/seeds.txt" -first 0 \
  -a Default Default -mc off -c 120 -q -o "$engine_run_dir/games.jsonl"
```

`-D /` makes the two deck filenames relative to the filesystem root. `-first 0|1` fixes the player taking the first turn independently of deck registration order. `-a` is the existing per-seat AI-profile flag. `-f` remains the existing game-format flag. This scope adds no sideboarding or AI behavior changes; the runner initially uses stock profiles, `-mc off`, and BO1s. The pinned upstream already implements `-mc`.

`-S FILE` reads signed Java 64-bit decimal integers, one per line, and applies each seed **before game creation**. Blank/malformed/out-of-range lines fail. With `-n N`, exactly N seeds are required. `-S` cannot combine with `-s` or tournament mode. A BO1 uses a new Match, so its prior batch position cannot affect the initial player or match history. Best-of-match mode consumes seeds in order and refuses if the file is exhausted; isolated replay guarantees in this verification cover BO1 only.

`-o FILE` appends one UTF-8 JSON line after each completed game and closes the file before playing the next. Existing files are appended, never truncated. A write failure or engine exception aborts instead of fabricating a result. Without `-S`, measured games receive individually generated, recorded seeds; `-s` initializes that generator. Without `-o` and `-S`, the original run-wide `-s` behavior is preserved. Structured output and forced starting seats are restricted to two-player non-tournament runs.

| Field | Meaning |
| --- | --- |
| `winner_seat` | `0` or `1` in deck order; JSON `null` for a draw |
| `winner` | Engine player name, or `Draw` |
| `loss_reason` | Forge loss enum, `Draw`, or `Clock` |
| `turns` | Forge global turn counter, not rounds |
| `elapsed_ms` | Existing game stopwatch, including game construction and timeout shutdown |
| `seed` | Actual per-game signed 64-bit seed |
| `seats` | Two deck names in registration order |
| `first_player_seat` | Actual starting player's registration seat |
| `mulligans` | Actual `PlayerStatistics.getMulliganCount()` values in seat order |
| `damage_by_turn_5` | Actual post-prevention damage to opponents by each source's controller through global turn 10 |
| `draw`, `clock_terminated` | Boolean outcome and timeout flags; a clock result has no winning seat |
| `match_game_index` | One-based position within the match; always 1 for BO1 |
| `game_index` | One-based position within this CLI batch, used for diagnostics only |
| `sideboarding` | Actual `GameRules.getSideboardForAI()`; false in this scope |
| `stripped` | Sorted unique names removed by actual deck validity or no-ante filtering |
| `cannot_play_well` | Sorted unique names returned by the actual AI complaint method, recalculated per game |

The damage metric includes combat and noncombat damage, including infect, and excludes life loss and self-damage. The cutoff counts the first ten global turns: **extra turns consume that budget**, so it does not promise five personal turns per seat in extra-turn decks. This is sufficient for the acceptance aggro fixtures and is explicit for later deck measurements.

Clock termination calls `intentionalDraw` on both players before `setGameOver(Draw)`: upstream's latter call alone incorrectly credits surviving players with wins. The executor is canceled and given five seconds to stop. A worker that still runs after that grace period fails without a record; the runner must kill/requeue it. Completed clock draws continue the batch. Timing is not deterministic and is excluded from seed comparisons.

The runner is responsible for attaching engine identity and validation to the experiment record. It verifies `identity.json` against the engine HEAD, clean tracked tree, ordered patch bytes and jar bytes. Unknown card names can be dropped before Forge constructs a Deck; the harness must combine the structured arrays with its named stderr-reveal parsing. These engine records do not independently establish legality or scoreability.

## Verification and patch application

Run the assert-based offline integration check with a **new** evidence directory:

```sh
cd /home/aiden/Projects/deckAI
python docs/engine-verification/verify_engine.py --evidence /tmp/deckai-engine-check
```

It checks complete records, ten-game same-seed agreement, different-seed divergence, isolated replay, both starting seats, real mulligan/damage variation, runtime AI complaints, and clock-draw invariants with continued batch execution. `docs/engine-verification/final-verification/` contains the final run's command arrays, seeds, outputs and summary. Upstream sample decks carry an AI complaint and are used only for engine verification.

The exported patch series was applied to a fresh detached worktree at the upstream pin, built offline, and its first five seeded records compared with the primary build. Reproduce the application without network access:

```sh
git -C /home/aiden/Projects/forge worktree add --detach /tmp/deckai-forge-check \
  d16199280919834339c9c17ce477e8e95191f996
git -C /tmp/deckai-forge-check am /home/aiden/Projects/deckAI/forge-patches/*.patch
cd /tmp/deckai-forge-check
export JAVA_HOME=/home/aiden/.local/opt/jdk-17.0.21.1+2
export PATH="$JAVA_HOME/bin:/home/aiden/.local/opt/apache-maven-3.9.9/bin:$PATH"
mvn -o -B -pl forge-gui-desktop -am install -DskipTests
```

`git am` creates new commit IDs when committer timestamps differ; source trees and game behavior are compared, not jar ZIP timestamps or rewritten commit IDs. The original branch's exact commit and artifact hash remain in `identity.json`.

Preliminary acceptance probes used `-Xmx2g`: healthy-vs-green, 10 games, median game time 2.570 s, process wall time 32.301 s, peak RSS 1,566,852 KiB measured by Python `getrusage`; healthy-vs-white, five games, 12.42 s process wall time and peak RSS 1,458,380 KiB measured by rootless GNU Time 1.10 `-v` at `/home/aiden/.local/opt/gnu-time/usr/bin/time`. Both had zero stripped/unplayable arrays. The green batch showed real mulligans and damage variation. These small probes are preliminary sizing evidence; the parent owns full 200-game calibration and the acceptance gate.
