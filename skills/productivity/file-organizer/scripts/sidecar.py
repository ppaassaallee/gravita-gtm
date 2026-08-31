#!/usr/bin/env python3
"""Write INDEX.txt sidecar files for organized folders."""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from classifier import Classification


def write_sidecar(folder_path: str, classifications: List[Classification]):
    """Write an INDEX.txt describing all files in a folder."""
    folder = Path(folder_path)
    folder.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append(f"FOLDER: {folder.resolve()}")
    lines.append(f"CREATED: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"FILE_COUNT: {len(classifications)}")
    lines.append("")
    lines.append("# FORMAT: filename | type | topic | client | proposal_type | doc_category | date | sensitivity | tags")
    lines.append("")

    for cls in sorted(classifications, key=lambda c: c.file_name.lower()):
        sensitivity_flags = []
        if cls.sensitivity.get("pricing"):
            sensitivity_flags.append("pricing")
        if cls.sensitivity.get("confidential"):
            sensitivity_flags.append("confidential")
        if cls.sensitivity.get("nda"):
            sensitivity_flags.append("nda")
        if cls.sensitivity.get("salary"):
            sensitivity_flags.append("salary")
        if cls.sensitivity.get("pii"):
            sensitivity_flags.append("pii")
        if cls.sensitivity.get("financial"):
            sensitivity_flags.append("financial")
        if cls.sensitivity.get("strategy"):
            sensitivity_flags.append("strategy")
        sens_str = ",".join(sensitivity_flags) if sensitivity_flags else "none"
        tags_str = ",".join(cls.tags) if cls.tags else "-"

        line = (
            f"{cls.file_name} | {cls.file_type} | {cls.topic} | "
            f"{cls.client} | {cls.proposal_type or '-'} | "
            f"{cls.doc_category} | {cls.date or '-'} | "
            f"{sens_str} | {tags_str}"
        )
        lines.append(line)

    index_path = folder / "INDEX.txt"
    with open(index_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    return str(index_path)
