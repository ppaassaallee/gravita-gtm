#!/usr/bin/env python3
"""
File Organizer — classification engine.

Scans files, extracts text, classifies by type/topic/client/proposal/sensitivity,
and produces a structured catalog. Used by organize.py (the CLI entry point).
"""

import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from text_extract import extract_text

# ---------------------------------------------------------------------------
# Known entities
# ---------------------------------------------------------------------------

# Known client names (proper nouns only — not department/category names)
# Department/category folder names are excluded to avoid false positives.
CLIENTS = {
    "Tigo", "Claro", "Movistar", "TPG", "Banrural", "BAC", "ABC", "APEX",
    "PTC", "DGA", "Kustomer", "Vensure", "Verizon", "Talsa", "TECO", "Solvo",
    "OneSource", "AlliedGlobal", "Equipara", "Woman", "CPG",
    "Herrera Llerandi", "San Vicente", "Ripley", "Fungi", "Farmacia",
    "Maxicolor", "PriceSmart", "Carrefour", "Target", "Walmar", "Sears",
    "Banco Industrial", "Estado", "Ministerio", "GOB",
    "Municipalidad", "Alcaldia", "Tigo Paraguay", "WOM Colombia",
    "WOM Ventas Chile", "Value Added Services", "Staples", "Staple",
    "Remote Workforce", "OCR", "Taroko",
    "Google", "Microsoft", "Apple", "AWS", "OpenAI", "Salesforce",
    "Zendesk", "Startups", "Sitio", "Kruops", "Swag", "Logo",
    "WOM", "Teco", "Talsa", "Verizon",
    "TikTok", "Tik Tok", "Sparring",
    "Igss", "Banco", "Hospital", "Clinica", "Clínica", "EPS", "Salud",
    "Health",
}

# Department / category names that appear in folder paths — NOT clients
DEPARTMENT_NAMES = {
    "GTM", "Operations", "People", "People-Finance", "Finance", "Meetings",
    "Marketing", "Strategy", "Retention", "CX", "BPO", "IVA", "Healthcare",
    "Speech Analytics", "Speech-Analytics", "Staffing", "F&A", "RevOps",
    "M&A", "Transformation", "Digital Products", "DigitalProducts",
    "Remote Workforce", "General", "Internal", "Services", "Service",
    "Product", "Solution", "Capability", "Technology", "Business",
    "Sales", "Support", "Admin", "Administration", "HR", "Human Resources",
    "Resources", "Inbox", "Inbox-Mail", "Teams", "Drive", "Files",
    "Site", "Sitio", "Stock Videos", "Value Added", "Added Services",
    "Tigo Paraguay", "WOM Colombia", "WOM Ventas Chile",
}

SERVING_COMPANIES = ["AlliedGlobal", "OneSource", "Equipara", "Woman", "Internal"]

PROPOSAL_KEYWORDS = [
    "proposal", "propuesta", "sow", "statement of work", "cotizacion",
    "cotización", "presupuesto", "oferta", "rfp", "bid", "quote",
    "quotation", "scope of work", "tos", "terms of service",
    "alcance", "alcance de trabajo", "entregables", "propuesta comercial",
    "propuesta de servicio", "propuesta de solucion", "propuesta de solución",
]

