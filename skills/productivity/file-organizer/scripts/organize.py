#!/usr/bin/env python3
"""
File Organizer CLI — scan, classify, rename, and reorganize files.

Usage:
  python organize.py --target ~/OneDrive --dry-run
  python organize.py --target ~/OneDrive --execute --plan-file /tmp/plan.json
"""

import argparse
import csv
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

# Ensure local scripts are importable
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from classifier import (
    Classification,
    classify_file,
    classification_to_dict,
    extract_text,
)
from sidecar import write_sidecar

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SKIP_DIRS = {
    ".Trash", ".DS_Store", "Microsoft Copilot Chat Files",
    "Microsoft Teams Chat Files", "Meetings", "Recordings",
    "Attachments", "Review - Potential Trash", "Inbox",
    "Customer Success",
}

SKIP_EXTENSIONS = {
    ".ds_store", ".tmp", ".temp", ".swp", ".swo", ".bak",
}

JUNK_FILE_NAMES = {
    ".DS_Store", "Thumbs.db", "desktop.ini", ".localized",
}

# Max files to process in one run (safety)
MAX_FILES = 50_000


# ---------------------------------------------------------------------------
# Directory walking
# ---------------------------------------------------------------------------

def walk_files(target: Path) -> List[Path]:
    """Recursively walk target, skipping junk dirs and files."""
    files = []
    for root, dirs, filenames in os.walk(target, topdown=True):
        # Filter dirs in-place
        dirs[:] = [
            d for d in dirs
            if d not in SKIP_DIRS
            and not d.startswith(".")
        ]
        for fname in filenames:
            if fname in JUNK_FILE_NAMES:
                continue
            p = Path(root) / fname
            if p.suffix.lower() in SKIP_EXTENSIONS:
                continue
            files.append(p)
            if len(files) >= MAX_FILES:
                print(f"Warning: reached max file limit ({MAX_FILES}); stopping scan.")
                return files
    return files


# ---------------------------------------------------------------------------
# Classification pass
# ---------------------------------------------------------------------------

def classify_all(files: List[Path], verbose: bool = False) -> List[Classification]:
    """Classify every file. Extract text lazily."""
    results = []
    for i, p in enumerate(files):
        if verbose and i % 500 == 0:
            print(f"  classifying... {i}/{len(files)}")

        try:
            text = extract_text(str(p))
        except Exception as e:
            text = ""
            if verbose:
                print(f"  WARN: text extraction failed for {p.name}: {e}")

        try:
            cls = classify_file(str(p), text)
        except Exception as e:
            cls = Classification(
                file_path=str(p),
                file_name=p.name,
                file_type=p.suffix.lower().lstrip("."),
                size_bytes=0,
                mtime=0,
                error=str(e),
            )

        results.append(cls)

    return results


# ---------------------------------------------------------------------------
# Renaming
# ---------------------------------------------------------------------------

def sanitize_component(s: str) -> str:
    """Lowercase, replace spaces with hyphens, strip unsafe chars."""
    s = s.lower().strip()
    s = s.replace(" ", "-")
    s = s.replace("_", "-")
    s = re.sub(r"[^a-z0-9\-]", "", s)
    s = re.sub(r"-+", "-", s)
    s = s.strip("-")
    return s


def build_canonical_name(cls: Classification) -> str:
    """Build canonical filename: Year-Company-Category-Project-Client-Description.ext"""
    year = cls.date[:4] if cls.date else "0000"
    company = sanitize_component(cls.serving_company or "internal")
    category = sanitize_component(cls.doc_category or "other")
    project = sanitize_component(cls.client or "general")
    client = sanitize_component(cls.client or "internal")
    desc = sanitize_component(cls.topic or "unnamed")
    if len(desc) > 40:
        desc = desc[:37] + "..."
    ext = cls.file_type
    if not ext:
        ext = Path(cls.file_name).suffix.lower().lstrip(".")
    if ext:
        ext = "." + ext
    base_name = f"{year}-{company}-{category}-{project}-{client}-{desc}{ext}"
    return base_name

def dedup_name(path: Path, target_name: str) -> str:
    """If target_name exists in path, append _2, _3, etc."""
    stem = target_name.rsplit(".", 1)
    if len(stem) == 2:
        base, ext = stem
    else:
        base, ext = target_name, ""
    candidate = target_name
    counter = 2
    while (path / candidate).exists():
        candidate = f"{base}_{counter}{ext}"
        counter += 1
    return candidate


