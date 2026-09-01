---
name: file-organizer
description: "Content-aware file organization: read each file, infer client→project→topic, reorganize into Proposal/Projects/Internal/Trash buckets, rename human-readably."
version: 0.2.0
author: Alejandro Pascual (ppaassaallee), Hermes Agent
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [organization, file-management, classification, rename, semantic-classification, content-aware]
    related_skills: [document-classification]
---

# File Organizer Skill (semantic / content-aware)

Reorganize a large folder (e.g. a live OneDrive) by **reading each file's
content** and inferring its real meaning — not by matching filename keywords.
This is the version that replaced the original keyword-based classifier after
the user rejected keyword matching ("you need to understand each file").

## When to Use

- A messy OneDrive/Downloads/project folder with thousands of files that need
  semantic organization.
- You need a hierarchy ordered **Client → Project → Topic** (the user's required
  order of precedence).
- You need four top-level buckets: `Proposal/`, `Projects/`, `Allied Global/`,
  `Potential Trash/`.
- You need files renamed to a human-readable convention (no codes/hashes/IDs).
- **Don't use for:** live sync folders while they're actively syncing large
  batches (moves race with sync).

## Entry Points

Two scripts exist. **Use `organize_semantic.py`** — the other is legacy.

| Script | Status | What it does |
|---|---|---|
| `scripts/organize_semantic.py` | ✅ **use this** | Content-aware pipeline: `semantic_classifier` → plan → move |
| `scripts/semantic_classifier.py` | ✅ engine | Reads text, infers client/project/topic/bucket/trash |
| `scripts/text_extract.py` | ✅ engine | Text extraction for docx/pdf/pptx/xlsx/txt/etc. |
| `scripts/pdf_worker.py` | ✅ engine | Subprocess-isolated PDF parsing (hang-proof) |
| `scripts/sidecar.py` | ✅ helper | Writes `INDEX.txt` per folder |
| `scripts/classifier.py` | ⛔ legacy | Original keyword classifier — do not use |
| `scripts/organize.py` | ⛔ legacy | Original keyword CLI — do not use |

## Prerequisites

- Python 3.9+ with `python-docx`, `openpyxl`, `python-pptx`, `PyPDF2`,
  `pymupdf` (fitz), `chardet` installed.
- Write access to the target folder.
- **Dry-run by default** — no moves unless `--execute` is passed.

## How to Run

```bash
# From repo root (gravita-gtm/):
cd skills/productivity/file-organizer/scripts

# Dry-run (plan + catalog only, no changes)
python3 organize_semantic.py \
  --target "/Users/alejandropascual/Library/CloudStorage/OneDrive-AlliedGlobal" \
  --plan-file /tmp/plan.json --catalog /tmp/catalog.csv

# Execute (actually move/rename)
python3 organize_semantic.py \
  --target "/Users/alejandropascual/Library/CloudStorage/OneDrive-AlliedGlobal" \
  --execute --plan-file /tmp/plan.json --catalog /tmp/catalog.csv

# Limit to N files for a sample test
python3 organize_semantic.py --target <path> --limit 50
```

## The Four-Bucket Output

```
<target>/
├── Proposal/          # proposals/SOWs/pricing, then Client → Project
├── Projects/          # client work, then Client → Project
├── Allied Global/     # internal consolidated: Type → Project
├── Potential Trash/   # duplicates + personal + system junk + boldr/rimoto
└── Microsoft ... Chat Files/   # left untouched
```

### Hierarchy inside each bucket

