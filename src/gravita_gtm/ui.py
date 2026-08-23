"""Gravita GTM — polished UX surface: REPL + dashboard + web preview.

The backend is done and verified. This module makes the platform feel
smooth and stunning: beautiful terminal output, at-a-glance dashboard,
and a self-contained HTML preview that opens in the browser.
"""

from __future__ import annotations

import html
import json
import os
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from gravita_gtm.config import VAULT_DIR, STATE_DIR
from gravita_gtm.core.core import Core
from gravita_gtm.core.sessions import SessionManager
from gravita_gtm.runtime.workflows import load_last_narration

# ---------------------------------------------------------------------------
# Brand palette — magenta primary, cyan interactive, soft neutrals.
# ---------------------------------------------------------------------------

MAGENTA = "magenta"
CYAN = "cyan"
GREEN = "green"
YELLOW = "yellow"
DIM = "dim"
WHITE = "white"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# ---------------------------------------------------------------------------
# Banner — the brand strip the user sees on startup and status.
# ---------------------------------------------------------------------------

def banner() -> Panel:
    return Panel(
        Text("Gravita GTM", style=f"bold {MAGENTA}")
        + Text("\nOutcome-orchestrated B2B demand generation\n")
        + Text(
            "Hermes-patterned sessions · governed triggers · Obsidian vault\n"
            "Dry-run first · connect real services after the platform is useable\n",
            style=DIM,
        ),
        title=f"v0.1.0 · phase 1 (backend, dry-run)",
        border_style=MAGENTA,
    )


# ---------------------------------------------------------------------------
# Welcome — printed once when the user enters the REPL.
# ---------------------------------------------------------------------------

def welcome(console: Console) -> None:
    console.print("\n")
    console.print(banner())
    console.print(
        Panel(
            Text("Welcome to Gravita GTM.", style=f"bold {WHITE}")
            + Text("\n\nYou're in a conversational GTM session. Tell me what to do, "
                   "or type [bold]help[/bold].\n\n")
            + Text("Session: ", style=DIM)
            + Text("default", style=CYAN)
            + Text("          Workspace: ", style=DIM)
            + Text("default", style=CYAN)
            + Text("          Channel: ", style=DIM)
            + Text("outbound", style=CYAN)
            + Text("\n\nQuick start:\n"
                   "  [bold]run signal-outbound top_n=5[/bold]     run a workflow\n"
                   "  [bold]status[/bold]                          see pending artifacts + drafts\n"
                   "  [bold]dashboard[/bold]                       at-a-glance overview\n"
                   "  [bold]approve <id>[/bold]                    approve a pending artifact\n"
                   "  [bold]vault[/bold]                           open the Obsidian vault\n\n"
                   "Type [bold]help[/bold] for the full command list.",
                   style=WHITE),
            border_style=CYAN,
            padding=(1, 2),
        )
    )
    console.print("\n")


# ---------------------------------------------------------------------------
# Help — clean, scannable, one-line-per-command.
# ---------------------------------------------------------------------------

def help_panel() -> Panel:
    return Panel(
        Text("Commands", style=f"bold {CYAN}")
        + Text(
          "\n"
          "  [bold]run <capability> [params][/bold]      execute a workflow\n"
          "       capabilities: signal-outbound, money-loop, content-batch\n"
          "       params: top_n=20, event='<json>', workspace=<name>\n"
          "       examples:\n"
          "         run signal-outbound top_n=20\n"
          "         run money-loop event='{\"type\":\"payment.failed\"}'\n"
          "         run content-batch\n"
          "\n"
          "  [bold]status[/bold]                         pending artifacts + audit snapshot\n"
          "  [bold]dashboard[/bold]                      at-a-glance platform overview\n"
          "  [bold]approve <id>[/bold]                   approve a pending artifact\n"
          "  [bold]hold <id>[/bold]                      hold a pending artifact for review\n"
          "  [bold]rulings[/bold]                        list governance rulings\n"
          "  [bold]add-ruling <text>[/bold]              add a governance ruling\n"
          "  [bold]query <topic>[/bold]                  grep rulings + vault for a topic\n"
          "  [bold]vault[/bold]                          print the vault path (open in Obsidian)\n"
          "  [bold]sessions[/bold]                       list active sessions\n"
          "  [bold]new-session <name>[/bold]             start a new conversational session\n"
          "  [bold]watch[/bold]                          watch pending artifacts (Phase 2)\n"
          "  [bold]preview[/bold]                        open a stunning HTML dashboard in your browser\n"
          "\n"
          "  [bold]clear[/bold]                          clear the screen\n"
          "  [bold]help[/bold]                           this help\n"
          "  [bold]quit[/bold] / [bold]exit[/bold]        exit\n",
          style=WHITE),
        title="help",
        border_style=CYAN,
    )


