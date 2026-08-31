---
name: file-organizer
description: "Scan, classify, rename, and reorganize files by client/project/type with metadata sidecars."
version: 0.1.0
author: Alejandro Pascual (ppaassaallee), Hermes Agent
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [organization, file-management, classification, rename, proposal-hub, project-folders]
    related_skills: []
---

# File Organizer Skill

Scan a folder, classify every file by type/topic/client/sensitivity, reorganize into a structured hierarchy (Proposal Hub by client→type, Projects by project), rename files with a canonical convention, and write a metadata `INDEX.txt` in every folder.

## When to Use

- You have a messy OneDrive/Downloads/project folder with hundreds or thousands of files.
- You need files organized by: client, proposal type (service/product/solution/capability), project, year.
- You want files renamed to a canonical convention: `Company-Category-Project-Client-Year.ext`.
- You want an `INDEX.txt` sidecar in every folder describing its contents.
- **Don't use for:** live sync folders where external tools rewrite files concurrently.

## Prerequisites

- Python 3.9+ with `python-docx`, `openpyxl`, `python-pptx`, `PyPDF2`, `pymupdf`, `chardet` installed.
- Write access to the target folder.
- **Dry-run mode by default.** No files are moved or renamed until you pass `--execute`.
- **Read the classification rules reference** (`references/classification-rules.md`) before tuning any detection logic — it documents the exact keyword sets, the filename-only proposal rule, the department-name exclusion list, and known false positives observed during the AlliedGlobal run.
- **Read the debugging reference** (`references/debugging.md`) before running `--execute` on a large folder — it has the sandbox verification recipe, CSV NUL-byte workaround, and collision troubleshooting.

## How to Run

### Quick start (scan + classify only, no changes)

```bash
# Run from repo root (gravita-gtm/):
python3 skills/productivity/file-organizer/scripts/organize.py \
  --target "/Users/alejandropascual/Library/CloudStorage/OneDrive-AlliedGlobal" \
  --dry-run
```

### Full reorganization (dry-run first, then execute)

```bash
# 1. Inspect the proposed plan
python3 skills/productivity/file-organizer/scripts/organize.py \
  --target "/Users/alejandropascual/Library/CloudStorage/OneDrive-AlliedGlobal" \
  --dry-run --plan-file /tmp/plan.json

# 2. Review /tmp/plan.json, then execute
python3 skills/productivity/file-organizer/scripts/organize.py \
  --target "/Users/alejandropascual/Library/CloudStorage/OneDrive-AlliedGlobal" \
  --execute --plan-file /tmp/plan.json
```

### Selective modes

```bash
# Only classify and catalog (no moves, no renames)
python3 skills/productivity/file-organizer/scripts/organize.py \
  --target ~/OneDrive -o /tmp/catalog.csv --classify-only

# Only rename files (keep them in place, apply canonical names)
python3 skills/productivity/file-organizer/scripts/organize.py \
  --target ~/OneDrive --rename-only --execute

# Only reorganize into folders (use existing names)
python3 skills/productivity/file-organizer/scripts/organize.py \
  --target ~/OneDrive --reorg-only --execute
```

## Quick Reference

| Flag | Purpose |
|---|---|
| `--target PATH` | Folder to organize (required) |
| `--execute` | Actually move/rename files; default is dry-run |
| `--dry-run` | Show what would happen, making no changes |
| `--plan-file PATH` | Write full action plan as JSON for review |
| `--output PATH` | Write classification catalog CSV |
| `--classify-only` | Only scan + classify + catalog |
| `--rename-only` | Only apply canonical filenames in place |
| `--reorg-only` | Only move files into the folder hierarchy |
| `--proposal-hub PATH` | Override proposal hub location |
| `--projects-path PATH` | Override projects folder location |
| `--years PATH` | Path to years folder (default: target/YYYY) |
| `--sensitivity` | Detect and flag pricing/confidential content |
| `--tags` | Emit tag columns in catalog output |
| `--batch-size N` | Files per transaction batch (default 100) |
| `--verbose` | Detailed per-file logs |

## Procedure

### Phase 1 — Scan and Classify (no changes)

