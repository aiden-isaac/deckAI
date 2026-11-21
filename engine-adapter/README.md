# External-pilot engine adapter checkpoint

This is a compiled, scripted-verification checkpoint, **not a runnable external-pilot game adapter**. No complete game or Codex/Kiro pilot run is claimed.

## Build and verification

```sh
bash engine-adapter/build.sh
bash engine-adapter/test.sh
```

The build fetches only missing, hash-pinned Java overlay sources, verifies cached bytes, and compiles into `engine-adapter/build/classes`. It does not modify the installed Forge checkout or assembly. Java 17 and the existing Forge assembly are reused. `FORGE_ROOT`, `FORGE_JAR`, `JAVAC` (build), and `JDK_HOME` (tests) can override local locations; source and assembly identities must still match `forge-identity.json`.

`source-pin.json` pins spike-eval commit `98d147c75772fb595317381e02a8573f4e69267c`. Its declared Forge baseline is `34a8662b7966a6ee757411feae2ae8ff38cce436`, while this installed engine is `eca608f57a47aca561c8559a534bd70d864edc75`. The compatibility patches port its mana hooks and the newer rollback API's waiting-trigger mark. The upstream sources and Forge are GPL-3.0; the fetched upstream LICENSE is retained. No assets or whole Forge repository are downloaded.

## Decision contract

`ExternalDecisionBridge` emits the parent's v1 envelope, with a single compound `answer` action whose schema comes from spike-eval's `AnswerTool`. The `parameters` object is the actual tool argument object, such as `{"option":2}`, not an encoded string. The private observation is the caller-supplied seat observation; the public object is currently empty. Actual game observation privacy has **not** been verified by the bridge payload-routing test.

Malformed, stale, wrong-seat and invalid-choice responses remain pending. An exact repeat of the immediately preceding accepted response gets its acknowledgement again without returning another choice. Acceptance records include action parameters and external provenance. EOF throws; it never returns an action. This is an in-memory decision channel: it does not yet provide durable journaling, reconnect/reconstruction, engine-state revisions, or arbitrary-history deduplication. Acceptance means validated reply, not completed engine action.

## Real mana-payment fixture

`ExternalManaPaymentTest` creates real Forge Island and Mountain permanents and pays a generic mana cost through `ComputerUtilMana`. The overlay's `ExternalManaController` hook selects the source before activation. Separate runs assert:

- external option 1 taps Island and leaves Mountain untapped;
- external option 2 taps Mountain and leaves Island untapped;
- an open, unanswered channel blocks without tapping either land; subsequent EOF stops without selecting a source.

The fixture asserts the selected `SpellAbility` host object and external acknowledgement provenance, not just prompt text. `ExternalManaSelection` currently supports tap-only source costs; other costs stop with an error that cannot be swallowed by upstream `catch(Exception)` fallback ladders. The fixture controller inherits AI implementation for engine plumbing, but source selection is external and its only activation cost is the forced tap of that selected land. This does **not** establish ownership of general costs, colors, pool expenditure, or a whole game.

## Ownership gaps and next integration

`ControllerOwnershipAudit` writes the installed API inventory to `build/controller-ownership.tsv`: 149 public callbacks, 102 implemented by `PlayerControllerLLM`, 20 inherited from `PlayerControllerAi`, and 27 inherited from `PlayerController`. This inventory is not an ownership certificate. Protected methods and strategic choices inside callback implementations also need review.

Concrete blockers to a production launcher:

- upstream `payManaCost` can release requested held sources and retry automatically; the new hook has not yet replaced that controller path;
- floating mana is consumed greedily before source selection; Phyrexian/life splits, filters, source activation costs and color choices need explicit ownership or rejection;
- `auto()` includes first/default legal choices, not only forced mechanics; transport/schema failures must bypass all these paths;
- inherited `chooseCardsForCost`, `orderCosts`, `specifyManaCombo`, zone-change and card-face callbacks need explicit routing/rejection. `chooseEntitiesForEffect` loops over a virtual single-choice callback and needs its own reachability test;
- both-seat registration, faithful observation wiring, strict callback guards, launch/handshake, durable journal and reconstruction remain unfinished.

For the current Standard lists, prioritize multicolor lands and life/tapped ETB choices, mana creatures, search/shuffle, scry/surveil, targets, optional/kicker costs, trigger ordering, mulligans, attack/block and damage assignment. No legacy gauntlet or Donate work is part of this adapter.
