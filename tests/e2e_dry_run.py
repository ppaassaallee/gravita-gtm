"""End-to-end dry-run test for the Gravita GTM backend.

Exercises the full loop: run -> inspect artifact -> approve -> audit log ->
vault write-back. Phase 1: stubs only, nothing touches a real service.

Run with: ``uv run python tests/e2e_dry_run.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

# ensure the package is importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from gravita_gtm.core.core import Core
from gravita_gtm.artifact import ArtifactStatus

console = Console()

# 1. Boot ------------------------------------------------------------------
core = Core()
console.print(f"[bold]boot ok — vault=[/bold] {core.triggers and 'wired'}")

# 2. Run signal-outbound ---------------------------------------------------
console.print("\n[dim]--- run signal-outbound top_n=3 ---[/dim]")
artifact = core.run("signal-outbound", top_n=3, workspace="default", channel="outbound")
console.print(f"[green]ran[/green]  {artifact.id}  {artifact.capability}  {artifact.status}")
console.print(f"  confidence rows: {len(artifact.confidence)}")
console.print(f"  accounts considered: {artifact.decision_evidence.get('accounts_considered')}")
console.print(f"  accounts kept: {artifact.decision_evidence.get('accounts_kept')}")
console.print(f"  accounts drafted: {artifact.decision_evidence.get('accounts_drafted')}")

# 3. Inspect the artifact --------------------------------------------------
console.print("\n[dim]--- research sheet (content) ---[/dim]")
table = Table(title="Research Sheet — top 3 rows", show_lines=True)
table.add_column("row", style="cyan")
table.add_column("company", style="green")
table.add_column("vertical")
table.add_column("employees")
table.add_column("changed")
table.add_column("confidence")
for row in artifact.content["rows"]:
    table.add_row(
        str(row["row"]),
        row["company"],
        row["vertical"],
        str(row["employees"]),
        row["what_changed"],
        str(row["confidence"].get("what_changed", "?")),
    )
console.print(table)

# show one draft
console.print("\n[dim]--- first message draft (row 1) ---[/dim]")
d0 = artifact.content["rows"][0]["draft"]
console.print(f"[bold]{d0}[/bold]\n")

# 4. Pending queue ---------------------------------------------------------
console.print("[dim]--- pending queue ---[/dim]")
for p in core.pending():
    console.print(f"  [cyan]{p['id']}[/cyan]  {p['capability']}  {p['status']}  {p['created_at'][:19]}")

# 5. Approve ---------------------------------------------------------------
console.print("\n[dim]--- approve ---[/dim]")
approved = core.approve(artifact.id)
console.print(f"[green]approved[/green]  {artifact.id}  ->  {approved.status if approved else 'None'}")
console.print(f"  pending after approve: {len(core.pending())}")

# 6. Audit log -------------------------------------------------------------
console.print("\n[dim]--- audit log ---[/dim]")
for e in core.audit_recent(5):
    console.print(f"  [dim]{e['id']}[/dim]  {e['capability']}  {e['status']}  "
                  f"risk={e.get('risk_class')}  approval={e.get('approval_mode')}  "
                  f"{e['fired_at'][:19]}")

# 7. Rulings ----------------------------------------------------------------
console.print("\n[dim]--- rulings (empty at start) ---[/dim]")
for r in core.list_rulings():
    console.print(f"  [dim]{r['date']}[/dim]  {r['text']}")

console.print("\n[dim]--- add a ruling ---[/dim]")
r = core.add_ruling("no pitch in the first line; open with the workload you spotted")
console.print(f"[green]added[/green]  {r['date']}  {r['text']}")

# 8. Query -----------------------------------------------------------------
console.print("\n[dim]--- query 'signal' ---[/dim]")
core.query("signal", console=console)

# 9. Vault check -----------------------------------------------------------
console.print("\n[dim]--- vault write-back check ---[/dim]")
from gravita_gtm.config import VAULT_DIR
for sub in ("prospects", "signals", "messages", "rulings"):
    d = VAULT_DIR / sub
    if d.exists():
        notes = list(d.glob("*.md"))
        console.print(f"  [cyan]{sub}/[/cyan]  {len(notes)} note(s)")
        for n in notes:
            console.print(f"    - {n.relative_to(VAULT_DIR)}  ({n.stat().st_size} bytes)")
    else:
        console.print(f"  [red]{sub}/[/red]  (not created yet)")

console.print("\n[dim]--- done ---[/dim]")
console.print("[bold green]Phase 1 backend is runnable: run -> inspect -> approve -> audit -> write-back.[/bold green]")