1. Walk the target folder recursively, skipping `.DS_Store`, `.Trash`, and known junk folders (`Inbox`, `Meetings`, `Recordings`, `Attachments`, `Microsoft Teams Chat Files`, `Microsoft Copilot Chat Files`, `Customer Success`, `Review - Potential Trash`).
2. For each file, extract:
   - **File type** from extension: `docx`, `pdf`, `pptx`, `xlsx`, `doc`, `xls`, `ppt`, `txt`, `md`, `csv`, `json`, `png`, `jpg`, `drawio`, `php`, `zip`, `otf`, `crswap`, etc.
   - **Encoding and extractable text** via `chardet` + format-specific extractors (see `scripts/text_extract.py`).
   - **Topic** — first 2-3 lines of text or filename keywords.
   - **Client** — named entities in filename/text: OneSource, AlliedGlobal, Tigo, Banrural, PTC, Kustomer, IVA, DGA, TPG, Apex, Claro, Vensure, Verizon, Talsa, TECO, Solvo, CPG, Woman/Equipara, Igss, Hospital, etc.
   - **Is proposal?** — filename or text contains `Proposal`, `Propuesta`, `SOW`, `Statement of Work`, `Cotización`, `Presupuesto`, `Oferta`, ` RFP response`, `Bid`.
   - **Proposal type** — `service`, `product`, `solution`, `capability`, `internal`, `pricing`, `transformation`, `CX`, `BPO`, `IVA`, `Healthcare`, `Digital Products`, `Staffing`, `Speech Analytics`, `F&A`, `RevOps`, `M&A`, `BPO`. Inferred from filename keywords, category folders, and text.
   - **Document category** — `proposal`, `sow`, `contract`, `plan`, `deck`, `report`, `pricing`, `data`, `spec`, `brief`, `template`, `internal`, `notes`, `tracking`, `invoice`, `po`, `email`, `image`, `font`, `archive`, `code`, `other`.
   - **Date** — from filename `YYYY-MM-DD`, `YYYY-MM`, `YYYY`, or file mtime. Priority: filename date > mtime.
   - **Sensitivity flags** — pricing/cost/fee words, `confidential`, `NDA`, `secret`, salary/compensation numbers, MFA/password, PII patterns (email, phone, ID numbers). Each flag is a yes/no plus the matched term.
   - **Serving company** — which company the file was created for/on behalf of: `AlliedGlobal`, `OneSource`, `Equipara`, `Woman`, or `Internal` (not client-facing).
3. Write a row to the catalog CSV for every file.

### Phase 2 — Plan the Reorganization

4. Group files into two top-level buckets:
   - **Proposal Hub** — every file classified as a proposal/SOW/offer. The existing `Proposal Hub/` folder is the default target.
   - **Projects** — everything else, organized by project.
5. For proposals, build the target path:
   ```
   Proposal Hub/<client>/<type>/<renamed file>
   ```
   - `<client>` = serving company or client name (OneSource, AlliedGlobal, Tigo, Banrural, etc.)
   - `<type>` = proposal type: `Service`, `Product`, `Solution`, `Capability`, `Internal`, `Pricing`, `SOW`, `Transformation`, `CX`, `BPO`, `IVA`, `Healthcare`, `Digital-Products`, `Staffing`, `Speech-Analytics`, `F&A`, `RevOps`, `M&A`.
   - If a proposal has no identifiable client, use `Unassigned`.
   - If a proposal has no identifiable type, use `Uncategorized`.
6. For non-proposals, build the target path:
   ```
   Projects/<project>/<category>/<renamed file>
   ```
   - `<project>` = project name extracted from filename/text. Known projects: Tigo, Banrural, PTC, Kustomer, IVA, DGA, TPG, Apex, Claro, Vensure, Verizon, Talsa, TECO, Solvo, OneSource, AlliedGlobal internal, etc.
   - If no project is identifiable, infer a category folder: `GTM`, `Operations`, `People-Finance`, `Meetings`, `Strategy`, `Administration`, `Resources`, `Uncategorized`.
   - `<category>` = document category: `Plans`, `Reports`, `Decks`, `Proposals`, `Contracts`, `SOWs`, `Pricing`, `Data`, `Specs`, `Briefs`, `Templates`, `Internal`, `Notes`, `Tracking`, `Invoices`, `Emails`, `Images`, `Fonts`, `Archives`, `Code`, `Other`.
7. For every target folder that will receive files, plan an `INDEX.txt` sidecar with:
   - Folder path
   - File count
   - Per-file rows: renamed filename, original filename, type, topic, client, proposal type, doc category, date, sensitivity flags, tags
8. Write the full plan (moves + renames + sidecars) to `--plan-file` as JSON if requested.

### Phase 3 — Rename

