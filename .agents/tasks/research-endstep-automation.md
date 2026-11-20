# Driving Endstep programmatically — feasibility findings

Read-only investigation, 2026-11-20. No code changed. Evidence is drawn from the live
`endstep.cc` JavaScript bundle, the site's public `/about`, `/changelog` and `robots.txt`,
the client-rendered Terms of Service chunk, and three public GitHub repositories read via
the GitHub API.

---

## Summary

- **Biggest risk is permission, not engineering.** Endstep's Terms of Service contain **no
  clause about bots, automation or scripted clients at all** — so there is nothing to rely
  on as permission and nothing precise to comply with. What governs instead is a
  discretionary rule ("Don't use bugs or **tools** to see hidden information or gain an
  unfair advantage") plus broad moderator discretion up to permanent ban. Endstep is a free,
  single-developer fan project with no API contract and no bot-authorisation path, so the
  whole pipeline would rest on one account that can be closed at any time with no recourse.
- **The hard technical problem the plan worried about does not exist.** Endstep's server
  enumerates legal actions and sends them to the client. The `pendingAction` object carries
  `cardOptions[]`, and each option carries `playableAbilities[{index, description, cost}]`.
  The controller answers with `{type: "PLAY_CARD", cardId, abilityIndex}`. No rules
  reimplementation is required. This is the single most consequential finding and it
  **refutes** the plan's framing of legal-action derivation as "a large amount of rules work".
- **The protocol is fully mapped and well-shaped for a controller**, including a
  `promptVersion` field for optimistic concurrency, `seq`/`baseSeq` ordering, `ATTACH`
  resync, `ROLLBACK`, and `ACTION_REFUSED`/`ACTION_ERROR` rejection paths. It is also
  private, undocumented and subject to change; `protocolVersion: 1` is the only stability
  signal.
- **Both tracker projects are real, but only one is useful.** Endstep-Tracker (MIT, actively
  maintained) is a faithful, proven WebSocket observer and is effectively the protocol
  documentation. Endstep Session Reader does **not** read the WebSocket — it scrapes the
  site's own event log out of page storage — and is an unfinished 0-star repo untouched since
  the day it was created.
- **Comparable public projects all drive Forge locally, not Endstep.** `spike-eval` already
  does what this plan proposes — LLMs taking a seat in Forge, with the engine enumerating
  every legal action — and no public project plays Endstep. Recommendation: build the
  controller against local headless Forge for volume work, and treat Endstep as an optional
  "play a human" front-end, not the training venue.

---

## Q1 — Does `mcouzinet/Endstep-Tracker` exist, and what does it observe?

**Verdict: Exists and is verified. The plan's claim is true and in fact understated. The
state information is complete enough to reconstruct a board state from the viewer's seat.**

### Evidence

Repository: <https://github.com/mcouzinet/Endstep-Tracker> — public, MIT licensed,
JavaScript, created 2026-09-23, last pushed 2026-11-05, 6 stars. Shipped on the
[Chrome Web Store](https://chromewebstore.google.com/detail/endstep-tracker/ioeffckengdfapnapdbphkbnnnnaajho),
[Firefox](https://addons.mozilla.org/en-US/firefox/addon/endstep-tracker/),
[Edge](https://microsoftedge.microsoft.com/addons/detail/endstep-tracker/oloikebkijkmhlodohfbjbekkmghblbp)
and the Mac App Store. Being a shipped store extension matters: its observation technique
demonstrably works against the live site.

**Transport — WebSocket, confirmed.** `hook.js` runs in the page's own JS world at
`document_start` and wraps the constructor with a `Proxy`:

```js
const WANTED = /"type":"(GAME_(STATE|DELTA|EVENT|OVER|GONE)|MATCH_STATUS|ATTACH|LOBBY_UPDATE)"/;
window.WebSocket = new Proxy(window.WebSocket, { construct(Target, args, newTarget) { … } });
```

So the claimed `GAME_STATE`, `GAME_DELTA`, `GAME_EVENT` are all real, plus `GAME_OVER`,
`GAME_GONE`, `MATCH_STATUS`, `ATTACH` and `LOBBY_UPDATE`. It also wraps `window.fetch` for
`/api/decks`, `/api/decks/<uuid>`, `/api/matches/<uuid>`, `/api/matches/<uuid>/deck`,
`/api/me/matches` and `/api/ranked/players?username=`.

**Schema — concrete field names.** `test/replay.test.js` is a real Bo3 captured
2026-09-22 and replayed through the tracker; its header states "Frame shapes and ordering
are as observed on the wire." `GAME_STATE`:

```
{ type, matchId, viewerSeat, seq, timestamp, protocolVersion,
  payload: { gameId, phase, turnNumber, activePlayerId, priorityPlayerId, status,
             winnerId, gameType, sideboarding,
             matchScore: { winsBySeat, player0Wins, player1Wins, gameNumber,
                           gamesPlayed, gamesPerMatch, isMatchOver },
             players: [ { id, name, life, hand, battlefield, graveyard, exile,
                          handSize, librarySize } ] } }
```

Card objects: `{ id, name, zone, ownerId, controllerId, faceDown, isToken, types, color }`.
Opponent hand cards arrive as `{ id, name: "Hidden card", faceDown: true, types: [] }` — i.e.
hidden information is correctly withheld, and the count is still visible.

`GAME_DELTA`: `{ type, matchId, viewerSeat, seq, payload: { baseSeq, patch: { state, players: [{ i, librarySize }] }, pendingAction } }`.

`GAME_EVENT`: `{ type: "GAME_EVENT", matchId, timestamp, protocolVersion, payload: { type, gameId, sequenceNumber, message, … } }`. Observed `payload.type` values include
`GAME_STARTED`, `MULLIGAN`, `HAND_SETTLED`, `SHUFFLE`, `TURN_BEGAN`, `TURN_PHASE`,
`LAND_PLAYED`, `SPELL_CAST`, `TRIGGER_FIRED`, `CARD_ZONE_CHANGE`, `CARD_REVEALED`,
`PLAYER_DAMAGED`, `PLAYER_LIFE_CHANGED`, `GAME_OUTCOME`.

`ATTACH` is the resync/catch-up envelope: `{ type: "ATTACH", payload: { matchId, fromSeq, headSeq, frames: [...] } }`.

**Completeness.** Sufficient. `GAME_STATE` is a full snapshot of all four public zones plus
the viewer's hand, with life, phase, turn and active/priority player; `GAME_DELTA` carries
incremental patches against `baseSeq`; `ATTACH` replays missed frames. The tracker
reconstructs opening hands, mulligans, play/draw, turn-by-turn plays, final life and end
reason purely from this stream. Documented limits (`docs/DEVELOPMENT.md`): events that
occurred before the page was opened are not recovered, and the opponent's decklist is only
ever a lower bound (what was seen).

**One compliance landmine, flagged by the tracker's own author.** In `hook.js`, the
`/api/matches/<uuid>` handler whitelists fields with this comment:

> Whitelisted on purpose: this response also carries a server-side state fingerprint that
> includes the opponent's hidden hand. Never forward it.

Reading that field would directly violate the ToS rule quoted in Q4. Any controller must
whitelist, never pass through, this endpoint's response.

**Confidence: High.** Source code read directly; technique validated by four store releases.

---

## Q2 — Does `MattNot/endstep-session-reader` exist, and what does it export?

**Verdict: Exists. The JSON/Markdown export claim is true. But the plan's implied
equivalence with the tracker is wrong: it does not read the WebSocket, it is post-hoc, and
it is an abandoned prototype.**

### Evidence

Repository: <https://github.com/MattNot/endstep-session-reader> — public, JavaScript,
created 2026-09-13, last pushed 2026-09-13 (same day), **0 stars**, no description, no
license file in the tree.

**What it exports — claim confirmed.** `README.md` lists `EXPORT JSON` (the full raw event
array) and `EXPORT Markdown` ("readable play-by-play transcript with turn/phase headings
when the site emits structural markers"), plus a per-game filterable log and sideboard
In/Out tracking.

**How it captures — materially different from the plan's description.** It reads the
**site's own session log out of page storage**, not the network:

> the site's session log is truncated at ~4 KB when mirrored to disk; the extension reads the
> real storage values in the page and reproduces the complete event stream.

`extension/src/lib/parser.js` confirms the shape it consumes: entries are recognised by
`typeof value.gameId === "string"` plus a `sequenceNumber`, i.e. **`GAME_EVENT` payloads
only**. It groups by `gameId` and marks a game complete on `GAME_OUTCOME`.

The only network observer, `extension/src/content/net-observer.js`, matches `/\/batch/i` on
`fetch` and `XMLHttpRequest` and extracts nothing but `body.cards[].name` — this is the card
resolution call (`/api/public/v1/cards/batch`), used to infer sideboard changes. **There is
no WebSocket hook anywhere in the repository.**

**Post-hoc only: yes.** It diffs stored events against a per-game `lastSeen` sequence number
and the popup polls every 10 s. There is no board state, no `pendingAction`, and no outbound
action capture. It cannot drive a controller.

**Maturity.** Its own README: "25/28 tasks done. The last three tasks (6.1–6.3) are manual
live-site verifications that need a human in a browser." Those verifications were never
done — the repo has not been touched since the day it was created.

**Confidence: High** for all of the above (source read directly).

---

## Q3 — Does Endstep enumerate legal actions, or only accept UI-level intents?

**Verdict: Endstep enumerates legal actions server-side and sends them to the client, per
decision point, including which abilities of each card are currently playable and what they
cost. The controller does not need to derive legality. This refutes the plan's central
technical risk.**

This was flagged as the single most important question, so the evidence is given in full
from three independent sources.

### Evidence 1 — First-party architecture statement

<https://endstep.cc/about>:

> Every card in Endstep resolves through Forge, the long-running open-source Magic rules
> engine, running headless on our server. The browser is a window onto that engine: it shows
> you what the engine says and sends back what you clicked. **It does not know the rules, and
> it is not allowed to guess at them.**

A client that is structurally forbidden from knowing the rules cannot be computing legality
locally. Legality must therefore arrive from the server. (Content rephrased for compliance
with licensing restrictions where not quoted.)

### Evidence 2 — The live `GameView` bundle

`https://endstep.cc/assets/GameView-CnGLK8j9.js` (528 KB, fetched 2026-11-20). The priority
prompt handler:

```js
let n = W.cardOptions?.find(t => t.id === e.id)?.playableAbilities;
return !n || n.length <= 1
  ? (Q({ type: `PLAY_CARD`, cardId: e.id, abilityIndex: void 0, autoPassAfter: … }), …)
  : (Sn(e), En(t), false);   // more than one ability → open the ability picker
```

and the ability picker itself:

```js
W?.type === `PRIORITY` && (() => {
  let t = W.cardOptions?.find(t => t.id === e.id)?.playableAbilities;
  return !t || t.length < 2 ? null : jsx(_f, { card: e, point: wn, abilities: t,
    onPlay: t => { … Q({ type: `PLAY_CARD`, cardId: e.id, abilityIndex: t, … }) } });
})()
```

Each `playableAbilities` entry has `{ index, description, cost }` — the log formatter reads
all three:

```js
let i = (t?.type === `PRIORITY` ? t.cardOptions?.find(t => t.id === e.cardId) : void 0)
          ?.playableAbilities?.find(t => t.index === e.abilityIndex),
    a = i && (i.description || i.cost) || ``;
```

So the server tells the client, for every object it may act on: its id, its zone, and the
indexed, described, costed list of abilities that are **currently playable**. `CHOOSE_MODE`
prompts likewise carry `modeOptions[{ index, description }]`, and options carry a
`declinable` flag. Prompts also carry `contextCards`/`contextType`/`sourceCardName`.

### Evidence 3 — Captured wire traffic in Endstep-Tracker

`test/replay.test.js` contains real `pendingAction` objects:

```js
pendingAction: { type: 'PRIORITY',
  message: 'Choose a spell or ability to play, or pass priority',
  cardOptions: [ { id: 29, name: 'Lightning Bolt', zone: 'Hand' },
                 { id: 11, name: 'Mountain', zone: 'Hand' } ], min: 0, max: 0 }
pendingAction: { type: 'DECLARE_BLOCKERS', message: 'Declare blockers',
  cardOptions: [ { id: 65, name: 'Goblin Guide', zone: 'Battlefield' } ] }
pendingAction: { type: 'CHOOSE_TARGETS', message: 'Select any target',
  cardOptions: [ { id: -1, name: 'guest_rZ8gWdWE', zone: 'Player' },
                 { id: -2, name: 'Forge AI', zone: 'Player' },
                 { id: 65, name: 'Goblin Guide', zone: 'Battlefield' } ] }
```

Players appear as options with negative ids. The tracker's own test asserts the
behaviour a controller depends on: *"passing with a playable option is a decision"* vs
*"passing with nothing to do is not"* — i.e. `cardOptions` being empty is a reliable signal
that there is genuinely nothing to do.

### The prompt and action taxonomy

Prompt (`pendingAction.type`) values present in the live bundle: `PRIORITY`,
`DECLARE_ATTACKERS`, `DECLARE_BLOCKERS`, `CHOOSE_TARGETS`, `CHOOSE_CARDS`, `CHOOSE_ABILITY`,
`CHOOSE_MODE`, `CHOOSE_COLOR`, `CHOOSE_NUMBER`, `CHOOSE_TYPE`, `CHOOSE_CARD_NAME`,
`CHOOSE_MANA`, `CHOOSE_PILE`, `YES_NO`, `MULLIGAN`, `MULLIGAN_SPECIAL`, `KEEP_HAND`, `SCRY`,
`ASSIGN_DAMAGE`, `DIVIDE_SHIELD`, `PAY_MANA`, `PAY_LIFE_PHYREXIAN`, `ARRANGE_CARDS`,
`ORDER_ABILITIES`, `ORDER_ATTACKERS`, `ORDER_BLOCKERS`, `NOTIFY_VALUE`, `COIN_FLIP`.

Outbound `GAME_ACTION` payload types: `PLAY_CARD` `{cardId, abilityIndex, autoPassAfter}`,
`PASS_PRIORITY`, `CHOOSE_TARGETS` `{targets:[]}`, `DECLARE_ATTACKERS` `{attackers:[]}`,
`DECLARE_BLOCKERS` `{blockers:{attackerId: blockerId}}`, `CHOOSE_CARDS` `{orderedCards:[]}`,
`CHOOSE_ABILITY`, `CHOOSE_MODE`, `CHOOSE_COLOR`, `CHOOSE_NUMBER`, `TAP_MANA`, `AUTO_PAY`,
`USE_FLOATING_MANA`, `UNDO`, `CONCEDE`, `CONCEDE_MATCH`, `SIDEBOARD_SUBMIT`,
`SIDEBOARD_WITHDRAW`, `DECLINE`, `SET_PHASE_STOPS`, `SET_AUTO_YIELDS`,
`CLEAR_REMEMBERED_ORDERS`, `ADD_LOG`, `MACRO`, `LOOP_SHORTCUT`, `ROLLBACK`, `CHEAT`.

Transport envelope, from `useWebSocket-C1JXB7OH.js`: `{ type: "GAME_ACTION", payload: {
matchId, actionId, type, promptVersion, … } }`. The client keeps an `inflight` map keyed by
`actionId`, attaches `promptVersion` to every action except a settings allow-list
(`SET_PHASE_STOPS`, `SET_AUTO_YIELDS`, `CLEAR_REMEMBERED_ORDERS`, `CHEAT`, `CONCEDE`,
`CONCEDE_MATCH`), and handles `ACTION_REFUSED` / `ACTION_ERROR` with an optional
`retryOnMain` resend. Session frames include `HELLO`, `PING`/`PONG`, `REAUTH`/`REAUTH_OK`,
`AUTH_REFRESH_NEEDED`, `RESYNC`, `ROLLBACK`, `CLIENT_RELOAD`, `SERVER_SHUTDOWN`,
`GAME_ATTACH`, `GAME_ATTACH_TICKET`, `GAME_ATTACH_STATE`.

### Caveats (inference, not fact)

- Enumeration is at **(object, ability-index)** granularity. Targets, modes, numbers and mana
  payments are resolved by **subsequent prompts** (`CHOOSE_TARGETS`, `CHOOSE_MODE`,
  `PAY_MANA`), not pre-expanded into a flat cross-product of complete actions. A controller
  must therefore model a small prompt state machine — a day or two of work, not a rules
  engine. The plan's illustrative flat `legal_actions` array is not the real shape.
- `AUTO_PAY` exists, so mana payment can usually be delegated to the server rather than
  solved.
- `promptVersion` must be echoed back or actions risk refusal; this is the main correctness
  trap.

**Confidence: High.** Three independent sources agree, two of them the live production
bundle and the vendor's own architecture statement.

---

## Q4 — Terms of service and policy on automation, bots, multiple accounts, bulk play

**Verdict: A Terms of Service exists. It contains no rule about bots, automation, scripted
clients or bulk play. Multiple accounts are prohibited only for sanction evasion. The
clauses that could be applied to an agent are discretionary.**

### Evidence

`/terms` is client-rendered, so it is not fetchable as HTML. The text lives in
`https://endstep.cc/assets/TermsPage-Gp5VJjRW.js`, read 2026-11-20. Sections:
`agreement`, `age`, `account`, `conduct` ("Rules"), `content`, `moderation`, `tournaments`,
`supporters`, `ip`, `service`, `liability`, `ending`, `changes`, `contact`. A sibling date
constant in `main.js` reads `12 November 2026`, and the public changelog mentions "finished
terms of service and privacy policy", so the document is recent and current.

The complete **Rules** section, verbatim:

> - **Be decent.** No harassment, threats, hate speech, sexual content, or sharing someone's personal information, in chat, names, pictures, decks or anywhere else.
> - **Nothing illegal.**
> - **Don't stall on purpose.** Taking time to think is fine.
> - **Don't abandon matches.** Leaving or idling out forfeits and can start a matchmaking cooldown.
> - **Don't fix results.** No win trading or arranged outcomes.
> - **Don't cheat.** Don't use bugs or tools to see hidden information or gain an unfair advantage. Report bugs instead.
> - **Don't dodge a sanction,** including with another account.
> - **Don't attack the service.** No flooding it with traffic, and no getting around its rate limits.
> - **No spam or impersonation.**

Reading each of the asked-about topics against that text:

| Topic | Policy |
| --- | --- |
| Bots / automation / scripted clients | **No policy. Not mentioned anywhere in the ToS.** |
| Multiple accounts | Prohibited **only** for sanction evasion ("Don't dodge a sanction, including with another account"). No general ban on alts. |
| Bulk play | **No policy.** The nearest constraint is "no flooding it with traffic, and no getting around its rate limits". |
| Hidden information | Explicitly prohibited: "Don't use bugs or **tools** to see hidden information or gain an unfair advantage." |
| Rate limits | Explicitly protected. Circumventing them is a ToS breach. |

Enforcement, from the **Moderation** section:

> If you break these rules or the law, we may remove content, warn you, mute you, restrict
> matchmaking, adjust ranked results, remove you from a tournament, or suspend or ban your
> account. Some limits are automatic (rate limits, idle forfeits, matchmaking cooldowns);
> moderators decide the rest. We keep a record of past breaches, so repeated breaches get
> stronger responses, and a serious breach, or repeated or combined ones, can lead to a
> permanent ban.

The **Service** section disclaims any stability guarantee:

> Endstep is free to play and provided as it is. Features can change, and the service can
> pause or end. Games can be lost to an outage or an update, and ratings can be corrected.

Also relevant: Endstep is an unofficial Wizards of the Coast Fan Content project, run by one
developer, funded by [Patreon](https://www.patreon.com/endstep), with no paid tier and no
advertising (`/about`). `robots.txt` disallows `/api/`. A contact address,
`contact@endstep.cc`, is in the bundle.

### Interpretation (inference, clearly separated)

A single agent playing at human pace through the real client is not prohibited by any clause
I can find. The exposure is that "tools to … gain an unfair advantage" is open-ended and
decided by moderators, not by a published automation rule, and a first-time breach can
escalate to a permanent ban. Volume self-play, deck A/B experiments across many games, and
anything that needs more throughput than a person would generate run into "no flooding it
with traffic, and no getting around its rate limits" — which *is* explicit. The absence of a
bot policy is not permission; it means there is no safe harbour and no appeal grounded in
text. The only way to get certainty is to ask the developer at `contact@endstep.cc`.

Endstep-Tracker's `docs/DEVELOPMENT.md` reports a limit of **300 requests per minute** on
the metagame API and describes backing off on `429` and honouring the `Retry-After` on `503`.
That figure is a third-party observation about one endpoint, not published policy, and should
not be assumed to apply to gameplay traffic.

**Confidence: High** that the ToS text is as quoted and that no automation clause exists
(full section read verbatim). **Low** on how the operator would actually treat an agent —
that is unknowable from documents.

---

## Q5 — Replay downloads

**Verdict: Replays exist and are downloadable, but they are a per-account gradual rollout —
NOT enabled by default — and cannot be recovered retroactively.**

### Evidence

The public changelog (<https://endstep.cc/changelog>), entry "Replays and combo shortcuts:
gradual rollout":

> When replay recording is enabled for your account, History → Replays lets you revisit
> recorded games from your own seat, jump between decisions and download a replay to keep.
> Earlier games cannot be recovered retroactively. … These features are early. Expect rough
> edges.

From `main.js`:

- Routes: `/replays`, `/replay/:id`, `/replay/local`, plus staff routes
  `/admin/reports/:reportId/replay` and `/admin/tournaments/:tournamentId/issues/:reportId/replay`.
- Chunks: `ReplayView-Bxnhpx-h.js`, `ReportReplaySection-D165K6J_.js`, `reportReplays-B3UR_YzK.js`.
- Access is gated on a server-reported quota: `Ci = { all: ['replays'], page: e => ['replays','page', e ?? 'latest'], quota: ['replays','quota'] }`, and availability is
  `wi().data?.available === true`.
- Feature flags `features.replays.preview` and `features.replays.configure` exist, scoped
  `global`.
- Download: chunked fetch with an `onProgress` callback and a `too_large` error, assembled
  into a `Uint8Array`, then `new Blob([bytes], { type: 'application/gzip' })` saved as
  `endstep-replay.esreplay`.

**Format:** `.esreplay`, a gzip container. Its internal structure is **not determinable from
the client bundle** — the client streams the bytes to disk without parsing them, and the
viewer loads replays through the API rather than by decoding a local file. `/replay/local`
suggests a locally-loaded replay is supported, which implies the format is parseable
client-side, but I could not locate the decoder. **Could not verify** the on-disk schema.

**Contents:** seat-scoped — "from your own seat", with decision-level navigation. Consistent
with a separate changelog note that on reconnect "You only get back what was sent to you
originally, so a card revealed privately to your opponent stays private." So a replay should
contain the same information the seat saw live, not a god's-eye view.

**Enabled by default: no.** "When replay recording is enabled for your account" plus a
quota-with-`available`-flag gate plus "gradual rollout" all point to per-account
enablement. A pipeline must not depend on replays being present.

**Confidence: High** on existence, gating and container format. **Low/none** on internal schema.

---

## Q6 — Practical automation path with Playwright, and anti-automation measures

**Verdict: Technically workable, and the proven approach is not the one the question
assumes. Playwright can read Endstep's WebSocket frames reliably, but injecting actions is
better done by proxying `window.WebSocket` in an init script than by Playwright's WebSocket
routing. Cloudflare fronts the site and Cloudflare Turnstile is wired into the login form;
I found no evidence of gameplay-level bot detection.**

### Playwright's documented capabilities (with versions)

Latest Playwright for Python is **1.65.2** (PyPI, checked 2026-11-20).

**Reading frames — fully supported, read-only.**
[`class WebSocket`](https://playwright.dev/python/docs/api/class-websocket): events
`on("framesent")`, `on("framereceived")`, `on("socketerror")` — all **added in v1.9**;
`url` and `is_closed()` added before v1.9. Frame data is `str | bytes`. The docs are explicit
about the limit: "If you want to intercept or modify WebSocket frames, consider using
WebSocketRoute." So this API observes but cannot alter or inject.

**Intercepting/injecting — supported since v1.48.**
[`class WebSocketRoute`](https://playwright.dev/python/docs/api/class-websocketroute) via
`page.route_web_socket()` / `browser_context.route_web_socket()`. `send`, `close`,
`on_message`, `on_close`, `connect_to_server`, `url` all **added in v1.48**; `protocols`
**added in v1.60**. Documented semantics and limits that matter here:

- "By default, the routed WebSocket will not connect to the server" — you must call
  `connect_to_server()` or you have mocked the whole connection by accident.
- Once `on_message()` is called on a side, **automatic forwarding for that direction stops**
  and the handler must forward manually. Miss a message type and the client silently breaks.
- Known defects at introduction: modifying a message can close the connection
  ([#33063](https://github.com/microsoft/playwright/issues/33063)); full URLs were not matched
  by the route pattern ([#33085](https://github.com/microsoft/playwright/issues/33085)).

### Recommended approach (inference, grounded in the tracker's proven technique)

Do **not** use `route_web_socket` for this. It puts Playwright in the middle of a protocol
with ticket-based attach, `seq` ordering, `promptVersion` concurrency and `inflight`
bookkeeping, where one dropped frame desynchronises the real client.

Instead replicate Endstep-Tracker's approach, which is shipped and demonstrably works:
`page.add_init_script()` to install a `Proxy` over `window.WebSocket` at document start
(exactly `hook.js`), keep a handle to the live socket, pipe frames out to Python via
`page.expose_binding()`, and inject actions with `page.evaluate()` calling `ws.send()` on the
captured socket. The real client keeps doing auth, tickets, reconnect and resync; the
controller only reads `pendingAction` and writes `GAME_ACTION`.

Two correctness requirements for injection, both evidenced in Q3: echo the current
`promptVersion`, and handle `ACTION_REFUSED` / `ACTION_ERROR` / `ROLLBACK`. A lower-risk
variant for a first prototype is read-via-WebSocket, act-via-UI-clicks — slower, but the
client's own bookkeeping stays authoritative.

A third option exists and is worth naming: the protocol is plain JSON over
`{origin}/ws?…&ticket=…` with per-game attach tickets, so a **headless Python client with no
browser at all** is architecturally possible. It would require reimplementing `HELLO`,
`PING`/`PONG`, `REAUTH`, `GAME_ATTACH_TICKET`, `seq` resync and `ROLLBACK`. It is also the
variant most unambiguously describable as a "scripted client", which bears on Q4.

### Anti-automation evidence found

| Measure | Evidence | Assessment |
| --- | --- | --- |
| Cloudflare | Response headers on `https://endstep.cc/`: `server: cloudflare`, `cf-ray: a5d66ea4ec2a3f5c-SIN`, `cf-cache-status: HIT`, `report-to` with a `cf-nel` group | Present. Standard CDN/WAF posture; no managed challenge observed on normal GETs. |
| Cloudflare Turnstile | `main.js` loads `https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit` and renders a widget `{ siteKey, resetKey, onToken, onProblem }` conditionally inside the login form, with the site key fetched from the server | A CAPTCHA gate exists on the credentialed login path and is server-toggleable. |
| Auth requirement | `robots.txt`: "The app itself is an auth-gated SPA: `/` draws Sign in for a signed-out visitor … the other app routes redirect to /login and hold no public content." | Confirmed. All game routes need a session. |
| Auth methods | `main.js`: "Sign in with Discord", plus a "Play as a guest" button calling a separate endpoint. Captured traffic shows a `guest_rZ8gWdWE` username | Discord OAuth or guest. The guest path appeared not to render the Turnstile widget, though the gate is server-conditional. |
| Rate limits | ToS: "no getting around its rate limits". `429` and `503`-with-`Retry-After` handling reported in Endstep-Tracker's dev docs (300 req/min on the metagame API) | Real and ToS-protected. |
| CSP | `content-security-policy: default-src 'self'; script-src 'self' https://static.cloudflareinsights.com; … connect-src 'self' https://api.scryfall.com https://cloudflareinsights.com ws: wss:` | Note `script-src` does **not** list `challenges.cloudflare.com`, so Turnstile may currently be inactive or the CSP differs on `/login`. Not resolved. |
| Gameplay bot detection | None found | No fingerprinting, no behavioural checks, no automation-detection code located in the bundle. A `wsLikelyBlocked` flag exists but reads as a network diagnostic for users behind restrictive proxies, not bot detection. |

**Confidence: High** on Playwright's API surface and versions (official docs) and on the
Cloudflare/Turnstile/auth facts (live headers and bundle). **Medium** on the recommended
injection approach — the technique is proven for *reading* by a shipped extension, but I
found no public example of anyone successfully *writing* `GAME_ACTION` frames, so the
`promptVersion`/`inflight` interaction is untested inference.

---

## Q7 — Does any public project *play* Endstep or Forge programmatically?

**Verdict: No public project plays Endstep. Several play Forge, and one of them is close
prior art for exactly this plan.**

### Nothing plays Endstep

The only two public Endstep integrations are the read-only recorders in Q1 and Q2. A third
Endstep-adjacent repository exists and is first-party:

- **<https://github.com/Neur0nz/endstep-forge-patches>** (GPL-3.0, created 2026-07-14) —
  "Quilt-style patch series for the Card-Forge/forge MTG engine … maintained by
  [Endstep](https://endstep.cc) — a fully online Magic: The Gathering platform that **runs
  Forge headless as its rules engine**". It describes itself as a downstream mirror of
  `forge-service/patches/` in "the Endstep monorepo", where the patches "co-evolve with the
  engine bridge". This independently confirms the Forge backend and that the WebSocket
  protocol is a bespoke bridge layer, not a Forge-native protocol — so Forge's own
  client/server protocol is **not** a usable reference for Endstep's wire format.

Separately, Endstep-Tracker's `docs/DEVELOPMENT.md` describes a dev-only "Coach" in a
**private** repo `Endstep-coach`, with a `bot/` directory "pour Forge, le serveur local,
l'entraînement" (for Forge, the local server, training). It evaluates decisions after the
fact and is explicitly stripped from all store builds; it does not play. Not public, so not
assessable.

### Projects that play Forge

- **<https://github.com/lumlaolao/spike-eval>** (GPL-3.0, Python, created 2026-07-10, updated
  2026-11-11) — the closest prior art by a wide margin. "A harness that lets language models
  play Magic: The Gathering… Models take a player's seat in Forge… and play against a person,
  Forge's built-in AI or another model." Its design notes read as a list of lessons this
  project would otherwise learn the hard way:
  - "**Answers are tool calls.** Each decision is answered by filling in a form with fixed
    fields. Nothing is read out of the model's own thinking."
  - "**Full game state.** … It also **lists every legal action the engine allows, so an
    illegal move is impossible**." (Independent confirmation of the Q3 finding, at the Forge
    level.)
  - "**Ids for every object, and a game log.** Each object gets an id like `@67` that stays
    the same until it changes zones."
  - "**No hidden fallback to Forge's AI.** If a model fails to make a choice, a default legal
    option is taken and it is marked in the log."
  - It also reports that win-counting is a poor eval — "Magic has a lot of luck in it, and
    decks beat each other like rock, paper, scissors, so a win rate says more about the draw
    and the decks than about the model" — and uses fixed puzzles instead. That bears directly
    on the plan's deck-optimisation loop. Write-up: <https://folds.ink/posts/mtg-benchmark>.
- **<https://github.com/hubertdungen/grimorio>** (GPL-3.0) — self-hosted deck testing with
  "real AI-vs-AI games (Forge)".
- **<https://github.com/KoalaTrapLord/commander-ai-lab>** — "rules-complete simulation (Forge
  + Monte Carlo), LLM deck builder with sim-driven feedback".
- **Forge itself ships headless batch play.** `Card-Forge/forge` `docs/AI.md`: "`sim` —
  'Simulation Mode' forces Forge to not start the GUI and automatically runs the AI matches in
  command line." Community-documented usage: `forge.exe sim <deck1> <deck2> [N]` where `N` is
  the number of games; `SimulateMatch.simulate(args)` is callable from Java.

Other LLM-and-MTG projects exist but do not use Forge: `GregorStocks/mage-bench`,
`taoroalin/mtg-llm`, `witchesofthehill/manabrew` (Rust rewrite of Forge, WebAssembly client),
`wingedsheep/argentum-engine` (own engine, with `gym-server`/`gym-trainer`).

**Confidence: High.** Repositories and the Forge doc read directly.

---

## Claims from the plan that are false or unsupported

1. **"If legal actions are not enumerated, the controller must derive them, which is a large
   amount of rules work" / "The controller would need to discover and validate these legal
   actions."** — **Refuted.** Endstep sends them. `pendingAction.cardOptions[].playableAbilities[{index, description, cost}]`
   is a server-computed legal-action list per decision point. The controller maps a schema; it
   does not implement rules. This was the plan's largest stated risk and it is not a risk.
2. **"[Endstep Session Reader] can export game logs as JSON and Markdown"** — **True but
   misleading in context.** It reads the site's event log out of page storage, not the
   WebSocket; it captures `GAME_EVENT`-shaped entries only, with no board state and no
   `pendingAction`; and it is a 0-star repo abandoned on its creation day with its three
   live-site verification tasks never done. Listing it beside Endstep-Tracker as a comparable
   integration overstates it.
3. **"These are read-only integrations, though; executing actions still needs to be solved
   separately."** — **Half true, and it understates what is already known.**
   Endstep-Tracker's shipped builds are read-only, but its dev-only code path intercepts
   outbound `GAME_ACTION` frames and its test suite asserts against real captured ones. The
   complete action schema, including `promptVersion`, `actionId` and every payload type, is
   public today. Execution is unsolved only in the sense that nobody has published a writer.
4. **The illustrative `legal_actions` JSON.** — The plan correctly labels it unverified. For
   the record the real shape differs: ids are numeric engine card ids (negative for players),
   actions are `{type, cardId, abilityIndex, promptVersion}`, and targets/modes/mana are
   resolved by follow-up prompts rather than pre-expanded into flat actions.
5. **Replays as a dependable recorder input.** — **Unsupported.** The plan's "Match Recorder
   … and replays" assumes availability. Replays are a per-account gradual rollout, not
   retroactive, and explicitly "early. Expect rough edges."
6. **"I wouldn't use Endstep for unlimited agent-vs-agent training."** — **Correct, and
   stronger than stated.** Beyond politeness, the ToS explicitly forbids traffic flooding and
   rate-limit circumvention, there is no bot-authorisation path, and Endstep fills seats with
   Forge's own AI anyway — so agent-vs-agent volume on Endstep is both prohibited-adjacent and
   unnecessary.
7. **Not assessed:** the claims about `codex exec --json` token accounting versus Kiro CLI
   were outside this investigation's brief and were neither verified nor refuted.

Claims that **held up**: Endstep is Forge-based (first-party confirmed); Endstep-Tracker
exists and observes `GAME_STATE`/`GAME_DELTA`/`GAME_EVENT` over WebSocket; structured state
can be fed to the LLM instead of screenshots; separating controller from pilot is the right
architecture and is what the one comparable public project also does.

---

## Blockers and unknowns for the controller

Ordered by how much risk each removes per unit of effort. The first item is a decision, not
code, and it gates the rest.

### Must be resolved before building

1. **Get a ruling from the operator.** Email `contact@endstep.cc`, describe the agent, the
   intended volume, and whether it will play ranked or only private tables and bot games. The
   ToS has no automation clause, so there is no safe harbour to rely on and no textual basis
   for appeal after a ban. This is a short email that converts the project's largest
   unquantified risk into a known one. **Blocker.**
2. **Decide the venue, and consider inverting it.** Every comparable public project drives
   local headless Forge, and `spike-eval` already does so with an LLM in the seat. Local Forge
   gives unlimited games, no ToS exposure, no Cloudflare, deterministic seeds, and real
   agent-vs-agent self-play — everything the learning loop and deck-optimisation loop in the
   plan actually need. Recommendation: **build the controller against local Forge first**, and
   add Endstep later as an optional "play real humans" adapter behind the same interface. The
   `pendingAction`/`GAME_ACTION` shape mapped above makes a good common abstraction precisely
   because Endstep's bridge is a thin layer over Forge's own prompt model.
3. **Hard-exclude the hidden-information leak.** `/api/matches/<uuid>` returns a server-side
   state fingerprint that includes the opponent's hidden hand (per Endstep-Tracker's own
   source comment). Any Endstep adapter must whitelist fields from this endpoint explicitly,
   and a test must assert the opponent's hand never reaches the pilot. Using it would breach
   "Don't use bugs or tools to see hidden information" and is the fastest route to a
   permanent ban.

### Prototype in this order to de-risk

4. **Read-only frame capture.** Playwright init script proxying `window.WebSocket`, logging
   `GAME_STATE` / `GAME_DELTA` / `GAME_EVENT` / `pendingAction` to disk through one bot game.
   Validates auth, Turnstile, Cloudflare and the guest path in one shot. Low risk — this is
   exactly what a shipped extension already does.
5. **Write one action.** Inject a single `PASS_PRIORITY` with the correct `promptVersion` and
   confirm no `ACTION_REFUSED`. **This is the main unknown in the whole plan.** Everything
   else is documented; nobody has published a writer. Do it in a private table or against a
   bot, never ranked.
6. **State reconstruction and `GAME_DELTA` patching.** Build the board model from
   `GAME_STATE`, apply `GAME_DELTA` against `baseSeq`, and reconcile with the next full
   `GAME_STATE`. Then force an `ATTACH` (reload mid-game) and confirm recovery. The tracker's
   `test/replay.test.js` is a ready-made fixture and documents the ordering hazards it already
   found: duplicate frames, a game-2 reset state arriving *before* game 1's `GAME_OUTCOME`,
   and cancelled casts that emit a `CARD_ZONE_CHANGE` to `Stack` but no `SPELL_CAST`.
7. **The prompt state machine.** Walk one real game and record which prompt types actually
   occur for a Mono-Red Pauper deck. Likely a small subset: `PRIORITY`, `CHOOSE_TARGETS`,
   `DECLARE_ATTACKERS`, `DECLARE_BLOCKERS`, `MULLIGAN`/`KEEP_HAND`, `YES_NO`, `PAY_MANA`
   (probably avoidable via `AUTO_PAY`), `ORDER_BLOCKERS`, `ASSIGN_DAMAGE`. Handle those;
   default-with-logging on the rest, following `spike-eval`'s "no hidden fallback" rule.

### Known unknowns to track

- **`.esreplay` internal format.** Not determinable from the client bundle. Do not plan to
  parse replays; derive match records from the live frame stream, as Endstep-Tracker does.
- **Whether replay recording can be enabled on a given account.** Gradual rollout, quota-gated.
- **Protocol stability.** `protocolVersion: 1` is the only signal; the bridge "co-evolves"
  with Endstep's private monorepo. Expect breakage. Pin a captured fixture set and assert
  against it, so a protocol change fails a test instead of a match.
- **Whether `CHEAT` is reachable by non-staff.** It appears in the action allow-list and in
  `GameView`, exempted from `promptVersion`. Almost certainly staff/dev-gated. Do not probe
  it on the live service; probing it is the kind of thing the ToS cheating clause exists for.
- **Whether Turnstile fires on the guest login path.** The gate is server-conditional and the
  CSP does not currently whitelist `challenges.cloudflare.com`. Resolved cheaply by step 4.
- **Multiplayer/pod and `MACRO`/`LOOP_SHORTCUT` semantics.** Out of scope for a 1-v-1
  Mono-Red agent; ignore.

---

## Sources

Live Endstep (fetched 2026-11-20): <https://endstep.cc/about>,
<https://endstep.cc/changelog>, <https://endstep.cc/robots.txt>, response headers on
`https://endstep.cc/`, and the bundles `/assets/main-B6GR5ONd.js`,
`/assets/GameView-CnGLK8j9.js`, `/assets/useWebSocket-C1JXB7OH.js`,
`/assets/TermsPage-Gp5VJjRW.js`.

GitHub (via API): <https://github.com/mcouzinet/Endstep-Tracker> (`hook.js`, `content.js`,
`tracker.js`, `manifest.json`, `docs/DEVELOPMENT.md`, `test/replay.test.js`),
<https://github.com/MattNot/endstep-session-reader> (`README.md`,
`extension/src/content/net-observer.js`, `extension/src/lib/parser.js`),
<https://github.com/Neur0nz/endstep-forge-patches>,
<https://github.com/lumlaolao/spike-eval>,
<https://github.com/Card-Forge/forge/blob/master/docs/AI.md>.

Playwright: <https://playwright.dev/python/docs/api/class-websocket>,
<https://playwright.dev/python/docs/api/class-websocketroute>, PyPI `playwright` 1.65.2,
Playwright issues [#33063](https://github.com/microsoft/playwright/issues/33063) and
[#33085](https://github.com/microsoft/playwright/issues/33085).

Content from third-party sources was paraphrased or briefly quoted for compliance with
licensing restrictions.
