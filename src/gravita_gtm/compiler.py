"""Outcome / Operational Compiler v0.1.

The compiler converts a GOS-like intent and its evidence into artifacts a
runtime can execute. In Phase 1 the input is a conversational utterance plus
context; the output is a harness manifest (which GHC + adapter + capability),
a runtime plan (which runner, which source, which top_n / which event), and
the decisions that the gate will enforce (risk class, approval mode, allowed
sources, tool allowlist).

Validation levels to start: L0 schema (is the artifact syntactically valid),
L1 referential (do the referred vault notes, capabilities, harnesses exist?).
Later phases add L2 (semantic), L3 (operational), L4 (business), L5 (compliance/
security), L6 (placement/resilience), L7 (learning safety).

Reference: Gravita Architecture v0.4, sections 5 and 11.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gravita_gtm.ghc import GHC, ApprovalMode, RiskClass, RuntimeAdapter
from gravita_gtm.harness.registry import HarnessRegistry
from gravita_gtm.runtime.adapters import Artifact, ArtifactStatus, adapter_for
from gravita_gtm.config import VAULT_DIR, STATE_DIR, CONFIG_PATH
from gravita_gtm.vault_io import read_note


@dataclass
class CompileInput:
    """What the compiler takes in. Phase 1: a conversational utterance + context.
    Later phases: a full GOS + context + policy packs."""
    intent: str                          # "run signal outbound for this week, top 20"
    capability: str                      # "signal-outbound"
    workspace: str = "default"
    channel: str = "outbound"
    top_n: int | None = None             # optional parameter from the utterance
    event: dict[str, Any] | None = None  # for payment-triggered workflows
    force_stub: bool | None = None       # override STUB_MODE for one run


@dataclass
class HarnessManifest:
    """Which harness (GHC version) + adapter implements the capability for this
    tenant/workspace/risk class/placement profile/release."""
    capability: str
    harness_version: str
    adapter: str
    risk_class: str
    approval_mode: str
    tool_allow: list[str]
    tool_deny: list[str]
    allowed_sources: list[str]


@dataclass
class RuntimePlan:
    """How to run the capability this time. Which runner, which source (stub or
    real), which parameters (top_n, event, etc.), which vault notes to preload."""
    capability: str
    runner: str
    source_mode: str                # "stub" or "real"
    parameters: dict[str, Any]
    vault_preload: list[str]        # notes to read before drafting


@dataclass
class CompileOutput:
    """What the compiler emits. Phase 1: a harness manifest + a runtime plan +
    the decisions the gate enforces. Later phases: placement spec, security
    policies, simulation suites, release manifest."""
    harness_manifest: HarnessManifest
    runtime_plan: RuntimePlan
    decisions: dict[str, Any]        # risk class, approval mode, allowed sources
    validation: list[dict[str, Any]]  # L0, L1 results


class Compiler:
    """Converts intent + capability + context into a harness manifest + runtime
    plan + decisions + validation, ready for the runtime adapter to execute."""

    def __init__(self, registry: HarnessRegistry) -> None:
        self.registry = registry

    def compile(self, inp: CompileInput, harness: GHC | None = None) -> CompileOutput:
        # Resolve the harness. If one wasn't handed in, resolve from the registry.
        if harness is None:
            reg = self.registry.for_capability(
                inp.capability,
                tenant=inp.workspace,
                risk_class="medium",
                placement_profile="shared",
                release="stable",
            )
            if reg is None:
                # Phase 1 fallback: build the default harness for the capability.
                harness = _default_harness_for(inp.capability)
            else:
                harness = reg.harness

        manifest = HarnessManifest(
            capability=inp.capability,
            harness_version=harness.version,
            adapter=harness.adapter.value,
            risk_class=harness.risk_class.value,
            approval_mode=harness.approval_mode.value,
            tool_allow=harness.tools.allow,
            tool_deny=harness.tools.deny,
            allowed_sources=harness.context.get("allowed_sources", []),
        )

        source_mode = "stub" if (inp.force_stub or (inp.force_stub is None and CONFIG_PATH.exists() is False
                                                 )) or _stub_mode_override(inp) else "real"

        # vault preload: the notes the runner reads before drafting
        vault_preload = _vault_preload_for(inp.capability, harness.context.get("allowed_sources", []))

        runtime_plan = RuntimePlan(
            capability=inp.capability,
            runner=_runner_for(inp.capability),
            source_mode=source_mode,
            parameters={
                "top_n": inp.top_n,
                "event": inp.event,
                "workspace": inp.workspace,
                "channel": inp.channel,
            },
            vault_preload=vault_preload,
        )

        decisions = {
            "risk_class": harness.risk_class.value,
            "approval_mode": harness.approval_mode.value,
            "allowed_sources": harness.context.get("allowed_sources", []),
            "tool_allow": harness.tools.allow,
            "tool_deny": harness.tools.deny,
            "approval_required": harness.approval_mode != ApprovalMode.AUTO_RUN,
        }

        validation = _validate(inp, manifest, runtime_plan)

        return CompileOutput(
            harness_manifest=manifest,
            runtime_plan=runtime_plan,
            decisions=decisions,
            validation=validation,
        )

    def execute(self, inp: CompileInput, harness: GHC | None = None) -> Artifact:
        """Compile + run in one step. Returns an artifact held at the gate."""
        output = self.compile(inp, harness)
        # hand the harness to the runtime adapter
        adapter = adapter_for(harness or _default_harness_for(inp.capability))
        # build the context the runner expects
        ctx = dict(inp.__dict__)
        ctx["trigger_kind"] = _infer_trigger_kind(inp)
        return adapter.execute(harness or _default_harness_for(inp.capability), ctx)


def _default_harness_for(capability: str) -> GHC:
    """Phase 1 fallback harness by capability. The registry replaces this once
    it has registrations. The first playbook adds the real tool roles for the
    Christian-on-X 10-million-cold-emails chain."""
    if capability == "signal-outbound":
        from gravita_gtm.ghc import default_signal_outbound_harness
        return default_signal_outbound_harness()
    if capability == "company-research":
        from gravita_gtm.ghc import default_company_research_harness
        return default_company_research_harness()
    if capability == "contact-enrichment":
        from gravita_gtm.ghc import default_contact_enrichment_harness
        return default_contact_enrichment_harness()
    if capability == "sequencing":
        from gravita_gtm.ghc import default_sequencing_harness
        return default_sequencing_harness()
    if capability == "send":
        from gravita_gtm.ghc import default_send_harness
        return default_send_harness()
    if capability == "multi-channel":
        from gravita_gtm.ghc import default_multi_channel_harness
        return default_multi_channel_harness()
    if capability == "close-layer":
        from gravita_gtm.ghc import default_close_layer_harness
        return default_close_layer_harness()
    if capability == "reasoning":
        from gravita_gtm.ghc import default_reasoning_harness
        return default_reasoning_harness()
    # generic fallback
    from gravita_gtm.ghc import GHC, ToolAllowlist
    return GHC(
        capability=capability,
        version="0.1.0",
        identity={"tenant_scope": "workspace", "workload_identity": True},
        context={"allowed_sources": [], "memory_policy": "read vault first"},
        tools=ToolAllowlist(),
        policy={"risk_class": "medium", "approval": "ask-first"},
        runtime={"adapter": "deterministic", "fallbacks": []},
    )


def _runner_for(capability: str) -> str:
    return {
        "signal-outbound": "runtime.workflows.run_signal_outbound",
        "money-loop": "runtime.workflows.run_money_loop",
        "content-batch": "runtime.workflows.run_content_batch",
    }.get(capability, f"runtime.workflows.run_{capability}")


def _vault_preload_for(capability: str, allowed_sources: list[str]) -> list[str]:
    """Which vault notes to preload before drafting, by capability.

    Mirrors the allowed_sources in the GHC but is a readable list the runner
    actually iterates. The runner still reads the workflow note, offer, ICP,
    voice, rulings, and account note on its own.
    """
    base = [
        "offer/product.md",
        "buyers/icp.md",
        "voice/voice.md",
        f"workflows/{capability}.md",
    ]
    # always read rulings
    base.append("rulings/README.md")
    return base


def _infer_trigger_kind(inp: CompileInput) -> str:
    if inp.event is not None:
        return "payment"
    if inp.top_n is not None or "run" in inp.intent.lower():
        return "manual"
    return "calendar"


def _stub_mode_override(inp: CompileInput) -> bool:
    """Force stub mode for one run when asked. Phase 1 always stubs unless the
    force is explicit and False."""
    if inp.force_stub is False:
        return False
    return True


def _validate(inp: CompileInput, manifest: HarnessManifest, plan: RuntimePlan) -> list[dict[str, Any]]:
    """L0 + L1 validation."""
    results: list[dict[str, Any]] = []
    # L0: schema — does the compile output have the required fields?
    schema_ok = all([
        manifest.capability,
        manifest.harness_version,
        manifest.adapter,
        plan.runner,
        plan.source_mode in ("stub", "real"),
    ])
    results.append({"level": "L0", "name": "schema", "status": "pass" if schema_ok else "fail",
                    "detail": "compile output structurally valid" if schema_ok else "compile output missing required fields"})
    # L1: referential — do the referred vault notes exist?
    missing: list[str] = []
    for note in plan.vault_preload:
        p = VAULT_DIR / note
        if not p.exists():
            missing.append(note)
    results.append({"level": "L1", "name": "referential", "status": "pass" if not missing else "warn",
                    "detail": f"vault preload exists" if not missing else f"missing vault notes: {missing}"})
    return results


def compile_and_run(registry: HarnessRegistry, intent: str, capability: str,
                    top_n: int | None = None, event: dict[str, Any] | None = None,
                    workspace: str = "default", channel: str = "outbound",
                    harness: GHC | None = None) -> Artifact:
    """Convenience: compile + run in one call. The main entry point for the
    CLI and the session layer."""
    compiler = Compiler(registry)
    inp = CompileInput(
        intent=intent,
        capability=capability,
        workspace=workspace,
        channel=channel,
        top_n=top_n,
        event=event,
    )
    return compiler.execute(inp, harness)