9. Apply canonical filename:
   ```
   <Year>-<Company>-<Category>-<Project>-<Client>-<Description>.<ext>
   ```
   - `Year` — 4-digit year from date.
   - `Company` — serving company: `AlliedGlobal`, `OneSource`, `Equipara`, `Woman`, `Internal`.
   - `Category` — document category: `Proposal`, `SOW`, `Contract`, `Plan`, `Deck`, `Report`, `Pricing`, `Data`, `Spec`, `Brief`, `Template`, `Internal`, `Notes`, `Tracking`, `Invoice`, `PO`, `Email`, `Image`, `Font`, `Archive`, `Code`, `Other`.
   - `Project` — project short name or `General`.
   - `Client` — client name or `Internal`.
   - `Description` — sanitized topic/description, maximum ~40 chars, kebab-case.
   - Deduplicate by appending `_2`, `_3` when collisions occur.
10. Sanitize: lowercase the structured parts, title-case the description; replace spaces with hyphens; strip characters invalid on macOS/Windows.
11. When in `--rename-only` mode, rename files in place and stop.

### Phase 4 — Move and Write Sidecars (--execute only)

12. Create target directories as needed (parents created automatically).
13. Move each file to its target path. If the destination exists, keep both by appending a counter.
14. After each batch of N files, write/update `INDEX.txt` in every affected folder.
15. **Safety checks before any move:**
    - Source file still exists and has the expected size.
    - Destination parent directory is writable.
    - No target path is an ancestor of the source (avoid moving a folder into itself).
16. Report a summary: files scanned, classified, moved, renamed, skipped, errors, new folders created.

## Classification Rules (in depth)

### Proposal detection

A file is a proposal when any of these are true:
- Filename (case-insensitive) contains: `proposal`, `propuesta`, `sow`, `statement of work`, `cotización`, `cotizacion`, `presupuesto`, `oferta`, `rfp`, `bid`, `quote`, `quotation`, `scope of work`, `tos`, `terms of service`.
- File is inside an existing `Proposal Hub` folder.
- Text contains phrases like `we propose`, `presupuesto`, `cotización`, `valor del servicio`, `inversión`, `pricing`, `fees`, `tarifa`.

### Proposal type classification

Map from keywords and context:

| Type | Triggers |
|---|---|
| `Service` | service, servicios, managed services, BPO service, support, operaciones, atención al cliente, CX service |
| `Product` | product, productos, digital product, software, platform, kustomer, digital products |
| `Solution` | solution, soluciones, digital solution, transformation solution, end-to-end |
| `Capability` | capability, capabilities, capability-as-a-service, capa |
| `Internal` | internal, interno, deck interno, plan interno, propuesta interna |
| `Pricing` | pricing, precios, preciosunitarios, fee, tarifa, cost structure |
| `SOW` | statement of work, sow, alcance, alcance de trabajo, entregables |
| `Transformation` | transformation, transformación, cambio, tranformation |
| `CX` | customer experience, experiencia del cliente, CX |
| `BPO` | BPO, business process outsourcing, externalización |
| `IVA` | IVA, interactive voice, voice, voz |
| `Healthcare` | healthcare, salud, hospital, clinica, eps |
| `Digital-Products` | digital products, productos digitales |
| `Staffing` | staffing, personal, reclutamiento, talent |
| `Speech-Analytics` | speech analytics, analitica de voz, speech |
| `F&A` | finance & accounting, finanzas, accounting |
| `RevOps` | revenue operations, revops, operaciones comerciales |
| `M&A` | M&A, mergers, fusiones, adquisiciones |

### Document category

| Category | Triggers |
|---|---|
| `Proposal` | proposal, propuesta, oferta, cotización, bid, rfp response |
| `SOW` | statement of work, sow, alcance |
| `Contract` | contract, contrato, agreement, acuerdo, MSA, NDA |
| `Plan` | plan, planificación, proyecto, roadmap, cronograma |
| `Deck` | deck, presentación, pptx, ppt, slides |
| `Report` | report, reporte, informe, resumen, estado |
| `Pricing` | pricing, precios, tarifa, fee, cost, cotización (when not a proposal) |
| `Data` | data, datos, xlsx, csv, dataset, base de datos |
| `Spec` | spec, especificaciones, requirements, requisitos, api |
| `Brief` | brief, briefing, brief de |
| `Template` | template, plantilla, template |
| `Internal` | internal, interno, memo, comunicación interna |
| `Notes` | notes, notas, meeting notes, acta |
| `Tracking` | tracking, seguimiento, pipeline, forecast |
| `Invoice` | invoice, factura, invoice, billing |
| `PO` | PO, purchase order, orden de compra |
| `Email` | email, correo, message, mensajes |
| `Image` | png, jpg, jpeg, gif, svg, screenshot |
| `Font` | otf, ttf, font, fuente |
| `Archive` | zip, rar, tar, gz, 7z |
| `Code` | php, js, py, html, css, json, xml, sql |
| `Other` | anything not matched |

