"""Vault write-back — after a run, write what the agent learned back to the
Obsidian vault as real markdown notes.

This is the loop: recall before work, write back after. Tonight's write-back is
tomorrow's recall. Without this, the vault doesn't fill from the runs and the
next run has nothing to read.

Phase 1: write back from the workflow runners (signal-outbound, money-loop,
content-batch) after the artifact is produced and held at the gate.

Reference: the GTM guide (the daily rhythm: AFTER write-back highlighted red —
one line to rulings, the fact onto the account note, numbers to metrics). Plus
the Obsidian vault infographic (how one prospect note compounds across 4+
touchpoints without anyone typing the research twice).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gravita_gtm.config import VAULT_DIR
from gravita_gtm.vault_io import read_note


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")


def write_back_signal_outbound(artifact: Any) -> list[str]:
    """After a signal-outbound run, write back:
    - one research sheet note per run in ``vault/prospects/`` (linked to the
      accounts it describes),
    - one signal note per account in ``vault/signals/``,
    - one message record per drafted message in ``vault/messages/``.

    Returns the list of files written.
    """
    written: list[str] = []
    rows = artifact.content.get("rows", [])
    if not rows:
        return written
    run_id = artifact.id

    # --- prospects: one note per run, linked to accounts ---
    prospect_dir = VAULT_DIR / "prospects"
    prospect_dir.mkdir(parents=True, exist_ok=True)
    prospect_note = prospect_dir / f"{run_id}.md"
    prospect_text = _prospect_note(artifact, rows)
    prospect_note.write_text(prospect_text, encoding="utf-8")
    written.append(str(prospect_note.relative_to(VAULT_DIR)))

    # --- signals: one note per account that had a signal ---
    signals_dir = VAULT_DIR / "signals"
    signals_dir.mkdir(parents=True, exist_ok=True)
    for row in rows:
        if row.get("what_changed") and row["what_changed"] != "No clear signal":
            sig_note = signals_dir / f"{run_id}-{row['row']:02d}.md"
            sig_text = _signal_note(artifact, row)
            sig_note.write_text(sig_text, encoding="utf-8")
            written.append(str(sig_note.relative_to(VAULT_DIR)))

    # --- messages: one record per drafted message ---
    messages_dir = VAULT_DIR / "messages"
    messages_dir.mkdir(parents=True, exist_ok=True)
    for row in rows:
        if row.get("draft"):
            msg_note = messages_dir / f"{run_id}-{row['row']:02d}.md"
            msg_text = _message_note(artifact, row)
            msg_note.write_text(msg_text, encoding="utf-8")
            written.append(str(msg_note.relative_to(VAULT_DIR)))

    return written


def write_back_money_loop(artifact: Any) -> list[str]:
    """After a money-loop run, write back:
    - one churn row to ``vault/metrics/`` split by churn bucket
      (card_failed vs chose_to_leave), as the guide specifies.
    - (win-back drafts are held at the gate; the actual send writes a message
      record later.)
    """
    written: list[str] = []
    metrics_dir = VAULT_DIR / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    bucket = artifact.content.get("churn_bucket", "unknown")
    metric_note = metrics_dir / f"{artifact.id}.md"
    metric_text = _metric_note(artifact)
    metric_note.write_text(metric_text, encoding="utf-8")
    written.append(str(metric_note.relative_to(VAULT_DIR)))
    return written


def _prospect_note(artifact: Any, rows: list[dict[str, Any]]) -> str:
    lines = [
        f"# Research sheet — {artifact.id}\n",
        f"run: {artifact.capability} · {artifact.created_at} · trigger: {artifact.content.get('trigger', 'manual')}\n",
        f"source: {artifact.content.get('source_summary', '')}\n",
        f"top_n: {artifact.content.get('top_n')} · kept: {artifact.content.get('total_kept')}\n",
        "\n---\n",
    ]
    for row in rows:
        conf = row.get("confidence", {})
        lines.append(f"## Row {row['row']:02d} — {row.get('company')}\n")
        lines.append(f"- vertical: {row.get('vertical')}\n")
        lines.append(f"- employees: {row.get('employees')}\n")
        lines.append(f"- spend_range: {row.get('spend_range')}\n")
        lines.append(f"- what_changed: {row.get('what_changed')}\n")
        lines.append(f"- what_you_see: {row.get('what_you_see')}\n")
        lines.append(f"- what_your_service_fixes: {row.get('what_your_service_fixes')}\n")
        lines.append(f"- confidence: {conf.get('what_changed','?')} / {conf.get('what_you_see','?')}\n")
        lines.append(f"\n{draft_block(row.get('draft',''))}\n")
    return "\n".join(lines)


def _signal_note(artifact: Any, row: dict[str, Any]) -> str:
    return "\n".join([
        f"# Signal — {row.get('company')}",
        f"run: {artifact.id}",
        f"date: {_now()}",
        f"signal: {row.get('what_changed')}",
        f"what_you_see: {row.get('what_you_see')}",
        f"confidence: {row.get('confidence', {}).get('what_changed', '?')}",
        "",
    ])


def _message_note(artifact: Any, row: dict[str, Any]) -> str:
    return "\n".join([
        f"# Message — {row.get('company')}",
        f"run: {artifact.id}",
        f"row: {row['row']}",
        f"channel: {artifact.content.get('trigger','manual')}",
        f"draft:",
        "",
        row.get('draft', ''),
        "",
        "status: drafted · held at approval gate",
        "sent: (not yet)",
        "reply: (not yet)",
        "",
    ])


def _metric_note(artifact: Any) -> str:
    actions = artifact.content.get("actions", [])
    return "\n".join([
        f"# Metric — money loop · {artifact.id}",
        f"date: {_now()}",
        f"customer: {artifact.content.get('customer')}",
        f"churn_bucket: {artifact.content.get('churn_bucket')}",
        f"amount: {artifact.content.get('amount')}",
        f"failure_reason: {artifact.content.get('failure_reason')}",
        f"cancellation_reason: {artifact.content.get('cancellation_reason')}",
        f"recovery_action: {artifact.decision_evidence.get('recovery_action', 'none')}",
        "",
        "actions:",
    ] + [f"- {a.get('action')}: {a.get('draft','')[:80]}..." if a.get('draft') else f"- {a.get('action')}"
         for a in actions])


def draft_block(draft: str) -> str:
    """Render a draft as a markdown block."""
    return "\n".join([draft]) if draft else "(no draft)"


def write_back_content_batch(artifact: Any) -> list[str]:
    """After a content-batch run, write back the batch + flagged strongest to
    ``vault/metrics/`` (content-batch metrics). The actual publish writes a
    message/artifact record later."""
    written: list[str] = []
    metrics_dir = VAULT_DIR / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    note = metrics_dir / f"{artifact.id}.md"
    note.write_text(_content_batch_note(artifact), encoding="utf-8")
    written.append(str(note.relative_to(VAULT_DIR)))
    return written


def _content_batch_note(artifact: Any) -> str:
    batch = artifact.content.get("batch", [])
    lines = [
        f"# Content batch — {artifact.id}",
        f"date: {_now()}",
        f"trigger: {artifact.content.get('trigger', 'manual')}",
        f"platforms: {len(batch)}",
        f"flagged_strongest: {artifact.content.get('flagged_strongest', {}).get('strongest', '')}",
        "",
        "batch:",
    ]
    for b in batch:
        lines.append(f"\n## {b.get('platform')} — {b.get('headline')}")
        lines.append(f"- engagement: {b.get('engagement')}")
        lines.append(f"- daily_posts:")
        for dp in b.get("daily_posts", []):
            lines.append(f"  - {dp}")
        lines.append(f"- manual_task: {b.get('manual_task')}")
    poll = artifact.content.get("poll_for_newsletter", {})
    if poll:
        lines.append(f"\npoll: {poll.get('question')}")
        for opt in poll.get("options", []):
            lines.append(f"  - {opt}")
    return "\n".join(lines)