PROPOSAL_TYPE_MAP = {
    "service": ["service", "servicios", "managed services", "support",
                "operaciones", "atención al cliente", "customer experience",
                "bpo service", "bpo services", "outsourcing", "externalizacion",
                "externalización", "contact center", "call center"],
    "product": ["product", "productos", "digital product", "software",
                "platform", "kustomer", "digital products"],
    "solution": ["solution", "soluciones", "digital solution",
                 "transformation solution", "end-to-end", "integral"],
    "capability": ["capability", "capabilities", "capa", "as-a-service",
                   "x-as-a-service", "platform-as-a-service"],
    "internal": ["internal", "interno", "deck interno", "plan interno",
                 "propuesta interna", "internal proposal"],
    "pricing": ["pricing", "precios", "precios unitarios", "fee", "tarifa",
                "cost structure", "costo", "precio", "cotizacion pricing"],
    "sow": ["statement of work", "sow", "alcance", "scope", "entregables"],
    "transformation": ["transformation", "transformacion", "transformación",
                      "cambio organizacional", "organizational change"],
    "cx": ["customer experience", "experiencia del cliente", "cx",
           "customer", "cliente"],
    "bpo": ["bpo", "business process outsourcing", "externalizacion",
            "externalización", "process outsourcing"],
    "iva": ["iva", "interactive voice", "voice", "voz", "telephony",
            "call recording", "call analytics"],
    "healthcare": ["healthcare", "salud", "hospital", "clinica", "clínica",
                   "eps", "health", "medical"],
    "digital-products": ["digital products", "productos digitales",
                         "digital product"],
    "staffing": ["staffing", "personal", "reclutamiento", "talent",
                 "hr", "human resources", "rrhh"],
    "speech-analytics": ["speech analytics", "analitica de voz",
                         "analítica de voz", "speech", "voice analytics"],
    "f&a": ["finance & accounting", "finanzas", "accounting", "f&a",
            "financial", "accounting"],
    "revops": ["revenue operations", "revops", "operaciones comerciales",
               "revenue ops", "sales operations"],
    "ma": ["m&a", "mergers", "fusiones", "adquisiciones", "mergers and acquisitions",
           "due diligence"],
}

DOC_CATEGORY_MAP = {
    "proposal": ["proposal", "propuesta", "oferta", "bid", "rfp response",
                 "propuesta comercial", "propuesta de"],
    "sow": ["statement of work", "sow", "alcance", "scope of work",
            "entregables"],
    "contract": ["contract", "contrato", "agreement", "acuerdo", "msa",
                 "nda", "adendum", "addendum",
                 "modification", "modificación", "modificacion"],
    "plan": ["plan", "planificacion", "planificación", "proyecto",
             "roadmap", "cronograma", "planning"],
    "deck": ["deck", "presentacion", "presentación", "pptx", "ppt",
             "slides", "diapositivas"],
    "report": ["report", "reporte", "informe", "resumen", "estado",
               "dashboard", "status report"],
    "pricing": ["pricing", "precios", "tarifa", "fee", "cost",
                "cotizacion", "cotización", "investment",
                "inversion", "inversión"],
    "data": ["data", "datos", "dataset", "base de datos",
             "database", "reporting data"],
    "spec": ["especificaciones", "requirements", "requisitos",
             "specs", "specification"],
    "brief": ["brief", "briefing", "brief de", "creative brief"],
    "template": ["template", "plantilla", "templates"],
    "internal": ["internal", "interno", "memo", "comunicacion interna",
                 "comunicación interna", "internal memo"],
    "notes": ["notes", "notas", "meeting notes", "acta", "acta de",
              "notas de"],
    "tracking": ["tracking", "seguimiento", "pipeline", "forecast",
                 "opportunity", "sales pipeline"],
    "invoice": ["invoice", "factura", "billing",
                "factura electronica", "factura electrónica"],
    "po": ["purchase order", "orden de compra"],
    "email": ["email", "correo", "message", "mensajes"],
    "image": ["png", "jpg", "jpeg", "gif", "svg", "screenshot",
              "imagen", "image", "photo", "foto"],
    "font": ["otf", "ttf", "font", "fuente", "typography"],
    "archive": ["zip", "rar", "tar", "gz", "7z", "archive", "archivo",
                "paquete"],
    "code": ["php", "js", "py", "html", "css", "json", "xml", "sql",
             "code", "script", "programa"],
}

SENSITIVITY_PATTERNS = {
    "pricing": [
        r"\b(price|pricing|cost|fee|tarifa|precio|presupuesto|monto|"
        r"cuota|investment|fee schedule|fee structure|precio unitario|"
        r"costos|costos unitarios|tarifa por|precio por|fee per|price per|"
        r"precios|precios unitarios|anlisis de precios|analisis de precios|"
        r"análisis de precios|priceline|pricing analysis)\b",
    ],
    "confidential": [
        r"\b(confidential|confidencial|secret|secreto|private|privado|"
        r"restricted|restringido|proprietary|propietario|not for"
        r" distribution|no distribuir)\b",
    ],
    "nda": [
        r"\b(nda|non[- ]disclosure|no divulgar|confidencialidad|"
        r"acuerdo de confidencialidad|confidentiality agreement)\b",
    ],
    "salary": [
        r"\b(salary|salario|compensacion|compensación|payroll|nomina|"
        r"nómina|benefits|beneficios|bonus|bono|bonus|hora|hourly|"
        r"annual salary|salario anual|remuneration|retribucion|"
        r"retribución)\b",
    ],
    "pii": [
        r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b",  # email
        r"\b(?:\+?502\s?)?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",  # phone GT
        r"\b\d{8,12}\b",  # ID numbers
    ],
    "financial": [
        r"\b(revenue|ingresos|ganancias|profit|margen|financial"
        r" statement|estado financiero|p&l|pl|balance sheet|"
        r" estado de resultados|bottom line|top line|ebitda)\b",
    ],
    "strategy": [
        r"\b(strategy|estrategia|plan estrategico|plan estratégico|"
        r"competitive|competitivo|competitive advantage|ventaja"
        r" competitiva|market strategy|estrategia de mercado)\b",
    ],
}