### Sensitivity detection

Flag a file as containing sensitive content when text matches:

| Flag | Triggers |
|---|---|
| `pricing` | price, pricing, cost, fee, tarifa, precio, presupuesto, monto, cuota, investment amount, fee schedule |
| `confidential` | confidential, confidencial, secret, secreto, private, privado, restricted |
| `NDA` | NDA, non-disclosure, no divulgar, confidencialidad |
| `salary` | salary, salario, compensación, compensacion, payroll, nómina, nomina, benefits, beneficios |
| `PII` | email addresses, phone numbers, ID numbers, passport, DPI, DUI, cédula |
| `financial` | revenue, ingresos, ganancias, P&L, profit, margen, financial statement, estado financiero |
| `strategy` | strategy, estrategia, plan estratégico, competitive (may or may not be sensitive — flag anyway) |

### Client / serving company detection

**Serving company** (who the file is from/for):
- `AlliedGlobal` — filename or text references AlliedGlobal as the advisor/consultant.
- `OneSource` — references OneSource.
- `Equipara` / `Woman` — references Equipara or Woman (Ventas/Equipara).
- `Internal` — generic internal files not tied to a specific serving company.

**Client** (who the work is for):
Named entities surfaced from filename + text. The classifier maintains a known-client list per industry vertical:

| Vertical | Clients |
|---|---|
| Telecom | Tigo, Claro, Movistar, Banco Industrial (BI), TPG, Banrural, BAC, ABC, APEX, PTC, DGA |
| Healthcare | Hospital, Clínica, EPS, Salud, Healthcare, Igss, San Vicente, Herrera Llerandi |
| Retail | OneSource, Sears, Walmar, Target, Carrefour, PriceSmart, Ripley, Fungi, Farmacia, Maxicolor |
| BPO/Operations | Vensure, TPA, BPO client names |
| Technology | Kustomer, Zendesk, Salesforce, Microsoft, Google, Apple, AWS, OpenAI |
| Government | Estado, Ministerio, GOB, municipalidad, alcaldía |
| Other | Any capitalized proper noun not otherwise categorized |

When a client cannot be identified, use `Unassigned`.

## INDEX.txt Format

Every target folder receives an `INDEX.txt` sidecar. Format:

```
FOLDER: <absolute path>
CREATED: <ISO timestamp>
FILE_COUNT: <n>

# <file> | type | topic | client | proposal_type | doc_category | date | sensitivity | tags
<renamed filename> | <doc type> | <topic> | <client> | <proposal type or '-'> | <doc category> | <date or '-'> | <sensitivity flags comma-sep or none> | <tags comma-sep>
...
```

## Known Projects List (for project extraction)

When a file is not a proposal, the project is extracted from the filename/text. Known projects include:

```
Tigo, Banrural, PTC, Kustomer, IVA, DGA, TPG, Apex, Claro, Vensure, Verizon,
Talsa, TECO, Solvo, OneSource, AlliedGlobal, Equipara, Woman/Equipara,
CPG, Igss, Hospital Herrera Llerandi, San Vicente, Startups, Digital Products,
Remote Workforce, Retention, Strategy, Marketing, OCR, Taroko, Tik Tok/TikTok,
Sparring, WOM Colombia, WOM Ventas Chile, Tigo Paraguay, Value Added Services,
Staple/ Staples
```

When no project matches, fall back to a category folder structure:
```
Projects/<category>/
```
where category is one of: `GTM`, `Operations`, `People-Finance`, `Meetings`, `Strategy`, `Administration`, `Resources`, `Uncategorized`.

## Pitfalls

