"""Minimal vault I/O — read notes, list by glob, grep rulings.

The platform reads the Obsidian vault as markdown on disk. No vector store,
no embedding index, no hidden layer. Files on disk, frontmatter, links, and a
agent that reads them. That's the semantic layer.

Used by every workflow runner before it drafts.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from gravita_gtm.config import VAULT_DIR, RULINGS_DIR


def read_note(relative_path: str) -> dict[str, Any]:
    """Read a vault note by its path relative to the vault root.

    Returns ``{"path": ..., "text": ..., "frontmatter": {...}, "links": [...], "exists": bool}``.
    """
    p = VAULT_DIR / relative_path
    if not p.exists():
        return {"path": str(p), "text": "", "frontmatter": {}, "links": [], "exists": False}
    text = p.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(text)
    links = _extract_links(body)
    return {"path": str(p), "text": body, "frontmatter": frontmatter, "links": links, "exists": True}


def read_raw(relative_path: str) -> str:
    p = VAULT_DIR / relative_path
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")


def list_notes(glob_pattern: str = "**/*.md") -> list[str]:
    p = VAULT_DIR / glob_pattern
    return [str(pp.relative_to(VAULT_DIR)) for pp in p.parent.glob(glob_pattern)
            if pp.is_file() and pp.suffix == ".md"]


def grep_rulings(topic: str) -> list[dict[str, Any]]:
    """Grep the rulings folder for a topic. Returns matching ruling lines.

    Each ruling is one dated line in a markdown file under ``vault/rulings/``.
    Returns ``[{file, line, text}]``.
    """
    results: list[dict[str, Any]] = []
    if not RULINGS_DIR.exists():
        return results
    topic_lower = topic.lower()
    for f in RULINGS_DIR.glob("*.md"):
        text = f.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), start=1):
            if topic_lower in line.lower():
                results.append({"file": str(f.relative_to(VAULT_DIR)), "line": i, "text": line})
    return results


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split ``--- frontmatter ---\n\nbody`` into (frontmatter_dict, body)."""
    if not text.startswith("---"):
        return {}, text
    # find the closing ---
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm_block = text[3:end].strip()
    body = text[end + 4:].lstrip("\n")
    fm = {}
    for line in fm_block.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm, body


def _extract_links(body: str) -> list[str]:
    """Extract ``[[wiki-links]]`` and ``[label](path)`` references."""
    wiki = re.findall(r"\[\[([^\]]+)\]\]", body)
    markdowns = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", body)
    paths = [m[1] for m in markdowns if m[1].endswith(".md") or "/" in m[1]]
    return wiki + paths