DATE_PATTERNS = [
    (re.compile(r"(\d{4})-(\d{2})-(\d{2})"), "%Y-%m-%d"),
    (re.compile(r"(\d{4})-(\d{2})"), "%Y-%m"),
    (re.compile(r"(\d{4})"), "%Y"),
    (re.compile(r"(\d{2})/(\d{2})/(\d{4})"), "%m/%d/%Y"),
    (re.compile(r"(\d{2})/(\d{2})/(\d{4})"), "%d/%m/%Y"),  # ambiguous
    (re.compile(r"(\d{4})[-_](\d{2})[-_](\d{2})"), "%Y-%m-%d"),
]


# ---------------------------------------------------------------------------
# Classification result
# ---------------------------------------------------------------------------

@dataclass
class Classification:
    file_path: str
    file_name: str
    file_type: str
    size_bytes: int
    mtime: float
    text: str = ""
    topic: str = ""
    client: str = ""
    serving_company: str = "Internal"
    is_proposal: bool = False
    proposal_type: str = ""
    doc_category: str = ""
    date: str = ""
    date_source: str = ""  # filename | mtime | unknown
    sensitivity: dict = field(default_factory=dict)
    tags: list = field(default_factory=list)
    error: str = ""


# ---------------------------------------------------------------------------
# Classifiers
# ---------------------------------------------------------------------------

def classify_file(file_path: str, text: str = "") -> Classification:
    p = Path(file_path)
    try:
        stat = p.stat()
    except OSError as e:
        return Classification(
            file_path=file_path,
            file_name=p.name,
            file_type=p.suffix.lower().lstrip("."),
            size_bytes=0,
            mtime=0,
            error=f"stat failed: {e}",
        )
    ext = p.suffix.lower().lstrip(".")
    name_lower = p.name.lower()

    cls = Classification(
        file_path=file_path,
        file_name=p.name,
        file_type=ext or "unknown",
        size_bytes=stat.st_size,
        mtime=stat.st_mtime,
        text=text,
    )

    # ---- date ----
    cls.date, cls.date_source = _extract_date(p.name, stat.st_mtime)

    # ---- doc category ----
    cls.doc_category = _classify_doc_category(name_lower, ext, text)

    # ---- proposal detection ----
    cls.is_proposal = _is_proposal(name_lower, text, cls.file_path)

    # ---- proposal type ----
    if cls.is_proposal:
        cls.proposal_type = _classify_proposal_type(name_lower, text, cls.doc_category)

    # ---- client ----
    cls.client = _detect_client(name_lower, text, cls.file_path)

    # ---- serving company ----
    cls.serving_company = _detect_serving_company(name_lower, text, cls.client)

    # ---- topic ----
    cls.topic = _extract_topic(name_lower, text, cls.doc_category)

    # ---- sensitivity ----
    cls.sensitivity = _detect_sensitivity(text)

    # ---- tags ----
    cls.tags = _build_tags(cls)

    return cls


def _extract_date(filename: str, mtime: float) -> tuple:
    """Try to extract a date from filename; fall back to mtime."""
    name_lower = filename.lower()
    for pattern, fmt in DATE_PATTERNS:
        m = pattern.search(name_lower)
        if m:
            try:
                if fmt == "%Y":
                    dt = datetime.strptime(m.group(1), fmt)
                elif fmt in ("%Y-%m", "%m/%d/%Y", "%d/%m/%Y"):
                    dt = datetime.strptime("".join(m.groups()), fmt)
                else:
                    dt = datetime.strptime(m.group(0), fmt)
                return dt.strftime("%Y-%m-%d"), "filename"
            except ValueError:
                continue
    # mtime fallback
    dt = datetime.fromtimestamp(mtime)
    return dt.strftime("%Y-%m-%d"), "mtime"


