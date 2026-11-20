# Forge engine pin

- Upstream: https://github.com/Card-Forge/forge
- Upstream commit: `d16199280919834339c9c17ce477e8e95191f996`
- Upstream release: `2.0.17-SNAPSHOT` (shallow master checkout; no tag available locally).
- Card-data version: `74f929e900b23e7e443193bd8e87e0fdf68532ab`, the Git tree ID of `forge-gui/res/cardsfolder/` at the upstream commit.
- Engine checkout: `/home/aiden/Projects/forge`, branch `deckai-patches`.
- Compiler target: Java 17 (`maven.compiler.release` in upstream `pom.xml`).
- JDK: Eclipse Temurin `17.0.21.1+2`, `/home/aiden/.local/opt/jdk-17.0.21.1+2`.
- Maven: Apache Maven `3.9.9`, `/home/aiden/.local/opt/apache-maven-3.9.9`.

Build from the Forge checkout with the above JDK's `bin` and Maven's `bin` on PATH:

```sh
mvn -B clean install -DskipTests -pl forge-gui-desktop -am
```

See `docs/engine-setup.md` for commands and verification. `identity.json` records the final patched commit, ordered patch files, combined patch hash and built jar hash. Patch hash is SHA256 of the concatenated patch bytes, in the listed order. Paths to patch files are relative to this directory.