# ---------------------------------------------------------------------------
# Dashboard — at-a-glance platform overview.
# ---------------------------------------------------------------------------

def dashboard(console: Console, core: Core) -> None:
    console.print("\n")
    console.print(banner())

    # Run narration if there is one
    nar = load_last_narration()
    if nar:
        _print_narration_panel(console, nar)

    # Platform strip
    n_triggers = len(core.triggers.list())
    n_harnesses = len(core.harness_registry.list())
    n_pending = len(core.pending())
    console.print(
        Panel(
            Text("PLATFORM", style=f"bold {CYAN}")
            + Text(
              f"\n  Phase:   1 (backend, dry-run)\n"
              f"  Triggers: {n_triggers}\n"
              f"  Harnesses: {n_harnesses}\n"
              f"  Pending:  {n_pending}\n"
              f"  Rulings:  {len(core.list_rulings())}\n"
              f"  {white_box('Everything runs in dry-run. No real services touched.')}",
              style=WHITE),
            border_style=CYAN,
        )
    )

    # Pending artifacts with draft previews
    pending = core.pending()
    if pending:
        console.print(f"\n[bold]{CYAN}PENDING ARTIFACTS ({n_pending})[/bold]")
        for p in pending[-8:]:
            cap = p.get("capability", "?")
            pid = p.get("id", "?")
            status = p.get("status", "?")
            created = p.get("created_at", "")[:19]
            rows = p.get("content", {}).get("rows", [])
            console.print(f"  [cyan]{pid}[/cyan]  {cap}  {status}  {created}")
            if rows:
                for r in rows[:3]:
                    draft = r.get("draft", "")
                    company = r.get("company", "?")
                    if draft:
                        console.print(f"    [dim]row {r.get('row','?')}:[/dim] [cyan]{company}[/cyan]")
                        console.print(f"    [dim]{draft[:180]}[/dim]")
            if len(rows) > 3:
                console.print(f"    [dim]... +{len(rows) - 3} more rows[/dim]")
    else:
        console.print("\n[dim]no pending artifacts[/dim]")

    # Recent audit
    audit = core.audit_recent(8)
    if audit:
        console.print(f"\n[bold]{CYAN}RECENT ACTIVITY ({len(audit)})[/bold]")
        for a in audit[-6:]:
            aid = a.get("id", "")[:10]
            cap = a.get("capability", "")
            status = a.get("status", "")
            fired = a.get("fired_at", "")[:19]
            console.print(f"  [dim]{aid}[/dim]  {cap}  [yellow]{status}[/yellow]  [dim]{fired}[/dim]")

    # Vault stats
    console.print(f"\n[bold]{CYAN}VAULT STATE[/bold]")
    vault_stats = _vault_stats()
    for label, count in vault_stats.items():
        console.print(f"  [dim]{label}[/dim]  {count} note{'s' if count != 1 else ''}")

    # Sessions
    sessions = SessionManager()
    slist = sessions.list()
    if slist:
        console.print(f"\n[bold]{CYAN}SESSIONS ({len(slist)})[/bold]")
        for s in slist:
            console.print(f"  [cyan]{s.id}[/cyan]  {s.name}  workspace={s.workspace}  channel={s.channel}")
    else:
        console.print("\n[dim]no active sessions[/dim]")

    console.print("\n")
    console.print(
        Panel(
            Text("Quick actions", style=f"bold {CYAN}")
            + Text(
              "\n"
              "  [bold]run signal-outbound top_n=5[/bold]     produce a research sheet\n"
              "  [bold]approve <id>[/bold]                    ship a pending artifact\n"
              "  [bold]add-ruling <text>[/bold]               correct the agents\n"
              "  [bold]preview[/bold]                         open the HTML dashboard\n"
              "  [bold]vault[/bold]                           edit the knowledge base in Obsidian\n",
              style=WHITE),
            border_style=CYAN,
        )
    )
    console.print("\n")


