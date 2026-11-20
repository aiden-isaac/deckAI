# Can a CLI coding agent pilot thousands of MTG games? — findings

Investigation date: 2026-11-20. Read-only; no code written, no agent sessions started.
Repo state at time of writing: `/home/aiden/Projects/deckAI` is empty apart from `.git`, `.kiro/skills`, `openspec/`, `.agents/`.

Scope as finally stated by the owner: subscriptions only (no per-token API billing); target format **Standard**; environment **Forge-vs-Forge** locally; objective is a **deck-brewing tool** that plays a candidate list against a fixed meta gauntlet across thousands of games and emits a tested 60+15; the per-decision decider is to be a **local model on the dev laptop**; unattended operation on **jarlaxle**.

---

## Summary

- **The decisive constraint is quota, not latency, and it fails by two orders of magnitude.** ChatGPT Plus is documented at 15–160 GPT-6.1 Sol messages per 5-hour window ([Codex pricing](https://learn.chatgpt.com/docs/pricing)). One decision = one message. At 300 decisions per Standard game and the *optimistic* 160/5h, that is 2.56 games/day, so 1,000 games takes **391 days**. No amount of engineering fixes a 100×+ shortfall. A CLI coding agent cannot be the in-game pilot.
- **Latency fails independently, and I measured it on this machine rather than guessing.** 42 real Codex turns from a local session rollout: median **9.0 s**, p90 13.4 s, mean 14.5 s per turn, with the server-side prompt cache already warm. A cold `codex exec` is worse: the first turn of that session cost **22,150 uncached input tokens** before the model said anything. At 30 s/decision × 300 decisions × 1,000 games = **104 days** of continuous wall-clock.
- **Every claim in the owner's earlier plan checks out, which is unusual.** PydanticAI, LangGraph, Hermes Agent, Pi, OpenClaw, Herdr and Jev are all real, all currently maintained, and `deepseek:deepseek-flash` is a real PydanticAI model id documented verbatim. Nothing in that list is hallucinated. Details and licences in the Q7 table.
- **Forge already contains the cheap pilot, and plugging a decider into it is far smaller than it looks.** `java -jar forge.jar sim` runs headless AI-vs-AI games with no network and no LLM ([Forge AI.md](https://github.com/Card-Forge/forge/blob/master/docs/AI.md)). `PlayerController` declares **113 abstract methods**, but you do not implement them — you subclass `PlayerControllerAi` and override the four that decide deck performance (`getAbilityToPlay`, `declareAttackers`, `declareBlockers`, `chooseTargetsFor`), delegating the rest to Forge's heuristics.
- **Two findings that change the plan's shape.** (1) Kiro's headless `KIRO_API_KEY` draws on the subscription, whereas Codex's `CODEX_API_KEY` switches you to API billing — so on a headless box Kiro is the only one of the two that honours "subscriptions only" without copying OAuth tokens around. (2) jarlaxle has ~2 GB free RAM and no GPU, so the local decider **cannot run there**; the box that can run it (the laptop) is not the box meant to run unattended. That contradiction needs an explicit decision before any code is written.

---

## Q6 table — pilot architectures

Cost column assumes 300 decisions/Standard game. "Subscription-safe" means it consumes no per-token API billing.

| | Architecture | Cost at 1,000 games | Latency / decision | Reliability | Structured output | Observability | Verdict |
|---|---|---|---|---|---|---|---|
| **(a)** | CLI agent drives the engine with its own tools | 391 days of Plus quota (Sol, optimistic) | 20–40 s + tool round-trips | Worst: agent must also drive Forge's UI/CLI; any misstep corrupts the game | None in-loop; agent free-forms | Good (`--json` event stream) | **Reject.** Compounds the quota wall with an unbounded tool loop. |
| **(b)** | Deterministic harness calls CLI agent per decision | Same 391 days | 20–40 s | Harness owns game state, so errors are contained | Good (`--output-schema`) | Good | **Reject on arithmetic.** Technically the cleanest CLI design; still 100× over budget. |
| **(c)** | CLI agent only for flagged decisions, cheap decider for the rest | 10% flagged → 39 days; still infeasible | 20–40 s on flagged, ms otherwise | Good | Good | Good | **Reject as stated.** Only works if "cheap decider" means option (f), at which point the CLI adds little. |
| **(d)** | Direct API SDK (PydanticAI) with typed outputs | GPT-6.2 Sol published USD rate: ~$13.20/game → **~$13,200** | 1–5 s | Best in-loop control: retries, `UsageLimits`, fallbacks | Best (Pydantic-validated) | Best (OpenTelemetry) | **Violates subscriptions-only.** Keep as the reference design if that constraint ever relaxes. |
| **(e)** | CLI agent offline only; in-game play by (c) or (d) | Subscription pays only for brewing | n/a in-loop | Good | Good | Good | **Viable**, and it is the half of (f) that spends the subscription well. |
| **(f)** | **Local decider model picks from enumerated legal actions; CLI agent used only offline for brewing and analysis** | **$0 marginal**; subscription spent on brewing only | Target 50–500 ms (unverified for any specific local model) | Depends on the local model; bounded because the harness enumerates the options | Enforced by construction — the decider returns an index into a legal-action list, so an invalid action is unrepresentable | Full: every state, option set and choice is yours to log | **Recommended.** |

Why (f) wins on the owner's own terms: the pilot is a *measuring instrument* for comparing decklists. A measuring instrument needs consistency and throughput, not brilliance. (f) is the only option whose marginal cost per game is zero and whose per-decision latency is compatible with thousands of games.

Jev (hosted) was the original (f). It remains the strongest *evidence* that the shape works — typed questions over a state, 70–500 ms, $0.042 per million input tokens with free output ([TypeSafe models docs](https://docs.typesafe.ai/models)) — but the owner has rejected hosted APIs on principle in favour of local. Which local model can actually do this is a separate investigation; this report only reserves the architecture slot.

---

## Q7 table — tool claims verified

| Tool | Real? | Licence | What it actually is | Fit, one line |
|---|---|---|---|---|
| [PydanticAI](https://pydantic.dev/docs/ai/overview) | Yes | MIT (21.3k★, pushed 2026-11-20) | Typed Python agent SDK; provider-agnostic | Right tool for the harness's offline analysis layer, even if in-game play never calls an LLM. |
| — typed outputs | Yes | | Pydantic-validated `output_type` | Real and central to the library. |
| — usage limits | Yes | | `UsageLimits` class; `pydantic_ai.usage` normalises cache-read accounting across providers | Real; the budget guard the owner wanted. |
| — OpenTelemetry | Yes | | Documented instrumentation | Real. |
| — [Pydantic Evals](https://pydantic.dev/docs/ai/evals/evals/) | Yes | | Separate evaluation framework in the same docs tree | Real; usable for scoring decklist experiments. |
| — DeepSeek provider | Yes | | `DeepSeekProvider`, `DEEPSEEK_API_KEY` | Real. |
| — `deepseek:deepseek-flash` | **Yes, exactly as written** | | Docs: "Use `deepseek-flash` for the current Flash model"; `Agent('deepseek:deepseek-flash')` appears verbatim | Real. Caveat worth knowing: Flash thinks by default and DeepSeek rejects forced tool choice while thinking, which makes structured output unreliable unless you set `thinking=False`. |
| [LangGraph](https://github.com/langchain-ai/langgraph) | Yes | MIT (45.2k★) | Graph/state-machine orchestration for agent loops | Overkill here; the game loop is a plain loop, not a graph. |
| [Hermes Agent](https://github.com/NousResearch/hermes-agent) (NousResearch) | Yes | MIT (264.9k★) | Monolithic Python agent runtime: ~47 tools, agent-managed memory, self-authored skills | Interesting for the "learn and improve" ambition; too much surface area for a deck tester. |
| [Pi](https://github.com/earendil-works/pi) (`badlogic/pi-mono`, now `earendil-works/pi`) | Yes — repo moved, old URL 301s | MIT (123k★) | Minimal terminal coding harness + unified LLM API; headless `pi -p`; OAuth subscription providers and API-key providers, **including `TYPESAFE_API_KEY` for classifier models** | Best-fit CLI harness if you want one process that can call both a coding model and a classifier; note its OpenAI path is `OPENAI_API_KEY` only, so it cannot spend a ChatGPT Plus subscription. |
| [OpenClaw](https://github.com/openclaw/openclaw) | Yes | MIT (394.9k★) | Self-hosted gateway bridging chat apps (Telegram, Slack, WhatsApp…) to coding agents | Wrong layer — it is a messaging front door, not a game loop. Useful only if you want phone notifications from jarlaxle. |
| [Herdr](https://github.com/herdrdev/herdr) | Yes — and **already installed on this laptop** at `~/.codex/herdr-agent-state.sh` (`HERDR_INTEGRATION_VERSION=10`), registered in `~/.codex/hooks.json` | Apache-2.0 (52.0k★) | Rust terminal multiplexer for coding agents; panes on a background daemon, semantic state (working/idle/blocked/done) over a Unix socket API | Real and relevant to unattended ops, but systemd is the better answer for a service (see Q8). |
| [Jev](https://en.wikipedia.org/wiki/Jev_(AI_model)) / TypeSafe AI | Yes | Proprietary, hosted | Discriminative "System One" model; state + typed questions → calibrated distributions; no text generation | Architecturally ideal, rejected by the owner on the local-only principle. |

All four Jev sources the owner supplied resolve: Wikipedia and the LangChain post fetched successfully, and `arxiv.org/abs/2609.37647` and `github.com/vamsikrishna2421/jev-usecases` both return HTTP 200 (I confirmed reachability, not content).

---

## Q1 — `codex exec` non-interactive mode

**Verdict:** Fully capable as an automation interface, and better documented than expected. `--json`, JSON-Schema-constrained output, session resume and token accounting all exist and are officially supported. None of that rescues it as a per-decision pilot.

**Evidence.** Local: `codex-cli 0.166.0` at `/home/aiden/.local/bin/codex` → `~/.codex/packages/standalone/releases/0.166.0-x86_64-unknown-linux-musl/bin/codex` (305 MB).

From `codex exec --help` on this machine, and [OpenAI's non-interactive mode docs](https://learn.chatgpt.com/docs/non-interactive-mode):

- **Flags:** `--json` (JSONL events to stdout), `--output-schema <FILE>` (JSON Schema for the final response), `-o/--output-last-message <FILE>`, `--ephemeral` (no rollout files), `--ignore-user-config`, `--ignore-rules`, `--skip-git-repo-check`, `-s/--sandbox {read-only,workspace-write,danger-full-access}`, `-m/--model`, `-C/--cd`.
- **Event stream:** the docs name `thread.started`, `turn.started`, `turn.completed`, `turn.failed`, `item.*` and `error`. Internally `--json` is the flag `experimental-json` (string extracted from the 0.166.0 binary), so treat the schema as stabilising rather than stable.
- **Token usage in completion events: yes.** The documented sample is `{"type":"turn.completed","usage":{"input_tokens":24763,"cached_input_tokens":24448,"output_tokens":122,"reasoning_output_tokens":0}}` — all four fields the owner asked about, including cached and reasoning. Confirmed independently in local rollout records: `token_usage_record` payloads carry `input_tokens`, `cached_input_tokens`, `cache_write_input_tokens`, `output_tokens`, `reasoning_output_tokens`, `total_tokens`, at turn and thread scope.
- **No approval prompts:** `codex exec` defaults to a read-only sandbox and does not prompt. `-a never`, `--sandbox workspace-write` and `--dangerously-bypass-approvals-and-sandbox` are available. `--full-auto` is removed; scripts using it must be updated.
- **Resume:** `codex exec resume --last "<prompt>"` or `codex exec resume <SESSION_ID> "<prompt>"`. Documented and present in `--help`.
- **Structured output:** reliable in the sense that matters — `--output-schema` constrains the final message server-side and `-o` writes it to a file.

**Startup overhead and per-call context — the part that matters for a loop.** The binary itself is not the problem: 5 sequential `codex --version` runs took 0.056 s total (~11 ms each). The problem is everything `codex exec` does before the first token:

- It loads `~/.codex/config.toml`, which on this machine declares **7 MCP servers**, two of which are `npx -y …@latest` (`chrome-devtools-mcp`, `@playwright/mcp`) and one of which sets `startup_timeout_sec = 120`. Each invocation pays that startup.
- It re-reads `AGENTS.md` and rebuilds the system prompt every call. Measured from the local rollout: `base_instructions.text` is **21,524 characters**, and the first turn of the session consumed **22,150 input tokens with 0 cached**. Turn 2 reported 31,693 input with 22,144 cached — caching only helps *within* a session.
- OpenAI's own pricing page names both costs in its "make your limits last longer" advice: reduce AGENTS.md size, and limit MCP servers because "every MCP server adds more context to your messages and uses more of your limit."

So yes, it re-reads context every call, and the fixed cost is roughly 22k input tokens per cold invocation. For a per-decision loop you would mitigate with `--ignore-user-config` (drops the MCP servers), `--ephemeral`, and `codex exec resume` to keep the cache warm — but you cannot get the fixed prompt below a few thousand tokens, because the Codex agent prompt is not yours to shrink.

**Confidence: high** on flags, events, usage fields and resume (official docs plus local `--help` and local rollout data). **High** on the 22k-token cold cost (measured, single session, one `cwd`). **Medium** on total cold-start wall time, which I did not measure because starting a session was out of scope.

---

## Q2 — Kiro CLI non-interactive use

**Verdict:** A headless one-shot mode exists and is officially blogged. It emits ACP events as JSON Lines. It meters in **credits and request counts, not tokens** — which makes per-decision budgeting coarser than Codex's. Its decisive advantage for this project is that headless auth uses a subscription-backed API key.

**Evidence.** Local: `kiro-cli 2.37.0` at `/home/aiden/.local/bin/kiro-cli` (42 MB). From `kiro-cli chat --help`:

- `--no-interactive` — "Whether the command should run without expecting user input".
- `--output-format stream-json` — "The run's ACP events as JSON Lines on stdout, one self-describing event per line"; the help text states **stream-json implies `--no-interactive`**.
- `-a/--trust-all-tools`, `--trust-tools=<list>` (and `--trust-tools=` to trust none), `--trust-workspace`.
- Resume: `-r/--resume`, `--resume-id <SESSION_ID>`, `-l/--list-sessions`.
- `--agent`, `--model`, `--effort {low,medium,high,xhigh,max}`, `--agent-engine {v1,v2,v3}`.
- `--require-mcp-startup` exits with **code 3** if any enabled MCP server fails — a usable hard signal.
- A separate `kiro-cli acp` subcommand runs a persistent ACP agent over stdio, which avoids per-decision process spawn if you ever needed a long-lived session.

[Kiro's headless-mode post](https://kiro.dev/blog/introducing-headless-mode/) documents the auth model: generate an API key in account settings, set `KIRO_API_KEY`, and the CLI skips browser login — "that single environment variable is the difference between interactive and headless mode". Install is `curl -fsSL https://cli.kiro.dev/install | bash`. A [spec-kit issue](https://github.com/github/spec-kit/issues/4797) records the operational gotcha from the field: in `--no-interactive` mode, without `--trust-all-tools` every write is denied, because tool approval is unavailable.

**Tokens or credits?** Credits. `kiro-cli chat --list-models -f json` (run locally; a list command, not a session) returns per-model `"rate_unit": "Credit"` and a `rate_multiplier`: `auto` 1.0, `claude-opus-5.5` 2.0, `claude-sonnet-5.5` 1.3, `claude-haiku-5.5` 0.06, `gpt-5.6-sol` 4.4, `gpt-5.6-luna` 0.6, `deepseek-3.2` 0.25, `minimax-m2.5` 0.25, `qwen3-coder-next` 0.05. Strings in the binary show the service API behind this: a `GetUsageLimits` operation returning a `UsageLimitList` with `DailyRequestCount` and `MonthlyRequestCount`, plus `SubscriptionInfo` (overage, upgrade) and `FreeTrialInfo`.

**Could not verify:** whether `--output-format stream-json` includes any per-turn token or credit figure, and whether a credit is charged per request or per token. Both require running one session. Exact command in the prototype section.

**Confidence: high** on flags and the credit-based metering (local `--help` and local `--list-models` output). **Medium** on quota surfacing, because no documented CLI command prints remaining credits — `kiro-cli user whoami|profile` exist but their output is unverified here.

---

## Q3 — Quota and rate-limit reality

**Verdict:** Codex surfaces quota well enough to build a clean pause/resume loop — better than its docs suggest, because the live event stream carries machine-readable reset timestamps. Kiro surfaces it poorly at the CLI. Neither has enough quota for the job.

### Codex, documented

From [the official pricing page](https://learn.chatgpt.com/docs/pricing), local messages per five-hour period:

| Model | Plus | Standard Business |
|---|---|---|
| GPT-6.2 Astra | 6–50 | 6–50 |
| GPT-6.2 Sol | 17–180 | 17–180 |
| GPT-6 Astra | 5–45 | 5–45 |
| **GPT-6.1 Sol** | **15–160** | 15–160 |
| GPT-6.1 Terra | 35–285 | 35–285 |
| GPT-6 Sol | 15–150 | 15–150 |
| **GPT-6 Luna** | **350–3,000** | 350–3,000 |

Also documented: "Weekly limits may also apply"; Pro plans currently have no five-hour limit but still have an included allowance; "Local messages and cloud chats share your plan's usage allowance"; and on exhaustion, "If you reach your usage limits during an active turn, the agent will be able to continue working on that turn, **subject to fair use limits**." That last clause is the one an unattended loop should worry about — see Q4.

### Codex, as it actually surfaces at the CLI (local evidence)

Every `token_count` event carries a `rate_limits` object. From a local rollout:

```json
"rate_limits": {
  "limit_id": "codex",
  "primary":   {"used_percent": 0.0,  "window_minutes": 300,   "resets_at": 1794653260},
  "secondary": {"used_percent": 23.0, "window_minutes": 10080, "resets_at": 1794998053},
  "credits": {"has_credits": false, "unlimited": false, "balance": "0"},
  "plan_type": "plus",
  "rate_limit_reached_type": null
}
```

`window_minutes: 300` is the 5-hour window; `10080` is the 7-day window — so the undocumented-in-detail weekly cap is directly observable. Across all 70 local sessions: `plan_type` was `"plus"` in 2,795 records, `rate_limit_reached_type` was `null` in all 3,017 records (never exhausted mid-stream here), and the maximum `used_percent` observed was **100.0 on the primary 300-minute window** — confirming the field does reach saturation.

Exhaustion messages, extracted from the 0.166.0 binary (these are the literals a harness would match):

- `You've hit your usage limit.`
- `You've hit your usage limit for <...>`
- `Usage limit reached. You've reached your usage limit. Increase your limits to continue using codex.`
- `You're out of credits. Your workspace is out of credits.`
- `Automatically switched to <model> due to usage limits.` / `Automatically switched back to <model> because ordinary usage is available again.`

That second-to-last one is a trap for a measurement harness: **Codex silently downgrades the model when you hit limits.** A deck-comparison run whose pilot swaps models mid-experiment has just invalidated its own results. Any harness must pin `-m` and assert the model in `turn.completed`.

**How a harness should detect exhaustion.** Do not scrape stderr. Read `--json`, and on each `token_count` event check `rate_limits.primary.used_percent` and `.secondary.used_percent`; when either crosses a threshold (say 95%), stop issuing work and sleep until the corresponding `resets_at` unix timestamp. Treat `rate_limit_reached_type != null` as a hard stop. Keep the string matches above only as a fallback.

**Exit codes: not verified.** I found no documentation of a distinct exit code for quota exhaustion, and could not test without running a session to exhaustion. Assume you cannot rely on exit codes and drive off the event stream.

### Kiro

Credit-metered. Widely reported plan structure — Free 50 credits/month, Pro $20/1,000, Pro+ $40/2,000, Pro Max $100/5,000, Power $200/10,000, i.e. $0.02 per included credit — comes from secondary sources ([twitterapi.io](https://twitterapi.io/blog/kiro-pricing), [tailkits](https://tailkits.com/tools/kiro/)), not from a page I fetched from kiro.dev; treat the exact numbers as **medium confidence**. The per-model `rate_multiplier` values above are first-hand from the local binary. Several sources state Kiro has no daily or weekly rate limits, only the monthly credit pool, but the binary's `DailyRequestCount` and `MonthlyRequestCount` limit types suggest daily limits exist at least as a concept.

**Confidence: high** on Codex's documented message bands and on the locally observed `rate_limits` structure. **Medium** on Kiro plan prices. **Low** on CLI exit codes for either tool.

### The arithmetic

Assumption, stated explicitly as the owner asked: **300 decision points per game for the piloted seat in Standard.** Standard games run longer than aggro Pauper games — roughly 8–14 turns per player, with many priority passes, blocks, trigger orderings and targeting choices per turn. 300 is a central estimate; I also show 150 as a conservative floor. The brief's "50–300 for a real MTG game" is a reasonable range for aggro; Standard sits at the top of it or above.

One decision = one Codex turn = one "message" against the quota.

**Quota (Plus, GPT-6.1 Sol, optimistic 160 messages / 5 h = 768 messages/day):**

```
768 messages/day ÷ 300 decisions/game  =  2.56 games/day
1,000 games ÷ 2.56                     =  391 days
10,000 games ÷ 2.56                    =  3,906 days  (10.7 years)
```

At the pessimistic end of the same documented band (15/5h = 72/day): 0.24 games/day → 1,000 games = **4,167 days**.

Switching to the cheapest model, GPT-6 Luna, optimistic 3,000/5h = 14,400 messages/day:

```
14,400 ÷ 300  =  48 games/day
1,000 games   =  20.8 days
10,000 games  =  208 days
```

And a weekly cap applies on top, so the 5-hour rate is not sustainable around the clock.

**Latency (independent of quota):**

```
30 s/decision × 300 decisions  =  9,000 s  =  2.5 hours per game
× 1,000 games                  =  104 days of continuous wall-clock
× 10,000 games                 =  2.85 years
```

Even using my measured best case — 9.0 s median in-session turn, and the conservative 150 decisions:

```
9 s × 150  =  1,350 s  =  22.5 min per game
× 1,000    =  15.6 days
× 10,000   =  156 days
```

**For contrast, the same 1,000 games under option (d), published USD rates.** GPT-6.2 Sol is $2 per million input tokens. At the measured 22k input tokens per cold invocation: `22,000 × $2/1e6 = $0.044` per decision → `× 300 = $13.20` per game → **$13,200 per 1,000 games**. That is the real price of CLI-shaped context on a per-decision loop, and it is why the fixed 22k prefix matters so much.

**Under option (f), local decider:** marginal cost $0, and at a 200 ms target, `200 ms × 300 = 60 s` per game of decider time — meaning Forge's own simulation speed becomes the bottleneck, which is the correct place for the bottleneck to be.

---

## Q4 — Terms of service

**Verdict:** Running `codex exec` from a script is explicitly sanctioned; that is not the risk. Three other things are. One of them — distilling the agent's play into a local decider model — is squarely addressed by OpenAI's Usage Policies and is the single clause most likely to bite this project.

**What is clearly permitted.** OpenAI's pricing page lists "Codex SDK, `codex exec`, and scriptable workflows" as an included Plus feature, and the non-interactive docs are a guide to CI automation. So the generic worry that "programmatic use breaches the ToU" is misplaced for the official CLI. The Terms of Use clause people cite — "Automatically or programmatically extracting data or Output" ([EU Terms of Use](https://openai.com/policies/eu-terms-of-use), *What you cannot do*) — targets scraping the consumer product, not using OpenAI's own documented CLI as documented.

**Risk 1 — training a model on the outputs. This is the serious one.** OpenAI's [Usage Policies](https://openai.com/policies/usage-policies), effective 20 November 2026, added a *Training and developing models* section. Its own words, quoted within limits: you must not use OpenAI models or their outputs to "generate, prepare, select, or supply training material or signals for models that are intended as alternatives to or substitutes for OpenAI models or services", and the enumerated prohibitions include "Providing feedback used in training, including labels, scores, rankings, preferences, rewards, or corrections" and "Selecting, filtering, or validating training data, tasks, or trajectories."

Read against the owner's original phrasing — "learn and improve", "automatically train on the homelab", "a decider model built into the harness" — the exposure is specific: **harvesting Codex's in-game decisions as labels to train the local decider would fall inside the enumerated conduct.** Whether the resulting narrow MTG policy counts as "intended as alternatives to or substitutes for OpenAI models or services" is genuinely arguable, and I will not pretend it is settled; a card-game action selector is not a general substitute for Codex. But the clause explicitly covers supplying "signals", "rewards" and "corrections", and explicitly applies "even if you do not train the resulting model". The same section does permit "research, software development, model evaluation and benchmarking, and product development, within these boundaries."

The clean line, and my recommendation: **never derive the local decider's training signal from a CLI agent's outputs.** Derive it from game outcomes, from Forge's own AI, or from human-authored heuristics. Use the subscription for brewing hypotheses, reading match logs and writing strategy notes — all plainly "software development" and "product development". This costs the project nothing, because option (f) already does not need the agent in the loop.

**Risk 2 — unattended continuous consumption.** Not prohibited anywhere I found. But the pricing page's phrase "subject to fair use limits" is undefined, and the Terms prohibit "circumventing any rate limits or restrictions or bypassing any protective measures". A harness that waits for `resets_at` and resumes is respecting limits. A harness that rotates accounts, buys instant resets to farm throughput, or retries through 429s is circumventing them. Keep to the former. Note also that 24/7 maximal consumption from a single account is exactly the pattern abuse-detection systems are built to flag, and account suspension is at OpenAI's discretion where "use of our Services could cause risk or harm to OpenAI, our users, or anyone else."

**Risk 3 — the consumer/commercial boundary and credential handling.** The consumer Terms cover "personal, non-commercial use". A personal deck-brewing tool is fine. Separately, the Terms forbid sharing account credentials, and OpenAI's own CI guidance warns that `~/.codex/auth.json` contains access tokens and should be treated like a password — relevant to Q8, where getting a subscription onto jarlaxle means moving that file.

**AWS/Kiro.** Kiro is an AWS service: "By downloading and using Kiro, you agree to the AWS Customer Agreement (or other agreement with us governing your use of AWS services), Service Terms, and Privacy Notice" ([kiro.dev/downloads](https://kiro.dev/downloads/)). The [AWS Acceptable Use Policy](https://aws.amazon.com/aup/) is short and concerns illegal/harmful/abusive use; nothing in it addresses game-playing or unattended loops. AWS actively encourages headless automation (the headless-mode blog post is a CI tutorial). I did **not** locate a Kiro-specific service-terms section addressing automated or unattended use, nor any clause analogous to OpenAI's model-training restriction. A [public issue](https://github.com/kirodotdev/Kiro/issues/2206) asks AWS to clarify Kiro's terms, which suggests the gap is real rather than my failure to find it.

**Being direct about the risk.** Game-playing on a coding subscription is not addressed by either provider's terms and is, in my reading, not prohibited. The two things that would make me stop are: distilling agent outputs into the local decider (OpenAI Usage Policies, explicit), and anything that looks like evading rate limits (both providers, explicit). Option (f) avoids both by construction. Kiro carries materially less documented ToS risk than Codex for this use, mainly because AWS has written less.

**Confidence: high** on the quoted clauses (fetched from the policy pages). **Medium** on applying the training clause to a narrow game-decision model — that is interpretation, and a one-paragraph question to OpenAI support would settle it better than more reading.

---

## Q5 — Latency

**Verdict:** 20–40 s per decision for a cold CLI invocation; ~9 s for a warm in-session turn; 1–5 s for a direct small-model API call; 70–500 ms for a discriminative local/hosted classifier. I found no published benchmark specific to `codex exec` cold-start, so I measured what I could locally and give the procedure for the rest.

**Measured locally (primary evidence).** From `~/.codex/sessions/2026/11/14/rollout-2026-11-14T13-47-04-01a1d898-5541-7cc3-b4bc-01857c0447f8.jsonl`, taking inter-arrival gaps between consecutive `token_usage_record` timestamps (n=42, outliers >300 s excluded as human think-time), model `gpt-6.1-sol` at `model_reasoning_effort = "high"`:

| min | median | mean | p90 | max |
|---|---|---|---|---|
| 3.1 s | **9.0 s** | 14.5 s | 13.4 s | 263.6 s |

These gaps include tool execution, so they overstate pure model time — but they are the right unit for a harness, because a harness waits for turns, not for tokens. Note the 263 s tail: a CLI agent's latency distribution has a long right tail, which for a 300-decision game means occasional multi-minute stalls.

**Process spawn is negligible; everything around it is not.** 5 × `codex --version` = 0.056 s total (~11 ms each); 5 × `kiro-cli --version` = 0.028 s. But `codex exec` additionally loads config, spawns 7 MCP servers (two via `npx -y …@latest`, one with a 120 s startup timeout), scans the git repo, and sends an uncached ~22k-token prompt. Lowering reasoning effort and passing `--ignore-user-config` are the two biggest levers.

**Published figures for the comparison points.** Jev: TypeSafe claims end-to-end 70–500 ms, "40–200x faster and 40–400x cheaper than frontier LLMs on comparable tests", with the honest caveat in their own notes that the workflows were built by their model-capabilities team and may be biased ([Wikipedia summary](https://en.wikipedia.org/wiki/Jev_(AI_model)), [LangChain](https://www.langchain.com/blog/building-a-harness-with-jev)). *Content was rephrased for compliance with licensing restrictions.* I found no published `codex exec` latency benchmark.

**Why this kills (a)–(c) on its own, restated with the Standard assumption:** `30 s × 300 decisions = 2.5 h/game`; 1,000 games = 104 days; 10,000 games = 2.85 years. Parallelism does not save it, because the binding constraint is the shared account quota, not CPU — and on jarlaxle it is also RAM (Q8).

**Confidence: high** for the local measurements (direct observation, though one session, one model, one effort level). **Medium** for the 20–40 s cold-invocation estimate — inferred from the 9 s warm median plus the known startup work, not measured. **Low** for the Jev figures, which are vendor-reported.

---

## Q8 — Unattended operation on jarlaxle

**Verdict:** A systemd **user** unit with lingering enabled. Not tmux, not cron. But three prerequisites must be settled first, and one of them is a contradiction in the current plan.

### Prerequisites, grounded in the stated specs

jarlaxle: Ubuntu 24.04, 12 cores, 8 GB RAM (~2 GB free), **no GPU**, 297 GB free disk; Java present; node, npm, uv, docker, ollama absent; neither `codex` nor `kiro-cli` installed.

1. **The local decider cannot run on jarlaxle.** No GPU and ~2 GB free RAM. The box that can run it is the laptop (16 GB, RTX 4050 6 GB). This directly contradicts "runs unattended on jarlaxle". Three ways out, and the owner should pick one before anything is built: (i) run the whole loop on the laptop and give up on jarlaxle; (ii) run Forge on jarlaxle and serve the decider from the laptop over the LAN, accepting that jarlaxle idles when the laptop is off; (iii) add RAM to jarlaxle and use a CPU-only decider small enough to fit. (ii) is the least work and preserves the division of labour; (iii) is the only one that delivers genuinely unattended operation.
2. **Forge's memory budget conflicts with 2 GB free.** Forge is a JVM app; a Standard game with a full card database wants ~1–2 GB heap. With 12 cores you would want parallel Forge instances for throughput, and RAM — not cores — will cap you at roughly one. Fix the RAM question before designing for parallelism, and set `MemoryMax=` on the unit so a runaway Forge cannot OOM the box.
3. **Installing and authenticating the CLIs.** Kiro: `curl -fsSL https://cli.kiro.dev/install | bash`, then `KIRO_API_KEY` — no node, no browser. Codex: the npm install path needs node; the standalone binary avoids it (305 MB on this laptop) but `codex login` wants a browser, and the only browserless options are `CODEX_API_KEY` (which switches you to API billing, violating subscriptions-only) or copying `~/.codex/auth.json` from the laptop, which OpenAI's docs describe as advanced, warn is credential-sensitive, and note must be persisted back after Codex refreshes it in place. **Consequence: if the offline brewing agent must run on jarlaxle under a subscription, use Kiro, not Codex.** If the brewing agent runs on the laptop interactively, use whichever you prefer.

### The service

A user unit, because the workload is a personal tool with no need for root:

- `~/.config/systemd/user/deckai.service`, then `systemctl --user enable --now deckai` and — the step people forget — `sudo loginctl enable-linger $USER`, without which the unit dies at logout.
- `Restart=on-failure`, `RestartSec=60`, and `StartLimitIntervalSec=0` so a long run of quota-driven restarts does not trip the rate limiter and give up permanently.
- `MemoryMax=` and `CPUQuota=` to protect the box, given point 2.
- **Log rotation is free.** Output to stdout/stderr goes to journald, which rotates by size and age on its own. This is the concrete reason to prefer systemd over tmux: a tmux scrollback is not a log, and a `nohup … > out.log` needs a logrotate config you will forget to write. Cap with `SystemMaxUse=` in `journald.conf` if 297 GB ever looks threatened.
- **Quota exhaustion belongs in the harness, not the service manager.** The event stream hands you `rate_limits.*.resets_at` as a unix timestamp, so the loop should finish the current game, write state, sleep until the reset, and continue. Restart-on-exit is the wrong shape: it loses in-memory experiment state and turns a known wait into a crash loop. Reserve `Restart=on-failure` for genuine crashes.
- **Crash recovery = checkpoint after every game.** The unit of work is one game; append its result (decklist hash, gauntlet opponent, seed, winner, turn count) to an append-only file or SQLite table as it completes, and make startup resume from the last checkpoint. Then a crash costs at most one game. Forge's `-c <seconds>` clock flag (default 120) caps pathological games as a draw — set it deliberately, since a hung game is otherwise indistinguishable from a slow one.
- **tmux / Herdr:** useful for attaching to watch a run, and Herdr is already installed on the laptop with a working Codex integration. Neither should be the supervisor.

**Confidence: high** on the systemd mechanics and the install/auth asymmetry between the two CLIs (the Kiro install command and `KIRO_API_KEY` are from Kiro's own post; the Codex `auth.json` caveat from OpenAI's non-interactive docs). **Medium** on Forge's heap requirement, which I estimated rather than measured.

---

## The engine, since it determines everything else

Not a numbered question, but it reframes the whole project and I would be withholding the most useful finding if I left it out.

**Forge already ships the pilot you need for the gauntlet.** From [Forge's AI.md](https://github.com/Card-Forge/forge/blob/master/docs/AI.md): `sim` mode "forces Forge to not start the GUI and automatically runs the AI matches in command line", explicitly "allowing the tests to be performed on headless servers", and the doc's own suggested use case is "script testing of decks, test a large tournament, or just bash 100's of games out to see how well a deck performs." Syntax: `java -jar forge.jar sim -d <deck1> <deck2> -n <games> -q -c <seconds>`. `-q` prints only results; `-c` caps game length. GPL-3.0, 2,922★, pushed 2026-11-20.

Three consequences:

1. **A zero-LLM baseline is available on day one.** Before any decider exists, you can run the candidate list against the fixed gauntlet with Forge's AI on both seats, thousands of games, no network, no quota. That baseline is also the only honest control for measuring whether your decider adds anything.
2. **Forge's AI is biased in a way that matters for Standard.** The doc states the AI is "Best with Aggro and midrange decks", "Poor to Ok in control decks", "Pretty bad for most combo decks", and is heuristic, not trained. For a Standard gauntlet containing control and combo decks, that bias systematically distorts matchup win rates — the gauntlet will flatter aggro candidates. Any deck recommendation must carry that caveat, and it is a stronger argument for replacing the *opponent's* controller than the pilot's.
3. **Plugging a decider in is much smaller than the class surface suggests.** `forge-game/src/main/java/forge/game/player/PlayerController.java` (421 lines) declares **113 abstract methods** — `announceRequirements`, `assignCombatDamage`, `chooseCardsToDiscardFrom`, `chooseModeForAbility`, and so on. You do not implement 113 methods. You subclass `forge-ai/src/main/java/forge/ai/PlayerControllerAi.java` and override only the decisions that move win rate:
   - `getAbilityToPlay(Card, List<SpellAbility>, ITriggerEvent)` — line 100, what to cast or play
   - `declareAttackers(Player, Combat)` — line 183
   - `declareBlockers(Player, Combat)` — line 184
   - `chooseTargetsFor(SpellAbility)` — line 146
   
   Everything else falls through to Forge's heuristics. This is exactly the shape option (f) wants: the harness enumerates legal `SpellAbility` options and the decider returns a choice from that list, so an illegal action is unrepresentable. Note the licence consequence: Forge is GPL-3.0, so a distributed derivative must be GPL-3.0 too. Also note `-f` accepts Commander, Oathbreaker, TinyLeaders, Brawl, MomirBasic, Vanguard and MoJhoSto but **not Standard** — Standard legality is not enforced by sim mode, so the harness must validate decklists against a Standard-legal card pool itself.

---

## Recommendation

1. **Do not use a CLI coding agent as the in-game pilot.** Quota is short by ~100× and latency by ~40×; both numbers are above.
2. **Spend the subscription on low-frequency, high-value work:** proposing card swaps, reading aggregated match logs, writing strategy notes, authoring the gauntlet. That is 10–100 invocations per experiment cycle, not 300,000, and it sits comfortably inside a Plus allowance.
3. **Build the Forge-AI-only baseline first.** It needs no decider, no LLM and no quota, and it is the control you cannot interpret your results without.
4. **Then add the local decider as a `PlayerControllerAi` subclass overriding four methods.** Keep the enumerate-then-choose contract so invalid actions cannot occur.
5. **Never train the decider on CLI-agent outputs.** Use game outcomes. This is both the ToS-safe path and the methodologically better one.
6. **Settle the jarlaxle contradiction before writing code.** Either add RAM, or accept that the decider lives on the laptop and jarlaxle runs only Forge.
7. **If anything agentic must run on jarlaxle under a subscription, use Kiro CLI** — `KIRO_API_KEY` is subscription-backed and needs no browser or node, whereas Codex's headless key path means API billing.

---

## What to prototype first to settle the unknowns

Ordered by how much each reduces risk per unit of effort. Commands are exact; none has been run.

**1. Forge headless baseline — settles throughput, the single most important unknown.**
```bash
# on jarlaxle (Java already present)
cd ~/forge && time java -Xmx2g -jar forge-gui-desktop-*-jar-with-dependencies.jar \
  sim -d candidate gauntlet_01 -n 50 -q -c 180
```
Record: wall time for 50 games, peak RSS, and how many games hit the `-c` clock. Divide to get games/hour. Then the project's whole feasibility question becomes arithmetic. Also try `-n 200` with two concurrent instances to find where 8 GB RAM caps parallelism.

**2. `codex exec` cold-invocation cost — settles the 20–40 s estimate and the 22k-token prefix.**
```bash
cd /tmp/scratch-repo && git init -q
cat > /tmp/dec.json <<'EOF'
{"type":"object","properties":{"action_index":{"type":"integer"},"reason":{"type":"string"}},
 "required":["action_index","reason"],"additionalProperties":false}
EOF
time codex exec --json --ephemeral --ignore-user-config --skip-git-repo-check \
  -m gpt-6-luna --output-schema /tmp/dec.json \
  "Board state: you have 3 lands untapped and these legal actions: 0) pass 1) cast Shock at opponent 2) play a land. Choose one." \
  2>/tmp/cold.err | tee /tmp/cold.jsonl
jq -c 'select(.type=="turn.completed") | .usage' /tmp/cold.jsonl
```
Answers: real cold wall time; whether `--ignore-user-config` eliminates MCP startup; `input_tokens` with no AGENTS.md and no MCP servers (my prediction: 5–8k, down from 22k); and whether `--output-schema` holds on the first try. Run it three times to see whether `cached_input_tokens` rises across separate processes — that single number decides whether a per-decision CLI loop is even theoretically cacheable.

**3. Kiro headless event stream — settles whether it reports tokens or only credits.**
```bash
cd /tmp/scratch-repo && time kiro-cli chat --no-interactive --output-format stream-json \
  --trust-tools= --model qwen3-coder-next \
  "Reply with only this JSON: {\"action_index\": 1}" | tee /tmp/kiro.jsonl
jq -rc '.' /tmp/kiro.jsonl | head -40
echo "exit=$?"
```
Then, immediately after, check whether remaining quota is readable without the web console:
```bash
kiro-cli user whoami; kiro-cli user profile
```
Answers: the ACP event vocabulary, whether any usage or credit figure appears, the exit code on success, and whether the CLI can self-report quota.

**4. Forge decider hook — settles the integration cost, the biggest engineering unknown.**
Build Forge from source, subclass `PlayerControllerAi`, override `getAbilityToPlay` to log the enumerated `List<SpellAbility>` and then delegate to `super`. Run `sim -n 1`. If the log shows a clean, serialisable option list at every decision, option (f) is confirmed buildable and you have the state/option schema the decider will consume. If the options are not cleanly serialisable, that is the moment to find out — not after the decider exists.

**5. Codex quota telemetry — settles pause/resume, cheaply.**
```bash
jq -c 'select(.type=="token_count") | .rate_limits' /tmp/cold.jsonl
```
Confirm `primary`/`secondary` `used_percent` and `resets_at` appear in the `exec --json` stream and not only in persisted rollouts. The whole pause/resume design depends on this one fact, and it costs one invocation to check.

---

## Claims I could not verify

Separating these out, as asked.

- **Codex exit code on quota exhaustion.** Undocumented; untestable without exhausting the account. Design off the event stream instead.
- **Cold `codex exec` wall time.** My 20–40 s is inferred from a measured 9.0 s warm median plus known startup work. Prototype 2 settles it.
- **Whether server-side prompt caching survives across separate `codex exec` processes.** The docs' own sample shows 24,448 of 24,763 input tokens cached, but I cannot tell whether that example is a resume. This materially changes the per-decision cost. Prototype 2 settles it.
- **Whether `kiro-cli --output-format stream-json` emits token or credit counts.** Help text says "self-describing ACP events" and nothing more; the binary yielded no usable field names. Prototype 3 settles it.
- **Whether a Kiro credit is charged per request or per token.** The `rate_multiplier` naming implies per-request, but that is inference from a field name.
- **Kiro plan prices (Free 50 / Pro $20–1,000 credits / … / Power $200–10,000).** Secondary sources only; I did not fetch a kiro.dev pricing page (it is cookie-gated). The per-model multipliers, by contrast, are first-hand from the local binary.
- **Whether Kiro's daily request limits apply to subscription plans.** `DailyRequestCount` exists as a limit type in the binary; several sources say Kiro has no daily caps. Unresolved.
- **Any Kiro-specific service-terms clause on automated or unattended use.** I did not find one. Absence of evidence, not evidence of absence — AWS's service terms are long and I fetched the AUP, not the full Kiro section.
- **Whether a narrow MTG decision model counts as "an alternative to or substitute for OpenAI models or services"** under the Usage Policies' training restriction. This is interpretation. Worth a direct question to OpenAI support if the owner wants the distillation route at all.
- **Forge's actual heap requirement and games/hour.** Estimated, not measured. Prototype 1 settles both.
- **The content of the two Jev sources I only pinged.** `arxiv.org/abs/2609.37647` and `github.com/vamsikrishna2421/jev-usecases` return HTTP 200; I did not read them, since Jev was demoted to an architecture note.
- **jarlaxle itself.** Every statement about it comes from the owner's message; I had no access to the box.
- **Standard decisions-per-game = 300.** My estimate from how Standard games play, not a measurement. Prototype 1 can produce the real number by instrumenting `getAbilityToPlay` call counts, which would also let the owner re-run all the arithmetic above on real data.

---

## Appendix — local evidence, reproducible

| Claim | How to re-derive |
|---|---|
| `codex-cli 0.166.0`, `kiro-cli 2.37.0` | `codex --version; kiro-cli --version` |
| Binary startup ~11 ms / ~6 ms | `time (for i in 1 2 3 4 5; do codex --version >/dev/null; done)` |
| 7 MCP servers, two via `npx -y …@latest` | `grep -c '^\[mcp_servers' ~/.codex/config.toml` |
| `base_instructions` = 21,524 chars | `session_meta` payload in any rollout under `~/.codex/sessions/` |
| First-turn 22,150 input tokens, 0 cached | first `token_usage_record` in `~/.codex/sessions/2026/11/14/rollout-2026-11-14T13-47-04-*.jsonl` |
| Turn latency median 9.0 s, n=42 | inter-arrival gaps of `token_usage_record` timestamps in that file |
| `rate_limits` with 300- and 10080-minute windows, `plan_type: "plus"` | any `token_count` event payload in that file |
| `used_percent` observed at 100.0 | scan `rate_limits` across `~/.codex/sessions/*/*/*/*.jsonl` |
| Exhaustion message literals | `strings ~/.codex/packages/standalone/releases/0.166.0-*/bin/codex \| grep -i "usage limit"` |
| Kiro meters in Credits; per-model multipliers | `kiro-cli chat --list-models -f json` |
| Kiro `GetUsageLimits`, `DailyRequestCount`, `MonthlyRequestCount` | `strings /home/aiden/.local/bin/kiro-cli \| grep -o 'GetUsageLimits'` |
| Herdr installed and hooked into Codex | `head -6 ~/.codex/herdr-agent-state.sh; grep -i herdr ~/.codex/hooks.json` |
| Forge `PlayerController` has 113 abstract methods | `curl -s https://raw.githubusercontent.com/Card-Forge/forge/master/forge-game/src/main/java/forge/game/player/PlayerController.java \| grep -cE '^\s*(public )?abstract '` |
| Licences and activity | `curl -s https://api.github.com/repos/<owner>/<repo> \| jq '.license.spdx_id, .stargazers_count, .pushed_at'` |

Sources are linked inline. Content from external pages was rephrased for compliance with licensing restrictions; direct quotation is limited to short policy clauses where exact wording carries the meaning.