# ---------------------------------------------------------------------------
# Reorganization planning
# ---------------------------------------------------------------------------

def plan_move(cls: Classification, proposal_hub: Path, projects_path: Path,
              years_path: Optional[Path] = None) -> Optional[dict]:
    """Plan a move target for a classified file. Returns None if no-op."""
    if cls.error:
        return None

    is_proposal = cls.is_proposal
    client = cls.client or "Unassigned"
    ptype = cls.proposal_type or "Uncategorized"
    doc_cat = cls.doc_category or "Other"
    project = client  # for non-proposals, project = client or category

    # Proposal → Proposal Hub/<client>/<type>/
    if is_proposal:
        client_dir = sanitize_component(client)
        type_dir = sanitize_component(ptype)
        dest_dir = proposal_hub / client_dir / type_dir
        dest_name = build_canonical_name(cls)
        dest_name = dedup_name(dest_dir, dest_name)
        return {
            "source": cls.file_path,
            "destination": str(dest_dir / dest_name),
            "destination_dir": str(dest_dir),
            "is_proposal": True,
            "reason": f"proposal → {client}/{ptype}",
        }

    # Non-proposal → Projects/<project>/<category>/
    # Try to use years folder if it exists
    year = cls.date[:4] if cls.date else None
    if year and years_path:
        # Check if the file is already under the years folder
        try:
            rel = Path(cls.file_path).relative_to(years_path)
            # Already under years/<year>/... — keep within years structure
            top = years_path
        except ValueError:
            top = projects_path
    else:
        top = projects_path

    # Determine project and category
    if client and client != "Unassigned":
        proj = sanitize_component(client)
        # If client maps to a known project, use it; else category
        category_dir = sanitize_component(doc_cat)
    else:
        # Use category as project
        proj = sanitize_component(doc_cat) if doc_cat else "uncategorized"
        category_dir = "files"

    dest_dir = top / proj / category_dir
    dest_name = build_canonical_name(cls)
    dest_name = dedup_name(dest_dir, dest_name)
    # destination_dir is the folder where the file actually lands
    return {
        "source": cls.file_path,
        "destination": str(dest_dir / dest_name),
        "destination_dir": str(dest_dir),
        "is_proposal": False,
        "reason": f"project → {proj}/{category_dir}",
    }


# ---------------------------------------------------------------------------
# Reorganization execution
# ---------------------------------------------------------------------------

def execute_moves(plan: List[dict], batch_size: int = 100,
                  verbose: bool = False) -> dict:
    """Execute a list of move plans. Returns summary dict."""
    summary = {
        "moved": 0,
        "renamed": 0,
        "skipped": 0,
        "errors": 0,
        "folders_created": set(),
        "failed": [],
    }
    dest_folders = set()

    for i, entry in enumerate(plan):
        if verbose and i % batch_size == 0:
            print(f"  moving... {i}/{len(plan)}")

        src = Path(entry["source"])
        dst = Path(entry["destination"])
        dst_dir = Path(entry["destination_dir"])

        # Safety: source must exist
        if not src.exists():
            summary["skipped"] += 1
            summary["failed"].append({"source": str(src), "reason": "source not found"})
            continue

        # Safety: destination not inside source
        try:
            dst.resolve().relative_to(src.resolve())
            # dst is inside src — skip to avoid moving a folder into itself
            summary["skipped"] += 1
            summary["failed"].append({"source": str(src), "reason": "dest inside source"})
            continue
        except ValueError:
            pass

        # Create destination dir
        try:
            dst_dir.mkdir(parents=True, exist_ok=True)
            dest_folders.add(str(dst_dir))
        except OSError as e:
            summary["errors"] += 1
            summary["failed"].append({"source": str(src), "reason": f"mkdir: {e}"})
            continue

        # Move
        try:
            # If dst exists (race or collision), append counter on the fly
            final_dst = dst
            counter = 2
            while final_dst.exists():
                stem = final_dst.stem
                ext = final_dst.suffix
                final_dst = dst.parent / f"{stem}_{counter}{ext}"
                counter += 1
            if final_dst != dst:
                summary["renamed"] += 1
            if final_dst.exists():
                summary["skipped"] += 1
                summary["failed"].append({"source": str(src), "reason": "dest exists (collision)"})
                continue
            shutil.move(str(src), str(final_dst))
            summary["moved"] += 1
        except Exception as e:
            summary["errors"] += 1
            summary["failed"].append({"source": str(src), "destination": str(dst), "reason": str(e)})

    summary["folders_created"] = sorted(summary["folders_created"])
    return summary


