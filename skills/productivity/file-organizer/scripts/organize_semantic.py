#!/usr/bin/env python3
"""
Semantic file organizer — organizes a folder into four top-level buckets:

    Proposal/         client-specific proposals & pricing
    Projects/         client- or project-specific work
    Allied Global/    internal / consolidated (AlliedGlobal + OneSource)
    Potential Trash/  personal receipts, bank statements, duplicates, shortcuts

Classification is CONTENT-driven (reads the text of every business document)
via semantic_classifier.py. Code/media files are bucketed mechanically.

Rename pattern: Company-Category-Topic-Client-Year.ext
  e.g. AlliedGlobal-Proposal-Omnicanal-Tigo-2023.pdf
"""

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import shutil
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from semantic_classifier import classify_semantic, md5_of_file

# Folders that are NOT reorganized (genuine system / cloud internals only).
# NOTE: "meetings"/"recordings"/"attachments"/"inbox" are REAL business content
# (call recordings, training videos) and MUST be processed — not skipped.
SKIP_DIRS = {
    "microsoft copilot chat files", "microsoft teams chat files",
    ".trash", ".ds_store",
}

# The four output buckets — already-organized, so skip on re-runs.
BUCKET_DIRS = {"Allied Global", "Projects", "Proposal", "Potential Trash"}

# Extensions that are clearly code/media — no content read needed
CODE_EXT = {"ts", "tsx", "js", "jsx", "mjs", "php", "py", "css", "scss",
            "html", "htm", "json", "xml", "sql", "sh", "java", "go", "rb",
            "vue", "svelte", "md", "markdown"}
MEDIA_EXT = {"png", "jpg", "jpeg", "gif", "svg", "webp", "mp3", "wav", "mp4",
             "mov", "avi", "ico", "tiff", "bmp", "ttf", "otf", "woff", "woff2"}
BUSINESS_EXT = {"pdf", "docx", "doc", "pptx", "ppt", "xlsx", "xls", "csv",
                "txt", "rtf", "odt", "pages", "numbers", "key", "drawio"}


def safe(s: str) -> str:
    """Make a string safe for a filename component."""
    if not s:
        return ""
    s = re.sub(r"[^\w\-]+", "-", s, flags=re.UNICODE)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s[:80]


