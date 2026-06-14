"""
extract.py
----------
Reads discovered section URLs from data/discovery.jsonl,
fetches each page with Crawl4AI, extracts the canonical
CCR hierarchy and section content, and writes structured
records to data/sections.jsonl.

Supports:
  - Exponential-backoff retries per URL
  - Persistent checkpoint (skip already-done URLs on resume)
  - Failure log (data/failures.jsonl) for visibility
  - Both URL patterns:
      dir.ca.gov/t8/10.html
      dir.ca.gov/Title8/6505.html
"""

import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from crawl4ai.extraction_strategy import JsonCssExtractionStrategy

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DISCOVERY_FILE  = Path("../data/discovery.jsonl")
SECTIONS_FILE   = Path("../data/sections.jsonl")
FAILURES_FILE   = Path("../data/failures.jsonl")
CHECKPOINT_FILE = Path("../data/checkpoint_extract.json")

# ---------------------------------------------------------------------------
# Concurrency / retry settings
# ---------------------------------------------------------------------------

MAX_CONCURRENCY = 5          # polite — avoid hammering dir.ca.gov
MAX_RETRIES     = 3
BASE_BACKOFF    = 2.0        # seconds; doubled each retry

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CSS extraction schema
# ---------------------------------------------------------------------------
# The breadcrumb box on every page is a <table> or <div> near the top that
# contains lines like:
#   "TITLE 8. INDUSTRIAL RELATIONS"
#   "DIVISION 1. DEPARTMENT OF INDUSTRIAL RELATIONS"
#   "CHAPTER 1. DIVISION OF WORKERS' COMPENSATION ..."
#   "Article 2. QME Eligibility"
#   "Subchapter 14. Petroleum Safety Orders ..."
#
# The section heading is an <h3> or rendered as bold text: "§10. Appointment of QMEs."
#
# Crawl4AI's JsonCssExtractionStrategy lets us declare selectors declaratively.
# We extract raw text fields and parse them in Python afterward.

EXTRACTION_SCHEMA = {
    "name": "CCR Section",
    "baseSelector": "body",          # one record per page
    "fields": [
        {
            # The breadcrumb box — grab ALL text lines inside it
            "name": "breadcrumb_raw",
            "selector": "table:first-of-type td, div.disclaimer + table td, "
                        "blockquote, .breadcrumb, #breadcrumb, "
                        # fallback: first bordered box before the <hr>
                        "table td font, table td b",
            "type": "text",
            "multiple": True,
        },
        {
            # Section heading: §10. Appointment of QMEs.
            "name": "section_heading_raw",
            "selector": "h3, h2, b",
            "type": "text",
            "multiple": True,
        },
        {
            # Full body text (we convert to markdown ourselves)
            "name": "body_text",
            "selector": "body",
            "type": "text",
            "multiple": False,
        },
    ],
}

# ---------------------------------------------------------------------------
# Hierarchy parsing
# ---------------------------------------------------------------------------

# Patterns that match breadcrumb lines
_RE_TITLE      = re.compile(r"^TITLE\s+(\d+)\.\s+(.+)$", re.I)
_RE_DIVISION   = re.compile(r"^DIVISION\s+([\w.]+)\.\s+(.+)$", re.I)
_RE_CHAPTER    = re.compile(r"^CHAPTER\s+([\w.]+)\.\s+(.+)$", re.I)
_RE_SUBCHAPTER = re.compile(r"^Subchapter\s+([\w.]+)\.\s+(.+)$", re.I)
_RE_ARTICLE    = re.compile(r"^Article\s+([\w.]+)\.\s+(.+)$", re.I)
_RE_GROUP      = re.compile(r"^Group\s+([\w.]+)\.\s+(.+)$", re.I)

# Section heading: §10. Appointment of QMEs.
_RE_SECTION    = re.compile(r"§\s*(\d[\w.]*)\.\s*(.+?)\.?\s*$")

# URL → section number
_RE_URL_SECTION = re.compile(r"/(?:t8|title8)/(\d[\w.]*)\.html", re.I)


