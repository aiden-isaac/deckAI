# Persistent Codex pilots

`harness.pilots.CodexPilot` maintains one app-server process and conversation per game seat. Create two instances with separate private directories. Existing Codex ChatGPT login is copied into each private runtime; no API key is required. Omit `model` to retain the provider default, or pass the operator's explicit gameplay model. Worker model assignments do not select gameplay models.

**Production is currently disabled before authentication is copied.** The actual installed tool inventory still includes `functions.exec` despite shell feature disables. A credentialed process and its tools sharing `/pilot/.codex` is an unverified boundary. The synthetic transport smoke below does not establish credential isolation. The constructor's explicit `command` injection exists for tests/probes; production callers must not use it to bypass the gate.

```python
from harness.pilots import CodexPilot, PilotPaused

with CodexPilot("data/game/seat0", "game-id", 0,
                playbook=profile_text, playbook_version=profile_hash) as pilot:
    answer = pilot.decide(engine_decision)
```

The referee supplies the frozen v1 envelope and engine-owned parameter schema. Each turn resends `outputSchema`. The adapter checks game, seat, profile, revision and action identity through `harness.pilot_protocol`; the engine separately checks actual legality before applying once. No default or first-legal response is selected. `PilotPaused` means preserve the pending decision and stop the game clock, without crediting a winner.

The runtime uses rootless `bwrap`, private `/pilot/.codex` and `/pilot/work` mounts, private `/tmp`, and a separate PID namespace. Host-owned `pilot.json`, pending/cache and lock files are outside the mounted directories. Referee and sibling files are excluded. Shell, unified execution, apps, plugins and delegation feature flags are disabled; unexpected server tool requests are refused. Those flags do not remove all model-facing tools. Runtime authentication and transcripts are private sensitive data. This host needs `/etc/ca-certificates` as well as `/etc/ssl`: the latter's certificate bundle is a symlink into the former. Without it, inference reports routing/network errors despite successful local thread creation.

The Codex 0.166.0 rollout's `response_item.tools` contains actual definitions: `functions.exec`, `functions.wait`, `functions.request_user_input`, `functions.request_user_input_async`, and `clock.sleep`. Disabling native code-mode/image/clock feature flags in a synthetic probe still exposed `functions.exec` and input helpers, plus `send_message_to_user_async`. This is stronger evidence than model self-report. A tool-only sanitized snapshot is recorded at `/tmp/deckai-pilot-tools-inventory.json`; raw rollouts remain private. App-server item notifications reveal calls, but observing `item/started` cannot guarantee denial before internal execution. Production requires a native read/network restriction proven through the actual execution path, or a separated execution host that denies dispatch.

Verified on the installed Codex 0.166.0: two authenticated structured decisions on one process/thread; reconnect recovered the second answer from provider history without another inference turn. The focused tests include an actual rootless-bwrap probe denying sibling and referee reads. Full advertised-tool inventory and two-seat gameplay attribution remain integration acceptance work; these smoke results establish transport and filesystem behavior, not gameplay quality.

`pilot.json` preserves thread identity, a pending decision and validated answers. A repeated identical decision returns its cached answer. A changed decision under an old ID is refused. After an uncertain transport failure, reconnect the same pilot and call `recover_pending()`: it searches persisted completed turns and returns only a matching validated answer, without resending the prompt. If none exists it stays paused. The coordinator must still reconcile the recovered answer with the referee's accepted-action journal before applying once; absent or failed provider turns require explicit operator recovery.

Profiles remain frozen in a match. The parent learning layer owns versioned playbooks and postgame evidence; this adapter consumes the selected version. This is context/external-memory learning, not model-weight training.

Kiro ACP is a follow-up provider, not implemented here. It offers persistent `session/new`, `session/load` and `session/prompt`; V3 requires capability negotiation and finishes turns from the prompt response. See [Kiro ACP migration](https://kiro.dev/docs/cli/v3/acp-migration/). Codex lifecycle and structured-output fields follow the [official app-server protocol](https://learn.chatgpt.com/docs/app-server).
