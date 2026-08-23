# Gravita GTM

Outcome-orchestrated B2B demand generation platform.

Hermes-patterned conversational sessions, governed multi-agent triggers,
cloud-hosted Obsidian vault as the semantic layer, dry-run first.

## What it is

A platform you deploy and run — not a SaaS you subscribe to. It puts a small
governed team of AI employees inside your workspace, all reading from and
writing back to one shared Obsidian vault you own and read, all governed by
Hermes Core (the trigger registry, the approval gate, the permission layer,
the rulings store, the audit log, the agent lifecycle), and all exposed
through the conversational surface you already use.

Nothing sends, publishes, or spends without your approval.

## What it is not

- Not a SaaS. You deploy it.
- Not a workflow builder with a canvas. Workflows are expressed as sentences
  and governed specs.
- Not an autonomous sender. The gate is structural.
- Not a replacement for your CRM, sequencer, payment processor, or content
  platforms. It reads them, drafts in them, governs them.
- Not a single-tool dependency. The harness contract (GHC) is the boundary;
  the runtime, the execution adapter, the model, the tools are all swappable.

## Architecture

Gravita GTM ships as three sequential phases. The repo is the platform
behind all three. Phase 1 and Phase 2 are already real and committed;
Phase 3 is the step you take when you're ready to connect and pay.

### The three phases, and what "done" looks like per phase

**Phase 1 — backend, dry-run.** The real platform. No keys, no money, no
service connected. Phase 1 is the *machine* worth proving end to end before
you spend a dollar: a governed team of AI employees that read your vault, run
your workflows through the four-part skeleton, hold artifacts at the gate,
write back to the vault, and record their reasoning in the audit ledger. You
run it against realisticfake stubs so you can prove the whole loop works
without wiring anything. Phase 1 is done when you can say `run signal-outbound
top_n=20` and the platform resolves the capability + harness, reads the vault
and the stubbed source, produces a research sheet with confidence notes per
row, posts drafts to the pending queue, waits for your yes, writes back to the
vault, and records the trace — and nothing left the machine.

**Phase 2 — UX prep.** Once the machine works, make it show what it does in
a way a human can actually use. This is the conversational surface: the REPL,
the status / dashboard / preview commands, the self-contained HTML preview
(`gravity preview`), the narration that tells each run's story in the image
order. Phase 2 is done when you can boot the platform, run a dry run, see the
pending artifacts with their rows and drafts, approve one, and watch it write
back to the vault — all through a smooth, stunning, Hermes-simple GTM surface.

**Phase 3 — connect and pay for real services.** This is the step you take
*after* Phases 1 and 2 are done. The platform already runs; you're now
replacing stubs with real capabilities behind the same harness, same gate,
same vault, same rulings, same narration. Apache, Clay, your sequencer, Stripe,
your CRM, your content platforms, your ad accounts, your analytics — you
connect them, you pay for them, you wire the tools. The approval gate is
already structural (ASK_FIRST / AUTO_RUN / DISABLED); you're now permitting
real sends / publishes / spends per the risk class and approval mode you set.
Phase 3 is not a build phase in the repo — it's a usage step on top of the
Phase 1/2 platform, and it happens one service at a time, one workflow at a
time, after you've decided what to connect.

### Why the repo is "only Phase 1" (and why that's the point)

The repo isn't only Phase 1 — it contains Phase 1 (the backend mechanics +
stub data) and Phase 2 (the UX surface), and it is ready to receive Phase 3
when you are. The confusion usually comes from reading "Phase 1" in the
README and assuming the whole repo is Phase 1. It isn't:

- The **machine** (Core, GHC, registry, compiler, adapter, runners, vault,
  gate, audit, rulings, narration) is real and end-to-end — that's Phase 1.
- The **surface** (CLI, UI, dashboard, preview, narrations) is real and
  committed — that's Phase 2.
- The **data and outbound actions** are stubbed by design — that's
  Phase 1 dry-run data feeding Phase 3 when you connect real services.
- Phase 3 itself is not yet in the repo because it's a *pay and connect* step,
  not a *build the platform* step. The platform is built for Phase 3: the
  harness, the gate, the vault, the rulings, the narration, the write-back —
  all of it is already there, waiting for you to swap stubs for real connectors
  one at a time.

Three-phase order is the platform's operating principle and the user's explicit
instruction: build the machine (Phase 1), make it showable (Phase 2), then
connect and pay (Phase 3). You don't wire Apollo / Clay / Stripe / your
sequencer / your CRM / your ad accounts into a platform that hasn't yet proven
it can run the four-part skeleton end to end. You prove the machine first, then
you connect and pay for real services one at a time.

### What's in the repo by phase

| Phase | What's here | Real today? |
|-------|-------------|-------------|
| 1 (backend, dry-run) | Hermes Core, GHC, Harness Registry, Compiler, DeterministicAdapter, 3 runners, vault I/O, write-back, artifact model, stubbed sources, narration layer | Machine: yes, end to end. Data: stubbed (realisticfake, deterministic). Outbound: stubbed (nothing sends today). |
| 2 (UX) | CLI (12 commands), ui.py (banner/welcome/help_panel/dashboard/status/preview), `state/gravita-dashboard.html`, narration rendering in CLI/dashboard/HTML | Yes — `make build` green, 79/79 smoke paths pass, dry runs show and approve. |
| 3 (connect services) | Not yet — Phase 3 is the pay-and-connect step. The platform it plugs into (harness/gate/vault/rulings/narration/write-back) is already built. | Not started — happens after Phases 1 and 2 are done, one service at a time. |