def _print_narration_panel(console: Console, nar: dict[str, Any]) -> None:
    """Compact one-panel version of the narration for the dashboard."""
    capability = nar.get("capability", "?")
    trigger = nar.get("trigger", "?")
    gate = nar.get("gate", "PENDING")
    console.print(
        Panel(
            Text(f"last run: {capability}", style=f"bold {CYAN}")
            + Text(f"\ntrigger: {trigger}", style=DIM)
            + Text(f"\ngate: {gate}", style=YELLOW),
            title="last run",
            border_style=CYAN,
        )
    )
    wf = nar.get("waterfall", {})
    if wf:
        raw = wf.get("raw", 0)
        kept = wf.get("kept", 0)
        drained = wf.get("drained", 0)
        if raw or kept or drained:
            console.print(f"  [dim]enrichment: {raw} raw → {kept} kept → {drained} drained[/dim]")
    rows = nar.get("rows", [])
    if rows:
        console.print(f"  [dim]research sheet: {len(rows)} rows with confidence notes[/dim]")
    rh = nar.get("rulings_honored", [])
    if rh:
        console.print(f"  [dim]rulings honored: {len(rh)}[/dim]")
    wb = nar.get("write_back", [])
    if wb:
        console.print(f"  [dim]write-back: {len(wb)} files[/dim]")
    console.print("")


def _vault_stats() -> dict[str, int]:
    stats: dict[str, int] = {}
    for sub in ["prospects", "signals", "messages", "metrics", "rulings", "offer", "buyers", "voice", "workflows", "market-map"]:
        d = VAULT_DIR / sub
        if d.exists():
            n = len(list(d.glob("*.md")))
            if n > 0:
                stats[sub] = n
    return stats


def _show_narration(console: Console, core: Core) -> None:
    """Show the last run's narration if there is one.

    The narration is the story of the most recent run in the image order:
    trigger -> sources -> enrichment waterfall -> research sheet (confidence
    notes per row) -> drafts -> gate -> write-back. Plus the rulings the run
    actually honored, as readable text.
    """
    nar = load_last_narration()
    if nar is None:
        return
    capability = nar.get("capability", "?")
    trigger = nar.get("trigger", "?")
    console.print(
        Panel(
            Text(f"last run: {capability}", style=f"bold {CYAN}")
            + Text(f"\ntrigger: {trigger}\n", style=DIM)
            + Text(f"gate: {nar.get('gate', 'PENDING')}\n", style=YELLOW),
            title="RUN NARRATION",
            border_style=CYAN,
        )
    )

    # Sources read
    sources = nar.get("sources", [])
    if sources:
        console.print(f"\n[dim]read ({len(sources)}):[/dim]")
        for s in sources:
            console.print(f"  [dim]• {s}[/dim]")

    # Enrichment waterfall — only meaningful for signal-outbound today
    wf = nar.get("waterfall", {})
    if wf:
        raw = wf.get("raw", 0)
        kept = wf.get("kept", 0)
        drained = wf.get("drained", 0)
        if raw or kept or drained:
            console.print(
                f"\n[dim]enrichment waterfall:[/dim] "
                f"[cyan]{raw}[/cyan] raw → [green]{kept}[/green] kept → "
                f"[yellow]{drained}[/yellow] drained (weak rows dropped before drafting)"
            )

    # Rows with confidence notes
    rows = nar.get("rows", [])
    if rows:
        console.print(f"\n[dim]research sheet — {len(rows)} rows with confidence notes:[/dim]")
        for r in rows[:6]:
            rn = r.get("row", "?")
            company = r.get("company", "?")
            conf = r.get("confidence", {})
            what = conf.get("what_changed", "?")
            see = conf.get("what_you_see", "?")
            draft = r.get("draft", "")
            console.print(f"  [dim]row {rn} · {company}[/dim]")
            console.print(f"    what_changed: [cyan]{what}[/cyan]")
            console.print(f"    what_you_see: [cyan]{see}[/cyan]")
            if draft:
                console.print(f"    draft (held at gate): [dim]{draft[:200]}[/dim]")
        if len(rows) > 6:
            console.print(f"  [dim]... +{len(rows) - 6} more rows[/dim]")

    # Rulings honored — the permanent corrections the run read first
    rh = nar.get("rulings_honored", [])
    if rh:
        console.print(f"\n[dim]rulings honored ({len(rh)}):[/dim]")
        for r in rh:
            console.print(f"  [dim]• {r['file']}:{r['line']} — {r['text']}[/dim]")

    # Write-back destinations
    wb = nar.get("write_back", [])
    if wb:
        console.print(f"\n[dim]write-back ({len(wb)} files):[/dim]")
        for f in wb[:10]:
            console.print(f"  [dim]• {f}[/dim]")
        if len(wb) > 10:
            console.print(f"  [dim]... +{len(wb) - 10} more[/dim]")

    console.print(f"\n[dim]draft rule: {nar.get('draft_rule', '')}[/dim]")
    console.print("\n")