def parse_breadcrumb(lines: list[str]) -> dict:
    """
    Walk the raw text lines from the breadcrumb box and extract hierarchy fields.
    Unknown / empty lines are skipped gracefully.
    """
    result = {
        "title_number": None,
        "title_name": None,
        "division_number": None,
        "division_name": None,
        "chapter_number": None,
        "chapter_name": None,
        "subchapter_number": None,
        "subchapter_name": None,
        "article_number": None,
        "article_name": None,
        "group_number": None,
        "group_name": None,
    }

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        if m := _RE_TITLE.match(line):
            result["title_number"] = m.group(1)
            result["title_name"]   = m.group(2).strip()
        elif m := _RE_DIVISION.match(line):
            result["division_number"] = m.group(1)
            result["division_name"]   = m.group(2).strip()
        elif m := _RE_CHAPTER.match(line):
            result["chapter_number"] = m.group(1)
            result["chapter_name"]   = m.group(2).strip()
        elif m := _RE_SUBCHAPTER.match(line):
            result["subchapter_number"] = m.group(1)
            result["subchapter_name"]   = m.group(2).strip()
        elif m := _RE_ARTICLE.match(line):
            result["article_number"] = m.group(1)
            result["article_name"]   = m.group(2).strip()
        elif m := _RE_GROUP.match(line):
            result["group_number"] = m.group(1)
            result["group_name"]   = m.group(2).strip()

    return result


def parse_section_heading(candidates: list[str]) -> tuple[str | None, str | None]:
    """Return (section_number, section_heading) from the heading candidates."""
    for raw in candidates:
        if m := _RE_SECTION.search(raw.strip()):
            return m.group(1), m.group(2).strip()
    return None, None


def section_number_from_url(url: str) -> str | None:
    if m := _RE_URL_SECTION.search(url):
        return m.group(1)
    return None


def build_breadcrumb_path(h: dict, section_number: str | None) -> str:
    """Human-readable breadcrumb, e.g. 'Title 8 > Division 1 > Chapter 1 > Article 2 > §10'"""
    parts = []
    if h.get("title_number"):
        parts.append(f"Title {h['title_number']}")
    if h.get("division_number"):
        parts.append(f"Division {h['division_number']}")
    if h.get("chapter_number"):
        parts.append(f"Chapter {h['chapter_number']}")
    if h.get("subchapter_number"):
        parts.append(f"Subchapter {h['subchapter_number']}")
    if h.get("article_number"):
        parts.append(f"Article {h['article_number']}")
    if h.get("group_number"):
        parts.append(f"Group {h['group_number']}")
    if section_number:
        parts.append(f"§{section_number}")
    return " > ".join(parts)


def build_citation(title_number: str | None, section_number: str | None) -> str | None:
    if title_number and section_number:
        return f"{title_number} CCR § {section_number}"
    if section_number:
        return f"8 CCR § {section_number}"   # T8 default
    return None


def body_to_markdown(raw_text: str) -> str:
    """
    Light cleanup of the raw body text.
    Crawl4AI already strips HTML; we just normalize whitespace and
    remove the boilerplate disclaimer header.
    """
    lines = raw_text.splitlines()
    cleaned = []
    skip_phrases = (
        "This information is provided free of charge",
        "user and no representation",
        "New Query",
        "Return to index",
        "New query",
    )
    for line in lines:
        stripped = line.strip()
        if any(stripped.startswith(p) for p in skip_phrases):
            continue
        cleaned.append(stripped)

    # Collapse multiple blank lines to one
    text = "\n".join(cleaned)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------

def load_checkpoint() -> set[str]:
    if CHECKPOINT_FILE.exists():
        data = json.loads(CHECKPOINT_FILE.read_text())
        return set(data.get("done", []))
    return set()


def save_checkpoint(done: set[str]) -> None:
    CHECKPOINT_FILE.write_text(json.dumps({"done": sorted(done)}, indent=2))


# ---------------------------------------------------------------------------
# Per-URL fetch + extract with retries
# ---------------------------------------------------------------------------