1. **Huge folders.** The OneDrive has ~35k files. Always dry-run first. Use `--batch-size` to control transaction size. Run in phases (classify, then rename, then reorg) if the folder is very large.
2. **Filename collisions.** The organizer appends `_2`, `_3`, etc. Two files with identical canonical names are not overwritten.
3. **Date ambiguity.** Prefer filename dates over mtime. When both are absent, the date field is `-` (unknown).
4. **Multi-lingual content.** Files can be in Spanish or English. Keyword matching is case-insensitive and accepts both languages.
5. **Proposals inside project folders.** A file may live under `2022/Tigo/GTM/` but still be a proposal. The classifier prioritizes content over folder location.
6. **Extractable-text limits.** Scanned PDFs, images, and binary formats produce no text. Those files are classified by filename and extension only, and the topic field is `-`.
7. **OneDrive sync.** Do not run `--execute` while OneDrive is actively syncing large batches — move operations can race with sync. Pause sync or run on a local copy first.
8. **Proposal detection is filename-only, NOT text-body.** Do NOT extend `_is_proposal` to scan document body text for keywords like "propuesta", "presupuesto", "pricing", or "proyecto". Doing so produces false positives: internal plans, project inventories, and spec docs routinely mention these words in body text without being proposals. Only filename patterns (e.g. `*_Proposal*`, `*_Propuesta*`, `*_Cotizacion*`, `*_SOW*`) trigger proposal classification. Body-text classification belongs to `doc_category`, not proposal detection. (Discovered empirically: a project plan file with "propuesta" in a slide, and a requirements spec with "requisitos" + "pricing" in body text, were both misclassified as proposals before this rule was applied.)
9. **Department names are NOT clients.** Functional folder names (`GTM`, `Operations`, `CX`, `Marketing`, `Healthcare`, `Transformation`, `Strategy`, `Meetings`, `People-Finance`, `Finance`, `Retention`, `Staffing`, `BPO`, `IVA`, `Speech Analytics`, `F&A`, `RevOps`, `M&A`, `Digital Products`, `Internal`, `General`, `Services`) must be excluded from client detection. Without this filter, hundreds of files get assigned to fake client folders because the path contains a department name that matches a client-name keyword list. The classifier maintains separate `CLIENTS` (proper-noun companies) and `DEPARTMENT_NAMES` sets; client detection filters both out. (Discovered empirically: `AlliedGlobal`, `Operations`, `Marketing`, `CX`, etc. were each being reported as clients for 10-600 files before this filter was applied.)
10. **Doc category uses filename-first matching, not body-text.** `_classify_doc_category` matches keywords against the filename only, falls back to file extension, and only inspects body text when the filename is empty or shorter than 5 characters. Concatenating name + body text and matching against the body causes false categories — e.g. `INDEX.md` (whose body mentions "Proposal Hub") was classified as `proposal` instead of `internal`. (Discovered empirically during the 1000-file dry run.)
11. **CSV output may contain NUL bytes from binary text extraction.** When `pymupdf` or `PyPDF2` extracts text from malformed PDFs, NUL bytes can appear in the `text_preview` column and crash `csv.DictReader`. Any script consuming the catalog CSV must strip `\\x00` from all fields before parsing. See `references/debugging.md` for the fix.
12. **Collision handling resolves on-the-fly during move.** The `dedup_name()` call during planning is a pre-check, but the actual move also resolves collisions by appending `_2`, `_3` if the destination appears between planning and execution (e.g. due to OneDrive sync). If a move still fails with "dest exists", check `references/debugging.md`.
13. **Always verify on a sandbox first.** Before running `--execute` on a large folder, copy a representative 20-100 file subfolder to `/tmp/organize-test`, run the full dry-run + execute cycle there, and verify file counts and sidecars. The sandbox recipe is in `references/debugging.md`.
13. **`Healthcare` is a vertical/domain, not a specific client company.** It was briefly in the `CLIENTS` set, which caused "Healthcare" to appear as a client for hospital/PHI files. It belongs only in proposal-type and department-name classification, not client detection. Same reasoning applies to other domain words that double as functional categories (`Transformation`, `CX`, `BPO`, etc.).

## Verification

After running with `--execute`:

1. Check the plan JSON or catalog CSV for unexpected moves (e.g., files moving outside the target tree).
2. Spot-check 5-10 files in Proposal Hub/<client>/<type>/ — confirm they are actually proposals for that client/type.
3. Spot-check 5-10 files in Projects/<project>/ — confirm they belong to that project.
4. Open 2-3 INDEX.txt files and confirm the metadata is accurate.
5. Confirm no files were lost: `find <target> -type f | wc -l` should equal the pre-run count minus any files you intentionally excluded.
6. If anything looks wrong, run again with `--dry-run` and `--plan-file`, inspect, and adjust classification rules before re-executing.
