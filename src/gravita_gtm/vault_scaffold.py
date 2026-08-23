"""Cloud-hosted Obsidian vault scaffold.

The vault is the semantic layer of the platform. It lives under ``VAULT_DIR``
as real markdown on disk, is git-backed (so it has cloud backup, version
history, and sync), and is opened locally in Obsidian. Every agent reads it
before it writes and writes back to it after it works.

This module scaffolds the folder structure, hubs, glossary, offer, ICP, voice,
the first workflow note (signal outbound for an agency), and an empty rulings
folder. You edit these in Obsidian; the platform reads them at runtime.

The vault mirrors the real GTM vault from the guide but is specialized to a
demand-generation platform tenant. Folders:

- offer/       — what you sell, price, what's in, what you refuse
- buyers/      — ICP, bad-fit, target accounts
- voice/       — how you write, words you never use, exemplars
- market-map/  — competitors, category pages, rooms
- workflows/   — one note per workflow: trigger, source, output, approval, checklist
- rulings/     — every correction, dated, one line each
- prospects/   — research sheets, one note per run
- signals/     — what changed, when, what it means
- messages/    — drafts that went out, with result
- metrics/     — what came in from where, per week
- calls/       — call transcripts/notes
- clients/     — client notes
- _index/      — hub notes per folder + glossary
"""

from __future__ import annotations

from gravita_gtm.config import VAULT_DIR, ensure_dirs


def scaffold() -> list[str]:
    """Create the vault folders and initial notes. Returns the list of files
    created so you can open them in Obsidian and verify."""
    ensure_dirs()
    created: list[str] = []
    for path, text in NOTES.items():
        p = VAULT_DIR / path
        if not p.exists():
            p.write_text(text)
            created.append(str(p))
    return created


# ---------------------------------------------------------------------------
# Folder index notes (one per top-level folder). Each is a one-paragraph hub
# that says what lives inside. Agents read these first.
# ---------------------------------------------------------------------------

