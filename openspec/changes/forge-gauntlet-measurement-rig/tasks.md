# Tasks

Authorized revision 2026-11-21: CLI-piloted Standard learning MVP. Historical checked tasks and Donate/throughput work remain in Git history. These checkboxes track the revised acceptance contract. Parent owns checkboxes; workers own disjoint paths.

## 1. Foundations and decision contract

- [ ] 1.1 Reconcile engine/source/patch/jar identity and preserve interrupted work in focused commits; verify installed validation checks and source identity without discarding changes
- [ ] 1.2 Pin the reused adapter and establish Forge compatibility; verify its build and document pins, provenance, licenses and launch command
- [ ] 1.3 Implement v1 decision/answer envelopes with engine-owned schemas; verify seat/revision/action rejection and duplicate-action idempotence

## 2. Standard deck profiles

- [ ] 2.1 Source Izzet aggro/prowess 60+15 plus profile, sideboard guide and source manifest; verify three-source legality, counts and claim-level URLs or inference labels
- [ ] 2.2 Source aggressive landfall 60+15 plus profile, sideboard guide and source manifest; verify legality/counts, provenance and video/transcript access labels
- [x] 2.3 Validate proposed sideboard exchanges against frozen lists; verify present cards, equal in/out counts, postboard legality and inferred-matchup labels

## 3. Rules-engine external seats

- [ ] 3.1 Implement both external seats and private observations; verify opponent hand/library/faces absent and authorized reveals visible
- [ ] 3.2 Route every reachable non-forced choice to the bridge and fail closed otherwise; verify ownership/API-drift checks and zero strategic AI/default choices in a scripted game
- [ ] 3.3 Journal accepted actions and structured outcomes under full identities; verify per-decision completeness and scripted winner/turn replay
- [ ] 3.4 Support external-pilot sideboarding; verify a selected legal main/sideboard exchange reaches the next game's configuration
- [ ] 3.5 Document and test interruption/reconstruction; verify the same pending decision restores or divergence is refused, with no duplicate move

## 4. Persistent CLI pilots

- [ ] 4.1 Implement two persistent authenticated Codex seats and per-turn structured output; verify fake-RPC lifecycle tests plus actual isolated session smoke without per-move restart
- [ ] 4.2 Enforce filesystem/tool/memory isolation; verify actual sibling/referee read denial and audit the advertised tool surface
- [ ] 4.3 Validate and relay exact decision identities; verify invalid/stale/duplicate/unsupported answers cannot mutate the game
- [ ] 4.4 Pause and reconnect on quota/transport/schema failure; verify no fallback/clock loss and injected response-loss recovery without duplicate moves
- [ ] 4.5 Add external-pilot run/resume/report commands and docs; verify fresh-shell commands and distinguish the legacy AI runner

## 5. Learning and review

- [ ] 5.1 Record decision-time evidence and freeze profile versions during a match; verify non-forced actions identify model/profile and seat memory isolation
- [ ] 5.2 Produce a versioned tentative lesson with decision reference, known information, alternative and test; verify evidence omissions refused and old versions preserved
- [ ] 5.3 Load a revised profile next game and test its lesson in a controlled replay; verify changed choice and expected rules result without win/loss-only claims

## 6. Integration acceptance

- [ ] 6.1 Run one actual complete Standard two-CLI game; verify all strategic choices model-attributed, legal actions, private views and complete structured result/journal
- [ ] 6.2 Exercise real pilot sideboarding into game two and reproduce a stored game; verify deck exchange, profile versions and replayed winner/turn count
- [ ] 6.3 Exercise interruption/resume and reviewed learning across games; record evidence and limits in docs/cli-pilot-acceptance.md with no fabricated fallback moves or quality claims

## Workflow follow-up

- Review acceptance evidence before archiving. Kiro ACP, Donate, optimization, weight training and throughput evaluation are later work.
