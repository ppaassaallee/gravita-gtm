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
    """The harness for the signal-outbound workflow (first playbook). One
    capability, one approval mode (ASK_FIRST for send), one adapter, the
    first-playbook tool chain:
      sourcing: Ocean.io / Apollo / Instant Data Scraper / Google Maps+Serper / OpenWeb Ninja
      company-research: Firecrawl / Exa / Serper
      contact-enrichment: BlitzAPI + waterfall (LeadMagic → Prospeo → IcyPeas → Trykitt)
      sequencing: EmailBison (+ PlusVibe backup, Porkbun/Name.com domains, ScaledMail inboxes)
      The gate (ASK_FIRST for send) holds the EmailBison send; drafts are auto-run.
    """
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
                "cap:sourcing",
                "cap:company-research",
                "cap:contact-enrichment",
            ],
            "memory_policy": "read vault first; context = relevant folders + rulings + account note",
        },
        tools=ToolAllowlist(
            allow=[
                "cap:sourcing",
                "cap:company-research",
                "cap:contact-enrichment",
                "cap:sequencing-draft",
                "cap:reasoning",
            ],
            deny=["cap:sequencing-send"],  # sending is the gate, not the harness
        ),
        policy={
            "risk_class": "medium",
            "approval": "ask-first",  # drafts are auto-run; sends stop at the gate
        },
        runtime={"adapter": "deterministic", "fallbacks": []},
        budgets=Budgets(time_seconds=120, tokens=4000, cost_usd=None),
        evaluation={"suites": ["confidence-note-per-row", "no-pitch-first-line", "verified-email-per-row"]},
        observability=Observability(trace=True, decision_evidence=True),
    )


def default_company_research_harness() -> GHC:
    """Reads the sourced accounts, taps Firecrawl/Exa/Serper to understand
    who each company is (scraped pages, semantic hits, site-specific lookups).
    Outputs researched companies with what they do / sell / what's happening.
    Auto-run; feeds the contact enrichment layer."""
    return GHC(
        capability="company-research",
        version="0.1.0",
        identity={"tenant_scope": "workspace", "workload_identity": True},
        context={
            "allowed_sources": [
                "cap:sourcing",
                "cap:company-research",
            ],
            "memory_policy": "read sourced accounts first; context = researched companies",
        },
        tools=ToolAllowlist(
            allow=["cap:firecrawl", "cap:exa", "cap:serper"],
            deny=["cap:contact-enrich", "cap:sequencing-send"],
        ),
        policy={"risk_class": "low", "approval": "auto-run"},
        runtime={"adapter": "deterministic", "fallbacks": []},
        budgets=Budgets(time_seconds=90, tokens=2000, cost_usd=None),
        evaluation={"suites": ["scraped-per-company", "confidence-note-per-row"]},
        observability=Observability(trace=True, decision_evidence=True),
    )


def default_contact_enrichment_harness() -> GHC:
    """Inputs researched companies, taps BlitzAPI (primary) + waterfall
    (LeadMagic → Prospeo → IcyPeas → Trykitt) for verified work emails.
    Rows without a verified email are low-confidence — folded and dimmed,
    never drafted, never sent. This is where Christian's 'bounce rate'
    failure gets caught by the confidence-note-per-row habit."""
    return GHC(
        capability="contact-enrichment",
        version="0.1.0",
        identity={"tenant_scope": "workspace", "workload_identity": True},
        context={
            "allowed_sources": [
                "cap:company-research",
                "cap:contact-enrichment",
            ],
            "memory_policy": "read researched companies first; context = verified contacts",
        },
        tools=ToolAllowlist(
            allow=[
                "cap:blitzapi",
                "cap:leadmagic",
                "cap:prospeo",
                "cap:icyPeas",
                "cap:trykitt",
            ],
            deny=["cap:sequencing-send"],
        ),
        policy={"risk_class": "medium", "approval": "auto-run"},
        runtime={"adapter": "deterministic", "fallbacks": []},
        budgets=Budgets(time_seconds=60, tokens=1500, cost_usd=None),
        evaluation={"suites": ["verified-email-per-row", "confidence-note-per-row"]},
        observability=Observability(trace=True, decision_evidence=True),
    )


def default_sequencing_harness() -> GHC:
    """Inputs verified contacts, drafts sequences (EmailBison / PlusVibe),
    spintax + conditional logic + reply detection. Drafts are auto-run;
    sends stop at the gate (ASK_FIRST). The seat's provisioned domains
    (Porkbun / Name.com) and inboxes (ScaledMail) are the infrastructure."""
    return GHC(
        capability="sequencing",
        version="0.1.0",
        identity={"tenant_scope": "workspace", "workload_identity": True},
        context={
            "allowed_sources": [
                "cap:contact-enrichment",
                "cap:sequencing",
            ],
            "memory_policy": "read verified contacts first; context = sequences",
        },
        tools=ToolAllowlist(
            allow=["cap:emailbison-draft", "cap:plusvibe-draft"],
            deny=["cap:emailbison-send", "cap:plusvibe-send"],
        ),
        policy={"risk_class": "high", "approval": "ask-first"},
        runtime={"adapter": "deterministic", "fallbacks": []},
        budgets=Budgets(time_seconds=30, tokens=800, cost_usd=None),
        evaluation={"suites": ["no-pitch-first-line", "confidence-note-per-row"]},
        observability=Observability(trace=True, decision_evidence=True),
    )


