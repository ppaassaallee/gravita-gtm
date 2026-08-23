"""Workflow runners — the things that execute a capability through its four-part
skeleton: trigger -> source -> artifact -> gate.

Each runner:
1. Reads the vault (offer, ICP, voice, workflow note, rulings, account note).
2. Reads the source (real or stub, depending on STUB_MODE).
3. Produces an artifact — a research sheet, a draft message, a numbers summary,
   a proposal link, a content batch, a placement sheet, a win-back draft.
4. Holds the artifact at the approval gate (PENDING).

The runner does not send. The gate holds. You approve in the surface.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich import box
from rich.console import Console
from rich.table import Table

from gravita_gtm.artifact import Artifact, ArtifactStatus
from gravita_gtm.config import (
    AUDIT_LEDGER, PENDING_ARTIFACTS, STATE_DIR, VAULT_DIR, ensure_dirs, stub_mode,
)
from gravita_gtm.vault_io import read_note, grep_rulings, list_notes
from gravita_gtm.stub.sources import (
    stub_accounts, stub_clay_enrichment, stub_transcript, stub_payment_event,
    stub_top_posts, stub_engagement_export,
)
from gravita_gtm.runtime.write_back import (
    write_back_signal_outbound,
    write_back_money_loop,
    write_back_content_batch,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trace(harness: object, capability: str, evidence: dict[str, Any], artifact_id: str) -> None:
    """Record one decision-evidence line in the audit ledger. Every outcome
    traceable: intent -> harness -> decision -> tool -> execution -> evidence."""
    hv = getattr(harness, "version", "0.1.0") if harness is not None else "0.1.0"
    rc = getattr(harness, "risk_class", None)
    rc = rc.value if rc is not None else "medium"
    am = getattr(harness, "approval_mode", None)
    am = am.value if am is not None else "ask-first"
    entry = {
        "id": artifact_id,
        "capability": capability,
        "harness_version": hv,
        "risk_class": rc,
        "approval_mode": am,
        "fired_at": _now_iso(),
        "evidence": evidence,
        "status": "produced",
    }
    AUDIT_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _write_pending(artifact: Artifact) -> None:
    """Persist a pending artifact so the UX surface can show and approve it."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    pending: list[dict[str, Any]] = []
    p = PENDING_ARTIFACTS
    if p.exists():
        pending = json.loads(p.read_text(encoding="utf-8"))
    pending.append(artifact.to_dict())
    p.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")


def read_pending() -> list[dict[str, Any]]:
    p = PENDING_ARTIFACTS
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def approve_pending(artifact_id: str) -> Artifact | None:
    """Flip a pending artifact to APPROVED, record the approval time, and
    remove it from the pending queue (it has shipped)."""
    pending = read_pending()
    item = next((x for x in pending if x["id"] == artifact_id), None)
    if item is None:
        return None
    pending.remove(item)
    PENDING_ARTIFACTS.write_text(
        json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    artifact = Artifact(
        capability=item["capability"],
        status=ArtifactStatus.APPROVED,
        content=item["content"],
        confidence=item["confidence"],
        decision_evidence=item["decision_evidence"],
        created_at=item["created_at"],
        approved_at=_now_iso(),
        id=artifact_id,
    )
    # record the approval in the audit ledger
    _trace(artifact, item["capability"], {"approved": True, "approved_at": artifact.approved_at}, artifact_id)
    return artifact


# ---------------------------------------------------------------------------
# Narration — the run tells the story in the image order so a human can
# follow it without being told. Single-seat, single-program, signal-outbound
# first; the other runners inherit the same socket.
# ---------------------------------------------------------------------------

class RulingHonored:
    """One ruling the run actually read and used, as readable text."""
    def __init__(self, file: str, line: int, text: str, how: str = "") -> None:
        self.file = file
        self.line = line
        self.text = text
        self.how = how

    def to_dict(self) -> dict[str, Any]:
        return {"file": self.file, "line": self.line, "text": self.text, "how": self.how}


class RunNarration:
    """Human-readable story of one run, in the image order.

    trigger -> sources -> enrichment waterfall -> research sheet (confidence
    notes per row) -> drafts -> gate -> write-back.
    """
    def __init__(self, capability: str, trigger: str) -> None:
        self.capability = capability
        self.trigger = trigger
        self.sources: list[str] = []
        self.rulings_honored: list[RulingHonored] = []
        self.waterfall_raw = 0
        self.waterfall_kept = 0
        self.waterfall_drained = 0
        self.rows: list[dict[str, Any]] = []
        self.draft_rule = ""
        self.gate = "PENDING"
        self.write_back: list[str] = []

    def add_source(self, label: str) -> None:
        self.sources.append(label)

    def add_ruling(self, r: RulingHonored) -> None:
        self.rulings_honored.append(r)

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability,
            "trigger": self.trigger,
            "sources": self.sources,
            "rulings_honored": [r.to_dict() for r in self.rulings_honored],
            "waterfall": {
                "raw": self.waterfall_raw,
                "kept": self.waterfall_kept,
                "drained": self.waterfall_drained,
            },
            "rows": self.rows,
            "draft_rule": self.draft_rule,
            "gate": self.gate,
            "write_back": self.write_back,
        }