def _is_proposal(name_lower: str, text: str, file_path: str = "") -> bool:
    """A file is a proposal if its filename contains proposal language.

    Text-level detection is intentionally NOT used — it produces too many
    false positives (e.g. 'proyecto' in a project plan, 'requisitos' in a
    spec doc). Proposal Hub folder membership is handled at the folder level
    by the existing directory structure, not by this classifier.

    Keyword matching uses custom boundaries so that short keywords like "tos"
    don't match inside "proyectos", "bid" doesn't match inside "abbreviated",
    and "proposal" DOES match when preceded/followed by _, -, . or string edges
    (unlike \\b which treats _ as a word character).
    """
    for kw in PROPOSAL_KEYWORDS:
        kw_l = kw.lower()
        if " " in kw_l:
            # Multi-word phrase: match phrase surrounded by non-alphanum or edges
            pat = rf"(?<![a-zA-Z0-9]){re.escape(kw_l)}(?![a-zA-Z0-9])"
        else:
            pat = rf"(?<![a-zA-Z0-9]){re.escape(kw_l)}(?![a-zA-Z0-9])"
        if re.search(pat, name_lower):
            return True
    return False


def _classify_proposal_type(name_lower: str, text: str, doc_category: str) -> str:
    """Map proposal to service/product/solution/capability/etc.

    Uses filename-only matching (with extension-based fallback), not body text.
    Body-text matching produces false types when a proposal's body mentions
    keywords from a different type more strongly than the filename suggests.
    """
    # Primary: filename keywords only
    scores = {}
    for ptype, keywords in PROPOSAL_TYPE_MAP.items():
        for kw in keywords:
            if kw in name_lower:
                scores[ptype] = scores.get(ptype, 0) + 1
    if scores:
        best = max(scores, key=scores.get)
        return best

    # Secondary: extension-based fallback (proposal detected by keyword,
    # but no type keyword in filename — guess from doc_category + ext)
    ext_map = {
        "docx": "service", "pdf": "service", "pptx": "internal",
        "xlsx": "pricing", "doc": "service", "xls": "pricing",
    }
    ext = name_lower.rsplit(".", 1)[-1] if "." in name_lower else ""
    if ext in ext_map:
        return ext_map[ext]

    # Ternary: map doc_category
    cat_to_type = {
        "proposal": "service",
        "sow": "sow",
        "deck": "internal",
        "pricing": "pricing",
        "data": "internal",
        "report": "internal",
        "internal": "internal",
        "plan": "internal",
        "contract": "service",
        "brief": "service",
        "template": "internal",
        "notes": "internal",
        "tracking": "internal",
        "invoice": "pricing",
        "po": "pricing",
        "email": "internal",
        "image": "other",
        "font": "other",
        "archive": "other",
        "code": "other",
    }
    return cat_to_type.get(doc_category, "other")


def _classify_doc_category(name_lower: str, ext: str, text: str) -> str:
    """Classify document into a category.

    Uses filename primarily; falls back to text only when filename is
    ambiguous. Avoids false positives from mentions in text body.
    Single-word keywords use word boundaries (\"bid\" != \"abbreviated\").
    """
    # Primary: filename keywords
    for cat, keywords in DOC_CATEGORY_MAP.items():
        for kw in keywords:
            kw_l = kw.lower()
            # Custom boundary: _ - . are delimiters (unlike \\b which treats _ as word char)
            pat = rf"(?<![a-zA-Z0-9]){re.escape(kw_l)}(?![a-zA-Z0-9])"
            if re.search(pat, name_lower):
                return cat

    # Secondary: extension-based fallback
    ext_map = {
        "docx": "doc", "doc": "doc", "pdf": "report", "pptx": "deck",
        "ppt": "deck", "xlsx": "data", "xls": "data", "txt": "internal",
        "md": "internal", "csv": "data", "json": "code", "xml": "code",
        "html": "code", "css": "code", "js": "code", "py": "code",
        "php": "code", "sql": "code", "drawio": "spec", "png": "image",
        "jpg": "image", "jpeg": "image", "gif": "image", "svg": "image",
        "otf": "font", "ttf": "font", "zip": "archive", "rar": "archive",
        "tar": "archive", "gz": "archive", "7z": "archive", "crswap": "code",
    }
    if ext in ext_map:
        return ext_map[ext]

    # Tertiary: text body only for very short filenames with no signal
    if not name_lower or len(name_lower) < 5:
        combined = text[:500].lower()
        for cat, keywords in DOC_CATEGORY_MAP.items():
            for kw in keywords:
                if kw in combined:
                    return cat

    return "other"


