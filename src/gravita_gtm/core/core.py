"""Gravita Core — the governor of the platform.

Core owns: trigger registry, approval gate, permission layer, rulings store,
audit log, agent lifecycle. Agents are workers; Core is the process manager.

Nothing sends, publishes, or spends without Core recording your approval.
Core enforces the gate on every action path, not just the happy path.

Reference: Gravita Architecture v0.4 — Outcome & Semantic Control Plane,
Policy/Action Gateway, Cybersecurity & Trust Fabric. Plus the GTM guide's
seat (one approval gate, four doors in, one door out).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gravita_gtm.artifact import Artifact, ArtifactStatus
from gravita_gtm.config import (
    AUDIT_LEDGER, PENDING_ARTIFACTS, RULINGS_DIR, RULINGS_MIRROR, STATE_DIR,
    VAULT_DIR, ensure_dirs, stub_mode,
)
from gravita_gtm.core.triggers import TriggerRegistry, register_defaults
from gravita_gtm.ghc import GHC, ApprovalMode
from gravita_gtm.harness.registry import HarnessRegistry, HarnessRegistration
from gravita_gtm.runtime.adapters import (
    Artifact, ArtifactStatus, RuntimeAdapter, adapter_for,
)
from gravita_gtm.runtime.workflows import (
    approve_pending, read_pending, run_signal_outbound, run_money_loop, run_content_batch,
)
from gravita_gtm.compiler import Compiler
from gravita_gtm.vault_io import read_note, grep_rulings
from gravita_gtm.stub.sources import stub_payment_event


# ---------------------------------------------------------------------------
# Agent lifecycle — workers that Core wakes per run. In Phase 1 these are
# just labels + state; later phases add real LangGraph/Pydantic sessions.
# ---------------------------------------------------------------------------

class AgentLifecycle:
    """Phase 1: a simple registry of agent runs. Each run is a capability +
    harness + state. Later phases: real agent sessions with interrupts/HITL."""

    def __init__(self) -> None:
        self._runs: dict[str, dict[str, Any]] = {}

    def start(self, capability: str, harness: GHC, workspace: str, channel: str) -> str:
        run_id = f"run-{uuid.uuid4().hex[:10]}"
        self._runs[run_id] = {
            "run_id": run_id,
            "capability": capability,
            "harness_version": harness.version,
            "workspace": workspace,
            "channel": channel,
            "state": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "artifact_id": None,
        }
        return run_id

    def finish(self, run_id: str, artifact_id: str) -> None:
        run = self._runs.get(run_id)
        if run is None:
            return
        run["state"] = "finished"
        run["artifact_id"] = artifact_id
        run["finished_at"] = datetime.now(timezone.utc).isoformat()

    def list(self) -> list[dict[str, Any]]:
        return list(self._runs.values())


# ---------------------------------------------------------------------------
# Rulings store — two homes, same content.
# ---------------------------------------------------------------------------

class RulingsStore:
    """Rulings live in ``vault/rulings/`` (human-readable, grepable) and are
    mirrored into ``state/rulings.json`` (the governed source of truth for
    Core's enforcement). One correction, two homes.

    Every agent reads the rulings folder before working. A correction becomes
    permanent instead of repeated.
    """

    def __init__(self) -> None:
        self._mirror: list[dict[str, Any]] = []
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        if RULINGS_MIRROR.exists():
            self._mirror = json.loads(RULINGS_MIRROR.read_text(encoding="utf-8"))

    def add(self, text: str) -> dict[str, Any]:
        ruling = {
            "id": f"rul-{uuid.uuid4().hex[:8]}",
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "text": text,
            "added_by": "human",
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
        self._mirror.append(ruling)
        RULINGS_MIRROR.write_text(json.dumps(self._mirror, ensure_ascii=False, indent=2), encoding="utf-8")
        # write to the Obsidian rulings folder as one dated line
        _write_ruling_to_vault(ruling)
        return ruling

    def list(self) -> list[dict[str, Any]]:
        return list(self._mirror)

    def list_vault(self) -> list[dict[str, Any]]:
        """Return rulings as they appear in the vault (file, line, text)."""
        return [{"file": r["id"], "date": r["date"], "text": r["text"]} for r in self._mirror]

    def grep(self, topic: str) -> list[dict[str, Any]]:
        topic_lower = topic.lower()
        return [r for r in self._mirror if topic_lower in r["text"].lower()]


def _write_ruling_to_vault(ruling: dict[str, Any]) -> None:
    RULINGS_DIR.mkdir(parents=True, exist_ok=True)
    p = RULINGS_DIR / f"{ruling['date']}.md"
    existing = p.read_text(encoding="utf-8") if p.exists() else ""
    line = f"- {ruling['date']} — {ruling['text']}\n"
    if line in existing:
        return
    p.write_text(existing + line, encoding="utf-8")


# ---------------------------------------------------------------------------
# Core — the governor.
# ---------------------------------------------------------------------------

class Core:
    """The governor of the platform. Owns the trigger registry, the approval
    gate, the permission layer, the rulings store, the audit log, and the agent
    lifecycle. Agents are workers; Core is the process manager."""

    def __init__(self) -> None:
        ensure_dirs()
        self.triggers = TriggerRegistry()
        register_defaults(self.triggers)
        self.harness_registry = HarnessRegistry()
        self.harness_registry.register(HarnessRegistration(
            capability="signal-outbound",
            version="0.1.0",
            harness=__import__("gravita_gtm.ghc", fromlist=["default_signal_outbound_harness"]).default_signal_outbound_harness(),
            enabled_for=["default"],
            risk_class="medium",
            placement_profile="shared",
            release="stable",
            notes="The harness for the signal-outbound workflow. ASK_FIRST for send.",
        ))
        self.agents = AgentLifecycle()
        self.rulings = RulingsStore()
        self.compiler = Compiler(self.harness_registry)

    # ------------------------------------------------------------------
    # Harness resolution.
    # ------------------------------------------------------------------

    def _resolve_harness(self, capability: str, workspace: str) -> GHC:
        reg = self.harness_registry.for_capability(
            capability, tenant=workspace, risk_class="medium",
            placement_profile="shared", release="stable",
        )
        if reg is not None:
            return reg.harness
        from gravita_gtm.ghc import default_signal_outbound_harness
        if capability == "signal-outbound":
            return default_signal_outbound_harness()
        return GHC(
            capability=capability,
            version="0.1.0",
            identity={"tenant_scope": "workspace", "workload_identity": True},
            context={"allowed_sources": [], "memory_policy": "read vault first"},
            tools=__import__("gravita_gtm.ghc", fromlist=["ToolAllowlist"]).ToolAllowlist(),
            policy={"risk_class": "medium", "approval": "ask-first"},
            runtime={"adapter": "deterministic", "fallbacks": []},
        )

    # ------------------------------------------------------------------
    # Run a capability — the main entry point.
    # ------------------------------------------------------------------

    def run(self, capability: str, top_n: int | None = None,
            event: dict[str, Any] | None = None,
            workspace: str = "default", channel: str = "outbound",
            harness: GHC | None = None) -> Artifact:
        """Run a capability through its harness + runtime adapter.

        The agent lifecycle starts, the compiler resolves the harness, the
        runtime adapter executes, the artifact is held at the gate, and the
        agent lifecycle finishes. Nothing sends. Nothing publishes. Nothing
        spends. The artifact is PENDING.
        """
        harness = self._resolve_harness(capability, workspace)

        run_id = self.agents.start(capability, harness, workspace, channel)

        adapter = adapter_for(harness)
        ctx = {
            "trigger_kind": "manual" if top_n else "calendar",
            "workspace": workspace,
            "channel": channel,
            "top_n": top_n,
            "event": event,
        }
        artifact = adapter.execute(harness, ctx)

        self.agents.finish(run_id, artifact.id)
        return artifact

    # ------------------------------------------------------------------
    # Approval gate — SEND / PUBLISH / SPEND / HUMAN-ALWAYS.
    # ------------------------------------------------------------------

    def pending(self) -> list[dict[str, Any]]:
        """Return pending artifacts awaiting approval."""
        return read_pending()

    def approve(self, artifact_id: str) -> Artifact | None:
        """Flip a pending artifact to APPROVED. The artifact has shipped."""
        return approve_pending(artifact_id)

    def hold(self, artifact_id: str) -> None:
        """Hold a pending artifact for review/edit. It stays in the queue."""
        pending = read_pending()
        item = next((x for x in pending if x["id"] == artifact_id), None)
        if item is None:
            return
        item["status"] = "held"
        PENDING_ARTIFACTS.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # Rulings.
    # ------------------------------------------------------------------

    def add_ruling(self, text: str) -> dict[str, Any]:
        return self.rulings.add(text)

    def list_rulings(self) -> list[dict[str, Any]]:
        return self.rulings.list_vault()

    def grep_rulings(self, topic: str) -> list[dict[str, Any]]:
        return self.rulings.grep(topic)

    # ------------------------------------------------------------------
    # Query — rulings + vault, in one call.
    # ------------------------------------------------------------------

    def query(self, topic: str, console=None) -> None:
        """Grep rulings and the vault for a topic. Prints results."""
        rulings = self.rulings.grep(topic)
        if console:
            console.print(f"[bold]rulings matching '{topic}' ({len(rulings)}):[/bold]")
            for r in rulings:
                console.print(f"  [dim]{r['date']}[/dim]  {r['text']}")
        notes = self._vault_search(topic)
        if console and notes:
            console.print(f"\n[bold]vault notes matching '{topic}' ({len(notes)}):[/bold]")
            for n in notes[:12]:
                console.print(f"  [cyan]{n['path']}[/cyan]  {n['snippet']}")

    def _vault_search(self, topic: str) -> list[dict[str, Any]]:
        """Search vault notes for a topic. Phase 1: grep; later: semantic."""
        results: list[dict[str, Any]] = []
        for p in VAULT_DIR.rglob("*.md"):
            if p.is_file():
                text = p.read_text(encoding="utf-8")
                if topic.lower() in text.lower():
                    snippet = text.replace("\n", " ")[:120]
                    results.append({"path": str(p.relative_to(VAULT_DIR)), "snippet": snippet})
        return results

    # ------------------------------------------------------------------
    # Audit — recent entries.
    # ------------------------------------------------------------------

    def audit_recent(self, n: int = 20) -> list[dict[str, Any]]:
        p = AUDIT_LEDGER
        if not p.exists():
            return []
        lines = p.read_text(encoding="utf-8").splitlines()
        entries = [json.loads(line) for line in lines if line.strip()]
        return entries[-n:]


# ---------------------------------------------------------------------------
# Boot — everything is created at import; calling Core() wires it.
# ---------------------------------------------------------------------------

def boot() -> Core:
    """Boot the platform. Creates directories, registers triggers and harnesses,
    instantiates the rulings store and the audit ledger."""
    return Core()
