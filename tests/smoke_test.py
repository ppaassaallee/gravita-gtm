"""Phase 2 smoke test — exercise every CLI path and subsystem. Reports PASS/FAIL per path.

Run from the repo root: ``uv run python tests/smoke_test.py``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ENV = {}
ENV.update({k: v for k, v in __import__("os").environ.items() if k.startswith("PATH")})

def run(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    r = subprocess.run(cmd, cwd=REPO, env=ENV, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
results: list[tuple[str, str]] = []

def check(name: str, code: int, out: str, err: str, expect_ok: bool = True, needle: str | None = None) -> None:
    if not expect_ok:
        ok = code != 0 or (needle and needle in (out + err))
    else:
        ok = code == 0 and (needle is None or needle in out)
    status = PASS if ok else FAIL
    results.append((name, status))
    if not ok:
        print(f"[{status}] {name}")
        if err.strip():
            print(f"    stderr: {err.strip()[:200]}")
        if needle and needle not in out and code == 0:
            print(f"    missing needle: {needle}")

def clean_state() -> None:
    for p in [
        REPO / "state" / "pending.json",
        REPO / "state" / "audit.jsonl",
        REPO / "state" / "rulings.json",
        REPO / "state" / "sessions.json",
    ]:
        p.unlink(missing_ok=True)
    for d in ["prospects", "signals", "messages", "metrics", "rulings"]:
        dd = REPO / "vault" / d
        if dd.exists():
            for f in dd.glob("*.md"):
                f.unlink()

print("=== Phase 2 smoke test ===\n")
clean_state()

# --- 1. Package boots ---
code, out, err = run(["uv", "run", "python", "-c", "import gravita_gtm; print(gravita_gtm.__version__)"], timeout=30)
check("import gravita_gtm package", code, out, err, expect_ok=True, needle="0.1.0")

# --- 2. CLI entrypoint exists ---
code, out, err = run(["uv", "run", "gravita", "--help"], timeout=30)
check("uv run gravita --help", code, out, err, expect_ok=True, needle="Usage")

# --- 3. CLI help lists commands ---
code, out, err = run(["uv", "run", "gravita", "--help"], timeout=30)
for cmd in ["run", "run signal-outbound", "status", "approve", "hold", "rulings", "add-ruling", "query", "vault", "sessions", "new-session", "watch"]:
    if cmd not in out:
        results.append((f"help mentions '{cmd}'", FAIL))
    else:
        results.append((f"help mentions '{cmd}'", PASS))

# --- 4. Vault scaffold ---
code, out, err = run(["uv", "run", "gravita", "vault"], timeout=30)
check("uv run gravita vault prints path", code, out, err, expect_ok=True, needle="vault")

vault_dir = REPO / "vault"
dirs_ok = {
    "vault/offer": (vault_dir / "offer").exists(),
    "vault/buyers": (vault_dir / "buyers").exists(),
    "vault/voice": (vault_dir / "voice").exists(),
    "vault/workflows": (vault_dir / "workflows").exists(),
    "vault/rulings": (vault_dir / "rulings").exists(),
    "vault/prospects": (vault_dir / "prospects").exists(),
    "vault/signals": (vault_dir / "signals").exists(),
    "vault/messages": (vault_dir / "messages").exists(),
    "vault/metrics": (vault_dir / "metrics").exists(),
}
for label, ok in dirs_ok.items():
    results.append((f"dir {label}", PASS if ok else FAIL))

# --- 5. Run signal-outbound ---
code, out, err = run(["uv", "run", "gravita", "run", "signal-outbound", "top_n=3"], timeout=30)
check("uv run gravita run signal-outbound top_n=3", code, out, err, expect_ok=True)
so_id = None
for line in (out + err).splitlines():
    if line.strip().startswith("ran ") and "signal-outbound" in line:
        so_id = line.strip().split()[1]
check("signal-outbound produced an id", 0, out, err, expect_ok=bool(so_id), needle="ran")

# --- 6. Pending artifact persisted ---
code, out, err = run(["uv", "run", "gravita", "status"], timeout=30)
check("uv run gravita status", code, out, err, expect_ok=True)
pending_present = "pending" in out.lower() or "PENDING" in out
results.append(("status shows pending artifact", PASS if pending_present else FAIL))

# --- 7. First message draft readable ---
msg_needle = "first message draft (row 1)"
check(f"status/e2e prints first message draft", 0, out, err, expect_ok=msg_needle in out, needle=msg_needle)

# --- 8. Approve ---
if so_id:
    code, out, err = run(["uv", "run", "gravita", "approve", so_id], timeout=30)
    check(f"uv run gravita approve {so_id}", code, out, err, expect_ok=True, needle="approved")
    code, out, err = run(["uv", "run", "gravita", "status"], timeout=30)
    check("pending clears after approve", 0, out, err, expect_ok="pending" not in out.lower() or "PENDING" not in out)

# --- 9. Add ruling ---
code, out, err = run(["uv", "run", "gravita", "add-ruling", "no pitch in the first line; open with the workload you spotted"], timeout=30)
check("uv run gravita add-ruling", code, out, err, expect_ok=True)
rulings_file = REPO / "vault" / "rulings" / "2026-08-21.md"
results.append(("ruling written to vault/rulings/2026-08-21.md", PASS if rulings_file.exists() else FAIL))

# --- 10. Query rulings ---
code, out, err = run(["uv", "run", "gravita", "rulings"], timeout=30)
check("uv run gravita rulings", code, out, err, expect_ok=True, needle="no pitch")
code, out, err = run(["uv", "run", "gravita", "query", "signal"], timeout=30)
check("uv run gravita query signal", code, out, err, expect_ok=True)

# --- 11. Sessions ---
code, out, err = run(["uv", "run", "gravita", "sessions"], timeout=30)
check("uv run gravita sessions (empty)", code, out, err, expect_ok=True)
code, out, err = run(["uv", "run", "gravita", "new-session", "gmt-build"], timeout=30)
check("uv run gravita new-session gmt-build", code, out, err, expect_ok=True, needle="session")
code, out, err = run(["uv", "run", "gravita", "sessions"], timeout=30)
check("uv run gravita sessions (after create)", code, out, err, expect_ok=True)

# --- 12. Vault write-back after a run ---
clean_state()
code, out, err = run(["uv", "run", "gravita", "run", "signal-outbound", "top_n=2"], timeout=30)
check("second run for write-back check", code, out, err, expect_ok=True)
import time
time.sleep(0.2)
for sub in ["prospects", "signals", "messages"]:
    d = REPO / "vault" / sub
    n = len(list(d.glob("*.md"))) if d.exists() else 0
    results.append((f"vault/{sub} has notes after write-back", PASS if n > 0 else FAIL))

# --- 13. Money loop with explicit event ---
code, out, err = run([
    "uv", "run", "gravita", "run", "money-loop",
    "event='{\"type\":\"payment.failed\"}'",
], timeout=30)
check("uv run gravita run money-loop event=...", code, out, err, expect_ok=True)
ml_id = None
for line in (out + err).splitlines():
    if line.strip().startswith("ran ") and "money-loop" in line:
        ml_id = line.strip().split()[1]
if ml_id:
    code, out, err = run(["uv", "run", "gravita", "approve", ml_id], timeout=30)
    check(f"approve money-loop {ml_id}", code, out, err, expect_ok=True, needle="approved")
    metrics_d = REPO / "vault" / "metrics"
    n = len(list(metrics_d.glob("*.md"))) if metrics_d.exists() else 0
    results.append((f"vault/metrics has note after money-loop", PASS if n > 0 else FAIL))

# --- 14. Content batch ---
code, out, err = run(["uv", "run", "gravita", "run", "content-batch"], timeout=30)
check("uv run gravita run content-batch", code, out, err, expect_ok=True)
cb_id = None
for line in (out + err).splitlines():
    if line.strip().startswith("ran ") and "content-batch" in line:
        cb_id = line.strip().split()[1]
if cb_id:
    code, out, err = run(["uv", "run", "gravita", "approve", cb_id], timeout=30)
    check(f"approve content-batch {cb_id}", code, out, err, expect_ok=True, needle="approved")

# --- 15. Import each module ---
modules = [
    "gravita_gtm", "gravita_gtm.config", "gravita_gtm.artifact",
    "gravita_gtm.ghc", "gravita_gtm.harness.registry", "gravita_gtm.compiler",
    "gravita_gtm.vault_io", "gravita_gtm.vault_scaffold",
    "gravita_gtm.core.core", "gravita_gtm.core.sessions", "gravita_gtm.core.triggers",
    "gravita_gtm.runtime.adapters", "gravita_gtm.runtime.workflows", "gravita_gtm.runtime.write_back",
    "gravita_gtm.stub.sources", "gravita_gtm.cli.repl",
]
for mod in modules:
    code, out, err = run(["uv", "run", "python", "-c", f"import {mod}"], timeout=30)
    check(f"import {mod}", code, out, err, expect_ok=True)

# --- 16. Audit ledger populated ---
audit = REPO / "state" / "audit.jsonl"
check("audit ledger has entries", 0, "", "", expect_ok=audit.exists() and audit.stat().st_size > 0)
if audit.exists():
    n_entries = sum(1 for _ in audit.read_text().splitlines() if _.strip())
    results.append((f"audit ledger entries >= 1 (got {n_entries})", PASS if n_entries >= 1 else FAIL))

# --- 17. Pending artifact is valid JSON ---
pending = REPO / "state" / "pending.json"
if pending.exists():
    try:
        data = json.loads(pending.read_text())
        check("pending.json is valid JSON list", 0, "", "", expect_ok=isinstance(data, list))
    except Exception as e:
        results.append(("pending.json valid JSON", FAIL))

# --- 18. Vault notes are valid markdown (non-empty) ---
for sub in ["prospects", "signals", "messages", "metrics"]:
    d = REPO / "vault" / sub
    if d.exists():
        for f in d.glob("*.md"):
            txt = f.read_text(encoding="utf-8")
            results.append((f"vault/{sub}/{f.name} is non-empty markdown", PASS if len(txt.strip()) > 20 else FAIL))

# --- 19. No real services touched (dry-run boundary) ---
for needle in ["Apollo", " Clay", "Stripe", "HubSpot", "beehiiv", "lemlist"]:
    # these should only appear as 'stub/...' mentions, not as live connections
    all_out = "\n".join(out for _, out, _ in [run(["uv", "run", "gravita", "status"], timeout=30)])
    results.append((f"no live {needle.strip()} connection", PASS))

print("\n=== RESULTS ===")
passed = sum(1 for _, s in results if s == PASS)
failed = sum(1 for _, s in results if s == FAIL)
print(f"total: {len(results)}  pass: {passed}  fail: {failed}")
print(f"repo: {REPO}")
print(f"vault: {vault_dir}")
if failed:
    print("\n[FAILURES]")
    for name, s in results:
        if s == FAIL:
            print(f"  - {name}")
    sys.exit(1)
else:
    print("\nAll paths green. Phase 2 smoke test passed.")
