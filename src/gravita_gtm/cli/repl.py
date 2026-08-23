"""Gravita GTM — Outcome-orchestrated B2B demand generation platform.

Hermes-patterned conversational sessions, governed multi-agent triggers,
cloud-hosted Obsidian vault as the semantic layer, dry-run first.

CLI entrypoint — boots the platform and drops you into a session.

Usage
-----
``gravita`` — interactive REPL (Hermes-patterned, session-based).
``gravita run <capability> [params]`` — one-shot run.
``gravita status`` — pending artifacts + audit snapshot.
``gravita vault`` — open the vault path in Obsidian.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

from gravita_gtm.config import ROOT, VAULT_DIR, STATE_DIR, ensure_dirs, stub_mode
from gravita_gtm.core.sessions import SessionManager
from gravita_gtm.core.core import Core
from gravita_gtm.ui import banner, dashboard, help_panel, load_last_narration, open_preview, show_status, welcome


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    console = Console()

    if argv in (["--help"], ["-h"], ["help"]):
        console.print(banner())
        console.print(Panel(
            "Usage\n"
            "  gravita run <capability> [params]   run a workflow (dry-run)\n"
            "    capabilities: signal-outbound, money-loop, content-batch\n"
            "    params: top_n=20, event='<json>'\n"
            "    examples: gravita run signal-outbound top_n=20\n"
            "              gravita run money-loop event='{\"type\":\"payment.failed\"}'\n"
            "              gravita run content-batch\n"
            "  status                      pending artifacts + audit snapshot\n"
            "  vault                       print the vault path (open in Obsidian)\n"
            "  sessions                    list sessions\n"
            "  new-session <name>          create a session\n"
            "  watch                       watch pending artifacts (Phase 2)\n"
            "  approve <id>                approve the pending artifact\n"
            "  hold <id>                   hold the pending artifact\n"
            "  rulings                     list rulings\n"
            "  add-ruling <text>           add a ruling\n"
            "  query <topic>               grep rulings + vault for a topic\n"
            "  clear                       clear the screen\n"
            "  quit / exit                 exit\n",
            title="gravita — GTM demand generation",
            border_style="cyan",
        ))
        return 0

    # one-shot mode
    parser = argparse.ArgumentParser(prog="gravita", description="Gravita GTM CLI")
    sub = parser.add_subparsers(dest="command")

    p_run = sub.add_parser("run", help="run a workflow")
    p_run.add_argument("capability", choices=["signal-outbound", "money-loop", "content-batch"])
    p_run.add_argument("params", nargs="*", help="key=value pairs, e.g. top_n=20")

    p_status = sub.add_parser("status", help="pending artifacts + audit snapshot")
    p_vault = sub.add_parser("vault", help="print vault path")
    p_sessions = sub.add_parser("sessions", help="session management")
    p_new_session = sub.add_parser("new-session", help="create a session")
    p_new_session.add_argument("name")
    p_watch = sub.add_parser("watch", help="watch pending artifacts (Phase 2)")
    p_dashboard = sub.add_parser("dashboard", help="at-a-glance platform overview")
    p_preview = sub.add_parser("preview", help="open a stunning HTML dashboard in the browser")
    p_approve = sub.add_parser("approve", help="approve pending artifact")
    p_approve.add_argument("id")
    p_hold = sub.add_parser("hold", help="hold pending artifact")
    p_hold.add_argument("id")
    p_rulings = sub.add_parser("rulings", help="list rulings")
    p_add_ruling = sub.add_parser("add-ruling", help="add a ruling")
    p_add_ruling.add_argument("text")
    p_query = sub.add_parser("query", help="grep rulings + vault")
    p_query.add_argument("topic")

    args = parser.parse_args(argv)
    core = Core()
    sessions = SessionManager()

    if args.command == "run":
        cap = args.capability or "signal-outbound"
        event = None
        w = "default"
        channel = "outbound"
        top_n = 8
        for p in (args.params or []):
            if p.startswith("event="):
                raw = p[len("event="):].strip().strip("'").strip('"')
                if raw:
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError as e:
                        console.print(f"[red]bad event JSON: {e}[/red]")
                        return 1
            elif p.startswith("workspace="):
                w = p.split("=", 1)[1]
            elif p.startswith("channel="):
                channel = p.split("=", 1)[1]
            elif p.startswith("top_n="):
                top_n = int(p.split("=", 1)[1])
        core.run(cap, top_n=top_n, event=event, workspace=w, channel=channel)
        console.print(f"[green]ran {args.capability} — top_n={top_n}[/green]")
        _show_narration(console)
        _show_pending(console, core)
        return 0

    if args.command == "status":
        _show_status(console, core)
        return 0

    if args.command == "dashboard":
        dashboard(console, core)
        return 0

    if args.command == "preview":
        open_preview(core, console)
        return 0

    if args.command == "vault":
        console.print(f"[bold cyan]{VAULT_DIR}[/bold cyan]")
        console.print("[dim]Open this folder in Obsidian. It's git-backed (cloud backup + version history).[/dim]")
        return 0

    if args.command == "sessions":
        for s in sessions.list():
            console.print(f"  [cyan]{s.id}[/cyan]  {s.name}  workspace={s.workspace}  channel={s.channel}")
        return 0

    if args.command == "approve":
        core.approve(args.id)
        console.print(f"[green]approved {args.id}[/green]")
        return 0

    if args.command == "hold":
        core.hold(args.id)
        console.print(f"[yellow]held {args.id}[/yellow]")
        return 0

    if args.command == "rulings":
        for r in core.list_rulings():
            console.print(f"  [dim]{r['date']}[/dim]  {r['text']}")
        return 0

    if args.command == "add-ruling":
        core.add_ruling(args.text)
        console.print(f"[green]ruling added[/green]")
        return 0

    if args.command == "query":
        core.query(args.topic, console=console)
        return 0

    parser.print_help()
    return 0


def _show_pending(console: Console, core: Core) -> None:
    pending = core.pending()
    if not pending:
        console.print("[dim]no pending artifacts[/dim]")
        return
    console.print(f"\n[dim]pending artifacts ({len(pending)}):[/dim]")
    for p in pending[-8:]:
        console.print(f"  [cyan]{p['id']}[/cyan]  {p['capability']}  {p['status']}  "
                      f"{p['created_at'][:19]}")


def _show_narration(console: Console) -> None:
    """Show the last run's narration, if there is one."""
    nar = load_last_narration()
    if nar is None:
        return
    capability = nar.get("capability", "?")
    trigger = nar.get("trigger", "?")
    gate = nar.get("gate", "PENDING")
    console.print(
        Panel(
            Text(f"last run: {capability}", style=f"bold cyan")
            + Text(f"\ntrigger: {trigger}\n", style="dim")
            + Text(f"gate: {gate}\n", style="yellow"),
            title="run narration",
            border_style="cyan",
        )
    )
    sources = nar.get("sources", [])
    if sources:
        console.print(f"\n[dim]read ({len(sources)}):[/dim]")
        for s in sources:
            console.print(f"  [dim]• {s}[/dim]")
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
    rh = nar.get("rulings_honored", [])
    if rh:
        console.print(f"\n[dim]rulings honored ({len(rh)}):[/dim]")
        for r in rh:
            console.print(f"  [dim]• {r['file']}:{r['line']} — {r['text']}[/dim]")
    wb = nar.get("write_back", [])
    if wb:
        console.print(f"\n[dim]write-back ({len(wb)} files):[/dim]")
        for f in wb[:10]:
            console.print(f"  [dim]• {f}[/dim]")
        if len(wb) > 10:
            console.print(f"  [dim]... +{len(wb) - 10} more[/dim]")
    console.print(f"\n[dim]draft rule: {nar.get('draft_rule', '')}[/dim]")
    console.print("")


