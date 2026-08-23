"""Stubbed sources — realisticfake data that exercises every workflow's four-part
skeleton without touching a real API. Phase 1 uses these; Phase 3 replaces them
with real capabilities behind the tool gateway.

The stubs are realistic, not obviously-placeholder, so dry-run artifacts feel
like real artifacts. Every account carries a real signal so the research sheet
looks like one you'd actually review.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

# realistic company names + verticals for dry-run artifacts
COMPANY_NAMES = [
    "Northwind Mercantile", "Acme Logistics Co.", "Brighthouse Media Group",
    "Piedmont Manufacturing", "Redwood Capital Partners", "Coastal Health Systems",
    "Summit Retail Group", "Ironclad Cyber Defense", "Meridian Logistics SA",
    "Cerulean Analytics LLC", "Halcyon Construction Group", "Astral Consulting",
    "Boreal Data Systems", "Kingsbridge Financial", "Lantern Education Partners",
    "Cascade Outdoor Brands", "Northgate Property Group", "Vanguard Health Network",
    "Eastman Hospitality Group", "Solstice Energy Advisors",
]
VERTICALS = [
    "logistics", "manufacturing", "healthcare", "retail", "financial services",
    "construction", "education", "energy", "hospitality", "data services",
]

# signal set — every account gets exactly one, so the research sheet reads like
# one you'd review rather than a column of "No clear signal".
SIGNALS = [
    {"type": "funding", "detail": "raised Series B, $25M"},
    {"type": "funding", "detail": "raised seed, $3M"},
    {"type": "hiring", "detail": "hiring 3 SDRs / BDRs"},
    {"type": "hiring", "detail": "hiring a head of demand generation"},
    {"type": "hiring", "detail": "hiring a VP of sales"},
    {"type": "owner", "detail": "new CEO appointed 6 weeks ago"},
    {"type": "owner", "detail": "new CMO appointed 3 weeks ago"},
    {"type": "stale", "detail": "website last updated 14 months ago"},
    {"type": "stale", "detail": "blogs dormant for 11 months"},
]


@dataclass
class StubAccount:
    name: str
    vertical: str
    website: str
    employees: int
    last_funded: str | None = None
    recent_hire: str | None = None
    stale_since: str | None = None
    new_owner_since: str | None = None
    spend_range: str = "$50k-$200k"
    contact: str = ""


def stub_accounts(n: int = 40, seed: int = 7) -> list[StubAccount]:
    """Return N realisticfake accounts filtered to a client profile (ICP).
    Every returned account carries exactly one real signal — funding, hiring,
    new owner, or stale site — so the research sheet reads like one you'd
    review rather than a column of 'No clear signal'."""
    rng = random.Random(seed)
    accounts: list[StubAccount] = []
    for i in range(n):
        name = COMPANY_NAMES[(i + seed) % len(COMPANY_NAMES)]
        vertical = VERTICALS[(i + seed) % len(VERTICALS)]
        years = rng.choice([3, 5, 8, 12, 15, 20, 30, 50, 80, 120])
        employees = int(years * rng.uniform(1.5, 4))
        spend_range = rng.choice(["$50k-$200k", "$200k-$500k", "$500k-$1M", ">$1M"])
        # exactly one signal per account — deterministic per index, not per random draw
        signal = SIGNALS[(i + seed) % len(SIGNALS)]
        last_funded = None
        recent_hire = None
        stale_since = None
        new_owner_since = None
        if signal["type"] == "funding":
            last_funded = signal["detail"]
        elif signal["type"] == "hiring":
            recent_hire = signal["detail"]
        elif signal["type"] == "stale":
            stale_since = signal["detail"]
        elif signal["type"] == "owner":
            new_owner_since = signal["detail"]
        accounts.append(StubAccount(
            name=name,
            vertical=vertical,
            website=f"https://{name.lower().replace(' ', '').replace('.', '')}.com",
            employees=employees,
            last_funded=last_funded,
            recent_hire=recent_hire,
            stale_since=stale_since,
            new_owner_since=new_owner_since,
            spend_range=spend_range,
            contact=f"{rng.choice(['j', 'm', 'k', 's', 'a'])}.{rng.choice(['smith', 'jones', 'lee', 'nguyen', 'patel', 'garcia', 'wong', 'martinez'])}@{name.lower().replace(' ', '').replace('.', '')}com",
        ))
    # filter to ICP: 50-500 employees, relevant verticals
    icp_verticals = {"logistics", "manufacturing", "healthcare", "retail", "financial services", "construction", "energy"}
    return [a for a in accounts if a.vertical in icp_verticals and 50 <= a.employees <= 500]


def stub_clay_enrichment(account: StubAccount, providers: int = 3) -> dict[str, Any]:
    """Simulate a Clay enrichment waterfall: fill empty fields provider by
    provider, drop weak rows, return confidence per field."""
    row: dict[str, Any] = {
        "company": account.name,
        "vertical": account.vertical,
        "employees": account.employees,
        "spend_range": account.spend_range,
        "website": account.website,
        "what_changed": None,
        "what_you_see": None,
        "what_your_service_fixes": None,
        "confidence": {},
    }
    # fill what_changed from the one signal each account carries
    if account.last_funded:
        row["what_changed"] = f"Funding: {account.last_funded}"
        row["confidence"]["what_changed"] = "high"
    elif account.recent_hire:
        row["what_changed"] = f"Hiring: {account.recent_hire}"
        row["confidence"]["what_changed"] = "high"
    elif account.new_owner_since:
        row["what_changed"] = f"New owner: {account.new_owner_since}"
        row["confidence"]["what_changed"] = "high"
    elif account.stale_since:
        row["what_changed"] = f"Stale site: {account.stale_since}"
        row["confidence"]["what_changed"] = "medium"
    else:
        row["what_changed"] = "No clear signal"
        row["confidence"]["what_changed"] = "low"

    # fill what_you_see (the workload your service fixes) from vertical + signal
    if account.vertical == "logistics":
        row["what_you_see"] = "No owned demand channel; pipeline flat QoQ; no SDR coverage visible"
        row["confidence"]["what_you_see"] = "medium"
        row["what_your_service_fixes"] = "A researched outbound engine that turns their ICP into conversations, held at your approval gate."
    elif account.vertical == "manufacturing":
        row["what_you_see"] = "No content cadence; case studies from 18 months ago; no follow-up to engaged readers"
        row["confidence"]["what_you_see"] = "medium"
        row["what_your_service_fixes"] = "A content batch and warm-outbound loop that turns their existing readers into a pipeline."
    elif account.vertical == "healthcare":
        row["what_you_see"] = "Enterprise sales cycle no foothold content; buyer personas undocumented"
        row["confidence"]["what_you_see"] = "low"
        row["what_your_service_fixes"] = "Market-map research and a content cadence aimed at the buyers they need to reach."
    elif account.spend_range in ("$500k-$1M", ">$1M"):
        row["what_you_see"] = "Large budget, no visible outbound motion; running on referrals and inbound alone"
        row["confidence"]["what_you_see"] = "medium"
        row["what_your_service_fixes"] = "Signal outbound that turns their visible changes into researched first touches."
    else:
        row["what_you_see"] = "No owned demand channel visible; pipeline reliant on inbound"
        row["confidence"]["what_you_see"] = "medium"
        row["what_your_service_fixes"] = "A governed demand-generation workflow that reads from your vault and drafts held at your approval gate."

    # enrich by provider waterfall: provider1 fills most, provider2 fills gaps, provider3 fills the rest
    for provider in range(1, providers + 1):
        if row["what_changed"] is None and provider == 1:
            row["what_changed"] = "No clear signal"
            row["confidence"]["what_changed"] = "low"
        if row["what_you_see"] is None and provider <= 2:
            row["what_you_see"] = "No owned demand channel visible; pipeline reliant on inbound"
            row["confidence"]["what_you_see"] = "medium"
        if row.get("what_your_service_fixes") is None and provider == 3:
            row["what_your_service_fixes"] = "A governed demand-generation workflow that reads from your vault and drafts held at your approval gate."
            row["confidence"]["what_your_service_fixes"] = "low"

    # drop weak rows: no signal and low confidence on what_you_see
    if row["confidence"].get("what_changed") == "low" and row["confidence"].get("what_you_see") == "low":
        row["dropped"] = True
    else:
        row["dropped"] = False

    return row


def stub_transcript(buying_signal: bool = True) -> dict[str, Any]:
    """A realisticfake call transcript with or without a buying signal."""
    if buying_signal:
        return {
            "summary": "Discovery call with Northwind Mercantile. Buyer confirmed scope: 8-week outbound ramp, ICP research, weekly content batch. Agreed on $18k for the first quarter. Start date discussed: first Monday of next month. Decision maker present. Procurement to follow.",
            "price_agreed": "$18k first quarter",
            "scope_asked": "8-week outbound ramp + ICP research + weekly content batch",
            "start_date_discussed": "first Monday of next month",
            "decision_maker_present": True,
            "buying_signal": True,
        }
    return {
        "summary": "Discovery call with Coastal Health Systems. Buyer exploring options; no price discussed; scope vague. Will think about it and loop back. No decision maker on the call.",
        "price_agreed": None,
        "scope_asked": None,
        "start_date_discussed": None,
        "decision_maker_present": False,
        "buying_signal": False,
    }


def stub_payment_event(outcome: str = "failed_card", days_ago: int = 2) -> dict[str, Any]:
    """A realisticfake payment event for the money loop."""
    now = datetime.now()
    event_date = now - timedelta(days=days_ago)
    customer = random.choice(COMPANY_NAMES).lower().replace(" ", "")
    if outcome == "failed_card":
        return {
            "type": "payment.failed",
            "customer": customer,
            "customer_name": customer.title(),
            "amount": random.choice([18000, 12000, 24000, 9000]),
            "failure_reason": random.choice(["card_expired", "insufficient_funds", "declined_by_issuer"]),
            "status": "retrying",
            "event_date": event_date.isoformat(),
            "churn_bucket": "card_failed",
        }
    return {
        "type": "customer.canceled",
        "customer": customer,
        "customer_name": customer.title(),
        "plan": "growth",
        "mrr": random.choice([12000, 18000, 24000]),
        "cancellation_reason": random.choice(["too_expensive", "not_using_it", "moved_to_inhouse", "couldnt_get_team_to_adopt"]),
        "exit_survey_answer": random.choice(["We went with an in-house hire", "Too expensive for the stage", "We are not using it enough to justify"]),
        "status": "win-back-draft-pending",
        "event_date": event_date.isoformat(),
        "churn_bucket": "chose_to_leave",
    }


def stub_top_posts(platform: str = "linkedin") -> list[dict[str, Any]]:
    """Realisticfake top posts for the content batch and owned-email triggers."""
    posts = [
        {"platform": "linkedin", "headline": "The three things a one-person sales team stops doing after month two", "engagement": 48, "comments": 12, "reposts": 5, "type": "post"},
        {"platform": "linkedin", "headline": "Signal outbound: the message that opens with what changed at their business", "engagement": 72, "comments": 19, "reposts": 8, "type": "post"},
        {"platform": "linkedin", "headline": "We ran signal outbound for four weeks. Here's the message that got the reply.", "engagement": 110, "comments": 27, "reposts": 11, "type": "post"},
        {"platform": "email", "headline": "The case study one client asked to see before they signed", "opens": 61, "clicks": 18, "type": "email"},
        {"platform": "linkedin", "headline": "Warm outbound: why you send the engaged list by hand", "engagement": 34, "comments": 9, "reposts": 3, "type": "post"},
    ]
    return posts


def stub_engagement_export(post: dict[str, Any], n_engagers: int = 35) -> list[dict[str, Any]]:
    """Realisticfake list of people who engaged with a post, some of whom match
    the ICP and some of whom don't."""
    rng = random.Random(hash(post["headline"]) % 1000)
    first_names = ["Alejandro", "Maria", "Chen", "Priya", "Daniel", "Fatima", "James", "Yuki", "Sofia", "Omar", "Lena", "Ravi", "Ingrid", "Hugo", "Nadia"]
    last_names = ["Pascual", "Reyes", "Wang", "Sharma", "Müller", "Okafor", "Kim", "Johansson", "Silva", "Kozlov", "Bennett", "Castro", "Andersson", "Tran", "Moreau"]
    icp_jobs = ["Head of Demand Generation", "VP Sales", "CEO", "Founder", "Director of Marketing", "Head of Growth"]
    non_icp_jobs = ["Intern", "Analyst", "Engineer", "Designer", "HR Coordinator", "Office Manager"]
    engagers: list[dict[str, Any]] = []
    for i in range(n_engagers):
        is_icp = rng.random() < 0.4
        job = icp_jobs if is_icp else non_icp_jobs
        engagers.append({
            "name": f"{rng.choice(first_names)} {rng.choice(last_names)}",
            "job": rng.choice(job),
            "company": rng.choice(COMPANY_NAMES),
            "action": rng.choice(["liked", "commented", "reposted"]),
            "matches_icp": is_icp,
            "comment": (rng.choice([
                "This is exactly what we need to figure out.",
                "What would you do in our vertical?",
                "Saved this for the team.",
                "We have been wrestling with this.",
                "Great point on the first line.",
                "",
            ]) if post.get("comments") else ""),
        })
    return engagers
