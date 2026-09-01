#!/usr/bin/env python3
"""
Content-aware semantic classifier for the file-organizer skill.

Unlike classifier.py (which matched keywords against filenames), this reads
the extracted text of each file and makes decisions from the MEANING of the
content:

  * bucket        -> Proposal / Projects / Allied Global / Potential Trash
  * client        -> the real client the doc is FOR (from content, not path)
  * project/topic -> what the doc is ABOUT (from title + body text)
  * doc_type      -> proposal / contract / report / deck / plan / etc.

Trash detection runs FIRST and is conservative: only things that are clearly
not business work get flagged (personal receipts, bank statements, shortcuts,
system files, exact duplicates).
"""

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from text_extract import extract_text

# ---------------------------------------------------------------------------
# The user's own identity — anything in the user's own name is personal,
# NOT client work.
# ---------------------------------------------------------------------------
OWNER_NAMES = {
    "alejandro pascual",
    "david alejandro pascual",
    "david alejandro pascual aguilar",
    "pascual aguilar",
    "alejandro pascual aguilar",
}

# ---------------------------------------------------------------------------
# Known real clients (proper nouns, from AlliedGlobal/OneSource GTM work).
# Expanded with names seen across the folder tree.
# ---------------------------------------------------------------------------
# Real GTM/BPO clients (telcos, banks, retail, healthcare, gov) — these are
# who the business work is FOR. Matched with HIGH priority.
PRIMARY_CLIENTS = {
    # Telcos
    "Tigo", "Tigo Paraguay", "Claro", "Movistar", "WOM", "WOM Colombia",
    "WOM Ventas Chile", "Verizon",
    # Banks / financial — specific names only (bare "Banco" = generic "bank")
    "Banrural", "BAC", "Banco Industrial", "BancoUnion", "BCP",
    "Banco Estado",
    # Retail
    "Target", "Walmart", "Walmar", "Sears", "Carrefour", "PriceSmart",
    "Maxicolor", "Ripley", "Staples", "Staple",
    # Healthcare — specific names only (bare "Health"/"Salud" = generic words)
    "Hospital", "Clinica", "Clínica", "EPS", "IGSS", "Igss", "Farmacia",
    # Government / public sector
    "GOB", "Ministerio", "Municipalidad", "Alcaldia", "DGA",
    # BPO / other services
    "PTC", "TPG", "TECO", "Teco", "Talsa", "Solvo", "Kustomer", "Vensure",
    "Taroko", "Kruops", "CPG", "OCR", "Remote Workforce",
    "Value Added Services",
    # Consulting / enterprise
    "Accenture", "Capgemini", "Amwins", "CBC", "CAP", "CENCOSUD",
    "CENCOSUD SM IVR DEFLACION", "APEX", "APEX Chile", "APEX Colombia",
    "APEX Peru",
    # Education
    "Kumon", "KUMON",
    # Other named accounts (ABC is a real client in pricing docs)
    "Herrera Llerandi", "San Vicente", "TikTok", "Tik Tok", "ABC",
}

# Tech vendors / platforms — appear as TOOLS in docs, not as the client.
# Matched only as a last resort (a file with no primary client).
TECH_VENDORS = {
    "Microsoft", "Apple", "Google", "AWS", "Amazon", "OpenAI", "Salesforce",
    "Zendesk", "Samsung", "Meta", "Adobe", "IBM", "Oracle",
}

CLIENTS = PRIMARY_CLIENTS | TECH_VENDORS

# Department / internal function names — never clients.
DEPARTMENT_NAMES = {
    "GTM", "Operations", "People", "People-Finance", "Finance", "Meetings",
    "Marketing", "Strategy", "Retention", "CX", "BPO", "IVA", "Healthcare",
    "Speech Analytics", "Speech-Analytics", "Staffing", "F&A", "RevOps",
    "M&A", "Transformation", "Digital Products", "DigitalProducts",
    "Remote Workforce", "General", "Internal", "Services", "Service",
    "Product", "Solution", "Capability", "Technology", "Business", "Sales",
    "Support", "Admin", "Administration", "HR", "Human Resources",
    "Resources", "Inbox", "Inbox-Mail", "Teams", "Drive", "Files", "Site",
    "Sitio", "Commercial", "Delivery Governance", "Agentic Collections",
    "CPA Ventures", "Delivery", "Recruitment", "HR-Recuitment",
}