def build_destination(sc, serving_default: str) -> tuple:
    """Return (bucket_path, new_filename) for a classification."""
    ext = sc.ext
    company = sc.serving_company or serving_default or "AlliedGlobal"
    client = safe(sc.client) if sc.client else ""
    topic = safe(sc.topic) if sc.topic else ""
    year = sc.date[:4] if (sc.date and sc.date[:4].isdigit()) else ""

    # ---- Bucket ----
    if sc.is_trash:
        bucket = "Potential Trash"
        subdir = safe(sc.trash_reason) or "misc"
        return os.path.join(bucket, subdir), sc.file_name  # don't rename trash

    bucket = sc.bucket

    # Code & media: keep original filename (names carry real meaning), no rename.
    if sc.doc_type in ("Code", "Image", "Audio", "Video", "Font", "Media"):
        return os.path.join(bucket, sc.doc_type), sc.file_name

    if bucket == "Proposal":
        subdir = client or "Unassigned"
        category = "Proposal"
    elif bucket == "Projects":
        subdir = client or "Unassigned"
        category = sc.doc_type or "Other"
    else:  # Allied Global (internal)
        subdir = sc.doc_type or "Internal"
        category = sc.doc_type or "Internal"

    # ---- Rename: Company-Category-Topic-Client-Year.ext ----
    parts = [company, category]
    if topic:
        parts.append(topic)
    if client:
        parts.append(client)
    if year:
        parts.append(year)
    base = "-".join(p for p in parts if p)
    new_name = f"{safe(base)}.{ext}" if ext else safe(base)

    dest = os.path.join(bucket, subdir)
    return dest, new_name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--dry-run", action="store_true", default=True)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--plan-file", default="/tmp/semantic_plan.json")
    ap.add_argument("--catalog", default="/tmp/semantic_catalog.csv")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    target = Path(args.target)
    if not target.is_dir():
        print(f"ERROR: not a directory: {target}")
        sys.exit(1)

    print(f"Target: {target}")
    print(f"Mode: {'EXECUTE' if args.execute else 'DRY-RUN'}")

    # ---- Phase 1: walk + hash (dedupe) ----
    print("Scanning files...")
    all_files = []
    seen_hash = {}
    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS
                   and d not in BUCKET_DIRS]
        for f in files:
            if f == ".DS_Store":
                continue
            # Skip our own sidecar files (regenerated separately)
            if f.upper() in ("INDEX.TXT", "INDEX.MD"):
                continue
            fp = os.path.join(root, f)
            all_files.append(fp)

    if args.limit:
        all_files = all_files[:args.limit]

    print(f"Found {len(all_files)} files")

    # ---- Phase 2: classify (incremental — writes JSONL line-by-line so a
    # crash never loses progress; append mode lets us resume) ----
    jsonl_path = args.plan_file.replace(".json", ".jsonl")
    # Fresh start for this run
    if os.path.exists(jsonl_path):
        os.remove(jsonl_path)

    dupes = 0
    trash = 0
    proposals = 0
    projects = 0
    internal = 0
    errors = 0
    seen_hash = {}   # md5 -> first path (dedupe by content, business docs only)

    for i, fp in enumerate(all_files):
        if i % 500 == 0:
            print(f"  classifying... {i}/{len(all_files)}", flush=True)

        ext = Path(fp).suffix.lower().lstrip(".")
        try:
            size = os.path.getsize(fp)
        except OSError:
            size = 0

        # --- Dedupe: MD5 content-hash only (a true duplicate is byte-identical
        # content, NOT a shared filename like "logo.png" or "README.md").
        # Only business docs are hashed; code/media are kept as-is (fast to move,
        # and byte-identical media is rare and harmless to keep).
        is_dup = False
        if ext in BUSINESS_EXT and 0 < size < 50 * 1024 * 1024:
            try:
                h = md5_of_file(fp)
                if h:
                    if h in seen_hash:
                        is_dup = True
                        dupes += 1
                    else:
                        seen_hash[h] = fp
            except OSError:
                pass

        # --- Classify (hard-guarded; skip huge files' content extraction)
        try:
            sc = classify_semantic(fp, is_duplicate=is_dup)
        except Exception as e:
            sc = None
            errors += 1
            if args.verbose:
                print(f"  ERROR {fp}: {e}", flush=True)

        if sc is None:
            continue

        dest, new_name = build_destination(sc, serving_default="AlliedGlobal")
        dest_full = os.path.join(str(target), dest)

        if sc.is_trash:
            trash += 1
        elif sc.bucket == "Proposal":
            proposals += 1
        elif sc.bucket == "Projects":
            projects += 1
        else:
            internal += 1

        record = {
            "source": fp,
            "destination_dir": dest_full,
            "destination": os.path.join(dest_full, new_name),
            "new_name": new_name,
            "bucket": sc.bucket if not sc.is_trash else "Potential Trash",
            "client": sc.client,
            "serving_company": sc.serving_company or "AlliedGlobal",
            "doc_type": sc.doc_type,
            "topic": sc.topic,
            "is_trash": sc.is_trash,
            "trash_reason": sc.trash_reason,
            "is_duplicate": sc.is_duplicate,
            "ext": ext,
            "size": size,
        }
        # Incremental write (flush every record — survives crashes)
        with open(jsonl_path, "a") as jf:
            jf.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"\n=== CLASSIFICATION SUMMARY ===")
    print(f"  Total:         {len(all_files)}")
    print(f"  Proposal:      {proposals}")
    print(f"  Projects:      {projects}")
    print(f"  Allied Global: {internal}")
    print(f"  Potential Trash: {trash}")
    print(f"  Duplicates:    {dupes}")
    print(f"  Errors:        {errors}")

    # Read back JSONL and produce the final plan.json + catalog.csv
    plan = []
    rows = []
    if os.path.exists(jsonl_path):
        with open(jsonl_path) as jf:
            for line in jf:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                plan.append(rec)
                rows.append({
                    "file": os.path.basename(rec["source"]),
                    "ext": rec["ext"],
                    "bucket": rec["bucket"],
                    "client": rec["client"],
                    "serving_company": rec["serving_company"],
                    "doc_type": rec["doc_type"],
                    "topic": rec["topic"],
                    "trash_reason": rec["trash_reason"],
                    "is_duplicate": rec["is_duplicate"],
                })

    with open(args.plan_file, "w") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    print(f"\nPlan written to {args.plan_file} ({len(plan)} entries)")

    with open(args.catalog, "w", newline="") as f:
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    print(f"Catalog written to {args.catalog}")

    # ---- Phase 3: execute ----
    if args.execute:
        print("\n=== EXECUTING MOVES ===")
        moved = 0
        failed = 0
        for entry in plan:
            src = entry["source"]
            dst = entry["destination"]
            dst_dir = entry["destination_dir"]
            try:
                os.makedirs(dst_dir, exist_ok=True)
                # Resolve name collisions with a short source-path hash suffix
                # (stable + unique, unlike _2/_3 chains which break ordering).
                final_dst = dst
                if os.path.exists(final_dst):
                    stem = Path(dst).stem
                    ext = Path(dst).suffix
                    h = hashlib.md5(src.encode("utf-8")).hexdigest()[:6]
                    final_dst = os.path.join(dst_dir, f"{stem}-h{h}{ext}")
                shutil.move(src, final_dst)
                moved += 1
            except Exception as e:
                failed += 1
                if args.verbose:
                    print(f"  FAIL {src}: {e}")
        print(f"\nMoved: {moved}, Failed: {failed}")
    else:
        print("\nDry-run complete. No files moved. Use --execute to apply.")


if __name__ == "__main__":
    main()