def white_box(text: str) -> str:
    return f"[dim]{text}[/dim]"


# ---------------------------------------------------------------------------
# Status — enhanced: pending + audit + first draft preview.
# ---------------------------------------------------------------------------

def show_status(console: Console, core: Core) -> None:
    console.print("\n")
    console.print(banner())
    _show_narration(console, core)
    _show_pending(console, core)
    _show_audit(console, core)
    _show_first_draft(console, core)
    console.print("\n")


def _show_pending(console: Console, core: Core) -> None:
    pending = core.pending()
    if not pending:
        console.print("[dim]no pending artifacts[/dim]")
        return
    console.print(f"\n[bold]{CYAN}PENDING ARTIFACTS ({len(pending)})[/bold]")
    for p in pending[-8:]:
        console.print(
            f"  [cyan]{p.get('id','?')}[/cyan]  "
            f"{p.get('capability','?')}  "
            f"[yellow]{p.get('status','?')}[/yellow]  "
            f"[dim]{p.get('created_at','')[:19]}[/dim]"
        )


def _show_audit(console: Console, core: Core) -> None:
    audit = core.audit_recent(10)
    if not audit:
        return
    console.print(f"\n[bold]{CYAN}RECENT AUDIT ({len(audit)} entries)[/bold]")
    for a in audit[-6:]:
        console.print(
            f"  [dim]{a.get('id','')[:10]}[/dim]  "
            f"{a.get('capability','')}  "
            f"[yellow]{a.get('status','')}[/yellow]  "
            f"[dim]{a.get('fired_at','')[:19]}[/dim]"
        )


def _show_first_draft(console: Console, core: Core) -> None:
    pending = core.pending()
    if not pending:
        return
    first = pending[0]
    rows = first.get("content", {}).get("rows", [])
    if not rows:
        return
    r1 = rows[0]
    draft = r1.get("draft", "")
    if not draft:
        return
    company = r1.get("company", "?")
    console.print(f"\n[bold]{CYAN}FIRST MESSAGE DRAFT (row 1)[/bold]")
    console.print(f"  [cyan]{company}[/cyan]")
    console.print(f"  [dim]{draft[:300]}[/dim]")
    more = len(rows) - 1
    if more > 0:
        console.print(f"  [dim]{more} more draft{'s' if more != 1 else ''} in this artifact[/dim]")


# ---------------------------------------------------------------------------
# Web preview — generates a stunning self-contained HTML dashboard.
# ---------------------------------------------------------------------------