def _detect_client(name_lower: str, text: str, file_path: str = "") -> str:
    """Detect client name from filename, path components, and text body.

    Uses word-boundary matching everywhere (custom boundary treats _ - . as
    delimiters, unlike \\b which treats _ as a word character), so short
    client names like "BAC", "AWS", "DGA" don't false-match inside other words.

    Path components are checked first (strongest signal — a file in /2025/PTC/
    is almost certainly a PTC file). Then filename. Then text body as fallback.
    Department names in the path are excluded.
    """
    # Build set of department names (lowercased) for exclusion
    dept_lower = {d.lower() for d in DEPARTMENT_NAMES}

    # 1. Check path components (excluding department names and cloud storage roots)
    #    Skip onedrive-* root components so OneDrive-AlliedGlobal doesn't match
    #    "AlliedGlobal" as a client for every file.
    if file_path:
        for part in Path(file_path).parts:
            pl = part.lower()
            # Skip cloud storage root folders
            if pl.startswith("onedrive-"):
                continue
            if pl in dept_lower:
                continue
            for client in sorted(CLIENTS, key=len, reverse=True):
                cl = client.lower()
                if cl == pl or re.search(rf"(?<![a-zA-Z0-9]){re.escape(cl)}(?![a-zA-Z0-9])", pl):
                    return client

    # 2. Check filename with word-boundary matching
    for client in sorted(CLIENTS, key=len, reverse=True):
        cl = client.lower()
        pat = rf"(?<![a-zA-Z0-9]){re.escape(cl)}(?![a-zA-Z0-9])"
        if re.search(pat, name_lower):
            return client

    # 3. Check text body with word-boundary matching (fallback only)
    if text:
        combined = text[:2000].lower()
        for client in sorted(CLIENTS, key=len, reverse=True):
            cl = client.lower()
            pat = rf"(?<![a-zA-Z0-9]){re.escape(cl)}(?![a-zA-Z0-9])"
            if re.search(pat, combined):
                return client

    return "Unassigned"


def _detect_serving_company(name_lower: str, text: str, client: str) -> str:
    """Determine who the file is from/for.

    Uses word-boundary matching for serving company detection to avoid
    false matches. Skips 'onedrive-*' path components.
    """
    # Check filename and text body with word boundaries
    combined = f"{name_lower}"
    if text:
        combined += " " + text[:2000].lower()

    for company in SERVING_COMPANIES:
        cl = company.lower()
        pat = rf"(?<![a-zA-Z0-9]){re.escape(cl)}(?![a-zA-Z0-9])"
        if re.search(pat, combined):
            return company

    # Heuristic fallback: if a real external client was found, assume
    # AlliedGlobal unless OneSource/Equipara/Woman also present
    if client and client not in ("Unassigned", "Internal", "General", ""):
        if "onesource" in combined:
            return "OneSource"
        if "equipara" in combined or "woman" in combined:
            return "Woman"
        return "AlliedGlobal"
    return "Internal"