# Serving companies
SERVING_COMPANIES = ["AlliedGlobal", "OneSource", "Equipara", "Woman"]

# File types that are categorically not business documents (dot-less, to match
# the `ext` variable which is `suffix.lower().lstrip(".")`).
SYSTEM_JUNK_EXT = {
    "lnk", "url", "ds_store", "tmp", "temp", "part", "crdownload",
    "download", "idx", "pack", "rev", "sample",
}

# Code files — bucketed to Allied Global/Code, never content-classified
CODE_EXT = {
    "ts", "tsx", "js", "jsx", "mjs", "php", "py", "css", "scss", "html",
    "htm", "json", "xml", "sql", "sh", "java", "go", "rb", "vue", "svelte",
    "md", "markdown", "yml", "yaml", "toml", "ini", "conf", "drawio",
}

# Media files — bucketed to Allied Global/<subtype>, never content-classified
MEDIA_EXT = {
    "png", "jpg", "jpeg", "gif", "svg", "webp", "mp3", "wav", "mp4", "mov",
    "avi", "ico", "tiff", "bmp", "ttf", "otf", "woff", "woff2", "m4a", "ogg",
    "flac", "webm", "heic",
}


def _media_subtype(ext: str) -> str:
    if ext in ("png", "jpg", "jpeg", "gif", "svg", "webp", "ico", "tiff", "bmp", "heic"):
        return "Image"
    if ext in ("mp3", "wav", "m4a", "ogg", "flac"):
        return "Audio"
    if ext in ("mp4", "mov", "avi", "webm"):
        return "Video"
    if ext in ("ttf", "otf", "woff", "woff2"):
        return "Font"
    return "Media"

# ---------------------------------------------------------------------------
# Trash / personal signals (content-driven).
# CONSERVATIVE: only flag things that are UNAMBIGUOUSLY personal junk.
# Business invoices, price proposals, client P&L/analysis are NOT trash.
#
# The generic financial keywords ("invoice date", "payment method", "bill to",
# "estado de cuenta", "transacciones del mes") were removed — they appear in
# every business billing document and caused massive false positives.

# Amazon / retail order confirmations have a very specific signature.
AMAZON_ORDER_PATTERNS = [
    r"amazon\.com order",
    r"final details for order",
    r"sold by and invoiced on behalf of",
    r"order placed:",
    r"shipped on",
    r"order total:",
]

# Bank statements are only personal if the OWNER's name is present.
BANK_STATEMENT_PATTERNS = [
    r"transacciones del mes",
    r"balance de la cuenta",
    r"saldo en libros",
    r"retenidos y diferidos",
]

# Personal account signup pages (rare, personal)
PERSONAL_ACCOUNT_PATTERNS = [
    r"sign up \|",
    r"create your account",
    r"reset your password",
    r"verify your email",
    r"free first bag",
    r"personalized plan",
]

# Explicit user directive: Boldr / rimoto are to be trashed.
BOLDR_PATTERNS = [
    r"\bboldr\b",
    r"\brimoto\b",
]

# doc_type keyword sets (content-driven, order matters = priority)
DOC_TYPE_SIGNALS = {
    "proposal": [
        "propuesta", "proposal", "propuesta comercial", "propuesta de servicio",
        "propuesta de solucion", "propuesta de solución", "cotizacion",
        "cotización", "statement of work", "scope of work", "oferta de servicio",
        "rfp response", "bid response", "propuesta tecnica", "propuesta técnica",
    ],
    "contract": [
        "contrato de", "contract", "master service agreement", "msa", "nda",
        "non-disclosure", "addendum", "adendum", "términos y condiciones",
        "terminos y condiciones", "modificación de contrato", "modificacion de contrato",
    ],
    "sow": [
        "statement of work", "alcance del trabajo", "entregables", "scope of work",
    ],
    "pricing": [
        "precios unitarios", "tarifa por", "fee schedule", "cost structure",
        "pricing", "precio unitario", "estructura de precios", "cotización de precios",
    ],
    "report": [
        "informe", "reporte", "report", "dashboard", "resumen ejecutivo",
        "status report", "kpi", "metricas", "métricas", "resultados",
        "estado del proyecto", "avance",
    ],
    "deck": [
        "agenda", "next steps", "siguientes pasos", "gracias", "thank you",
        "q&a", "preguntas", "introducción", "introduccion", "welcome",
    ],
    "plan": [
        "cronograma", "roadmap", "plan de trabajo", "plan de proyecto",
        "planificacion", "planificación", "hitos", "milestones", "fases",
        "plan de implementacion", "plan de implementación",
    ],
    "spec": [
        "especificaciones", "requirements", "requisitos funcionales",
        "requisitos tecnicos", "requisitos técnicos", "specification",
        "historias de usuario", "user stories",
    ],
    "invoice": [
        "factura", "invoice", "numero de factura", "número de factura",
        "total a pagar", "fecha de emision", "fecha de emisión",
    ],
}


