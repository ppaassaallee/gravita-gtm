"""Harness Registry — the stable boundary between the control plane and the
runtime. Every capability is registered once, with a version and the harness
that implements it. The runtime never looks up "the signal-outbound agent by
name"; it requests a capability and the registry resolves it.

Reference: Gravita Architecture v0.4, section 3.3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from gravita_gtm.ghc import GHC


@dataclass
class HarnessRegistration:
    """A capability + the harness version that implements it, for a given
    tenant/workspace/risk class/placement profile/release."""
    capability: str
    version: str
    harness: GHC
    enabled_for: list[str] = field(default_factory=list)  # tenant/workspace ids
    risk_class: str = "low"
    placement_profile: str = "shared"
    release: str = "stable"
    notes: str = ""


class HarnessRegistry:
    """In-memory registry for Phase 1. Backed by a real store (PostgreSQL or
    the artifact registry) in later phases. The registry is the source of truth
    for "which harness is enabled for this tenant, workspace, risk class, and
    release right now."
    """

    def __init__(self) -> None:
        self._regs: dict[str, HarnessRegistration] = {}

    def register(self, reg: HarnessRegistration) -> None:
        key = f"{reg.capability}@{reg.version}"
        self._regs[key] = reg

    def list(self) -> list[HarnessRegistration]:
        return list(self._regs.values())

    def for_capability(
        self,
        capability: str,
        tenant: str = "default",
        workspace: str = "default",
        risk_class: str = "low",
        placement_profile: str = "shared",
        release: str = "stable",
    ) -> HarnessRegistration | None:
        """Resolve which harness version is enabled for the given context.

        In Phase 1 this returns the latest registered version of the capability
        that is enabled for the tenant/workspace. Later phases add full
        risk-class, placement-profile, and release filtering.
        """
        candidates = [
            r for r in self._regs.values()
            if r.capability == capability
            and tenant in r.enabled_for
            and r.risk_class == risk_class
            and r.placement_profile == placement_profile
            and r.release == release
        ]
        if not candidates:
            return None
        # latest version wins
        candidates.sort(key=lambda r: r.version, reverse=True)
        return candidates[0]