def run_signal_outbound(harness: Any, context: dict[str, Any]) -> Artifact:
    """Four-part skeleton:
    1. Trigger: context says weekly or manual.
    2. Source: Apollo filtered to ICP + signals; Clay enrichment waterfall.
    3. Output: research sheet, one row per prospect, top rows only, with
       drafts held at the gate.
    4. Gate: PENDING.

    Returns the artifact. The runner also narrates itself (trigger -> sources
    -> enrichment waterfall -> research sheet with confidence notes -> drafts
    -> gate -> write-back) and surfaces the rulings it actually honored; the
    last narration is stored in ``state/narration.json`` so the CLI / dashboard
    / preview can show it.
    """
    artifact_id = f"so-{uuid.uuid4().hex[:10]}"
    top_n = context.get("top_n", 8)
    trigger = context.get("trigger_kind", "manual")

    narration = RunNarration("signal-outbound", trigger)

    # 1. Read vault context ---------------------------------------------------
    offer = read_note("offer/product.md")
    icp = read_note("buyers/icp.md")
    voice = read_note("voice/voice.md")
    workflow_note = read_note("workflows/signal-outbound.md")

    narration.add_source("vault/offer/product.md")
    narration.add_source("vault/buyers/icp.md")
    narration.add_source("vault/voice/voice.md")
    narration.add_source("vault/workflows/signal-outbound.md")

    # rulings: read first, every run. These are the permanent corrections.
    rulings_raw = grep_rulings("signal") + grep_rulings("outbound") + grep_rulings("first line") + grep_rulings("pitch")
    rulings_read: list[dict[str, Any]] = rulings_raw
    narration.rulings_honored = [
        RulingHonored(r["file"], r["line"], r["text"], "read before drafting")
        for r in rulings_read
    ]

    # 2. Read source ---------------------------------------------------------
    if stub_mode():
        raw_accounts = stub_accounts(n=40)
        enriched: list[dict[str, Any]] = []
        for acct in raw_accounts:
            row = stub_clay_enrichment(acct)
            enriched.append(row)
        # drain weak rows before drafting
        drained = [r for r in enriched if r.get("dropped")]
        kept = [r for r in enriched if not r.get("dropped")]
        narration.waterfall_raw = len(raw_accounts)
        narration.waterfall_kept = len(kept)
        narration.waterfall_drained = len(drained)
        narration.add_source("stub/apollo")
        narration.add_source("stub/clay (enrichment waterfall)")
    else:
        # Phase 3: read real Apollo + Clay through the tool gateway.
        raise NotImplementedError("connect Apollo + Clay in Phase 3")

    # 3. Produce artifact ----------------------------------------------------
    top_rows = kept[:top_n]
    confidence_notes: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    for i, row in enumerate(top_rows, start=1):
        confidence = row.get("confidence", {})
        note = f"row {i:02d}: what_changed={confidence.get('what_changed','?')}, what_you_see={confidence.get('what_you_see','?')}"
        confidence_notes.append({"row": i, "note": note, **confidence})
        row_obj = {
            "row": i,
            "company": row.get("company"),
            "vertical": row.get("vertical"),
            "employees": row.get("employees"),
            "spend_range": row.get("spend_range"),
            "what_changed": row.get("what_changed"),
            "what_you_see": row.get("what_you_see"),
            "what_your_service_fixes": row.get("what_your_service_fixes"),
            "confidence": confidence,
            "draft": _draft_first_message(row, voice, rulings_read),
        }
        rows.append(row_obj)
    narration.rows = rows

    content = {
        "type": "research-sheet",
        "trigger": trigger,
        "source_summary": f"Apollo filtered to ICP + signals; {len(raw_accounts)} raw accounts, {len(kept)} kept after enrichment waterfall",
        "top_n": top_n,
        "total_kept": len(kept),
        "rows": rows,
    }
    decision_evidence = {
        "read_vault": [offer["path"], icp["path"], voice["path"], workflow_note["path"]],
        "rulings_matched": [r["file"] for r in rulings_read],
        "rulings_honored": [{"file": r["file"], "text": r["text"], "how": "read before drafting"} for r in rulings_read],
        "source": "stub/apollo + stub/clay (Phase 1 dry-run)" if stub_mode() else "Apollo + Clay",
        "accounts_considered": len(raw_accounts),
        "accounts_kept": len(kept),
        "accounts_drafted": len(rows),
        "draft_rules": "open with workload, two short paragraphs, no pitch in first line, handful not a list",
    }
    narration.draft_rule = decision_evidence["draft_rules"]

    artifact = Artifact(
        capability="signal-outbound",
        status=ArtifactStatus.PENDING,
        content=content,
        confidence=confidence_notes,
        decision_evidence=decision_evidence,
        created_at=_now_iso(),
        id=artifact_id,
    )
    _write_pending(artifact)
    _trace(harness, "signal-outbound", decision_evidence, artifact_id)
    wb = write_back_signal_outbound(artifact)
    narration.write_back = wb
    narration.gate = "PENDING (ask-first for send)"
    _store_narration(narration)
    return artifact