def default_send_harness() -> GHC:
    """The send capability — denied by default. Only the gate unlocks it
    per approved artifact. EmailBison / PlusVibe send through the seat's
    provisioned domains (Porkbun / Name.com) and inboxes (ScaledMail).
    Nothing sends without your approval."""
    return GHC(
        capability="send",
        version="0.1.0",
        identity={"tenant_scope": "workspace", "workload_identity": True},
        context={
            "allowed_sources": ["cap:sequencing"],
            "memory_policy": "read approved sequences first",
        },
        tools=ToolAllowlist(
            allow=["cap:emailbison-send", "cap:plusvibe-send"],
            deny=[],
        ),
        policy={"risk_class": "high", "approval": "ask-first"},
        runtime={"adapter": "deterministic", "fallbacks": []},
        budgets=Budgets(time_seconds=20, tokens=400, cost_usd=None),
        evaluation={"suites": ["approved-artifact-required"]},
        observability=Observability(trace=True, decision_evidence=True),
    )


def default_multi_channel_harness() -> GHC:
    """Multi-channel (HeyReach / Trigify / Calendly) gated by signal score.
    Accounts scoring 50+ get the multi-channel harness; below threshold,
    email-only. Spending a LinkedIn touch on a low-signal account is effort
    you could point at a better one."""
    return GHC(
        capability="multi-channel",
        version="0.1.0",
        identity={"tenant_scope": "workspace", "workload_identity": True},
        context={
            "allowed_sources": ["cap:reasoning (signal scoring)"],
            "memory_policy": "read signal scores first; context = accounts 50+",
        },
        tools=ToolAllowlist(
            allow=["cap:heyreach", "cap:trigify", "cap:calendly"],
            deny=[],
        ),
        policy={"risk_class": "medium", "approval": "ask-first"},
        runtime={"adapter": "deterministic", "fallbacks": []},
        budgets=Budgets(time_seconds=30, tokens=500, cost_usd=None),
        evaluation={"suites": ["signal-score-50-plus-required"]},
        observability=Observability(trace=True, decision_evidence=True),
    )


def default_close_layer_harness() -> GHC:
    """Reply routing: OutboundSync pushes every replying lead from EmailBison
    into the CRM the second it happens; Slack + webhook pages the rep inside
    5 minutes; n8n is the automation backbone. Speed to lead is the whole
    point — the audit ledger traces T+0 → T+0 → T+0 → T+X."""
    return GHC(
        capability="close-layer",
        version="0.1.0",
        identity={"tenant_scope": "workspace", "workload_identity": True},
        context={
            "allowed_sources": ["cap:sequencing (replies)"],
            "memory_policy": "read replies first; context = routed leads",
        },
        tools=ToolAllowlist(
            allow=["cap:outboundsync", "cap:slack-webhook", "cap:n8n"],
            deny=[],
        ),
        policy={"risk_class": "high", "approval": "ask-first"},
        runtime={"adapter": "deterministic", "fallbacks": []},
        budgets=Budgets(time_seconds=20, tokens=400, cost_usd=None),
        evaluation={"suites": ["reply-routed-within-5-minutes"]},
        observability=Observability(trace=True, decision_evidence=True),
    )


def default_reasoning_harness() -> GHC:
    """The seat's reasoning layer: Claude Code (GTM strategy, ICP modelling,
    message creation, ABM lead magnets, signal scoring, content production),
    GPT 4.1 mini (cheap binary classification: B2B/B2C, keep/drop, sentiment),
    n8n (automation backbone). Reads the vault; honors the rulings; the gate
    is where its artifacts stop."""
    return GHC(
        capability="reasoning",
        version="0.1.0",
        identity={"tenant_scope": "workspace", "workload_identity": True},
        context={
            "allowed_sources": [
                "vault/offer/product.md",
                "vault/buyers/icp.md",
                "vault/voice/voice.md",
                "vault/workflows/signal-outbound.md",
                "vault/rulings/",
            ],
            "memory_policy": "read vault first; context = relevant folders + rulings",
        },
        tools=ToolAllowlist(
            allow=["cap:claude-code", "cap:gpt-41-mini", "cap:n8n"],
            deny=[],
        ),
        policy={"risk_class": "medium", "approval": "auto-run"},
        runtime={"adapter": "deterministic", "fallbacks": []},
        budgets=Budgets(time_seconds=120, tokens=8000, cost_usd=None),
        evaluation={"suites": ["confidence-note-per-row", "no-pitch-first-line"]},
        observability=Observability(trace=True, decision_evidence=True),
    )