def preview(core: Core, sessions: SessionManager | None = None) -> Path:
    """Generate a self-contained HTML dashboard and return its path."""
    pending = core.pending()
    audit = core.audit_recent(20)
    rulings = core.list_rulings()
    vault_stats = _vault_stats()
    slist = (sessions or SessionManager()).list()

    # Last run narration, if there is one
    nar = load_last_narration()

    rows_html = ""
    for p in pending[-10:]:
        cap = html.escape(str(p.get("capability", "?")))
        pid = html.escape(str(p.get("id", "?")))
        status = html.escape(str(p.get("status", "?")))
        created = html.escape(str(p.get("created_at", "")[:19]))
        rows = p.get("content", {}).get("rows", [])
        row_cards = ""
        for r in rows[:5]:
            draft = html.escape(str(r.get("draft", "")))
            company = html.escape(str(r.get("company", "?")))
            row_num = html.escape(str(r.get("row", "?")))
            if draft:
                row_cards += f"""
      <div class="row-card">
        <div class="row-head">row {row_num} — {company}</div>
        <div class="row-draft">{draft}</div>
      </div>"""
        if len(rows) > 5:
            row_cards += f"""      <div class="row-more">+{len(rows) - 5} more rows</div>"""
        rows_html += f"""
      <div class="artifact">
        <div class="art-head">
          <span class="art-id">{pid}</span>
          <span class="art-cap">{cap}</span>
          <span class="art-status">{status}</span>
          <span class="art-time">{created}</span>
        </div>
        {row_cards}
      </div>"""

    audit_html = ""
    for a in audit[-10:]:
        aid = html.escape(str(a.get("id", "")[:10]))
        cap = html.escape(str(a.get("capability", "")))
        status = html.escape(str(a.get("status", "")))
        fired = html.escape(str(a.get("fired_at", "")[:19]))
        audit_html += f"""
      <tr>
        <td>{aid}</td>
        <td>{cap}</td>
        <td>{status}</td>
        <td>{fired}</td>
      </tr>"""

    rulings_html = ""
    for r in rulings[-10:]:
        date = html.escape(str(r.get("date", "")))
        text = html.escape(str(r.get("text", "")))
        rulings_html += f"""
      <tr>
        <td>{date}</td>
        <td>{text}</td>
      </tr>"""

    vault_rows = ""
    for label, count in vault_stats.items():
        label = html.escape(label)
        count = html.escape(str(count))
        vault_rows += f"""
      <tr>
        <td>{label}</td>
        <td>{count}</td>
      </tr>"""

    sessions_html = ""
    for s in slist:
        sid = html.escape(str(s.id))
        name = html.escape(str(s.name))
        ws = html.escape(str(s.workspace))
        channel = html.escape(str(s.channel))
        sessions_html += f"""
      <tr>
        <td>{sid}</td>
        <td>{name}</td>
        <td>{ws}</td>
        <td>{channel}</td>
      </tr>"""

    last_run_html = ""
    if nar:
        cap = html.escape(str(nar.get("capability", "?")))
        trigger = html.escape(str(nar.get("trigger", "?")))
        gate = html.escape(str(nar.get("gate", "PENDING")))
        sources = nar.get("sources", [])
        sources_html = "".join(
            f"<li>{html.escape(s)}</li>" for s in sources
        ) if sources else "<li class=\"muted\">(none)</li>"
        wf = nar.get("waterfall", {})
        raw = wf.get("raw", 0)
        kept = wf.get("kept", 0)
        drained = wf.get("drained", 0)
        waterfall_html = ""
        if raw or kept or drained:
            waterfall_html = (
                f"<div class=\"narration-row\"><span class=\"narration-label\">enrichment</span> "
                f"<span class=\"narration-num cyan\">{raw}</span> raw "
                f"<span class=\"narration-arrow\">→</span> "
                f"<span class=\"narration-num green\">{kept}</span> kept "
                f"<span class=\"narration-arrow\">→</span> "
                f"<span class=\"narration-num yellow\">{drained}</span> drained"
                f"</div>"
            )
        rows = nar.get("rows", [])
        rows_count = len(rows)
        confidence_html = ""
        if rows:
            sample_rows = rows[:5]
            confidence_html = '<div class="narration-section"><div class="narration-label">research sheet</div>'
            for r in sample_rows:
                rn = html.escape(str(r.get("row", "?")))
                company = html.escape(str(r.get("company", "?")))
                what = html.escape(str(r.get("confidence", {}).get("what_changed", "?")))
                see = html.escape(str(r.get("confidence", {}).get("what_you_see", "?")))
                draft = html.escape(str(r.get("draft", "")))
                confidence_html += f"""<div class="narration-row">
                  <span class="narration-label">row {rn} · {company}</span>
                  <span class="narration-muted">what_changed: {what} · what_you_see: {see}</span>
                </div>"""
                if draft:
                    confidence_html += f"""<div class="narration-draft">{draft}</div>"""
            if rows_count > 5:
                confidence_html += f'<div class="narration-more">+{rows_count - 5} more rows</div>'
            confidence_html += "</div>"
        rh = nar.get("rulings_honored", [])
        rulings_honored_html = ""
        if rh:
            rules_items = "".join(
                f"<li><span class=\"narration-muted\">{html.escape(r['file'])}:{r['line']} — </span>{html.escape(r['text'])}</li>"
                for r in rh
            )
            rulings_honored_html = (
                f"<div class=\"narration-section\">"
                f'<div class="narration-label">rulings honored ({len(rh)})</div>'
                f"<ul>{rules_items}</ul></div>"
            )
        wb = nar.get("write_back", [])
        wb_html = ""
        if wb:
            wb_items = "".join(
                f"<li>{html.escape(f)}</li>" for f in wb[:12]
            )
            wb_html = (
                f"<div class=\"narration-section\">"
                f'<div class="narration-label">write-back ({len(wb)} files)</div>'
                f"<ul>{wb_items}</ul></div>"
            )
            if len(wb) > 12:
                wb_html += f'<div class="narration-more">+{len(wb) - 12} more</div>'
        draft_rule = html.escape(str(nar.get("draft_rule", "")))
        last_run_html = f"""
    <div class="narration">
      <div class="narration-head">
        <span class="narration-cap">{cap}</span>
        <span class="narration-trigger">trigger: {trigger}</span>
        <span class="narration-gate">{gate}</span>
      </div>
      <div class="narration-sources">
        <div class="narration-label">read ({len(sources)})</div>
        <ul>{sources_html}</ul>
      </div>
      {waterfall_html}
      {confidence_html}
      {rulings_honored_html}
      {wb_html}
      {draft_rule and f'<div class="narration-rule">draft rule: {draft_rule}</div>' or ""}
    </div>
    """

    n_pending = len(pending)
    n_triggers = len(core.triggers.list())
    n_harnesses = len(core.harness_registry.list())
    n_rulings = len(rulings)
    n_audit = len(audit)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Gravita GTM — Dashboard</title>