def _show_status(console: Console, core: Core) -> None:
    console.print(banner())
    _show_pending(console, core)
    pending = core.pending()
    if pending:
        first = pending[0]
        rows = first.get("content", {}).get("rows", [])
        if rows:
            r1 = rows[0]
            draft = r1.get("draft", "")
            if draft:
                console.print(f"\n[dim]first message draft (row 1):[/dim]  [cyan]{r1.get('company','?')}[/cyan]")
                console.print(f"  {draft[:200]}")
    audit = core.audit_recent()
    if audit:
        console.print(f"\n[dim]recent audit ({len(audit)} entries):[/dim]")
        for a in audit[-6:]:
            console.print(f"  [dim]{a['id'][:10]}[/dim]  {a['capability']}  {a['status']}  "
                          f"{a['fired_at'][:19]}")


def _repl(console: Console) -> None:
    """Hermes-patterned conversational REPL. Session-based, turn-based,
    with inline approvals. Phase 1: terminal REPL; later phases can surface
    this through a richer conversational surface without changing the backend."""
    core = Core()
    sessions = SessionManager()
    session = sessions.create("default", workspace="default", channel="outbound")
    welcome(console)
    console.print(f"[dim]session [cyan]{session.id}[/cyan] started · workspace={session.workspace} · channel={session.channel}[/dim]\n")

    while True:
        try:
            line = Prompt.ask("[bold cyan]you[/bold cyan]")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]bye[/dim]")
            break
        if not line.strip():
            continue
        if line.strip().lower() in ("quit", "exit", "q"):
            console.print("[dim]bye[/dim]")
            break
        if line.strip().lower() == "help":
            console.print(help_panel())
            continue
        if line.strip().lower() == "clear":
            console.clear()
            console.print(banner())
            continue
        if line.strip().lower() == "vault":
            console.print(f"[bold cyan]{VAULT_DIR}[/bold cyan]")
            continue
        if line.strip().lower() == "dashboard":
            dashboard(console, core)
            continue
        if line.strip().lower() == "preview":
            open_preview(core, console)
            continue
        if line.strip().lower() == "status":
            dashboard(console, core)
            continue
        if line.strip().lower() == "rulings":
            for r in core.list_rulings():
                console.print(f"  [dim]{r['date']}[/dim]  {r['text']}")
            continue

        # parse: run <capability> [params]
        if line.strip().lower().startswith("run "):
            parts = line.strip().split()
            cap = parts[1] if len(parts) > 1 else ""
            if cap not in ("signal-outbound", "money-loop", "content-batch"):
                console.print(f"[red]unknown capability {cap}[/red]")
                continue
            top_n = 8
            for p in parts[2:]:
                if p.startswith("top_n="):
                    top_n = int(p.split("=", 1)[1])
            core.run(cap, top_n=top_n, workspace=session.workspace, channel=session.channel)
            console.print(f"[green]ran {cap} — top_n={top_n}[/green]")
            _show_pending(console, core)
            continue

        # parse: approve <id> / hold <id>
        if line.strip().lower().startswith("approve "):
            aid = line.strip().split()[1]
            core.approve(aid)
            console.print(f"[green]approved {aid}[/green]")
            continue
        if line.strip().lower().startswith("hold "):
            aid = line.strip().split()[1]
            core.hold(aid)
            console.print(f"[yellow]held {aid}[/yellow]")
            continue

        # parse: add-ruling <text>
        if line.strip().lower().startswith("add-ruling "):
            text = line.strip()[len("add-ruling "):]
            core.add_ruling(text)
            console.print("[green]ruling added[/green]")
            continue

        # parse: query <topic>
        if line.strip().lower().startswith("query "):
            topic = line.strip()[len("query "):]
            core.query(topic, console=console)
            continue

        # anything else: echo with a hint
        console.print(Panel(
            f"[dim]I didn't understand that. Try [bold]help[/bold] for commands, "
            f"or say [bold]run signal-outbound top_n=20[/bold].[/dim]",
            title="didn't understand",
            border_style="yellow",
        ))


if __name__ == "__main__":
    sys.exit(main())