def _doc_type_from_content(text_lower: str, name_lower: str) -> str:
    """Determine the document type from MEANING, weighting WHERE the signal
    appears: title region (first 600 chars) is the doc's own type; a keyword
    buried deep in the body is a passing mention, not the document type."""
    def _score(haystack: str) -> str:
        scores = {}
        for dtype, signals in DOC_TYPE_SIGNALS.items():
            for s in signals:
                if s in haystack:
                    scores[dtype] = scores.get(dtype, 0) + 1
        if scores:
            return max(scores, key=scores.get)
        return ""

    # 1. Title region (strongest — "what this document IS")
    d = _score(text_lower[:600])
    if d:
        return d

    # 2. Filename
    d = _score(name_lower)
    if d:
        return d

    # 3. Full body (weakest — a mention, not the type; only if no other signal)
    d = _score(text_lower)
    if d:
        return d
    return ""


def _is_trash(text_lower: str, name_lower: str, ext: str, is_duplicate: bool) -> tuple:
    """Return (is_trash, reason). CONSERVATIVE: only unambiguous personal junk.

    Business invoices, price proposals, P&L, and client analysis are NOT trash
    even when they contain financial words — those words are the point of the doc.
    """
    # 1. Exact duplicates
    if is_duplicate:
        return True, "duplicate"

    # 2. System / shortcut / temp files
    if ext in SYSTEM_JUNK_EXT:
        return True, "shortcut_or_system"
    if name_lower.startswith("~$") or name_lower.startswith("._"):
        return True, "temp_file"

    # 3. Boldr / rimoto (explicit user directive — always trash)
    for pat in BOLDR_PATTERNS:
        if re.search(pat, text_lower) or re.search(pat, name_lower):
            return True, "boldr_rimoto"

    # 4. Amazon / retail order confirmations (specific signature only)
    for pat in AMAZON_ORDER_PATTERNS:
        if re.search(pat, text_lower):
            return True, "personal_receipt"

    # 5. Bank statements are ONLY personal if the OWNER's name is present.
    #    A client's "estado de cuenta" (Salcobrand) or bank analysis is business.
    name_present = any(nm in text_lower for nm in OWNER_NAMES)
    if name_present:
        for pat in BANK_STATEMENT_PATTERNS:
            if re.search(pat, text_lower):
                return True, "personal_bank_statement"

    # 6. Personal account signup pages
    for pat in PERSONAL_ACCOUNT_PATTERNS:
        if re.search(pat, text_lower):
            return True, "personal_account"

    # 7. Owner's CV/resume — UNAMBIGUOUS signals only.
    #    MUST use word boundaries: "resume" was matching "resumen" (Spanish
    #    "summary"), which trashed every proposal with an executive summary.
    #    "curriculum" alone also matches academic curriculum/training content,
    #    so require the full "curriculum vitae" / "hoja de vida" phrase.
    if name_present:
        # Unambiguous: full CV phrases or word-bounded English "resume"
        cv_signals = [
            r"\bhoja de vida\b",
            r"\bcurriculum vitae\b",
            r"\bcurrículum vitae\b",
            r"\bcurriculo vitae\b",
            r"\bcv\b",              # standalone "cv" (rare in business text)
            r"\bresume\b",          # word-bounded: NOT "resumen" (summary)
        ]
        # Secondary signals: only count if a primary CV marker is ALSO present
        secondary = [r"\bexperiencia laboral\b", r"\bexperiencia profesional\b"]
        for s in cv_signals:
            if re.search(s, text_lower) or re.search(s, name_lower):
                return True, "personal_cv"
        # "experiencia laboral/profesional" alone is common in staffing docs —
        # only treat as CV if a strong personal marker is also present.
        has_secondary = any(re.search(s, text_lower) for s in secondary)
        has_personal_marker = any(
            re.search(p, text_lower) for p in [
                r"\bfecha de nacimiento\b", r"\bdpi\b", r"\bestado civil\b",
                r"\bmarital status\b", r"\bfecha nacimiento\b",
            ]
        )
        if has_secondary and has_personal_marker:
            return True, "personal_cv"

    return False, ""


