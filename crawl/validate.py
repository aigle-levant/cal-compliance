"""
validation.py
-------------
Reads data/sections.jsonl and data/failures.jsonl and produces:
  1. A human-readable coverage report printed to stdout
  2. data/coverage_report.json — machine-readable version

Coverage dimensions checked:
  - URL-level:  how many discovered URLs were extracted vs failed
  - Field-level: which canonical fields are populated vs missing
  - Hierarchy-level: breadth of titles / divisions / chapters covered
  - Content-level: sections with suspiciously short content
  - Duplicate detection: same section_number appearing > once
  - Citation integrity: every record should have a citation
"""

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DISCOVERY_FILE  = Path("../data/discovery.jsonl")
SECTIONS_FILE   = Path("../data/sections.jsonl")
FAILURES_FILE   = Path("../data/failures.jsonl")
REPORT_FILE     = Path("../data/coverage_report.json")

# Canonical fields — every record should ideally have these populated
REQUIRED_FIELDS = [
    "title_number",
    "title_name",
    "section_number",
    "section_heading",
    "citation",
    "breadcrumb_path",
    "content_markdown",
    "source_url",
    "retrieved_at",
]

# Optional hierarchy fields — presence/absence is informational
OPTIONAL_HIER_FIELDS = [
    "division_number",
    "chapter_number",
    "subchapter_number",
    "article_number",
    "group_number",
]

MIN_CONTENT_CHARS = 80   # flag records whose content is suspiciously short


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as e:
            print(f"  [WARN] {path.name} line {i}: bad JSON — {e}")
    return records


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

def field_coverage(records: list[dict], fields: list[str]) -> dict[str, dict]:
    """For each field, return count of populated vs missing."""
    n = len(records)
    result = {}
    for f in fields:
        populated = sum(1 for r in records if r.get(f))
        result[f] = {
            "populated": populated,
            "missing":   n - populated,
            "pct":       round(100 * populated / n, 1) if n else 0,
        }
    return result


def detect_duplicates(records: list[dict]) -> dict[str, list[str]]:
    """Return section_numbers that appear more than once, with their URLs."""
    seen: dict[str, list[str]] = defaultdict(list)
    for r in records:
        sn = r.get("section_number")
        if sn:
            seen[sn].append(r.get("source_url", ""))
    return {k: v for k, v in seen.items() if len(v) > 1}


def short_content(records: list[dict]) -> list[dict]:
    return [
        {"section_number": r.get("section_number"), "url": r.get("source_url"), "chars": len(r.get("content_markdown") or "")}
        for r in records
        if len(r.get("content_markdown") or "") < MIN_CONTENT_CHARS
    ]


def hierarchy_breadth(records: list[dict]) -> dict:
    return {
        "unique_titles":      len({r.get("title_number") for r in records if r.get("title_number")}),
        "unique_divisions":   len({r.get("division_number") for r in records if r.get("division_number")}),
        "unique_chapters":    len({r.get("chapter_number") for r in records if r.get("chapter_number")}),
        "unique_subchapters": len({r.get("subchapter_number") for r in records if r.get("subchapter_number")}),
        "unique_articles":    len({r.get("article_number") for r in records if r.get("article_number")}),
    }


def retry_stats(records: list[dict]) -> dict:
    attempts = [r.get("_attempts", 1) for r in records]
    return {
        "1_attempt":  sum(1 for a in attempts if a == 1),
        "2_attempts": sum(1 for a in attempts if a == 2),
        "3_attempts": sum(1 for a in attempts if a == 3),
    }


def sample_missing(records: list[dict], field: str, n: int = 5) -> list[str]:
    return [
        r.get("source_url", "?")
        for r in records
        if not r.get(field)
    ][:n]


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def build_report() -> dict:
    discovered_urls = {
        json.loads(l)["url"]
        for l in DISCOVERY_FILE.read_text(encoding="utf-8").splitlines()
        if l.strip()
    } if DISCOVERY_FILE.exists() else set()

    sections  = load_jsonl(SECTIONS_FILE)
    failures  = load_jsonl(FAILURES_FILE)

    extracted_urls = {r["source_url"] for r in sections}
    failed_urls    = {f["url"] for f in failures}

    not_attempted = discovered_urls - extracted_urls - failed_urls

    # URL-level
    url_stats = {
        "discovered":    len(discovered_urls),
        "extracted":     len(sections),
        "failed":        len(failed_urls),
        "not_attempted": len(not_attempted),
        "coverage_pct":  round(100 * len(sections) / len(discovered_urls), 1) if discovered_urls else 0,
    }

    # Field coverage
    req_coverage  = field_coverage(sections, REQUIRED_FIELDS)
    opt_coverage  = field_coverage(sections, OPTIONAL_HIER_FIELDS)

    # Structural issues
    dupes         = detect_duplicates(sections)
    short_recs    = short_content(sections)
    hier          = hierarchy_breadth(sections)
    retries       = retry_stats(sections)

    # Sections missing citation
    no_citation = [r.get("source_url") for r in sections if not r.get("citation")]

    report = {
        "generated_at":   __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "url_coverage":   url_stats,
        "field_coverage": {
            "required": req_coverage,
            "optional_hierarchy": opt_coverage,
        },
        "hierarchy_breadth": hier,
        "retry_stats":   retries,
        "issues": {
            "duplicate_section_numbers": dupes,
            "short_content_records":     short_recs,
            "missing_citation_urls":     no_citation,
            "failed_urls":               sorted(failed_urls),
            "not_attempted_urls":        sorted(not_attempted),
        },
    }
    return report


