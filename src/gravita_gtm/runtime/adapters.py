"""Runtime adapters — the things that execute a harness.

In Phase 1 the only adapter is ``deterministic``: a Python worker that runs a
capability through its four-part skeleton (trigger -> source -> artifact ->
gate) and returns an artifact held at the approval gate. LangGraph and
Pydantic AI/Harness are candidates for later phases; the GHC is the boundary
that lets us swap them without changing the GOS or the vault semantics.

Reference: Gravita Architecture v0.4, sections 4 and 21.2.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Protocol

from gravita_gtm.artifact import Artifact, ArtifactStatus
from gravita_gtm.ghc import GHC
from gravita_gtm.runtime.workflows import run_signal_outbound, run_money_loop, run_content_batch


class RuntimeAdapter(Protocol):
    """The protocol every runtime adapter implements. The harness registry
    resolves a GHC + an adapter name; the runtime executes the harness and
    returns an artifact held at the gate."""

    def execute(self, harness: GHC, context: dict[str, Any]) -> Artifact:
        """Run the capability described by the harness, with the given context,
        and return an artifact held at the approval gate (PENDING)."""


def adapter_for(harness: GHC) -> RuntimeAdapter:
    """Pick the runtime adapter for a harness. Phase 1 only has deterministic;
    later phases add langgraph and pydantic and keep the deterministic adapter
    as an escape hatch."""
    name = harness.adapter.value
    if name == "deterministic":
        return DeterministicAdapter()
    raise NotImplementedError(f"no adapter for {name} yet — swap the harness adapter")


class DeterministicAdapter:
    """Phase 1 runtime. Runs a capability through its four-part skeleton and
    returns an artifact held at the gate.

    It is not an agent orchestration framework — it is the execution plumbing
    for capabilities that are expressed as a trigger, a source, an output, and
    a gate. Deterministic workflows (schedules, retries, webhooks, APIs) can
    be materialized through this adapter or through a tool adapter (Kestra,
    n8n, Activepieces, workers) in later phases.
    """

    def execute(self, harness: GHC, context: dict[str, Any]) -> Artifact:
        cap = harness.capability
        if cap == "signal-outbound":
            return run_signal_outbound(harness, context)
        if cap == "money-loop":
            return run_money_loop(harness, context)
        if cap == "content-batch":
            return run_content_batch(harness, context)
        raise NotImplementedError(f"no runner for capability {cap}")