NOTES: dict[str, str] = {
    "_index/hub-offer.md": """# What you sell

Everything about the offer lives here: the product or service, the price, what is included, what you refuse to do, and the case studies that prove it.

Files in this folder:
- ``product.md`` — what you sell, in one read
- ``pricing.md`` — tiers and what changes between them
- ``case-studies/`` — one note per win, linked to the accounts that produced it

Read this folder before drafting a proposal, a win-back, or a case study.
""",

    "_index/hub-buyers.md": """# Who buys

Who buys from you, which verticals, what a qualified lead looks like, what a bad-fit lead looks like, and the accounts you are actively tracking.

Files in this folder:
- ``icp.md`` — the ideal customer profile, in one read
- ``bad-fit.md`` — who you do not chase and why
- ``accounts/`` — one note per target account, enriched over time

Read this folder before any outbound run. A prospect note without an ICP read is a guess.
""",

    "_index/hub-voice.md": """# How you write

How you write, the words you never use, and five of your best messages and posts as examples. This is the voice the agents write under.

Files in this folder:
- ``voice.md`` — how you write, in one read
- ``examples/`` — five best messages or posts as exemplars

Read this folder before drafting anything that will carry your name.
""",

    "_index/hub-market-map.md": """# The market map

Your competitors, the category pages that list them, and the rooms your buyers already sit in. This is the research that makes messages specific.

Files in this folder:
- ``competitors.md`` — who they are, what they do, where they are cited
- ``category-pages/`` — the roundups, resource pages, and directories that list several of them
- ``rooms/`` — newsletters, podcasts, communities, and small creators your audience trusts

Read this folder before a placement hunt or a borrowed-rooms run.
""",

    "_index/hub-workflows.md": """# How the work runs

One note per workflow: the trigger, the source, the output, the approval point, and the checklist the agent follows. This is the runbook every agent reads before working.

Files in this folder:
- ``signal-outbound.md`` — signal outbound (agencies first workflow)
- ``warm-outbound.md``
- ``call-to-proposal.md``
- ``retention.md``
- ``money-loop.md``
- ``content-batch.md``
- ``placement-hunt.md``
- ``owned-email.md``
- ``borrowed-rooms.md``
- ``member-health.md``
- ``seo-answer-engine.md``

Read the note for the workflow you are about to run. Do not draft from memory.
""",

    "_index/hub-prospects.md": """# Research sheets

One note per run, linked to the account it describes. A prospect note written today feeds the follow-up next month, the proposal after the call, and the case study a year from now.

Each note is a research sheet: what changed, what you see at their business, what your service fixes, a confidence note, and the drafts that came from it.

Read this folder before a follow-up or a proposal so you never type the research twice.
""",

    "_index/hub-signals.md": """# Signals

What changed at an account, when, and what it means. A signal is a change at the prospect's business — a funding round, a hiring post for the role you replace, a new head of marketing, a website untouched for a year — not a list you bought.

Each note is one signal, dated, linked to the account note. The next run reads these.
""",

    "_index/hub-messages.md": """# Messages

Drafts that went out, with what happened to them. A message record is a draft plus its result — sent, replied, ignored, booked — plus any correction that applies to the next one.

Read this folder when you review a run's output and when you add a ruling about what gets replies.
""",

    "_index/hub-metrics.md": """# Metrics

What came in from where, per week. Numbers go here, not in prose. A metric note is a number, a source, a date, and what it means.

Read this folder when you write a numbers summary or a retention report.
""",

    "_index/hub-calls.md": """# Calls

Call transcripts and notes. A discovery call ends, the transcript comes off the notetaker, and the call-to-proposal workflow reads it before it drafts anything.

Each note is one call: date, who was there, the transcript or its summary, the buying signal (or the absence of one), and what happened next.
""",

    "_index/hub-clients.md": """# Clients

The client you close is the client you never have to find again. A client note is the account, the numbers, the pipeline, the campaign state, the documented wins, and the referral asks that have gone out.

Read this folder before a retention run.
""",

    "_index/glossary.md": """# Glossary — canonical names

The canonical names for this tenant's world. Agents read this before working so the words mean the same thing to them as to you.

- **qualified lead** — an account that fits the ICP, has a signal or engagement worth a touch, and is within the geographic and budgetary reach of the offer.
- **bad-fit lead** — an account that does not fit the ICP, cannot buy the offer as priced, or is in a vertical you do not serve.
- **signal** — a change at the prospect's business worth a touch: funding, hiring for the role you replace, a new head of marketing, a stale site, a new owner.
- **warm** — a person who engaged with your content (liked, commented, reposted) and matches the ICP.
- **research sheet** — one row per prospect: what changed, what you see at their business, what your service fixes, a confidence note, and the drafts.
- **confidence note** — how solid the read is, per row. Low confidence flags the row before it reaches you.
- **approval gate** — nothing sends, publishes, or spends until you say yes. SEND, PUBLISH, SPEND, HUMAN-ALWAYS.
- **ruling** — a correction you give an agent, written as one dated line. Every agent reads the rulings folder before working. A correction becomes permanent instead of repeated.
- **7am test** — a workflow passes when it produced this morning without a message from you.
""",

    "offer/product.md": """# What we sell

One read. If you can't say it in this paragraph, it's not ready to sell.

We run B2B demand generation for one-person and small teams — the GTM jobs a sales team used to own, done by a governed team of AI employees that read from and write back to one shared knowledge base, with everything held at an approval gate so nothing sends, publishes, or spends without you.

What's included:
- Signal outbound — outreach that starts from a change at the prospect's business.
- Warm outbound — the people who engaged with your posts, matched to the ICP.
- Call to proposal — the proposal written from the call itself.
- Retention loop — keep clients past the first quarter with a numbers summary and a referral ask.
- Demo-first content — the product doing one job for one kind of user, every week.
- Placement hunt — borrow your competitors' placements.
- Money loop — recover revenue from failed charges and cancellations.
- Owned email — one good post turned into an owned list.
- Content batch — the week's content from receipts, not guesses.
- Borrowed rooms — the rooms your audience already sits in.
- Member health — keep members past the second month.
- SEO / answer engine — entity consistency, answer blocks, mentions, third-party hosts.

What we refuse to do:
- Send, publish, or spend without your approval.
- Open a message with a pitch in the first line.
- Chase a bad-fit lead.
- Discount to save a slow deal. Subtract scope instead.
- Run more workflows than you can review.
""",

    "offer/pricing.md": """# Pricing

One read. What changes between tiers, what does not.

Tiers:
- **Starter** — one workflow at a time, one channel, the vault, the gate, the audit log.
- **Growth** — two workflows at a time, multiple channels, the full vault, rulings, simulation.
- **Team** — the full platform, multiple tenants, placement profiles, policy packs.

What does not change between tiers:
- The approval gate. Nothing sends, publishes, or spends without you.
- The vault. The knowledge base is the business.
- The rulings. A correction becomes permanent instead of repeated.
- The dry-run-first rule. The platform is useable before any service is connected.
""",

    "workflows/signal-outbound.md": """# Signal outbound — workflow note

The first workflow. The one that moves revenue first for an agency. Read this before running signal outbound. Do not draft from memory.

## Trigger

- Calendar: weekly, Monday 09:00 in the workspace time zone. Or:
- Manual: you say "run signal outbound for this week, top N" in the channel.

## Source

- Apollo, filtered to the client profile (ICP). The wide list: every account the signals point at.
- Signals watched: funding round, hiring post for the role you replace, new head of marketing, website untouched for a year.
- Clay enriches every row. Empty fields filled by the next provider down. Weak rows drained before anything is written.

## Output

- A research sheet: one row per prospect.
  - What changed
  - What you see at their business
  - What your service fixes
  - Confidence note — how solid the read is
  - Drafts — one first message per top row
- Top rows only. Nothing below the line gets a message.

## Draft rules

- Opens with the workload you spotted at their business.
- Two short paragraphs.
- No pitch in the first line.
- A handful, not a list.

## Approval point — SEND

- You read it and send it from your own inbox.
- Nothing here sends by itself.
- The sequencer records what sent.

## Checklist

1. Read this note.
2. Read ``../buyers/icp.md``, ``../offer/product.md``, ``../voice/voice.md``.
3. Grep ``../rulings/`` for anything that applies to this topic, account, or workflow.
4. Read the account note if one exists in ``../buyers/accounts/``.
5. Read Apollo filtered to the ICP, signals watched.
6. Enrich through Clay. Drain weak rows.
7. Produce the research sheet, top rows only.
8. Draft one first message per top row, following the draft rules.
9. Post the drafts to the channel, held at the approval gate.
10. Write back: research sheet to ``../prospects/``, signal notes to ``../signals/``, message records to ``../messages/``.

## Stop point

The agent stops at the approval gate. It never sends. You send from your own inbox.

## What the agent does not do

- It does not send.
- It does not pitch in the first line.
- It does not chase a bad-fit lead.
- It does not discount to save a slow deal.
- It does not invent a fact it couldn't see. If a field is empty after enrichment, the row gets a confidence note and the draft opens with what it could see.
""",

    "voice/voice.md": """# How we write

One read. The agents write under this voice. If you correct the voice, add a ruling — do not just rewrite the draft.

- Short sentences. Two paragraphs max in a first message.
- Specific, not broad. Name what you saw at their business.
- No pitch in the first line. Open with the workload you spotted.
- No words we never use: " synergize", "game-changing", "cutting-edge", "disrupt", "best-in-class".
- No hedging: "might", "could potentially", "we believe". Say what you see.
- No fake intimacy: "I was just thinking about you" is not a signal.

Five best messages as exemplars are in ``examples/``. Read them before drafting.
""",
}

# ---------------------------------------------------------------------------
# Empty rulings folder — one note that says what it is. The platform writes
# dated lines here as agents and humans correct things.
# ---------------------------------------------------------------------------

INITIAL_RULINGS = """# Rulings

One line per correction, dated. Every agent reads this folder before working.
A correction becomes permanent instead of repeated.

No rulings yet. The first one you add is the most important one.
"""


def scaffold_rulings() -> str:
    p = VAULT_DIR / "rulings" / "README.md"
    if not p.exists():
        p.write_text(INITIAL_RULINGS)
    return str(p)
