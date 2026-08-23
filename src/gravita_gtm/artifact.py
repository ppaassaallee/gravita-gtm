"""Artifact model — the thing a harness produces and the gate holds.

Phase 1: one artifact per capability run, held at the approval gate (PENDING).
Later phases: multiple artifacts, streaming, live artifacts in the UX surface.

Reference: Gravita Architecture v0.4 — Experience Surface (live artifacts),
Cybersecurity & Trust Fabric (evidence/audit), and the GTM guide's seat
(drafts held at the gate, confidence note per row).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ArtifactStatus(Enum):
    PENDING = "pending"         # held at the approval gate
    APPROVED = "approved"       # human flipped it; ready to send/publish/spend
    HELD = "held"               # human held it for review/edit
    SENT = "sent"               # shipped (recorded in audit ledger + vault)


@dataclass
class Artifact:
    """The thing a harness produces and the gate holds.

    Every artifact carries:
    - capability: which workflow produced it
    - status: where it is in the gate lifecycle
    - content: the actual artifact — research sheet, draft message, numbers
      summary, proposal link, content batch, placement sheet, win-back draft.
      JSON-serializable.
    - confidence: per-row or per-artifact confidence note. Bad research shows
      itself before it reaches you.
    - decision_evidence: what the harness read, what it decided, why. Traceable
      intent -> harness -> decision -> tool -> execution -> evidence.
    - created_at, approved_at: timestamps.
    """
    capability: str
    status: ArtifactStatus = ArtifactStatus.PENDING
    content: dict[str, Any] = field(default_factory=dict)
    confidence: list[dict[str, Any]] = field(default_factory=list)
    decision_evidence: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    approved_at: str | None = None
    id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "capability": self.capability,
            "status": self.status.value,
            "content": self.content,
            "confidence": self.confidence,
            "decision_evidence": self.decision_evidence,
            "created_at": self.created_at,
            "approved_at": self.approved_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Artifact:
        return cls(
            id=d.get("id", ""),
            capability=d.get("capability", ""),
            status=ArtifactStatus(d.get("status", "pending")),
            content=d.get("content", {}),
            confidence=d.get("confidence", []),
            decision_evidence=d.get("decision_evidence", {}),
            created_at=d.get("created_at", ""),
            approved_at=d.get("approved_at"),
        )