# ---------------------------------------------------------------------------
# Storage for the run narration — last narration lives in state/ so the CLI,
# dashboard, and preview can show the story of the most recent run.
# ---------------------------------------------------------------------------

NARRATION_PATH = STATE_DIR / "narration.json"


def _store_narration(narration: RunNarration) -> None:
    """Persist the last run's narration so the surface can show it."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    NARRATION_PATH.write_text(
        json.dumps(narration.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_last_narration() -> dict[str, Any] | None:
    """Return the last run's narration dict, or None if nothing has run."""
    if not NARRATION_PATH.exists():
        return None
    try:
        return json.loads(NARRATION_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _draft_first_message(row: dict[str, Any], voice: dict[str, Any], rulings: list[dict[str, Any]]) -> str:
    """Draft one first message for a top-row prospect.

    Draft rules (from the workflow note + rulings):
    - Opens with the workload you spotted at their business.
    - Two short paragraphs.
    - No pitch in the first line.
    - A handful, not a list.

    The banned set is derived from the rulings the run just read, so a newly
    added ruling (e.g. "no word X in the first line") shapes the next draft.
    """
    company = row.get("company", "them")
    changed = row.get("what_changed", "something changed")
    see = row.get("what_you_see", "a workload you can fix")
    fixes = row.get("what_your_service_fixes", "a governed demand-generation workflow")

    # Stable banned words (never good GTM writing).
    banned = ["synergize", "game-changing", "cutting-edge", "disrupt", "best-in-class",
              "might", "could potentially", "we believe"]
    # Additional banned words from the rulings the run read — this is how a
    # one-line ruling like "no 'leverage' in the first line" actually bites.
    for r in rulings:
        rl = r.get("text", "").lower()
        m = re.search(r"no\s+['\"]?(\w+)['\"]?\s+(in|on|inside)\s+the\s+first\s+line", rl)
        if m:
            banned.append(m.group(1))
        m2 = re.search(r"never\s+use\s+['\"]?(\w+)['\"]?", rl)
        if m2:
            banned.append(m2.group(1))

    def clean(t: str) -> str:
        for w in banned:
            t = _unword(t, w)
        return t

    first_line = f"Saw {changed.lower()} at {company} — "
    if "funding" in changed.lower():
        first_line += "new money usually means new hires and new vendors, and usually a window to set the pattern before the noise catches up."
    elif "hiring" in changed.lower():
        first_line += "a hire for the role you replace usually means the budget already exists and someone is now accountable for filling it."
    elif "owner" in changed.lower():
        first_line += "a new owner usually looks for quick wins in the first 90 days, and the work that's visible from outside is usually the easiest one to point to."
    elif "stale" in changed.lower():
        first_line += "a site untouched for a year usually means the work is visible from outside — and usually the easiest place to start."
    else:
        first_line += f"something changed at {company}, and the work that's visible from outside is usually the easiest place to start."

    second = f" {see}. {fixes}."
    return clean(first_line) + clean(second)


def _unword(t: str, w: str) -> str:
    """Remove a banned word (case-insensitive), cleaning up leftover punctuation."""
    pat = re.compile(rf"\b{re.escape(w)}\b", re.IGNORECASE)
    t = pat.sub("", t)
    t = re.sub(r"\s+[.,;:—-]+\s*", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


# ---------------------------------------------------------------------------
# Money loop — recover revenue from failed charges and cancellations.
# ---------------------------------------------------------------------------

def run_money_loop(harness: Any, context: dict[str, Any]) -> Artifact:
    """Four-part skeleton:
    1. Trigger: payment event (failed charge or cancellation) or monthly calendar.
    2. Source: Stripe event + CRM customer history.
    3. Output: retry/exit-survey/win-back draft + one churn row (card_failed vs chose_to_leave).
    4. Gate: PENDING (SEND for emails, SPEND for anything that moves money).
    """
    artifact_id = f"ml-{uuid.uuid4().hex[:10]}"
    event = context.get("event", {})

    offer = read_note("offer/product.md")
    rulings_read = grep_rulings("money") + grep_rulings("win-back") + grep_rulings("retry")

    if stub_mode():
        if event.get("type") == "payment.failed":
            row = stub_payment_event("failed_card", days_ago=2)
            event = row
        elif event.get("type") == "customer.canceled":
            row = stub_payment_event("canceled", days_ago=3)
            event = row
    else:
        # Phase 3: read real Stripe event through the tool gateway.
        raise NotImplementedError("connect Stripe in Phase 3")

    churn_bucket = event.get("churn_bucket", "unknown")
    content: dict[str, Any] = {
        "type": "money-loop-artifact",
        "event_type": event.get("type"),
        "customer": event.get("customer_name", event.get("customer")),
        "churn_bucket": churn_bucket,
        "amount": event.get("amount"),
        "failure_reason": event.get("failure_reason"),
        "cancellation_reason": event.get("cancellation_reason"),
        "actions": [],
    }
    actions: list[dict[str, Any]] = []

    if churn_bucket == "card_failed":
        retry_days = {"card_expired": 5, "insufficient_funds": 2, "declined_by_issuer": 1}[event.get("failure_reason", "card_expired")]
        actions.append({
            "action": "retry_charge",
            "retry_in_days": retry_days,
            "reason": event.get("failure_reason"),
            "email_draft": f"Hi there — a payment for ${event.get('amount',0):,} didn't go through ({event.get('failure_reason','unknown')}). We'll retry in {retry_days} days. If you'd rather update your card now, here's the link: [update card]. No need to reply unless something's off.",
        })
    elif churn_bucket == "chose_to_leave":
        reason = event.get("cancellation_reason", "left")
        survey = event.get("exit_survey_answer", "")
        actions.append({
            "action": "exit_survey",
            "sent": True,
            "reason": reason,
            "exit_survey_answer": survey,
        })
        # win-back draft, sent within 1-2 days
        winback = _winback_draft(reason, survey, str(event.get("customer_name", event.get("customer"))), offer["text"])
        actions.append({
            "action": "win-back-email",
            "send_in_days": 2,
            "draft": winback,
        })

    confidence_notes = [{"note": f"churn_bucket={churn_bucket}; reason={event.get('failure_reason') or event.get('cancellation_reason')}"}]

    content["actions"] = actions
    decision_evidence = {
        "read_vault": [offer["path"]],
        "rulings_matched": [r["file"] for r in rulings_read],
        "rulings_honored": [{"file": r["file"], "text": r["text"], "how": "read before drafting"} for r in rulings_read],
        "source": "stub/stripe (Phase 1 dry-run)" if stub_mode() else "Stripe",
        "churn_bucket": churn_bucket,
        "recovery_action": actions[0]["action"] if actions else "none",
    }

    artifact = Artifact(
        capability="money-loop",
        status=ArtifactStatus.PENDING,
        content=content,
        confidence=confidence_notes,
        decision_evidence=decision_evidence,
        created_at=_now_iso(),
        id=artifact_id,
    )
    _write_pending(artifact)
    _trace(harness, "money-loop", decision_evidence, artifact_id)
    wb = write_back_money_loop(artifact)
    _store_narration(_money_narration(harness, context, rulings_read, wb))
    return artifact


def _winback_draft(reason: str, survey: str, customer: str, offer_text: str) -> str:
    """Draft a win-back message written for the reason they gave."""
    if "in-house" in reason or "in-house" in survey:
        return (f"Hi — saw you moved to an in-house hire. Totally get it. "
                f"If the thing you're solving is still on your roadmap and you want "
                f"a second opinion on the gap between what you built and what you need, "
                f"I'm happy to spend 20 minutes on it with no ask. Either way, wish you "
                f"well with the build — {customer}")
    if "expensive" in reason or "expensive" in survey:
        return (f"Hi — understood on price. If it's the stage rather than the tool, "
                f"the starter tier is built for exactly that: one workflow at a time, "
                f"the vault, the gate, the audit log. Happy to walk you through it in 15 "
                f"minutes and you can decide either way — {customer}")
    if "not using" in reason or "not using" in survey:
        return (f"Hi — makes sense that you're not using it enough to justify it. "
                f"If the gap is adoption rather than the tool, the money loop won't fix "
                f"that, but a 20-minute reset on the one workflow that would have moved "
                f"the needle might. Happy to do it with no ask — {customer}")
    return (f"Hi — sorry to see you go. If the reason was timing rather than the tool, "
            f"I'd love to lend a second opinion whenever the window opens again. Either "
            f"way, wish you well — {customer}")


# ---------------------------------------------------------------------------
# Narration helpers for the other two runners (mirror signal-outbound).
# ---------------------------------------------------------------------------

def _money_narration(harness: Any, context: dict[str, Any],
                     rulings_read: list[dict[str, Any]], wb: list[str]) -> RunNarration:
    n = RunNarration("money-loop", context.get("trigger_kind", "manual") or "manual")
    n.add_source("vault/offer/product.md")
    n.add_source("stub/stripe (Phase 1 dry-run)" if stub_mode() else "Stripe")
    n.rulings_honored = [
        RulingHonored(r["file"], r["line"], r["text"], "read before drafting")
        for r in rulings_read
    ]
    n.gate = "PENDING (ask-first for SEND/SPEND)"
    n.write_back = wb
    n.draft_rule = "open with the reason, one offer, no pressure; held at the gate"
    return n


def _content_narration(harness: Any, context: dict[str, Any],
                       rulings_read: list[dict[str, Any]], wb: list[str]) -> RunNarration:
    n = RunNarration("content-batch", context.get("trigger_kind", "manual") or "manual")
    n.add_source("vault/voice/voice.md")
    n.add_source("stub/platform-numbers (Phase 1 dry-run)" if stub_mode() else "platform numbers")
    n.rulings_honored = [
        RulingHonored(r["file"], r["line"], r["text"], "read before drafting")
        for r in rulings_read
    ]
    n.gate = "PENDING (ask-first for PUBLISH)"
    n.write_back = wb
    n.draft_rule = "write in voice, flag strongest, add a poll; nothing publishes without you"
    return n


# ---------------------------------------------------------------------------
# Content batch — the week's content from receipts, not guesses.
# ---------------------------------------------------------------------------

def run_content_batch(harness: Any, context: dict[str, Any]) -> Artifact:
    """Four-part skeleton:
    1. Trigger: weekly calendar or manual.
    2. Source: top posts, transcripts, high-engagement replies.
    3. Output: batch per platform in your voice, flagged strongest + why, a poll
       for the newsletter.
    4. Gate: PENDING (PUBLISH — you edit and approve).
    """
    artifact_id = f"cb-{uuid.uuid4().hex[:10]}"
    voice = read_note("voice/voice.md")
    rulings_read = grep_rulings("content") + grep_rulings("batch") + grep_rulings("voice")

    if stub_mode():
        top_posts = stub_top_posts("linkedin")
        engagers = stub_engagement_export(top_posts[0], n_engagers=12)
    else:
        raise NotImplementedError("connect content platforms in Phase 3")

    # draft the batch, one per platform, in voice
    batch: list[dict[str, Any]] = []
    banned = ["synergize", "game-changing", "cutting-edge", "disrupt", "best-in-class"]
    def clean(t: str) -> str:
        for w in banned:
            t = t.replace(w, "")
        return t

    for post in top_posts[:3]:
        headline = post.get("headline", "")
        # daily short posts derived from the top post
        daily = [
            f"{headline}",
            f"The one thing most people miss about {headline.split(':')[0].strip()}.",
            f"A short version of {headline.split(':')[0].strip()}, for the people who won't read the long one.",
        ]
        batch.append({
            "platform": post.get("platform", "linkedin"),
            "headline": headline,
            "engagement": post.get("engagement"),
            "daily_posts": [clean(d) for d in daily],
            "manual_task": f"Make the first outputs by hand for the people who commented on this one. A stranger who got a personalized result tells someone.",
        })

    # flag strongest + why
    strongest = max(batch, key=lambda b: b.get("engagement") or 0)
    flagged = {
        "strongest": strongest["headline"],
        "why": f"Highest engagement ({strongest.get('engagement')}), most comments, most repost-worthy angle in the batch.",
        "next_batch_starts_from": "a poll, not a guess — the newsletter asks readers what to write about next",
    }

    # a poll for the newsletter
    poll = {
        "question": "What should the next content batch focus on?",
        "options": [
            "Signal outbound — the first message that opens with what changed",
            "Warm outbound — the engaged list you send by hand",
            "The money loop — recovering revenue you already have",
            "Member health — keeping people past the second month",
        ],
    }

    content = {
        "type": "content-batch",
        "trigger": context.get("trigger_kind", "manual"),
        "batch": batch,
        "flagged_strongest": flagged,
        "poll_for_newsletter": poll,
        "manual_tasks": [b["manual_task"] for b in batch],
    }
    confidence_notes = [{"note": "draft only; edits and approvals required before publish"}]

    decision_evidence = {
        "read_vault": [voice["path"]],
        "rulings_matched": [r["file"] for r in rulings_read],
        "rulings_honored": [{"file": r["file"], "text": r["text"], "how": "read before drafting"} for r in rulings_read],
        "source": "stub/platform-numbers (Phase 1 dry-run)" if stub_mode() else "platform numbers",
        "posts_read": len(top_posts),
        "draft_rule": "write in voice, flag strongest, add a poll; nothing publishes without you",
    }

    artifact = Artifact(
        capability="content-batch",
        status=ArtifactStatus.PENDING,
        content=content,
        confidence=confidence_notes,
        decision_evidence=decision_evidence,
        created_at=_now_iso(),
        id=artifact_id,
    )
    _write_pending(artifact)
    _trace(harness, "content-batch", decision_evidence, artifact_id)
    wb = write_back_content_batch(artifact)
    _store_narration(_content_narration(harness, context, rulings_read, wb))
    return artifact