# ---------------------------------------------------------------------------
# Pretty printer
# ---------------------------------------------------------------------------

SEP  = "=" * 70
SEP2 = "-" * 70


def bar(pct: float, width: int = 30) -> str:
    filled = round(pct / 100 * width)
    return f"[{'█' * filled}{'░' * (width - filled)}] {pct:5.1f}%"


def print_report(r: dict) -> None:
    uc = r["url_coverage"]
    fc = r["field_coverage"]
    hi = r["hierarchy_breadth"]
    is_ = r["issues"]
    rt = r["retry_stats"]

    print(f"\n{SEP}")
    print("  T8 CCR EXTRACTION COVERAGE REPORT")
    print(f"  Generated: {r['generated_at']}")
    print(SEP)

    # --- URL coverage ---
    print("\n▶  URL COVERAGE")
    print(SEP2)
    print(f"  Discovered URLs   : {uc['discovered']:>6,}")
    print(f"  Extracted (OK)    : {uc['extracted']:>6,}   {bar(uc['coverage_pct'])}")
    print(f"  Permanently failed: {uc['failed']:>6,}")
    print(f"  Not yet attempted : {uc['not_attempted']:>6,}")

    # --- Retry stats ---
    print("\n▶  RETRY DISTRIBUTION (among successes)")
    print(SEP2)
    for k, v in rt.items():
        print(f"  {k.replace('_', ' '):18s}: {v:>5,}")

    # --- Required field coverage ---
    print("\n▶  REQUIRED FIELD COVERAGE")
    print(SEP2)
    for field, stats in fc["required"].items():
        marker = "✓" if stats["pct"] == 100 else ("⚠" if stats["pct"] >= 80 else "✗")
        print(f"  {marker} {field:<25s} {bar(stats['pct'])}  (missing: {stats['missing']:,})")

    # --- Optional hierarchy coverage ---
    print("\n▶  OPTIONAL HIERARCHY FIELD COVERAGE")
    print(SEP2)
    print("  (Not every section has all levels — low % is expected here)")
    for field, stats in fc["optional_hierarchy"].items():
        print(f"    {field:<25s} {stats['populated']:>5,} / {uc['extracted']:,} sections populated")

    # --- Hierarchy breadth ---
    print("\n▶  HIERARCHY BREADTH")
    print(SEP2)
    for k, v in hi.items():
        print(f"  {k:<25s}: {v}")

    # --- Issues ---
    print("\n▶  ISSUES DETECTED")
    print(SEP2)

    dupes = is_["duplicate_section_numbers"]
    print(f"  Duplicate section numbers : {len(dupes)}")
    for sn, urls in list(dupes.items())[:5]:
        print(f"    §{sn}:")
        for u in urls:
            print(f"      {u}")

    short = is_["short_content_records"]
    print(f"\n  Short content records (<{MIN_CONTENT_CHARS} chars): {len(short)}")
    for rec in short[:5]:
        print(f"    §{rec['section_number']} — {rec['chars']} chars — {rec['url']}")

    no_cite = is_["missing_citation_urls"]
    print(f"\n  Missing citations         : {len(no_cite)}")
    for u in no_cite[:5]:
        print(f"    {u}")

    failed = is_["failed_urls"]
    print(f"\n  Permanently failed URLs   : {len(failed)}")
    for u in failed[:10]:
        print(f"    {u}")
    if len(failed) > 10:
        print(f"    ... and {len(failed) - 10} more (see coverage_report.json)")

    not_att = is_["not_attempted_urls"]
    print(f"\n  Not yet attempted         : {len(not_att)}")
    if not_att:
        print("  → Re-run extract.py to process these.")

    print(f"\n{SEP}")
    print(f"  OVERALL COVERAGE: {uc['coverage_pct']}% of discovered URLs extracted")
    print(SEP)

    # Final verdict
    if uc["coverage_pct"] >= 98 and not failed and not not_att:
        print("\n  ✓ COMPLETE — all discovered sections extracted successfully.\n")
    elif uc["coverage_pct"] >= 90:
        print("\n  ⚠ MOSTLY COMPLETE — a small number of sections are missing.\n")
    else:
        print("\n  ✗ INCOMPLETE — significant gaps remain. Check failures.jsonl.\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print("Building coverage report …")
    report = build_report()

    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Machine-readable report saved → {REPORT_FILE}")

    print_report(report)


if __name__ == "__main__":
    main()