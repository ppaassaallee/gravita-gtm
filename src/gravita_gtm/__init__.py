"""Gravita GTM package root.

Everything anchors on ``ROOT`` (the repo) and ``VAULT_DIR`` (the Obsidian
vault, git-backed, open locally in Obsidian). The platform boots via
``gravita_gtm.core.core.Core`` and the CLI via ``gravita`` (the ``gravita``
console script).
"""

from __future__ import annotations

from gravita_gtm.config import ROOT, VAULT_DIR, STATE_DIR, ensure_dirs

__version__ = "0.1.0"
__all__ = ["ROOT", "VAULT_DIR", "STATE_DIR", "ensure_dirs"]