# ---------------------------------------------------------------------------
# Catalog output (CSV)
# ---------------------------------------------------------------------------

def write_catalog(classifications: List[Classification], output_path: str):
    """Write classification catalog as CSV."""
    fieldnames = [
        "file_path", "file_name", "file_type", "size_bytes",
        "mtime", "text_preview",
        "topic", "client", "serving_company", "is_proposal",
        "proposal_type", "doc_category", "date", "date_source",
        "sensitivity_pricing", "sensitivity_confidential",
        "sensitivity_nda", "sensitivity_salary", "sensitivity_pii",
        "sensitivity_financial", "sensitivity_strategy",
        "tags", "error",
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for cls in classifications:
            writer.writerow(classification_to_dict(cls))
    return output_path


# ---------------------------------------------------------------------------
# Plan JSON output
# ---------------------------------------------------------------------------

def write_plan_json(classifications: List[Classification],
                    proposal_hub: Path, projects_path: Path,
                    years_path: Optional[Path], output_path: str,
                    verbose: bool = False) -> List[dict]:
    """Generate and write the full move plan as JSON."""
    if verbose:
        print("  planning moves...")
    plan = []
    for cls in classifications:
        move = plan_move(cls, proposal_hub, projects_path, years_path)
        if move:
            plan.append(move)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(plan, fh, indent=2, ensure_ascii=False)
    return plan


# ---------------------------------------------------------------------------
# Sidecar writing
# ---------------------------------------------------------------------------

def write_all_sidecars(classifications: List[Classification],
                       plan: Optional[List[dict]] = None,
                       verbose: bool = False):
    """Write INDEX.txt sidecars for all destination folders."""
    if verbose:
        print("  writing sidecars...")
    # Group by destination folder
    by_folder: dict[str, list[Classification]] = {}
    if plan:
        for entry, cls in zip(plan, classifications):
            folder = entry.get("destination_dir", "")
            if folder:
                by_folder.setdefault(folder, []).append(cls)
    else:
        for cls in classifications:
            folder = str(Path(cls.file_path).parent)
            by_folder.setdefault(folder, []).append(cls)

    for folder, clss in by_folder.items():
        try:
            write_sidecar(folder, clss)
        except Exception as e:
            if verbose:
                print(f"  WARN: sidecar failed for {folder}: {e}")


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="File Organizer — classify, rename, and reorganize files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --target ~/OneDrive --dry-run
  %(prog)s --target ~/OneDrive --execute --plan-file /tmp/plan.json
  %(prog)s --target ~/OneDrive --classify-only -o /tmp/catalog.csv
  %(prog)s --target ~/OneDrive --rename-only --execute
  %(prog)s --target ~/OneDrive --reorg-only --execute --plan-file /tmp/plan.json
        """,
    )
    parser.add_argument("--target", required=True, help="Folder to organize")
    parser.add_argument("--execute", action="store_true",
                        help="Actually move/rename files (default: dry-run)")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run",
                        help="Show what would happen without changes")
    parser.add_argument("--plan-file", help="Write full action plan as JSON")
    parser.add_argument("--output", "-o", help="Write classification catalog CSV")
    parser.add_argument("--classify-only", action="store_true",
                        help="Only scan + classify + catalog")
    parser.add_argument("--rename-only", action="store_true",
                        help="Only rename files in place")
    parser.add_argument("--reorg-only", action="store_true",
                        help="Only move files into folder hierarchy")
    parser.add_argument("--proposal-hub", help="Override proposal hub path")
    parser.add_argument("--projects-path", help="Override projects folder path")
    parser.add_argument("--years", help="Path to years folder (default: target/YYYY)")
    parser.add_argument("--sensitivity", action="store_true",
                        help="Detect and flag pricing/confidential content")
    parser.add_argument("--tags", action="store_true",
                        help="Emit tag columns in catalog output")
    parser.add_argument("--batch-size", type=int, default=100,
                        help="Files per transaction batch (default 100)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Detailed per-file logs")
    parser.add_argument("--limit", type=int, default=0,
                        help="Limit number of files to process (0 = no limit)")

    args = parser.parse_args()

    if not args.execute and not args.dry_run:
        args.dry_run = True  # default to dry-run

    target = Path(args.target).expanduser().resolve()
    if not target.is_dir():
        print(f"ERROR: target not found: {target}", file=sys.stderr)
        sys.exit(1)

    # Default paths
    proposal_hub = Path(args.proposal_hub).expanduser().resolve() if args.proposal_hub \
        else target / "Proposal Hub"
    projects_path = Path(args.projects_path).expanduser().resolve() if args.projects_path \
        else target / "Projects"
    years_path = Path(args.years).expanduser().resolve() if args.years \
        else target  # years are typically <target>/YYYY

    if args.verbose:
        print(f"Target: {target}")
        print(f"Proposal Hub: {proposal_hub}")
        print(f"Projects: {projects_path}")
        print(f"Years base: {years_path}")
        print(f"Mode: {'EXECUTE' if args.execute else 'DRY-RUN'}")

    # Walk
    if args.verbose:
        print("Scanning files...")
    files = walk_files(target)
    print(f"Found {len(files)} files to process")

    if args.limit and args.limit > 0:
        files = files[:args.limit]
        print(f"Limited to {len(files)} files")

    # Classify
    if args.verbose:
        print("Classifying files...")
    classifications = classify_all(files, verbose=args.verbose)
    print(f"Classified {len(classifications)} files")

    # Stats
    n_proposals = sum(1 for c in classifications if c.is_proposal)
    n_with_client = sum(1 for c in classifications if c.client and c.client != "Unassigned")
    n_sensitive = sum(1 for c in classifications if c.sensitivity)
    print(f"  Proposals: {n_proposals}")
    print(f"  With client: {n_with_client}")
    print(f"  Sensitive: {n_sensitive}")
    print(f"  Errors: {sum(1 for c in classifications if c.error)}")

    # Catalog
    if args.output:
        write_catalog(classifications, args.output)
        print(f"Catalog written to {args.output}")

    # Classify-only: done
    if args.classify_only:
        print("Done (classify-only).")
        return

    # Plan moves
    if args.plan_file or not args.rename_only:
        plan = write_plan_json(
            classifications, proposal_hub, projects_path, years_path,
            args.plan_file or "/tmp/plan.json", verbose=args.verbose,
        )
        if args.plan_file:
            print(f"Plan written to {args.plan_file}")
        n_moves = len(plan)
        print(f"Planned {n_moves} moves")

        # Preview
        if args.dry_run and args.verbose:
            print("\n--- Sample planned moves (first 10) ---")
            for entry in plan[:10]:
                print(f"  {Path(entry['source']).name} → {entry['destination']}")
            if len(plan) > 10:
                print(f"  ... and {len(plan) - 10} more")

    if args.rename_only:
        if not args.execute:
            print("Rename-only requested but not executing. Add --execute.")
            return
        if args.verbose:
            print("Renaming files in place...")
        renamed = 0
        for cls in classifications:
            new_name = build_canonical_name(cls)
            src = Path(cls.file_path)
            dst = src.parent / new_name
            dst = Path(dedup_name(src.parent, new_name))
            if dst != src:
                shutil.move(str(src), str(dst))
                renamed += 1
        print(f"Renamed {renamed} files in place.")
        return

    if args.reorg_only:
        if not args.execute:
            print("Reorg-only requested but not executing. Add --execute.")
            return
        if args.plan_file:
            with open(args.plan_file) as fh:
                plan = json.load(fh)
        summary = execute_moves(plan, batch_size=args.batch_size,
                                verbose=args.verbose)
        print(f"Moved: {summary['moved']}, Errors: {summary['errors']}")
        return

    # Full execution
    if args.execute:
        if args.plan_file:
            with open(args.plan_file) as fh:
                plan = json.load(fh)
        # Write sidecars before moving (so INDEX.txt includes planned files)
        if args.verbose:
            print("Writing sidecars...")
        write_all_sidecars(classifications, plan, verbose=args.verbose)
        summary = execute_moves(plan, batch_size=args.batch_size,
                                verbose=args.verbose)
        print(f"\n=== Summary ===")
        print(f"  Files moved: {summary['moved']}")
        print(f"  Files renamed: {summary['renamed']}")
        print(f"  Skipped: {summary['skipped']}")
        print(f"  Errors: {summary['errors']}")
        print(f"  Folders created: {len(summary['folders_created'])}")
        if summary['failed']:
            print(f"\n  Failed moves (first 10):")
            for f in summary['failed'][:10]:
                print(f"    {f}")
    else:
        print("\nDry-run complete. No files were moved.")
        print(f"Use --execute to apply changes.")
        if args.plan_file:
            print(f"Plan saved to: {args.plan_file}")


if __name__ == "__main__":
    main()