### Phase 1 (backend, dry-run) — detail

- Hermes Core — trigger registry, approval gate, permission layer, rulings
  store, audit log, agent lifecycle.
- GHC (Grávita Harness Contract) — the harness is the structural unit. An
  agent is model + harness. The harness owns identity, context, tools, policy,
  budgets, evaluation, observability, lifecycle.
- Harness Registry + Resolver — capability request → approved harness version
  + adapter.
- Runtime adapters — deterministic adapter (Phase 1), later LangGraph/Pydantic
  candidates. The harness contract is the boundary that lets you swap runtimes
  without changing the GOS or the vault semantics.
- Compiler — intent + evidence → harness manifests, runtime plan, capability
  bindings, decisions (risk class, approval mode, allowed sources), validation
  L0–L1.
- Obsidian vault — real markdown on disk, git-backed (cloud backup + version
  history), open locally in Obsidian. The semantic layer. Every agent reads it
  before it writes and writes back to it after it works.
- Stubbed sources — realisticfake Apollo/Clay/Stripe/transcript/posts for
  dry-run artifacts. Phase 3 replaces stubs with real capabilities behind the
  tool gateway.
- Workflows — signal-outbound, money-loop, content-batch (Phase 1). Each is a
  runner that executes the four-part skeleton: trigger → source → artifact →
  gate (PENDING).
- Narration — every run tells its story in the image order (trigger → sources →
  enrichment waterfall → research sheet with confidence notes per row → drafts →
  gate → write-back) plus `rulings_honored` (readable text), stored in
  `state/narration.json` and shown in the CLI / dashboard / HTML preview.

### Phase 2 (UX) — detail

The conversational surface is built and can already show and approve artifacts
from Phase 1 dry runs. Terminal-first for v1.

- `gravity` (no args) — REPL loop.
- `gravity --help` — brand banner + help panel (all 12 commands + examples).
- `gravity run <capability> [params]` — compile + run in one step; parses
  `event='<json>'` for payment-triggered workflows.
- `gravity status` / `gravity dashboard` — live platform state + the last run's
  narration (sources, enrichment waterfall, research sheet rows, drafts, gate,
  rulings honored, write-back).
- `gravity preview` — regenerates `state/gravita-dashboard.html` (dark theme,
  magenta/cyan, live data, Last Run narration section).
- `gravity approve` / `hold` — flip the gate.
- `gravity rulings` / `add-ruling` — the rulings store, one dated line per
  correction, read first by every run, shown in `rulings honored`.
- `gravity query` / `vault` / `sessions` / `new-session` / `watch`.

### Phase 3 (connect services) — detail

You pay, you connect APIs, you wire tools. The platform already runs; you're
replacing stubs with real capabilities. The approval gate is already structural;
you're now permitting real sends/publishes/spends per the risk class and
approval mode you set. Phase 3 happens one service at a time, one workflow at a
time, after you've decided what to connect. Candidate connectors (read them,
draft in them, govern them — never autonomous-send):

- Apollo (prospect / signal source).
- Clay (enrichment waterfall — Provider 1 → Provider 2 → Provider 3).
- Your sequencer / email tool (drafts → gate → send).
- Stripe (payment events → money-loop).
- CRM (HubSpot/Attio — account context).
- Content platforms (top posts, transcripts, engagement exports → content-batch).
- Ad accounts / analytics (owned-email triggers, measurement).

Each connector lives behind the same harness, same tool allowlist/denylist,
same approval mode, same vault reads, same rulings, same narration. Swapping a
stub for a real connector is a *swap* — it doesn't change the machine.

## Quickstart

```bash
cd gravita-gtm
uv sync
uv run gravita          # interactive REPL
uv run gravita run signal-outbound top_n=20
uv run gravita status
uv run gravita vault    # open this folder in Obsidian
```

The vault is at `vault/`. Open it in Obsidian. It's git-backed: the repo gives
it cloud backup, version history, and sync.

## Phase 1 done looks like

You say (in the REPL) `run signal-outbound top_n=20`, and the platform:
- Resolves the capability + harness (GHC v0.1.0, ASK_FIRST for send).
- Reads the vault (offer, ICP, voice, workflow note, rulings).
- Reads the stubbed Apollo/Clay source.
- Produces a research sheet artifact: one row per prospect, confidence note
  per row, drafts held at the gate.
- Posts the drafts to the pending queue with approve/hold/edit.
- Writes back to the vault (prospects, signals, messages).
- Records the trace in the audit ledger.

Nothing left the machine. But the whole loop works. That's the 7am test before
any service is connected.

## Governance

- The approval gate is structural: SEND / PUBLISH / SPEND / HUMAN-ALWAYS. Core
  enforces it on every action path, not just the happy path.
- Rulings: every correction you give an agent becomes one dated line in
  `vault/rulings/`. Every agent reads the rulings folder before working. A
  correction becomes permanent instead of repeated.
- The vault is the business. The agents are interchangeable. The harness
  contract is the boundary that makes them swappable.
- Dry-run first. The platform is useable before any service is connected. You
  build one workflow at a time; you run it until it passes the 7am test; then
  you add the next.

## Reference

- GTM guide (signal outbound, warm outbound, call→proposal, retention, demo-
  first content, placement hunt, money loop, owned email, content batch,
  borrowed rooms, member health, SEO/answer engine).
- Gravita Architecture v0.4 (harness-first, outcome-orchestrated, protocol
  boundaries, tech decision gate, portable contracts not identical
  implementations).