def _extract_topic(name_lower: str, text: str, doc_category: str) -> str:
    """Extract a short topic/description from filename."""
    # Remove date prefix if present
    name = re.sub(r"^\d{4}[-_]\d{2}[-_]\d{2}[-_]", "", name_lower)
    name = re.sub(r"^\d{4}[-_]\d{2}[-_]", "", name)
    name = re.sub(r"^\d{4}[-_]", "", name)

    # Remove known prefixes
    for prefix in [
        "internal_", "interno_", "proposal_", "propuesta_",
        "sow_", "plan_", "planificacion_", "planificación_",
        "report_", "reporte_", "deck_", "brief_", "briefing_",
        "pricing_", "tracking_", "notes_", "notas_",
        "template_", "plantilla_", "spec_", "data_", "datos_",
        "image_", "imagen_", "screenshot_", "font_", "code_",
        "archive_", "invoice_", "factura_", "po_", "email_",
        "correo_", "meeting_", "reunion_", "meeting notes_",
        "alliedglobal_", "onesource_", "client_", "project_",
        "tigo_", "banrural_", "ptc_", "kustomer_", "iva_",
        "dga_", "tpg_", "apex_", "claro_", "vensure_",
        "verizon_", "talsa_", "teco_", "solvo_", "equipara_",
        "woman_", "cpg_", "igss_", "wom_", "retention_",
        "marketing_", "ocr_", "taroko_", "tiktok_", "tik tok_",
        "sparring_", "digital products_", "digitalproducts_",
        "remote workforce_", "staffing_", "bpo_", "cx_",
        "healthcare_", "speech analytics_", "speech-analytics_",
        "f&a_", "revops_", "m&a_", "transformation_",
        "strategy_", "operations_", "gtm_", "people_",
        "people-finance_", "meetings_", "finance_",
        "general_", "external_", "wetransfer_", "drive download",
    ]:
        if name.startswith(prefix):
            name = name[len(prefix):]
            break

    # Remove extensions and numbers-only suffixes
    name = re.sub(r"\.[^.]+$", "", name)
    name = re.sub(r"_[0-9]+$", "", name)
    name = re.sub(r"\s*[-_]\s*$", "", name)

    # Clean up
    name = re.sub(r"[-_]+", " ", name).strip()
    name = re.sub(r"\s+", " ", name)

    if len(name) > 60:
        name = name[:57].rstrip() + "..."

    if not name:
        # Use first meaningful words from text
        if text:
            words = text.split()[:10]
            name = " ".join(words)
            if len(name) > 60:
                name = name[:57] + "..."
        else:
            name = "unnamed"

    return name.title()


def _detect_sensitivity(text: str) -> dict:
    """Detect sensitivity flags in text."""
    result = {}
    text_sample = text[:5000].lower()
    for flag, patterns in SENSITIVITY_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, text_sample, re.IGNORECASE):
                result[flag] = True
                break
    return result


def _build_tags(cls: Classification) -> list:
    """Build a list of tags for the file."""
    tags = []
    if cls.is_proposal:
        tags.append("proposal")
        if cls.proposal_type:
            tags.append(f"proposal-{cls.proposal_type}")
    if cls.doc_category:
        tags.append(cls.doc_category)
    if cls.client and cls.client != "Unassigned":
        tags.append(f"client-{cls.client}")
    if cls.serving_company and cls.serving_company != "Internal":
        tags.append(f"serving-{cls.serving_company}")
    if cls.sensitivity:
        tags.extend(f"sensitive-{k}" for k in cls.sensitivity if cls.sensitivity[k])
    if cls.date:
        tags.append(f"year-{cls.date[:4]}")
    # file type tag
    tags.append(f"filetype-{cls.file_type}")
    return list(dict.fromkeys(tags))  # unique, order preserved


# ---------------------------------------------------------------------------
# Catalog output
# ---------------------------------------------------------------------------

def classification_to_dict(cls: Classification) -> dict:
    return {
        "file_path": cls.file_path,
        "file_name": cls.file_name,
        "file_type": cls.file_type,
        "size_bytes": cls.size_bytes,
        "mtime": cls.mtime,
        "text_preview": cls.text[:300] if cls.text else "",
        "topic": cls.topic,
        "client": cls.client,
        "serving_company": cls.serving_company,
        "is_proposal": cls.is_proposal,
        "proposal_type": cls.proposal_type,
        "doc_category": cls.doc_category,
        "date": cls.date,
        "date_source": cls.date_source,
        "sensitivity_pricing": cls.sensitivity.get("pricing", False),
        "sensitivity_confidential": cls.sensitivity.get("confidential", False),
        "sensitivity_nda": cls.sensitivity.get("nda", False),
        "sensitivity_salary": cls.sensitivity.get("salary", False),
        "sensitivity_pii": cls.sensitivity.get("pii", False),
        "sensitivity_financial": cls.sensitivity.get("financial", False),
        "sensitivity_strategy": cls.sensitivity.get("strategy", False),
        "tags": ",".join(cls.tags),
        "error": cls.error,
    }