<style>
  :root {{
    --bg: #0d0d12;
    --surface: #16161f;
    --border: #2a2a3a;
    --fg: #e0e0e8;
    --muted: #8888a0;
    --magenta: #c084d0;
    --cyan: #80d0d0;
    --green: #80d080;
    --yellow: #d0b060;
    --red: #d06060;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg);
    color: var(--fg);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 14px;
    line-height: 1.5;
    padding: 24px;
    max-width: 900px;
    margin: 0 auto;
  }}
  .header {{
    display: flex;
    align-items: baseline;
    gap: 16px;
    margin-bottom: 24px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--border);
  }}
  .header h1 {{
    font-size: 22px;
    color: var(--magenta);
    font-weight: 700;
    letter-spacing: -0.5px;
  }}
  .header .version {{
    color: var(--muted);
    font-size: 13px;
    font-family: monospace;
  }}
  .header .tagline {{
    color: var(--muted);
    font-size: 13px;
    margin-top: 4px;
  }}
  .section {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 16px;
  }}
  .section h2 {{
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: var(--cyan);
    margin-bottom: 12px;
    font-weight: 600;
  }}
  .stats {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
    gap: 8px;
  }}
  .stat {{
    background: rgba(255,255,255,0.03);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 10px 12px;
    text-align: center;
  }}
  .stat .num {{
    font-size: 24px;
    font-weight: 700;
    color: var(--magenta);
    display: block;
  }}
  .stat .label {{
    font-size: 11px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-top: 2px;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }}
  th {{
    text-align: left;
    color: var(--muted);
    font-weight: 500;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
    padding: 6px 8px;
    border-bottom: 1px solid var(--border);
  }}
  td {{
    padding: 6px 8px;
    border-bottom: 1px solid rgba(255,255,255,0.05);
  }}
  tr:hover td {{
    background: rgba(255,255,255,0.02);
  }}
  .artifact {{
    background: rgba(255,255,255,0.02);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 12px;
    margin-bottom: 8px;
  }}
  .art-head {{
    display: flex;
    gap: 12px;
    align-items: baseline;
    margin-bottom: 8px;
    flex-wrap: wrap;
  }}
  .art-id {{
    font-family: monospace;
    color: var(--cyan);
    font-weight: 600;
    font-size: 13px;
  }}
  .art-cap {{
    color: var(--fg);
    font-weight: 500;
  }}
  .art-status {{
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 10px;
    background: rgba(208,176,96,0.15);
    color: var(--yellow);
    border: 1px solid rgba(208,176,96,0.3);
  }}
  .art-time {{
    color: var(--muted);
    font-size: 12px;
    margin-left: auto;
  }}
  .row-card {{
    background: rgba(255,255,255,0.03);
    border-left: 2px solid var(--magenta);
    padding: 8px 10px;
    margin-top: 6px;
    border-radius: 0 4px 4px 0;
  }}
  .row-head {{
    font-size: 12px;
    color: var(--cyan);
    font-weight: 500;
    margin-bottom: 4px;
  }}
  .row-draft {{
    font-size: 13px;
    color: var(--fg);
    line-height: 1.5;
  }}
  .row-more {{
    font-size: 12px;
    color: var(--muted);
    margin-top: 6px;
    font-style: italic;
  }}
  .empty {{
    color: var(--muted);
    font-style: italic;
    font-size: 13px;
  }}
  .footer {{
    margin-top: 24px;
    padding-top: 16px;
    border-top: 1px solid var(--border);
    color: var(--muted);
    font-size: 12px;
    display: flex;
    justify-content: space-between;
  }}
  .pill {{
    display: inline-block;
    font-size: 10px;
    padding: 2px 8px;
    border-radius: 10px;
    background: rgba(128,208,208,0.1);
    color: var(--cyan);
    border: 1px solid rgba(128,208,208,0.2);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}
  .narration {{
    background: rgba(255,255,255,0.02);
    border: 1px solid var(--border);
    border-left: 3px solid var(--magenta);
    border-radius: 6px;
    padding: 14px;
  }}
  .narration-head {{
    display: flex;
    gap: 12px;
    align-items: baseline;
    flex-wrap: wrap;
    margin-bottom: 12px;
    padding-bottom: 10px;
    border-bottom: 1px solid var(--border);
  }}
  .narration-cap {{
    font-size: 15px;
    color: var(--magenta);
    font-weight: 700;
    letter-spacing: -0.3px;
  }}
  .narration-trigger {{
    color: var(--muted);
    font-size: 12px;
  }}
  .narration-gate {{
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 10px;
    background: rgba(208,176,96,0.15);
    color: var(--yellow);
    border: 1px solid rgba(208,176,96,0.3);
  }}
  .narration-label {{
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--cyan);
    font-weight: 600;
  }}
  .narration-muted {{
    color: var(--muted);
    font-size: 12px;
  }}
  .narration-section {{
    margin-bottom: 10px;
  }}
  .narration-section .narration-label {{
    margin-bottom: 6px;
  }}
  .narration-row {{
    font-size: 13px;
    color: var(--fg);
    padding: 4px 0 2px 0;
    border-bottom: 1px solid rgba(255,255,255,0.03);
  }}
  .narration-draft {{
    font-size: 13px;
    color: var(--fg);
    line-height: 1.5;
    padding: 6px 10px;
    background: rgba(255,255,255,0.03);
    border-left: 2px solid var(--magenta);
    margin: 4px 0 8px 8px;
    border-radius: 0 4px 4px 0;
  }}
  .narration-muted {{
    color: var(--muted);
    font-size: 12px;
  }}
  .narration-arrow {{
    color: var(--muted);
    padding: 0 2px;
  }}
  .narration-num {{
    font-weight: 600;
    font-size: 13px;
  }}
  .narration-num.cyan {{ color: var(--cyan); }}
  .narration-num.green {{ color: var(--green); }}
  .narration-num.yellow {{ color: var(--yellow); }}
  .narration-more {{
    font-size: 12px;
    color: var(--muted);
    font-style: italic;
    padding: 2px 0;
  }}
  .narration-rule {{
    font-size: 12px;
    color: var(--muted);
    padding: 6px 0 0 0;
    border-top: 1px solid var(--border);
    margin-top: 8px;
  }}
  .narration-sources ul, .narration-section ul {{
    margin: 4px 0 0 0;
    padding-left: 18px;
  }}
  .narration-sources li, .narration-section li {{
    font-size: 12px;
    color: var(--fg);
    line-height: 1.5;
  }}
  .narration-sources li.muted {{
    color: var(--muted);
    font-style: italic;
  }}