# Build a single combined regex of primary clients, longest-first, for
# position-aware matching (the client is the one named EARLIEST in the doc,
# not the longest name anywhere).
_PRIMARY_SORTED = sorted(PRIMARY_CLIENTS, key=len, reverse=True)
_CLIENT_RE = re.compile(
    r"(?<![a-z0-9])(" + "|".join(re.escape(c.lower()) for c in _PRIMARY_SORTED) + r")(?![a-z0-9])"
)


def _earliest_client(haystack: str) -> str:
    """Return the client name that appears EARLIEST in haystack (position-based,
    longest-at-same-position). This is the doc's subject, not a passing mention."""
    if not haystack:
        return ""
    best_pos = None
    best_client = ""
    best_len = -1
    for m in _CLIENT_RE.finditer(haystack):
        c = m.group(1)
        if best_pos is None or m.start() < best_pos or (m.start() == best_pos and len(c) > best_len):
            best_pos = m.start()
            best_client = c
            best_len = len(c)
    if best_client:
        # Return the canonical casing from PRIMARY_CLIENTS
        for c in _PRIMARY_SORTED:
            if c.lower() == best_client:
                return c
    return ""


def _detect_client(text_lower: str, name_lower: str, file_path: str) -> str:
    """Detect the real client by WHERE the name appears, earliest-first.

    Priority:
      1. Title region of content (first 600 chars)
      2. Full content
      3. Filename
      4. Path components (weakest)
    Tech vendors (Microsoft/Apple/Google/...) are NOT clients — they're tools
    referenced inside docs, so they are never matched here.
    """
    dept_lower = {d.lower() for d in DEPARTMENT_NAMES}

    # 1. Title region
    c = _earliest_client(text_lower[:600])
    if c:
        return c

    # 2. Full content
    c = _earliest_client(text_lower)
    if c:
        return c

    # 3. Filename
    c = _earliest_client(name_lower)
    if c:
        return c

    # 4. Path components
    for part in [p.lower() for p in Path(file_path).parts]:
        if part.startswith("onedrive-"):
            continue
        if part in dept_lower:
            continue
        c = _earliest_client(part)
        if c:
            return c

    return ""


def _detect_serving_company(text_lower: str, name_lower: str, client: str) -> str:
    combined = name_lower
    if text_lower:
        combined += " " + text_lower
    for company in SERVING_COMPANIES:
        cl = company.lower()
        if re.search(rf"(?<![a-z0-9]){re.escape(cl)}(?![a-z0-9])", combined):
            return company
    # If an external client was found, the serving company is AlliedGlobal
    if client and client not in ("", "AlliedGlobal", "OneSource"):
        return "AlliedGlobal"
    return ""


# Tokens that are NOT meaningful topic material — IDs, codes, hashes, emails,
# timestamps, metadata keys, machine hostnames. Filtered out before naming.
_TOPIC_JUNK_RE = re.compile(
    r"^(?:"
    r"\d[\d_]*$|"                     # pure numbers / ID strings
    r"[a-f0-9]{8,40}$|"               # hashes
    r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$|"  # uuid
    r".*@.*\.(?:com|cl|net|org|io)$|" # emails
    r"\d{1,2}[_]\d{1,2}[_]\d{1,2}(?:pm|am)?$|"  # 12_35_27 timestamps
    r".*\d{6,}.*$|"                   # anything with a long digit run (IDs)
    r"\d{4}-\d{2}-\d{2}t.*$|"         # ISO timestamps 2026-02-23T16:25.014Z
    r"\d+\.\d+.*$|"                   # decimals (duration 457.71994)
    r".*[^\x00-\x7f].*$"              # non-ascii garbage (binary)
    r")",
    re.IGNORECASE,
)

