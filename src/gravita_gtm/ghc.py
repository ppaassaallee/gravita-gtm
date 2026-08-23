"""Grávita Harness Contract (GHC) — the structural unit of the platform.

An agent is model + harness. The model provides cognitive capacity; the harness
provides identity, context, tools, permissions, policies, limits, retries,
evaluation, observability, and lifecycle. The harness is the boundary between
the control plane and the runtime, and it is what makes model, runtime, and
provider swappable without changing the GOS or the vault semantics.

This is the demand-generation specialization of the Gravita GHC. The contract
is stable; the runtime adapter and the tool adapters behind it are swappable.

Reference: Gravita Architecture v0.4, sections 3.1–3.3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ApprovalMode(Enum):
    """The gate mode for a harness. Controls what the agent can do without
    asking and what stops at the approval gate."""
    AUTO_RUN = "auto-run"        # reads and drafts, no question asked
    ASK_FIRST = "ask-first"      # anything that sends/spends stops at the gate
    DISABLED = "disabled"        # never touches the outside, not even to read


class RiskClass(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RuntimeAdapter(str, Enum):
    """Which runtime backs this harness. The adapter is swappable by the
    resolver without changing the GHC or the GOS."""
    LANGGRAPH = "langgraph"
    PYDANTIC = "pydantic"
    TYPED_AGENT = "typed-agent"
    DETERMINISTIC = "deterministic"


@dataclass
class ToolAllowlist:
    """Which capabilities a harness can reference. Agents reference capability
    IDs, not URLs or credentials."""
    allow: list[str] = field(default_factory=list)
    deny: list[str] = field(default_factory=list)

    def allows(self, capability_id: str) -> bool:
        if self.deny and capability_id in self.deny:
            return False
        return not self.allow or capability_id in self.allow


@dataclass
class Budgets:
    """Time, token, and cost budgets for the harness. A runaway agent hits
    these and is cut. Deterministic timeout is separate and lower-level."""
    time_seconds: float | None = None
    tokens: int | None = None
    cost_usd: float | None = None


@dataclass
class Observability:
    trace: bool = True
    decision_evidence: bool = True


@dataclass
class GHC:
    """The Grávita Harness Contract, demand-generation specialization.

    Fields
    -------
    capability : the capability id this harness implements (e.g.
        ``signal-outbound``, ``money-loop``, ``content-batch``).
    version : semver of this harness version.
    identity : tenant scope and workload identity requirement.
    context : which sources the harness may read, and the memory policy that
        governs what context enters, how long it stays, and tenant boundaries.
    tools : capability allowlist and explicit denials. The tools that should
        never reach the outside are in ``deny``.
    policy : risk class and approval mode. The approval mode is the gate.
    runtime : which adapter backs this harness, and what fallbacks exist.
    budgets : time, token, and cost limits.
    evaluation : what suites run before the artifact reaches the gate.
    observability : trace and decision-evidence flags.
    """
    capability: str
    version: str
    identity: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    tools: ToolAllowlist = field(default_factory=ToolAllowlist)
    policy: dict[str, Any] = field(default_factory=dict)
    runtime: dict[str, Any] = field(default_factory=dict)
    budgets: Budgets = field(default_factory=Budgets)
    evaluation: dict[str, Any] = field(default_factory=dict)
    observability: Observability = field(default_factory=Observability)

    # Convenience accessors -------------------------------------------------
    @property
    def approval_mode(self) -> ApprovalMode:
        raw = self.policy.get("approval", "auto-run")
        try:
            return ApprovalMode(raw)
        except ValueError:
            return ApprovalMode.AUTO_RUN

    @property
    def risk_class(self) -> RiskClass:
        raw = self.policy.get("risk_class", "low")
        try:
            return RiskClass(raw)
        except ValueError:
            return RiskClass.LOW

    @property
    def adapter(self) -> RuntimeAdapter:
        raw = self.runtime.get("adapter", "deterministic")
        try:
            return RuntimeAdapter(raw)
        except ValueError:
            return RuntimeAdapter.DETERMINISTIC

    def can_send(self, capability_id: str) -> bool:
        """Can this harness execute a send action for the given capability,
        given the tool allowlist and the approval mode? A harness in ASK_FIRST
        mode can draft but cannot send without the gate."""
        if not self.tools.allows(capability_id):
            return False
        return self.approval_mode != ApprovalMode.DISABLED

    def can_spend(self) -> bool:
        return self.approval_mode == ApprovalMode.ASK_FIRST  # spending always stops


def default_signal_outbound_harness() -> GHC:
    """The harness for the signal-outbound workflow. One capability, one
    approval mode (ASK_FIRST for send), one adapter, one set of allowed
    sources. This is what the resolver returns when you run signal outbound."""
    return GHC(
        capability="signal-outbound",
        version="0.1.0",
        identity={"tenant_scope": "workspace", "workload_identity": True},
        context={
            "allowed_sources": [
                "vault/workflows/signal-outbound.md",
                "vault/buyers/icp.md",
                "vault/offer/product.md",
                "vault/voice/voice.md",
                "vault/rulings/",
                "vault/buyers/accounts/",
                "stub/apollo",
                "stub/clay",
            ],
            "memory_policy": "read vault first; context = relevant folders + rulings + account note",
        },
        tools=ToolAllowlist(
            allow=["cap:apollo-read", "cap:clay-enrich", "cap:sequencer-draft"],
            deny=["cap:sequencer-send"],  # sending is the gate, not the harness
        ),
        policy={
            "risk_class": "medium",
            "approval": "ask-first",  # drafts are auto-run; sends stop at the gate
        },
        runtime={"adapter": "deterministic", "fallbacks": []},
        budgets=Budgets(time_seconds=120, tokens=4000, cost_usd=None),
        evaluation={"suites": ["confidence-note-per-row", "no-pitch-first-line"]},
        observability=Observability(trace=True, decision_evidence=True),
    )