</style>
</head>
<body>
  <div class="header">
    <div>
      <h1>Gravita GTM</h1>
      <div class="tagline">Outcome-orchestrated B2B demand generation · Hermes-patterned sessions · governed triggers · Obsidian vault</div>
    </div>
    <div class="version">v0.1.0 · phase 1 (backend, dry-run)</div>
  </div>

  <div class="section">
    <h2>Platform</h2>
    <div class="stats">
      <div class="stat"><span class="num">{n_triggers}</span><span class="label">Triggers</span></div>
      <div class="stat"><span class="num">{n_harnesses}</span><span class="label">Harnesses</span></div>
      <div class="stat"><span class="num">{n_pending}</span><span class="label">Pending</span></div>
      <div class="stat"><span class="num">{n_rulings}</span><span class="label">Rulings</span></div>
      <div class="stat"><span class="num">{n_audit}</span><span class="label">Audit entries</span></div>
      <div class="stat"><span class="num">1</span><span class="label">Phase</span></div>
    </div>
    <p style="color: var(--muted); font-size: 12px; margin-top: 12px;">
      <span class="pill">dry-run</span> Everything runs in dry-run. No real services touched. Connect real APIs in Phase 3.
    </p>
  </div>

  <div class="section">
    <h2>Pending Artifacts ({n_pending})</h2>
    {rows_html if rows_html else '<div class="empty">No pending artifacts. Run a workflow to produce one.</div>'}
  </div>

  <div class="section">
    <h2>Recent Activity ({n_audit})</h2>
    <table>
      <thead><tr><th>ID</th><th>Capability</th><th>Status</th><th>Fired at</th></tr></thead>
      <tbody>
        {audit_html if audit_html else '<tr><td colspan="4" class="empty">No activity yet.</td></tr>'}
      </tbody>
    </table>
  </div>

  <div class="section">
    <h2>Last Run</h2>
    {last_run_html if last_run_html else '<div class="empty">No run yet. Run a workflow to produce one.</div>'}
  </div>

  <div class="section">
    <h2>Vault State</h2>
    <table>
      <thead><tr><th>Folder</th><th>Notes</th></tr></thead>
      <tbody>
        {vault_rows if vault_rows else '<tr><td colspan="2" class="empty">Vault empty. Run <code>gravita vault</code> to scaffold.</td></tr>'}
      </tbody>
    </table>
  </div>

  <div class="section">
    <h2>Rulings ({n_rulings})</h2>
    <table>
      <thead><tr><th>Date</th><th>Text</th></tr></thead>
      <tbody>
        {rulings_html if rulings_html else '<tr><td colspan="2" class="empty">No rulings yet. Add one with <code>gravita add-ruling</code>.</td></tr>'}
      </tbody>
    </table>
  </div>

  <div class="section">
    <h2>Sessions ({len(slist)})</h2>
    <table>
      <thead><tr><th>ID</th><th>Name</th><th>Workspace</th><th>Channel</th></tr></thead>
      <tbody>
        {sessions_html if sessions_html else '<tr><td colspan="4" class="empty">No active sessions.</td></tr>'}
      </tbody>
    </table>
  </div>

  <div class="footer">
    <span>Generated {_now()} · <a href="https://github.com/ppaassaallee/gravita-gtm">github.com/ppaassaallee/gravita-gtm</a></span>
    <span style="color: var(--muted);">dry-run · nothing leaves the machine</span>
  </div>
</body>
</html>"""

    out_dir = STATE_DIR if STATE_DIR.exists() else Path.cwd()
    out_path = out_dir / "gravita-dashboard.html"
    out_path.write_text(html_content, encoding="utf-8")
    return out_path


def open_preview(core: Core, console: Console) -> None:
    """Generate and open the HTML dashboard in the default browser."""
    sessions = SessionManager()
    path = preview(core, sessions)
    console.print(f"\n[bold]{CYAN}opening dashboard:[/bold] [dim]{path}[/dim]\n")
    try:
        webbrowser.open(f"file://{path.resolve().as_uri()}")
    except Exception as e:
        console.print(f"[yellow]couldn't open browser: {e}[/yellow]")
        console.print(f"[dim]open manually: {path}[/dim]")