_METADATA_KEYS = {
    "metadata", "transaction_key", "deprecated", "request_id", "sha256",
    "created", "duration", "channels", "models", "model_info", "results",
    "alternatives", "transcript", "arch", "version", "name", "general",
    "nova", "call", "llc", "inc", "s", "a",
}

_STOPWORDS = {
    "the", "a", "an", "de", "la", "el", "los", "las", "del", "en", "y", "o",
    "for", "of", "to", "with", "and", "un", "una", "por", "para", "con",
    "que", "su", "sus", "es", "se", "al", "este", "esta", "este", "esta",
}

# Spanish call-center QA / campaign labels. These come from speech-analytics
# call transcripts. CAMPAIGNS (collections/sales/welcome) map to descriptive
# English project names. QA SCORES (buena/mala = good/bad call) are NOT real
# projects — they are dropped so audio calls just file under the client.
_CAMPAIGN_LABELS = {
    "cobros": "collections",
    "cobro": "collections",
    "venta": "sales",
    "ventas": "sales",
    "no venta": "no-sale",
    "no-venta": "no-sale",
    "bienvenida": "welcome",
    "bienvenido": "welcome",
    "oportunidad": "opportunity",
}

# QA scoring labels — never a project; audio calls just go under the client.
_QA_SCORE_LABELS = {
    "buena", "buenas", "bueno", "buen", "mala", "malas", "malo",
    "contraejemplo", "ejemplar", "ejemplo",
    "buena pyme", "mala pyme", "buena consumo", "mala consumo",
    "good call", "bad call", "noncompliance", "overall delivery",
    "top driver rechazo", "rechazo",
}


def _translate_label(label: str) -> str:
    """Return an English project name for a campaign label, or '' for a QA
    score (so the file just files under its client with no project folder)."""
    key = label.strip().lower()
    if key in _QA_SCORE_LABELS:
        return ""
    if key in _CAMPAIGN_LABELS:
        return _CAMPAIGN_LABELS[key]
    return label


def _extract_topic(text_lower: str, name_lower: str) -> str:
    """Extract a short HUMAN topic from the doc's meaning.

    Strategy:
      1. If the doc is a call transcript (first line has '– label'), use that
         label (e.g. "Cobros", "Bienvenida", "Venta", "Buena", "Contraejemplo").
      2. Otherwise, take meaningful words from the title region, filtering out
         codes, IDs, hashes, emails, timestamps, metadata keys, and stopwords.
    """
    if not text_lower:
        return ""

    # 1. Call-transcript label: "… – Cobros" or "… — Cobros"
    #    Cut at the first '{' (JSON metadata) so the label is clean text only.
    first_line = text_lower.split("\n")[0][:200]
    first_line = first_line.split("{")[0]
    m = re.split(r"[–—]\s*", first_line)
    if len(m) > 1:
        label = m[-1].strip()
        label = re.sub(r"[^\w\s]", " ", label)
        label = re.sub(r"\s+", " ", label).strip()
        words = label.split()
        # Keep only real words (no IDs/metadata)
        real = [w for w in words
                if not _TOPIC_JUNK_RE.match(w)
                and w.lower() not in _METADATA_KEYS
                and w.lower() not in _STOPWORDS]
        if real:
            raw = "-".join(real[:4])
            # Translate campaign names (cobros→collections); QA scores → empty
            translated = _translate_label(raw)
            if translated:
                return translated.replace(" ", "-")
            # QA score — fall through to title words (don't use "buena" as topic)
            # but skip returning the QA label itself

    # 2. Title-region words, junk-filtered
    title = text_lower[:600]
    # strip JSON metadata blobs
    title = re.sub(r'\{[^{}]*\}', ' ', title)
    words = re.findall(r"[a-záéíóúñü0-9@._-]+", title)
    topic_words = []
    for w in words:
        wl = w.lower()
        if wl in _STOPWORDS or wl in _METADATA_KEYS:
            continue
        if _TOPIC_JUNK_RE.match(wl):
            continue
        if len(wl) < 3:
            continue
        topic_words.append(wl)
        if len(topic_words) >= 5:
            break
    if topic_words:
        return "-".join(topic_words)

    return ""


