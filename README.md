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

Phase 1 (backend, dry-run):
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

Phase 2 (UX) — the conversational surface is built and can already show and
approve artifacts from Phase 1 dry runs. Terminal-first for v1.

Phase 3 (connect services) — you pay, you connect APIs, you wire tools. The
platform already runs; you're replacing stubs with real capabilities. The
approval gate is already structural; you're now permitting real sends/publishes/
spends per the risk class and approval mode you set.

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
