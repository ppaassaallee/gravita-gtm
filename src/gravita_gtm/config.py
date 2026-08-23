"""Gravita GTM — Outcome-orchestrated B2B demand generation platform.

Hermes-patterned conversational sessions, governed multi-agent triggers,
cloud-hosted Obsidian vault as the semantic layer. Dry-run first, connect
real services after the platform is useable.

Path convention
---------------
All runtime paths are relative to this package's project root. The vault
lives under ``VAULT_DIR`` and is git-backed so Obsidian can open it locally
from disk while the repo gives it cloud backup and version history.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Project root = the repo root (``/Users/alejandropascual/gravita-gtm``).
# In production this is wherever you deploy; in dev it is the repo.
# ---------------------------------------------------------------------------

ROOT: Path = Path(__file__).resolve().parent.parent.parent
"""Repo/project root. Everything else is anchored here."""

VAULT_DIR: Path = ROOT / "vault"
"""Cloud-hosted Obsidian vault (git-backed markdown on disk). Open locally
in Obsidian; the repo gives it cloud backup, version history, and sync."""

STATE_DIR: Path = ROOT / "state"
"""Platform state: audit ledger, pending artifacts, session store, rulings
mirror. Kept separate from the vault so the platform's governed state doesn't
pollute the knowledge base you read in Obsidian."""

RULINGS_DIR: Path = VAULT_DIR / "rulings"
"""Human-readable rulings folder. Every agent reads this first."""

RULINGS_MIRROR: Path = STATE_DIR / "rulings.json"
"""Governed rulings source of truth (the enforcement version). Same content as
``RULINGS_DIR``, mirrored so Core can enforce without parsing markdown."""

AUDIT_LEDGER: Path = STATE_DIR / "audit.jsonl"
"""Append-oriented, tamper-evident audit ledger. One JSON object per line.
Every outcome traceable: intent -> harness -> decision -> tool -> execution ->
evidence."""

PENDING_ARTIFACTS: Path = STATE_DIR / "pending.json"
"""Pending artifacts awaiting approval. SEND/PUBLISH/SPEND/HUMAN-ALWAYS held
here until the human flips them."""

CONFIG_PATH: Path = ROOT / "config.json"
"""Optional runtime config (vault path override, stub mode flag, default risk
class, default approval mode, model gateway hint). Absent = sensible defaults."""


def ensure_dirs() -> None:
    """Create the platform directories that must exist on first boot."""
    for d in (VAULT_DIR, STATE_DIR, RULINGS_DIR, VAULT_DIR / "_index",
              VAULT_DIR / "offer", VAULT_DIR / "buyers", VAULT_DIR / "voice",
              VAULT_DIR / "market-map", VAULT_DIR / "workflows",
              VAULT_DIR / "prospects", VAULT_DIR / "signals",
              VAULT_DIR / "messages", VAULT_DIR / "metrics",
              VAULT_DIR / "calls", VAULT_DIR / "clients"):
        d.mkdir(parents=True, exist_ok=True)


def stub_mode() -> bool:
    """True when the platform should use stubbed sources instead of real APIs.
    Phase 1 = True until you wire and flip it."""
    return os.environ.get("GTM_STUB_MODE", "1") == "1"