@dataclass
class SemanticClassification:
    file_path: str
    file_name: str
    ext: str
    size_bytes: int
    text: str = ""
    bucket: str = ""            # Proposal | Projects | Allied Global | Potential Trash
    client: str = ""            # "" = internal/unassigned
    project: str = ""           # engagement/campaign/program within a client
    serving_company: str = ""
    topic: str = ""
    doc_type: str = ""
    is_trash: bool = False
    trash_reason: str = ""
    is_duplicate: bool = False
    date: str = ""
    sensitivity: dict = field(default_factory=dict)
    tags: list = field(default_factory=list)
    error: str = ""


def _detect_project(text_lower: str, name_lower: str, client: str,
                    text_original: str = "") -> str:
    """Extract the PROJECT (engagement/campaign/program) within a client.

    CONSERVATIVE — a wrong project folder is worse than none, so only extract
    from high-precision signals:
      1. Call-transcript campaign label ("… – Cobros" → "collections"). These
         are the real campaigns in this dataset.
      2. Explicit "PROJECT <Name>" / "PROYECTO <Name>" where <Name> is a short
         Title/Upper-case proper noun (e.g. "PROJECT TRANSATRON").
    Everything else → "" (files stay flat under the client with topic in name).
    """
    text = text_lower or ""
    title_region = (text_original or text)[:500]

    # 1. Call-transcript campaign label: "… – Cobros" / "… — Cobros".
    #    A call transcript has an ID/call-number BEFORE the dash and a SHORT
    #    label after. A dash in a bullet list is NOT a campaign label.
    first_line = text.split("\n")[0][:250].split("{")[0]
    m = re.search(r"^(.*?)[–—]\s*([^–—]{1,40})$", first_line)
    if m:
        before = m.group(1)
        label = m.group(2).strip()
        # before must contain an ID (digits) — call transcripts carry call numbers
        if re.search(r"\d", before) and len(label) > 1:
            label_clean = re.sub(r"[^\w\s]", " ", label)
            label_clean = re.sub(r"\s+", " ", label_clean).strip()
            words = [w for w in label_clean.split()
                     if not _TOPIC_JUNK_RE.match(w)
                     and w.lower() not in _METADATA_KEYS
                     and w.lower() not in _STOPWORDS]
            if 1 <= len(words) <= 4:
                translated = _translate_label(" ".join(words).strip())
                if translated:
                    return translated

    # 2. Explicit "PROJECT <Name>" / "PROYECTO <Name>" — a short proper noun.
    #    Only in the title region, and <Name> must be mostly Capitalized.
    #    (?i:...) makes the keyword case-insensitive while keeping the name
    #    capture case-sensitive (so we only take real proper nouns).
    m = re.search(r"\b(?i:project|proyecto)\s*[:]?\s+([A-ZÁÉÍÓÚÑÜ][\wáéíóúñü]*(?:\s+[A-ZÁÉÍÓÚÑÜ][\wáéíóúñü]*){0,3})",
                  title_region)
    if m:
        cand = m.group(1).strip()
        # reject if the "name" is actually sentence continuation (too long / lowercase)
        if 2 <= len(cand) <= 30 and not re.search(r"\b(?:de|del|la|el|por|para|the|of|to|and)\b", cand, re.IGNORECASE):
            cand = re.sub(r"[^\w\s]", " ", cand).strip()
            cand = re.sub(r"\s+", " ", cand)
            if cand and cand.lower() not in _GENERIC_PROJECT_WORDS:
                return cand[:40].strip()

    # 3. No high-precision project → empty (flat under client, topic in name)
    return ""


# Single generic words that are never a project name (too vague).
_GENERIC_PROJECT_WORDS = {
    "strategy", "overview", "report", "plan", "deck", "proposal", "summary",
    "analysis", "update", "agenda", "notes", "document", "review", "introduction",
    "presentation", "general", "details", "results", "conclusion",
}