- **Proposal / Projects:** `Client/Project/<topic-named file>` (Client first,
  then Project — the user's required precedence). No client → `Unassigned/`.
- **Allied Global:** `Type/Project/<file>` (internal docs have no client).
- **Trash subfolders:** `duplicate/`, `personal_cv/`, `personal_receipt/`,
  `personal_bank_statement/`, `personal_account/`, `boldr_rimoto/`,
  `shortcut_or_system/`, `Shortcut/`.

### Rename convention

`Company-Category-Topic-Client-Year.ext` — e.g.
`AlliedGlobal-Proposal-Omnicanal-Tigo-2023.pdf`. Topic is a **human-readable**
subject, never an ID/hash/code. Code & media files keep their original names.

## Classification Model (content-first)

For every business document (docx/pdf/pptx/xlsx/doc/xls/ppt/msg/csv/txt), the
pipeline reads the extracted text and infers:

1. **Trash first** (conservative — see Pitfalls).
2. **Client** — the entity the work is *for*, matched by position (earliest
   occurrence in title region wins, not longest name).
3. **Project** — engagement/campaign within the client (conservative: only call
   campaigns + explicit "PROJECT <Name>").
4. **Topic** — the meaningful subject, junk-filtered.
5. **Bucket** — Proposal / Projects / Allied Global, from doc type + client.

Code/media files short-circuit to `Allied Global/<Type>` with no fake client.

## Pitfalls (all discovered empirically — read before changing anything)

1. **"resume" matches "resumen".** The Spanish word "resumen" (summary) contains
   the substring "resume". A naive CV detector trashed every proposal with an
   "Resumen ejecutivo". Always word-bound (`\bresume\b`) and require co-occurring
   personal-data markers (birth date, DPI/NIT, marital status) or a filename
   CV signal (`cv-`, `-resume`).
2. **CVs are only personal when owned by the user.** "Alejandro Pascual" as an
   author signature is NOT a trash signal — it appears in his own business docs.
   Genuine CVs are documents *dominated* by personal bio data.
3. **Business finance words are not trash.** "invoice date", "payment method",
   "estado de cuenta", "transacciones del mes" appear in *every* business
   invoice and client P&L. Bank statements are personal only when the owner's
   name is present. Amazon orders match a specific signature only.
4. **A corrupt PDF hangs PyMuPDF (fitz) at the C level.** Python's SIGALRM
   cannot interrupt C code — one bad PDF spun a run for ~3 hours. Always extract
   PDFs via `pdf_worker.py` in a subprocess with a hard-kill timeout (30s).
5. **Spanish QA call-labels are not projects.** "Buena" (good call) / "Mala"
   (bad call) / "Contraejemplo" (counterexample) are speech-analytics scoring
   labels, not folders. Audio calls file under their client only. Real campaigns
   translate: cobros→collections, venta→sales, bienvenida→welcome, no-venta→no-sale.
6. **Over-eager project extraction creates garbage folders.** "Propuesta
   Comercial…" (in every Spanish proposal) and random title-case body text were
   extracted as "projects" (e.g. `com-erci-al-banrural-presentado-por`). Project
   extraction must be conservative — a wrong project folder is worse than none.
7. **Department/team names are not clients.** "Carolina", "Teams", "General",
   "Logo", "Health", "Estado" (Spanish "status"), "Startups" were all matched as
   fake clients. Keep a clean proper-noun client list; tech vendors (Microsoft/
   Apple/AWS) are tools, not clients.
8. **The OneDrive root path names every file "AlliedGlobal".** `_detect_client`
   must skip path components starting with `onedrive-*`.
9. **Dedupe by content hash, not (name,size).** "logo.png"/"README.md" appear
   legitimately in many folders — only byte-identical content is a duplicate.
10. **CSV catalog may contain NUL bytes** from binary text extraction. Strip
    `\x00` before `csv.DictReader`.
11. **Boldr / rimoto are user-directed trash.** Match `\bboldr\b` / `\brimoto\b`
    in content OR filename → `Potential Trash/boldr_rimoto/`.
12. **Run the full scan in the background with `notify_on_complete`.** It re-reads
    ~36k files and takes 15+ min. Incremental JSONL output survives crashes.

## Verification

1. Spot-check `Proposal/<client>/<project>/` — confirm files are actually that
   client's proposals.
2. Spot-check `Potential Trash/personal_cv/` — confirm every file is a real
   resume (name it after the person), zero proposals.
3. `find <target> -type f | wc -l` before/after — confirm no files lost.
4. Confirm zero Spanish QA folders (`buena`/`mala`/`cobros`/`venta`) remain;
   only English campaign names (`collections`/`sales`/`welcome`).