async def fetch_section(
    crawler: AsyncWebCrawler,
    url: str,
    run_cfg: CrawlerRunConfig,
) -> dict | None:
    """
    Fetch a single section URL, extract structured data.
    Returns None on permanent failure (after all retries).
    """
    strategy = JsonCssExtractionStrategy(EXTRACTION_SCHEMA, verbose=False)
    cfg = CrawlerRunConfig(
        wait_until=run_cfg.wait_until,
        exclude_external_links=run_cfg.exclude_external_links,
        extraction_strategy=strategy,
    )

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = await crawler.arun(url, config=cfg)

            if not result.success:
                raise RuntimeError(f"crawl4ai reported failure: {result.error_message}")

            # Parse the CSS-extracted JSON
            raw = json.loads(result.extracted_content or "[]")
            if not raw:
                raise ValueError("Empty extraction result")

            page = raw[0] if isinstance(raw, list) else raw

            # --- Hierarchy ---
            breadcrumb_lines: list[str] = page.get("breadcrumb_raw") or []
            hierarchy = parse_breadcrumb(breadcrumb_lines)

            # --- Section heading ---
            heading_candidates: list[str] = page.get("section_heading_raw") or []
            sec_num_from_heading, sec_heading = parse_section_heading(heading_candidates)

            # Fall back to URL-derived section number if heading parse missed it
            sec_num = sec_num_from_heading or section_number_from_url(url)

            # Title number defaults to 8 for T8
            if not hierarchy.get("title_number"):
                hierarchy["title_number"] = "8"
            if not hierarchy.get("title_name"):
                hierarchy["title_name"] = "Industrial Relations"

            # --- Content ---
            body_raw = page.get("body_text") or result.markdown or ""
            content_md = body_to_markdown(body_raw)

            record = {
                # Canonical hierarchy
                "title_number":      hierarchy["title_number"],
                "title_name":        hierarchy["title_name"],
                "division_number":   hierarchy["division_number"],
                "division_name":     hierarchy["division_name"],
                "chapter_number":    hierarchy["chapter_number"],
                "chapter_name":      hierarchy["chapter_name"],
                "subchapter_number": hierarchy["subchapter_number"],
                "subchapter_name":   hierarchy["subchapter_name"],
                "article_number":    hierarchy["article_number"],
                "article_name":      hierarchy["article_name"],
                "group_number":      hierarchy["group_number"],
                "group_name":        hierarchy["group_name"],
                # Section identity
                "section_number":    sec_num,
                "section_heading":   sec_heading,
                "citation":          build_citation(hierarchy["title_number"], sec_num),
                "breadcrumb_path":   build_breadcrumb_path(hierarchy, sec_num),
                # Content
                "content_markdown":  content_md,
                # Provenance
                "source_url":        url,
                "retrieved_at":      datetime.now(timezone.utc).isoformat(),
                # QA
                "_attempts":         attempt,
            }
            return record

        except Exception as exc:
            last_error = exc
            wait = BASE_BACKOFF ** attempt
            log.warning(
                "[attempt %d/%d] %s — %s — retrying in %.1fs",
                attempt, MAX_RETRIES, url, exc, wait,
            )
            await asyncio.sleep(wait)

    log.error("PERMANENT FAILURE after %d attempts: %s — %s", MAX_RETRIES, url, last_error)
    return None


# ---------------------------------------------------------------------------
# Main extraction loop
# ---------------------------------------------------------------------------

async def extract() -> None:
    if not DISCOVERY_FILE.exists():
        log.error("discovery.jsonl not found at %s — run discover.py first", DISCOVERY_FILE)
        return

    urls = [
        json.loads(line)["url"]
        for line in DISCOVERY_FILE.read_text().splitlines()
        if line.strip()
    ]
    log.info("Loaded %d URLs from %s", len(urls), DISCOVERY_FILE)

    done = load_checkpoint()
    log.info("Checkpoint: %d already extracted, %d remaining", len(done), len(urls) - len(done))

    pending = [u for u in urls if u not in done]

    SECTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    FAILURES_FILE.parent.mkdir(parents=True, exist_ok=True)

    browser_cfg = BrowserConfig(headless=True, java_script_enabled=False)
    run_cfg     = CrawlerRunConfig(
        wait_until="domcontentloaded",
        exclude_external_links=True,
    )

    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    success_count = 0
    failure_count = 0

    # Append mode — safe to resume
    sections_fh = SECTIONS_FILE.open("a", encoding="utf-8")
    failures_fh = FAILURES_FILE.open("a", encoding="utf-8")

    try:
        async with AsyncWebCrawler(config=browser_cfg) as crawler:

            async def worker(url: str) -> None:
                nonlocal success_count, failure_count
                async with sem:
                    record = await fetch_section(crawler, url, run_cfg)

                    if record:
                        sections_fh.write(json.dumps(record) + "\n")
                        sections_fh.flush()
                        success_count += 1
                        done.add(url)
                        if success_count % 50 == 0:
                            save_checkpoint(done)
                            log.info(
                                "Checkpoint saved — %d extracted, %d failed",
                                success_count, failure_count,
                            )
                    else:
                        failure_count += 1
                        failures_fh.write(json.dumps({
                            "url": url,
                            "failed_at": datetime.now(timezone.utc).isoformat(),
                        }) + "\n")
                        failures_fh.flush()

            await asyncio.gather(*[worker(u) for u in pending])

    finally:
        sections_fh.close()
        failures_fh.close()
        save_checkpoint(done)

    log.info(
        "\nExtraction complete — %d succeeded, %d failed (permanent)",
        success_count, failure_count,
    )
    if failure_count:
        log.warning("See %s for failed URLs — re-run extract.py to retry them.", FAILURES_FILE)


if __name__ == "__main__":
    asyncio.run(extract())