def classify_semantic(file_path: str, is_duplicate: bool = False,
                      text: str = "") -> SemanticClassification:
    p = Path(file_path)
    try:
        stat = p.stat()
    except OSError as e:
        return SemanticClassification(
            file_path=file_path, file_name=p.name, ext=p.suffix.lower().lstrip("."),
            size_bytes=0, error=f"stat failed: {e}",
        )

    ext = p.suffix.lower().lstrip(".")
    name = p.name
    name_lower = name.lower()

    # ---- Code & media short-circuit: never content-classified, no client/topic.
    # These are internal artifacts (dev files, images, audio). They bucket to
    # "Allied Global/<type>" with a clean type label and nothing else.
    if ext in CODE_EXT:
        sc = SemanticClassification(
            file_path=file_path, file_name=name, ext=ext, size_bytes=stat.st_size,
            bucket="Allied Global", doc_type="Code",
        )
        sc.date = _extract_date(name, stat.st_mtime)
        return sc
    if ext in MEDIA_EXT:
        media_type = _media_subtype(ext)
        sc = SemanticClassification(
            file_path=file_path, file_name=name, ext=ext, size_bytes=stat.st_size,
            bucket="Allied Global", doc_type=media_type,
        )
        sc.date = _extract_date(name, stat.st_mtime)
        return sc

    if not text:
        # Memory guard: never extract text from files > 20MB (a corrupt/huge
        # PDF can spike memory and get the process jetsam-killed).
        if stat.st_size > 20 * 1024 * 1024:
            text = ""
        else:
            text = extract_text(file_path)
    text_lower = text.lower() if text else ""

    sc = SemanticClassification(
        file_path=file_path, file_name=name, ext=ext or "unknown",
        size_bytes=stat.st_size, text=text, is_duplicate=is_duplicate,
    )

    # Date from filename (fallback mtime)
    sc.date = _extract_date(name, stat.st_mtime)

    # Trash detection FIRST
    sc.is_trash, sc.trash_reason = _is_trash(text_lower, name_lower, ext, is_duplicate)
    if sc.is_trash:
        sc.bucket = "Potential Trash"
        return sc

    # Doc type from content
    sc.doc_type = _doc_type_from_content(text_lower, name_lower)

    # Client from content
    sc.client = _detect_client(text_lower, name_lower, file_path)

    # Project (engagement/campaign within the client) — detect after client.
    # Pass BOTH lowercased (campaign labels) and original-case (proper nouns).
    sc.project = _detect_project(text_lower, name_lower, sc.client, text_original=text)
    # Drop a lone generic word as "project" (too vague to be meaningful)
    if sc.project and sc.project.strip().lower() in _GENERIC_PROJECT_WORDS:
        sc.project = ""

    # Serving company
    sc.serving_company = _detect_serving_company(text_lower, name_lower, sc.client)

    # Topic
    sc.topic = _extract_topic(text_lower, name_lower)

    # Bucket
    if sc.doc_type in ("proposal", "sow", "pricing") or is_proposal_signal(name_lower, text_lower):
        sc.bucket = "Proposal"
    elif sc.client:
        sc.bucket = "Projects"
    else:
        sc.bucket = "Allied Global"

    return sc


def is_proposal_signal(name_lower: str, text_lower: str) -> bool:
    """Proposal if the doc is, in content, a proposal/pitch to a client."""
    signals = [
        "propuesta", "proposal", "cotizacion", "cotización", "oferta de",
        "statement of work", "scope of work", "propuesta comercial",
    ]
    for s in signals:
        if s in text_lower or s in name_lower:
            return True
    return False


def md5_of_file(file_path: str) -> str:
    try:
        h = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return ""


def _extract_date(filename: str, mtime: float) -> str:
    """Extract a year/date from the filename, fall back to mtime."""
    # YYYY-MM-DD or YYYY_MM_DD or YYYYMMDD
    m = re.search(r"(20\d{2})[-_.]?(\d{2})[-_.]?(\d{2})", filename)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # YYYY
    m = re.search(r"(20\d{2})", filename)
    if m:
        return f"{m.group(1)}-01-01"
    from datetime import datetime
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")


if __name__ == "__main__":
    import sys
    for f in sys.argv[1:]:
        sc = classify_semantic(f)
        print(f"=== {sc.file_name} ===")
        print(f"  bucket={sc.bucket} client={sc.client or '-'} "
              f"serving={sc.serving_company or '-'} type={sc.doc_type or '-'}")
        if sc.is_trash:
            print(f"  TRASH: {sc.trash_reason}")
        if sc.topic:
            print(f"  topic={sc.topic}")
        print()
