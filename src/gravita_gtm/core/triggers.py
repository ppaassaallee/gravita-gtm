"""Triggers — what starts a workflow.

A trigger registry maps triggers to capabilities. Core enforces that nothing
fires without its trigger being satisfied. Triggers are: calendar (weekly,
monthly), manual (utterance), webhook (call ends, payment event), threshold
(post crosses engagement threshold), and payment (Stripe event). In Phase 1
these are stubs/simulations; in Phase 3 they are real webhooks and real
calendar ticks.

Reference: Gravita Architecture v0.4, section 2 (Experience Surface /
Operations Cockpit), and the four-part skeleton (trigger -> source -> output -> gate).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable

from gravita_gtm.ghc import GHC


class TriggerKind(Enum):
    CALENDAR = "calendar"
    MANUAL = "manual"
    WEBHOOK = "webhook"
    THRESHOLD = "threshold"
    PAYMENT = "payment"


@dataclass
class Trigger:
    """One trigger that can start a workflow.

    A trigger has a kind, a schedule or condition, the capability it starts,
    the workspace/channel it belongs to, and a handler that produces the
    context the harness needs when the trigger fires.
    """
    id: str
    kind: TriggerKind
    capability: str
    workspace: str = "default"
    channel: str = "outbound"
    schedule: str | None = None          # e.g. "weekly monday 09:00", "monthly"
    condition: str | None = None         # human-readable description of the condition
    handler: Callable[[], dict[str, Any]] | None = None  # produces context on fire
    notes: str = ""


class TriggerRegistry:
    """Maps triggers to capabilities. Core asks: "what triggers are due?" and
    "what capability does this trigger start?" and "fire this trigger". No
    workflow runs unless the trigger registry says its trigger is satisfied."""

    def __init__(self) -> None:
        self._triggers: dict[str, Trigger] = {}

    def register(self, trigger: Trigger) -> None:
        self._triggers[trigger.id] = trigger

    def list(self, workspace: str = "default") -> list[Trigger]:
        return [t for t in self._triggers.values() if t.workspace == workspace]

    def for_capability(self, capability: str) -> list[Trigger]:
        return [t for t in self._triggers.values() if t.capability == capability]

    def due(self, now: datetime | None = None) -> list[Trigger]:
        """Return calendar triggers whose schedule says they are due now.
        Phase 1: all weekly calendar triggers are due on demand (you run them
        manually or on a clock). Phase 3: real schedule evaluation."""
        # Phase 1 simplification: every calendar trigger is "due" when asked.
        # Real scheduling comes with a real clock in Phase 3.
        return [t for t in self._triggers.values()
                if t.kind == TriggerKind.CALENDAR and t.schedule is not None]

    def fire(self, trigger_id: str) -> dict[str, Any]:
        """Fire a trigger and return the context it produces for the harness."""
        t = self._triggers.get(trigger_id)
        if t is None:
            raise KeyError(f"unknown trigger {trigger_id}")
        if t.handler is not None:
            return t.handler()
        return {"trigger_id": trigger_id, "fired_at": datetime.now().isoformat()}


def _manual_signal_outbound_context() -> dict[str, Any]:
    return {"trigger_kind": "manual", "note": "run signal outbound for this week, top 20"}


def _weekly_calendar_signal_outbound() -> dict[str, Any]:
    return {"trigger_kind": "calendar", "schedule": "weekly monday 09:00", "note": "weekly signal outbound"}


def _weekly_calendar_content_batch() -> dict[str, Any]:
    return {"trigger_kind": "calendar", "schedule": "weekly monday 10:00", "note": "weekly content batch"}


def _monthly_calendar_placement_hunt() -> dict[str, Any]:
    return {"trigger_kind": "calendar", "schedule": "monthly first monday", "note": "monthly placement hunt"}


def _manual_content_batch_context() -> dict[str, Any]:
    return {"trigger_kind": "manual", "note": "run the content batch"}


def _monthly_calendar_borrowed_rooms() -> dict[str, Any]:
    return {"trigger_kind": "calendar", "schedule": "monthly first monday", "note": "monthly borrowed rooms"}


def _weekly_calendar_retention() -> dict[str, Any]:
    return {"trigger_kind": "calendar", "schedule": "weekly", "note": "weekly retention loop"}


def _payment_failed_event() -> dict[str, Any]:
    from gravita_gtm.stub.sources import stub_payment_event
    return {"trigger_kind": "payment", "event": stub_payment_event("failed_card", days_ago=2)}


def _payment_canceled_event() -> dict[str, Any]:
    from gravita_gtm.stub.sources import stub_payment_event
    return {"trigger_kind": "payment", "event": stub_payment_event("canceled", days_ago=3)}


def _monthly_calendar_money_loop() -> dict[str, Any]:
    return {"trigger_kind": "calendar", "schedule": "monthly first monday", "note": "monthly money loop"}


def _manual_money_loop_context() -> dict[str, Any]:
    return {"trigger_kind": "manual", "note": "run the money loop"}


def _monthly_calendar_seo_answer_engine() -> dict[str, Any]:
    return {"trigger_kind": "calendar", "schedule": "monthly first monday", "note": "monthly seo / answer engine"}


def register_defaults(registry: TriggerRegistry) -> None:
    """Register the standard GTM triggers. One per workflow, plus manual
    variants. In Phase 1 these are stubs; in Phase 3 the calendar ones become
    real schedules and the webhook/payment ones become real webhooks."""
    registry.register(Trigger(
        id="signal-outbound.weekly", kind=TriggerKind.CALENDAR,
        capability="signal-outbound", workspace="default", channel="outbound",
        schedule="weekly monday 09:00", condition="Every Monday 09:00 in workspace TZ",
        handler=_weekly_calendar_signal_outbound,
        notes="The workflow that moves revenue first for an agency.",
    ))
    registry.register(Trigger(
        id="signal-outbound.manual", kind=TriggerKind.MANUAL,
        capability="signal-outbound", workspace="default", channel="outbound",
        condition="You say 'run signal outbound for this week, top N'",
        handler=_manual_signal_outbound_context,
    ))
    registry.register(Trigger(
        id="content-batch.weekly", kind=TriggerKind.CALENDAR,
        capability="content-batch", workspace="default", channel="content",
        schedule="weekly monday 10:00", condition="Every Monday 10:00",
        handler=_weekly_calendar_content_batch,
        notes="The week's content from receipts, not guesses.",
    ))
    registry.register(Trigger(
        id="content-batch.manual", kind=TriggerKind.MANUAL,
        capability="content-batch", workspace="default", channel="content",
        condition="You say 'run the content batch'",
        handler=_manual_content_batch_context,
    ))
    registry.register(Trigger(
        id="placement-hunt.monthly", kind=TriggerKind.CALENDAR,
        capability="placement-hunt", workspace="default", channel="content",
        schedule="monthly first monday", condition="First Monday of the month",
        handler=_monthly_calendar_placement_hunt,
        notes="Borrow your competitors' placements.",
    ))
    registry.register(Trigger(
        id="retention.weekly", kind=TriggerKind.CALENDAR,
        capability="retention", workspace="default", channel="pipeline",
        schedule="weekly", condition="Weekly during ramp, monthly after",
        handler=_weekly_calendar_retention,
        notes="Keep clients past the first quarter.",
    ))
    registry.register(Trigger(
        id="money-loop.monthly", kind=TriggerKind.CALENDAR,
        capability="money-loop", workspace="default", channel="pipeline",
        schedule="monthly first monday", condition="First Monday of the month",
        handler=_monthly_calendar_money_loop,
        notes="The workflow everyone sets up last and should set up first.",
    ))
    registry.register(Trigger(
        id="money-loop.manual", kind=TriggerKind.MANUAL,
        capability="money-loop", workspace="default", channel="pipeline",
        condition="You say 'run the money loop'",
        handler=_manual_money_loop_context,
    ))
    registry.register(Trigger(
        id="money-loop.payment-failed", kind=TriggerKind.PAYMENT,
        capability="money-loop", workspace="default", channel="pipeline",
        condition="A payment failed (Stripe webhook)",
        handler=_payment_failed_event,
    ))
    registry.register(Trigger(
        id="money-loop.payment-canceled", kind=TriggerKind.PAYMENT,
        capability="money-loop", workspace="default", channel="pipeline",
        condition="A customer canceled (Stripe webhook)",
        handler=_payment_canceled_event,
    ))
    registry.register(Trigger(
        id="borrowed-rooms.monthly", kind=TriggerKind.CALENDAR,
        capability="borrowed-rooms", workspace="default", channel="content",
        schedule="monthly first monday", condition="First Monday of the month",
        handler=_monthly_calendar_borrowed_rooms,
        notes="The rooms your audience already sits in.",
    ))
    registry.register(Trigger(
        id="seo-answer-engine.monthly", kind=TriggerKind.CALENDAR,
        capability="seo-answer-engine", workspace="default", channel="content",
        schedule="monthly first monday", condition="First Monday of the month",
        handler=_monthly_calendar_seo_answer_engine,
        notes="Entity consistency, answer blocks, mentions, third-party hosts.",
    ))
