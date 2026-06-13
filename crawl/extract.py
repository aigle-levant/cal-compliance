import asyncio
import json
import re
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone
from pathlib import Path

from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CrawlerRunConfig,
    CacheMode,
)

INPUT_FILE      = "../data/urls.jsonl"
OUTPUT_FILE     = "../data/extract.jsonl"
VALIDATION_FILE = "../data/coverage.jsonl"
SUMMARY_FILE    = "../data/summary.jsonl"
CHUNKS_FILE     = "../data/chunks.jsonl"
MAX_CONCURRENCY = 5
CHUNK_SIZE      = 2000
CHUNK_OVERLAP   = 200


# ─────────────────────────────────────────────────────────────────────────────
# T8 section-range → hierarchy lookup
#
# Sourced from the two official DIR Table of Contents pages:
#   Cal/OSHA chapters : https://dir.ca.gov/samples/search/query.htm
#   DLSE/IWC chapters : https://dir.ca.gov/samples/search/querydlse.htm
#
# Row schema:
#   (range_start, range_end,
#    chapter_id, chapter_name,
#    division_id, division_name,
#    subchapter_id, subchapter_name)
#
# Division structure (official):
#   Division 1 — Department of Industrial Relations  (Ch 3.2, 3.3, 3.5, 4, 7)
#   Division 2 — Division of Labor Standards Enforcement  (Ch 5, 6)
#
# Rows are ordered so the first match wins; tighter ranges come before wider
# ones that share the same chapter (e.g. sub-ranges of Ch 4).
# ─────────────────────────────────────────────────────────────────────────────

T8_SECTION_RANGES: list[tuple] = [

    # ── Chapter 3.2 · California Occupational Safety and Health Regulations ─
    (330,    339.11, "3.2", "California Occupational Safety and Health Regulations",
     "1", "Department of Industrial Relations",
     "1",  "Regulations of the Director of Industrial Relations"),

    (340,    344.90, "3.2", "California Occupational Safety and Health Regulations",
     "1", "Department of Industrial Relations",
     "2",  "Regulations of the Division of Occupational Safety and Health"),

    # ── Chapter 3.3 · Occupational Safety and Health Appeals Board ──────────
    (345,    397,    "3.3", "Occupational Safety and Health Appeals Board",
     "1", "Department of Industrial Relations",
     None, None),

    # ── Chapter 3.5 · Occupational Safety and Health Standards Board ────────
    (401,    428,    "3.5", "Occupational Safety and Health Standards Board",
     "1", "Department of Industrial Relations",
     "1",  "Rules of Procedure for Permanent Variances and Appeals from Temporary Variances"),

    # ── Chapter 4 · Division of Industrial Safety ────────────────────────────
    (450,    560,    "4", "Division of Industrial Safety",
     "1", "Department of Industrial Relations",
     "1",  "Unfired Pressure Vessel Safety Orders"),

    (750,    797,    "4", "Division of Industrial Safety",
     "1", "Department of Industrial Relations",
     "2",  "Boiler and Fired Pressure Vessel Safety Orders"),

    (1200,   1280,   "4", "Division of Industrial Safety",
     "1", "Department of Industrial Relations",
     "3",  "Compressed Air Safety Orders"),

    (1500,   1962,   "4", "Division of Industrial Safety",
     "1", "Department of Industrial Relations",
     "4",  "Construction Safety Orders"),

    (2299,   2974,   "4", "Division of Industrial Safety",
     "1", "Department of Industrial Relations",
     "5",  "Electrical Safety Orders"),

    (3000,   3146,   "4", "Division of Industrial Safety",
     "1", "Department of Industrial Relations",
     "6",  "Elevator Safety Orders"),

    (3150,   3191,   "4", "Division of Industrial Safety",
     "1", "Department of Industrial Relations",
     "6.1", "Passenger Tramway Safety Orders"),

    (3195.1, 3195.14,"4", "Division of Industrial Safety",
     "1", "Department of Industrial Relations",
     "6.2", "Permanent Amusement Ride Safety Orders"),

    (3200,   6184,   "4", "Division of Industrial Safety",
     "1", "Department of Industrial Relations",
     "7",  "General Industry Safety Orders"),

    (6248,   6402,   "4", "Division of Industrial Safety",
     "1", "Department of Industrial Relations",
     "13", "Logging and Sawmill Safety Orders"),

    (6500,   6693,   "4", "Division of Industrial Safety",
     "1", "Department of Industrial Relations",
     "14", "Petroleum Safety Orders--Drilling and Production"),

    (6750,   6894,   "4", "Division of Industrial Safety",
     "1", "Department of Industrial Relations",
     "15", "Petroleum Safety Orders--Refining, Transportation and Handling"),

    (6950,   7283,   "4", "Division of Industrial Safety",
     "1", "Department of Industrial Relations",
     "17", "Mine Safety Orders"),

    (8345,   8399,   "4", "Division of Industrial Safety",
     "1", "Department of Industrial Relations",
     "18", "Ship Building, Ship Repairing and Ship Breaking Safety Orders"),

    (8400,   8568,   "4", "Division of Industrial Safety",
     "1", "Department of Industrial Relations",
     "20", "Tunnel Safety Orders"),

    (8600,   8618,   "4", "Division of Industrial Safety",
     "1", "Department of Industrial Relations",
     "21", "Telecommunication Safety Orders"),

    # ── Chapter 5 · Industrial Welfare Commission ────────────────────────────
    # Ch 5 uses "Groups" instead of numbered subchapters; subchapter_id is None.
    (11000,  11000,  "5", "Industrial Welfare Commission",
     "2", "Division of Labor Standards Enforcement",
     None, "General Minimum Wage Order"),

    (11010,  11170,  "5", "Industrial Welfare Commission",
     "2", "Division of Labor Standards Enforcement",
     None, "Industry and Occupation Orders"),

    (11530,  11538,  "5", "Industrial Welfare Commission",
     "2", "Division of Labor Standards Enforcement",
     None, "Regulations Governing Wage Boards"),

    # ── Chapter 6 · Division of Labor Standards Enforcement ──────────────────
    (11701,  11707,  "6", "Division of Labor Standards Enforcement",
     "2", "Division of Labor Standards Enforcement",
     "1",    "Child Labor Orders--Prohibited Occupations"),

    (11750,  11767,  "6", "Division of Labor Standards Enforcement",
     "2", "Division of Labor Standards Enforcement",
     "2",    "Employment of Minors in the Entertainment Industry"),

    (11770,  11773,  "6", "Division of Labor Standards Enforcement",
     "2", "Division of Labor Standards Enforcement",
     "2.2",  "Child Performer Services Permits"),

    (11775,  11785,  "6", "Division of Labor Standards Enforcement",
     "2", "Division of Labor Standards Enforcement",
     "2.5",  "Child Labor Law Violations"),

    (12000,  12033,  "6", "Division of Labor Standards Enforcement",
     "2", "Division of Labor Standards Enforcement",
     "3",    "Employment Agencies"),

    (13200,  13236,  "6", "Division of Labor Standards Enforcement",
     "2", "Division of Labor Standards Enforcement",
     "5",    "Registration of Persons Who Unload Farm Products"),

    (13260,  13267,  "6", "Division of Labor Standards Enforcement",
     "2", "Division of Labor Standards Enforcement",
     "5.5",  "Unloading of Farm Products in the Markets of San Mateo, Alameda, and San Francisco"),

    (13300,  13302,  "6", "Division of Labor Standards Enforcement",
     "2", "Division of Labor Standards Enforcement",
     "6",    "Security For Wages"),

    (13500,  13520,  "6", "Division of Labor Standards Enforcement",
     "2", "Division of Labor Standards Enforcement",
     "6.5",  "Hearings on Actions to Recover Wages, Penalties, and Other Demands for Compensation"),

    (13600,  13624,  "6", "Division of Labor Standards Enforcement",
     "2", "Division of Labor Standards Enforcement",
     "7",    "Industrial Homework"),

    (13630,  13659,  "6", "Division of Labor Standards Enforcement",
     "2", "Division of Labor Standards Enforcement",
     "8",    "Garment Manufacturers"),

    (13660,  13662,  "6", "Division of Labor Standards Enforcement",
     "2", "Division of Labor Standards Enforcement",
     "9",    "Labor Commissioner's Farm Labor Contractor Fund"),

    (13670,  13677,  "6", "Division of Labor Standards Enforcement",
     "2", "Division of Labor Standards Enforcement",
     "10",   "Registration of Employers, Transporters, and Supervisors of Minors Engaged in Door-to-Door Sales"),

    (13680,  13694,  "6", "Division of Labor Standards Enforcement",
     "2", "Division of Labor Standards Enforcement",
     "11",   "Car Washing and Polishing"),

    (13800,  13800,  "6", "Division of Labor Standards Enforcement",
     "2", "Division of Labor Standards Enforcement",
     "12",   "Collections"),

    (13810,  13822,  "6", "Division of Labor Standards Enforcement",
     "2", "Division of Labor Standards Enforcement",
     "13",   "Janitorial Registration and Training"),

    (13830,  13832,  "6", "Division of Labor Standards Enforcement",
     "2", "Division of Labor Standards Enforcement",
     "13.5", "Enforcement of Client Employer Liability Under Labor Code Section 2810.3"),

    (13850,  13874,  "6", "Division of Labor Standards Enforcement",
     "2", "Division of Labor Standards Enforcement",
     "14",   "Foreign Labor Contractor Registration"),

    (13875,  13888,  "6", "Division of Labor Standards Enforcement",
     "2", "Division of Labor Standards Enforcement",
     "15",   "Public List of Certain Port Drayage Motor Carriers"),

    (13900,  13903,  "6", "Division of Labor Standards Enforcement",
     "2", "Division of Labor Standards Enforcement",
     "16",   "Assessment of Civil Penalties for Violations of Retaliation Laws"),

    # ── Chapter 7 · Division of Labor Statistics and Research ────────────────
    (14000,  14400,  "7", "Division of Labor Statistics and Research",
     "2", "Division of Labor Standards Enforcement",
     "1",    "Occupational Injury or Illness Reports and Records"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Leginfo code → title name
# ─────────────────────────────────────────────────────────────────────────────

LEGINFO_CODE_NAMES: dict[str, str] = {
    "lab":  "California Labor Code",
    "bpc":  "Business and Professions Code",
    "civ":  "Civil Code",
    "pen":  "Penal Code",
    "gov":  "Government Code",
    "hsc":  "Health and Safety Code",
    "ins":  "Insurance Code",
    "veh":  "Vehicle Code",
    "fam":  "Family Code",
    "wic":  "Welfare and Institutions Code",
    "corp": "Corporations Code",
    "edu":  "Education Code",
    "uic":  "Unemployment Insurance Code",
    "prc":  "Public Resources Code",
}


# ─────────────────────────────────────────────────────────────────────────────
# Hierarchy
# ─────────────────────────────────────────────────────────────────────────────

class Hierarchy:
    """
    All ID fields are plain strings ("1", "6.2") for easy downstream filtering.
    All name fields contain only the bare label, no level prefix
    ("Industrial Relations", not "Title 8. Industrial Relations").
    Label properties build the prefixed string on demand for breadcrumbs.
    """
    __slots__ = (
        "source_type",
        "title_id",      "title_name",
        "division_id",   "division_name",
        "chapter_id",    "chapter_name",
        "subchapter_id", "subchapter_name",
        "article_id",    "article_name",
    )

    def __init__(self):
        for s in self.__slots__:
            setattr(self, s, None)

    @property
    def title_label(self)      -> str | None: return f"Title {self.title_id}"           if self.title_id      else None
    @property
    def division_label(self)   -> str | None: return f"Division {self.division_id}"     if self.division_id   else None
    @property
    def chapter_label(self)    -> str | None: return f"Chapter {self.chapter_id}"       if self.chapter_id    else None
    @property
    def subchapter_label(self) -> str | None: return f"Subchapter {self.subchapter_id}" if self.subchapter_id else None
    @property
    def article_label(self)    -> str | None: return f"Article {self.article_id}"       if self.article_id    else None


# ─────────────────────────────────────────────────────────────────────────────
# T8 hierarchy resolution
# ─────────────────────────────────────────────────────────────────────────────

def _section_to_float(s: str) -> float | None:
    """'1604.3' → 1604.3,  '339.11' → 339.11,  'ABC' → None."""
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _lookup_t8_by_section(section_number: str) -> dict | None:
    """
    Return the first T8_SECTION_RANGES row that covers section_number,
    or None if no row matches. Used as the fallback when the TOC backlink
    is absent (e.g. repealed stub pages).
    """
    val = _section_to_float(section_number)
    if val is None:
        return None
    for start, end, ch_id, ch_name, div_id, div_name, sb_id, sb_name in T8_SECTION_RANGES:
        if start <= val <= end:
            return {
                "chapter_id":      ch_id,
                "chapter_name":    ch_name,
                "division_id":     div_id,
                "division_name":   div_name,
                "subchapter_id":   sb_id,
                "subchapter_name": sb_name,
            }
    return None


def _decode_t8_slug(slug: str) -> dict:
    """
    Decode a T8 TOC slug into IDs.
    Grammar:  ch<N> [sb<N>] [a<N>]
    Negative lookbehind on 'a' avoids matching the letter inside words.

    Examples:
      ch7sb1a1  → chapter=7,  subchapter=1,  article=1
      ch4_5sb1  → chapter=4.5 subchapter=1
      ch3_2sb2  → chapter=3.2 subchapter=2
    """
    slug = slug.lower().replace("_", ".")   # ch4_5 → ch4.5
    ch_m = re.search(r"ch(\d+(?:\.\d+)?)", slug)
    sb_m = re.search(r"sb(\d+(?:\.\d+)?)", slug)
    a_m  = re.search(r"(?<![a-z])a(\d+(?:\.\d+)?)", slug)
    return {
        "chapter_id":    ch_m.group(1) if ch_m else None,
        "subchapter_id": sb_m.group(1) if sb_m else None,
        "article_id":    a_m.group(1)  if a_m  else None,
    }


def _apply_range_row(h: Hierarchy, row: dict) -> None:
    """Write a _lookup_t8_by_section result into a Hierarchy in-place."""
    h.chapter_id      = row["chapter_id"]
    h.chapter_name    = row["chapter_name"]
    h.division_id     = row["division_id"]
    h.division_name   = row["division_name"]
    h.subchapter_id   = row["subchapter_id"]
    h.subchapter_name = row["subchapter_name"]


def extract_t8_hierarchy(raw_markdown: str, section_number: str | None = None) -> Hierarchy:
    """
    Two-pass T8 hierarchy extraction.

    Pass 1 — TOC backlink slug (primary):
      Looks for the 'Go Back to … Table of Contents' footer link in the raw
      markdown. The href slug encodes chapter, subchapter, and article directly.
      Must run against raw_markdown BEFORE trim_before_section() is called, as
      the footer is stripped by that function.

    Pass 2 — section-range lookup (fallback):
      Used when no backlink exists, e.g. repealed stub pages. Maps the numeric
      section number to its chapter/subchapter via T8_SECTION_RANGES.
    """
    h = Hierarchy()
    h.source_type = "t8"
    h.title_id    = "8"
    h.title_name  = "Industrial Relations"

    # ── Pass 1: slug from TOC backlink ───────────────────────────────────────
    # Matches both markdown links  ](…/T8/slug.html)
    # and raw hrefs                href="…/T8/slug.html"
    slug_patterns = [
        r'\]\((?:https?://[^)]*)?/[Tt]8/([A-Za-z0-9_.]+)\.html\)',
        r'href=["\'](?:https?://[^"\']*)?/[Tt]8/([A-Za-z0-9_.]+)\.html["\']',
    ]
    for pat in slug_patterns:
        m = re.search(pat, raw_markdown, re.IGNORECASE)
        if m:
            raw_slug = m.group(1)
            # Normalise underscores so ch4_5sb1 → ch4.5sb1 before the ch\d check
            normalised = raw_slug.lower().replace("_", ".")
            if re.match(r"ch\d", normalised):
                decoded = _decode_t8_slug(raw_slug)
                ch_id = decoded["chapter_id"]
                if ch_id:
                    h.chapter_id   = ch_id
                    h.chapter_name = f"Chapter {ch_id}"

                    # Resolve division and canonical subchapter from range table
                    # (slug gives chapter+subchapter IDs; range table gives names)
                    if decoded["subchapter_id"]:
                        # Use range table to get the subchapter *name* for this ch/sb pair
                        # by scanning for a row whose ch_id and sb_id both match.
                        for row in T8_SECTION_RANGES:
                            _, _, r_ch, _, r_div_id, r_div_name, r_sb, r_sb_name = row
                            if r_ch == ch_id and r_sb == decoded["subchapter_id"]:
                                h.division_id     = r_div_id
                                h.division_name   = r_div_name
                                h.subchapter_id   = decoded["subchapter_id"]
                                h.subchapter_name = r_sb_name
                                break
                        else:
                            # ch/sb combo not in table — store ID only, name unknown
                            h.subchapter_id   = decoded["subchapter_id"]
                            h.subchapter_name = f"Subchapter {decoded['subchapter_id']}"
                    else:
                        # No subchapter in slug — pick division from first matching ch row
                        for row in T8_SECTION_RANGES:
                            _, _, r_ch, _, r_div_id, r_div_name, _, _ = row
                            if r_ch == ch_id:
                                h.division_id   = r_div_id
                                h.division_name = r_div_name
                                break

                    if decoded["article_id"]:
                        h.article_id   = decoded["article_id"]
                        h.article_name = f"Article {decoded['article_id']}"
                break  # found a valid slug — stop trying patterns

    # ── Pass 2: range lookup by section number (fallback) ────────────────────
    if not h.chapter_id and section_number:
        row = _lookup_t8_by_section(section_number)
        if row:
            _apply_range_row(h, row)

    return h


# ─────────────────────────────────────────────────────────────────────────────
# Leginfo hierarchy resolution
# ─────────────────────────────────────────────────────────────────────────────

def extract_leginfo_hierarchy(url: str, page_title: str | None = None) -> Hierarchy:
    """
    Primary:  decode hierarchy from URL query parameters.
    Fallback: parse page <title> string for any level not present in the URL.

    URL example:
      ?lawCode=LAB&division=2.&part=1.&chapter=1.&article=1.&sectionNum=200.
    Trailing dots in California's URL convention are stripped from all values.
    """
    h = Hierarchy()
    h.source_type = "leginfo"

    params = parse_qs(urlparse(url).query, keep_blank_values=False)

    def get(key: str) -> str | None:
        for k, v in params.items():
            if k.lower() == key.lower() and v:
                return v[0].rstrip(".")
        return None

    law_code = get("lawCode")
    if law_code:
        h.title_id   = law_code.upper()
        h.title_name = LEGINFO_CODE_NAMES.get(law_code.lower(), f"{law_code.upper()} Code")
    else:
        h.title_id   = "LAB"
        h.title_name = "California Labor Code"

    division = get("division")
    part     = get("part")
    chapter  = get("chapter")
    article  = get("article")

    # Fold part into division when both present ("2.1" style)
    if division and part:
        h.division_id   = f"{division}.{part}"
        h.division_name = f"Division {division}, Part {part}"
    elif division:
        h.division_id   = division
        h.division_name = f"Division {division}"

    if chapter:
        h.chapter_id   = chapter
        h.chapter_name = f"Chapter {chapter}"

    if article:
        h.article_id   = article
        h.article_name = f"Article {article}"

    # Fallback: fill remaining nulls from the HTML page <title>
    # Patterns are tight (digits/dots only) to avoid over-capturing.
    if page_title:
        if not h.division_id:
            m = re.search(r"\bDivision\s+([\d.]+)", page_title)
            if m:
                h.division_id   = m.group(1)
                h.division_name = f"Division {m.group(1)}"
        if not h.chapter_id:
            m = re.search(r"\bChapter\s+([\d.]+)", page_title)
            if m:
                h.chapter_id   = m.group(1)
                h.chapter_name = f"Chapter {m.group(1)}"
        if not h.article_id:
            m = re.search(r"\bArticle\s+([\d.]+)", page_title)
            if m:
                h.article_id   = m.group(1)
                h.article_name = f"Article {m.group(1)}"

    return h


# ─────────────────────────────────────────────────────────────────────────────
# Markdown cleaning
# ─────────────────────────────────────────────────────────────────────────────

_RE_HR         = re.compile(r"^\s*(\*\s*){3,}\s*$", re.MULTILINE)
_RE_SKIP_NAV   = re.compile(r"\[Skip to Main Content\][^\n]*\n", re.IGNORECASE)
_RE_DISCLAIMER = re.compile(
    r"This information is provided free of charge.*?full disclaimer[^\n]*\n",
    re.IGNORECASE | re.DOTALL,
)
_RE_BLANKS     = re.compile(r"\n{3,}")
_RE_MD_IMAGE   = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_RE_MD_LINK    = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_RE_GO_BACK = re.compile(
    r"\[!\[Go Back.*?Table of Contents\]\([^)]*\)",
    re.IGNORECASE | re.DOTALL,
)
SECTION_RE = re.compile(
    r"§\s*(\d+(?:\.\d+)*)\.?\s+(.+)"
)
SECTION_RE2 = re.compile(
    r"[Ss]ection\s+(\d+(?:\.\d+)*)\.?\s+(.+)"
)
_RE_EMPTY_TABLE = re.compile(
    r"\|\s*\|\s*\n\|\s*---\s*\|?",
    re.MULTILINE,
)

def clean_markdown(md: str) -> str:
    md = _RE_HR.sub("", md)
    md = _RE_SKIP_NAV.sub("", md)
    md = _RE_DISCLAIMER.sub("", md)

    md = _RE_GO_BACK.sub("", md)
    md = _RE_EMPTY_TABLE.sub("", md)

    md = _RE_BLANKS.sub("\n\n", md)

    return md.strip()


def trim_before_section(md: str) -> str:
    """Drop everything before the first § (nav boilerplate)."""
    idx = md.find("§")
    return md[idx:] if idx != -1 else md


def _strip_inline_markup(text: str) -> str:
    """Remove markdown images and collapse links to their label text."""
    text = _RE_MD_IMAGE.sub("", text)
    text = _RE_MD_LINK.sub(r"\1", text)
    return text.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Section header extraction
# ─────────────────────────────────────────────────────────────────────────────

def extract_section_header(md: str) -> tuple[str | None, str | None]:
    """
    Scan the first 40 lines for a section number + title.

    Handles:
      §14004. Employer's Report...
      § 5194.1 Hazard Communication
      Section 200. Definitions.

    Inline markdown links/images are stripped from the returned title so
    artefacts like '[Form 5020](http://...)' don't pollute the heading.
    """
    text = "\n".join(md.splitlines()[:120])
    patterns = [
    r"§\s*(\d+(?:\.\d+)*)\.?\s+(.+)",
    r"[Ss]ection\s+(\d+(?:\.\d+)*)\.?\s+(.+)",
]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            section = m.group(1).strip()

            section_match = re.match(
    r"\d+(?:\.\d+)*",
    section
)

            if not section_match:
                continue

            section = section_match.group(0)

            title = _strip_inline_markup(
    m.group(2)
)

            return section, title
    return None, None


# ─────────────────────────────────────────────────────────────────────────────
# Validation
#
# Validation rules are source-type aware:
#   - T8 records are expected to have a full division/chapter hierarchy.
#   - Leginfo records frequently lack a division (many Labor Code sections
#     only carry chapter/part/article), so requiring division here would
#     produce false-positive warnings on every such page.
# ─────────────────────────────────────────────────────────────────────────────

_REQUIRED_COMMON = (
    "title_id", "title_name",
    "section_number", "section_title",
    "citation", "source_url", "content_markdown",
)

_REQUIRED_T8      = _REQUIRED_COMMON + ("division_id", "division_name", "chapter_id", "chapter_name")
_REQUIRED_LEGINFO = _REQUIRED_COMMON


def validate_record(record: dict) -> list[str]:
    source_type = record.get("source_type")
    required = _REQUIRED_T8 if source_type == "t8" else _REQUIRED_LEGINFO

    issues = [f"missing: {f}" for f in required if not record.get(f)]

    if source_type == "t8":
        if record.get("chapter_id") and not record.get("division_id"):
            issues.append("hierarchy gap: chapter without division")
        if record.get("subchapter_id") and not record.get("chapter_id"):
            issues.append("hierarchy gap: subchapter without chapter")
        if record.get("article_id") and not record.get("chapter_id"):
            issues.append("hierarchy gap: article without chapter")
    elif source_type == "leginfo":
        # leginfo: article without chapter is the only structural gap worth flagging
        if record.get("article_id") and not record.get("chapter_id"):
            issues.append("hierarchy gap: article without chapter")

    return issues


# ─────────────────────────────────────────────────────────────────────────────
# RAG chunking
# ─────────────────────────────────────────────────────────────────────────────

def is_useful_chunk(text: str) -> bool:
    text = text.strip()

    if len(text) < 50:
        return False

    junk_markers = (
        "Go Back to",
        "Table of Contents",
        "arrow_marble_left.gif",
    )

    return not any(marker in text for marker in junk_markers)

def _make_chunks(text: str) -> list[str]:
    """
    Split text into overlapping chunks, preferring paragraph boundaries
    so chunks don't cut mid-sentence.
    """
    if len(text) <= CHUNK_SIZE:
        return [text]
    chunks, start = [], 0
    while start < len(text):
        end = start + CHUNK_SIZE
        if end < len(text):
            bp = text.rfind("\n\n", start, end)
            if bp != -1 and bp > start + CHUNK_OVERLAP:
                end = bp
        chunks.append(text[start:end].strip())
        start = end - CHUNK_OVERLAP
    return [c for c in chunks if c]


def build_chunks(record: dict) -> list[dict]:
    """
    Every chunk carries the full hierarchy so it can be filtered or
    reconstructed by a vector DB without joining back to the parent record.
    """
    chunks = [
        c
        for c in _make_chunks(record.get("content_markdown", ""))
        if is_useful_chunk(c)
    ]
    base = {
        "document_type":   record["document_type"],
        "source_type":     record["source_type"],
        "title_id":        record["title_id"],
        "title_name":      record["title_name"],
        "division_id":     record["division_id"],
        "division_name":   record["division_name"],
        "chapter_id":      record["chapter_id"],
        "chapter_name":    record["chapter_name"],
        "subchapter_id":   record["subchapter_id"],
        "subchapter_name": record["subchapter_name"],
        "article_id":      record["article_id"],
        "article_name":    record["article_name"],
        "section_number":  record["section_number"],
        "section_title":   record["section_title"],
        "citation":        record["citation"],
        "breadcrumb_path": record["breadcrumb_path"],
        "source_url":      record["source_url"],
        "retrieved_at":    record["retrieved_at"],
    }
    section = record["section_number"] or "unknown"
    return [
        {"chunk_id": f"{section}_{i}", "chunk_index": i, "chunk_total": len(chunks), "text": c, **base}
        for i, c in enumerate(chunks)
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Record assembly
# ─────────────────────────────────────────────────────────────────────────────

def build_record(url: str, raw_markdown: str, page_title: str | None = None) -> dict:
    """
    Assemble one structured regulation record.

    Ordering contract (T8):
      1. extract_t8_hierarchy() runs on raw_markdown — the footer TOC backlink
         must still be present; trim_before_section() removes it.
      2. section number is extracted from the *cleaned* markdown so it can also
         be passed to extract_t8_hierarchy() as the range-lookup fallback.
      3. clean + trim happens after hierarchy extraction.
    """
    url_lower = url.lower()
    is_t8      = "dir.ca.gov/title8" in url_lower or "/t8/" in url_lower
    is_leginfo = "leginfo.legislature.ca.gov" in url_lower

    # ── Hierarchy ────────────────────────────────────────────────────────────
    # For T8 we need the section number to drive the range-lookup fallback,
    # but we also need raw markdown for the slug extraction.  Extract section
    # from a temporary clean+trim, then reuse that result below.
    if is_t8:
        _md_preview = trim_before_section(clean_markdown(raw_markdown))
        section_number, section_title = extract_section_header(_md_preview)
        h = extract_t8_hierarchy(raw_markdown, section_number=section_number)
    elif is_leginfo:
        h = extract_leginfo_hierarchy(url, page_title)
        section_number = section_title = None   # resolved below after cleaning
    else:
        h = Hierarchy()
        h.source_type  = "unknown"
        section_number = section_title = None

    # ── Clean content ────────────────────────────────────────────────────────
    markdown = clean_markdown(raw_markdown)
    if is_t8:
        markdown = trim_before_section(markdown)
        if markdown.startswith("§"):
            markdown = markdown.strip()

    # For non-T8 sources, extract section header from the cleaned markdown
    if not is_t8:
        section_number, section_title = extract_section_header(markdown)

    # ── Citation ─────────────────────────────────────────────────────────────
    citation = None
    if section_number:
        if is_leginfo:
            citation = f"{h.title_id} § {section_number}"
        elif h.title_id:
            citation = f"{h.title_id} CCR § {section_number}"

    # ── Breadcrumb ───────────────────────────────────────────────────────────
    crumbs = [
        label for label in (
            h.title_label,
            h.division_label,
            h.chapter_label,
            h.subchapter_label,
            h.article_label,
            f"§{section_number}" if section_number else None,
        )
        if label
    ]

    return {
        "document_type":   "regulation",
        "source_type":     h.source_type,
        "retrieved_at":    datetime.now(timezone.utc).isoformat(),
        "source_url":      url,
        "title_id": h.title_id,
        "division_id": h.division_id,
        "chapter_id": h.chapter_id,
        "subchapter_id": h.subchapter_id,
        "article_id": h.article_id,

        # hierarchy names
        "title_name": h.title_name,
        "division_name": h.division_name,
        "chapter_name": h.chapter_name,
        "subchapter_name": h.subchapter_name,
        "article_name": h.article_name,
        # section
        "section_number":  section_number,
        "section_title":   section_title,
        "citation":        citation,
        "breadcrumb_path": " -> ".join(crumbs) if crumbs else None,
        # content
        "content_markdown": markdown,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Coverage report
#
# coverage.jsonl contains:
#   - one "page" record per successfully processed URL, with detailed
#     hierarchy/validation status for that page
#   - one "skipped" / "failed" / "error" record per URL that did not
#     produce a regulation record
#   - a single trailing "summary" record with crawl-wide aggregates
# ─────────────────────────────────────────────────────────────────────────────

def build_coverage_record(record: dict, issues: list[str]) -> dict:
    """Detailed per-page coverage entry for a successfully processed URL."""
    content = record.get("content_markdown") or ""
    return {
        "record_type":     "page",
        "status":          "ok" if not issues else "warn",
        "source_url":      record["source_url"],
        "source_type":     record.get("source_type"),
        "retrieved_at":    record.get("retrieved_at"),

        # identification
        "section_number":  record.get("section_number"),
        "section_title":   record.get("section_title"),
        "citation":        record.get("citation"),
        "breadcrumb_path": record.get("breadcrumb_path"),

        # hierarchy presence flags
        "has_title":       bool(record.get("title_id")),
        "has_division":    bool(record.get("division_id")),
        "has_chapter":     bool(record.get("chapter_id")),
        "has_subchapter":  bool(record.get("subchapter_id")),
        "has_article":     bool(record.get("article_id")),

        # hierarchy values (useful for spot-checking directly in coverage.jsonl)
        "title_id":        record.get("title_id"),
        "division_id":     record.get("division_id"),
        "chapter_id":      record.get("chapter_id"),
        "subchapter_id":   record.get("subchapter_id"),
        "article_id":      record.get("article_id"),

        # content stats
        "content_length":  len(content),
        "content_empty":   len(content.strip()) == 0,

        # validation outcome
        "issue_count":     len(issues),
        "issues":          issues,
    }


def build_skip_record(url: str, reason: str, detail: str | None = None) -> dict:
    """Coverage entry for a URL that did not yield a regulation record."""
    rec = {
        "record_type": "page",
        "status":      reason,       # "failed" | "skipped" | "error"
        "source_url":  url,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
    if detail:
        rec["detail"] = detail
    return rec


class CoverageAggregator:
    """
    Accumulates crawl-wide stats so a single "summary" record can be
    appended to coverage.jsonl once all URLs have been processed.

    Safe under asyncio.gather()/Semaphore concurrency: all mutation happens
    in synchronous, non-awaiting methods, so no two updates can interleave
    on the single-threaded event loop.
    """

    def __init__(self):
        self.total_urls = 0
        self.processed  = 0
        self.failed     = 0
        self.skipped    = 0
        self.errors     = 0

        self.by_source_type = {}   # source_type -> count
        self.ok_count   = 0
        self.warn_count = 0

        self.missing_field_counts = {}  # field -> count
        self.hierarchy_gap_counts = {}  # gap message -> count

        self.has_division_count   = 0
        self.has_chapter_count    = 0
        self.has_subchapter_count = 0
        self.has_article_count    = 0

        self.unresolved_section_urls = []  # source_urls with no section_number

    def record_total(self, n: int) -> None:
        self.total_urls = n

    def record_fail(self) -> None:
        self.failed += 1

    def record_skip(self) -> None:
        self.skipped += 1

    def record_error(self) -> None:
        self.errors += 1

    def record_page(self, record: dict, issues: list[str]) -> None:
        self.processed += 1

        st = record.get("source_type") or "unknown"
        self.by_source_type[st] = self.by_source_type.get(st, 0) + 1

        if issues:
            self.warn_count += 1
        else:
            self.ok_count += 1

        for issue in issues:
            if issue.startswith("missing:"):
                field = issue.split("missing:", 1)[1].strip()
                self.missing_field_counts[field] = self.missing_field_counts.get(field, 0) + 1
            elif issue.startswith("hierarchy gap:"):
                self.hierarchy_gap_counts[issue] = self.hierarchy_gap_counts.get(issue, 0) + 1

        if record.get("division_id"):
            self.has_division_count += 1
        if record.get("chapter_id"):
            self.has_chapter_count += 1
        if record.get("subchapter_id"):
            self.has_subchapter_count += 1
        if record.get("article_id"):
            self.has_article_count += 1

        if not record.get("section_number"):
            self.unresolved_section_urls.append(record["source_url"])

    def build_summary(self) -> dict:
        return {
            "record_type":  "summary",
            "generated_at": datetime.now(timezone.utc).isoformat(),

            "total_urls": self.total_urls,
            "processed":  self.processed,
            "failed":     self.failed,
            "skipped":    self.skipped,
            "errors":     self.errors,

            "by_source_type": self.by_source_type,

            "status_counts": {
                "ok":   self.ok_count,
                "warn": self.warn_count,
            },

            "hierarchy_coverage": {
                "has_division":   self.has_division_count,
                "has_chapter":    self.has_chapter_count,
                "has_subchapter": self.has_subchapter_count,
                "has_article":    self.has_article_count,
            },

            "missing_field_counts": self.missing_field_counts,
            "hierarchy_gap_counts": self.hierarchy_gap_counts,

            "unresolved_section_count": len(self.unresolved_section_urls),
            "unresolved_section_urls":  self.unresolved_section_urls,
        }

    def build_summary_stats(self) -> dict:
        """
        Compact summary record for summary.jsonl, matching the schema:
          {
            "total_documents": int,
            "valid_documents": int,
            "invalid_documents": int,
            "division_coverage_pct": float,
            "chapter_coverage_pct": float,
            "subchapter_coverage_pct": float,
            "article_coverage_pct": float,
            "issues": {<issue message>: <count>}
          }
        """
        def pct(count: int) -> float:
            return round((count / self.processed) * 100.0, 2) if self.processed else 0.0

        all_issues: dict[str, int] = {}
        for field, count in self.missing_field_counts.items():
            all_issues[f"missing: {field}"] = count
        for gap, count in self.hierarchy_gap_counts.items():
            all_issues[gap] = count

        return {
            "total_documents":   self.processed,
            "valid_documents":   self.ok_count,
            "invalid_documents": self.warn_count,
            "division_coverage_pct":   pct(self.has_division_count),
            "chapter_coverage_pct":    pct(self.has_chapter_count),
            "subchapter_coverage_pct": pct(self.has_subchapter_count),
            "article_coverage_pct":    pct(self.has_article_count),
            "issues": all_issues,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Crawler
# ─────────────────────────────────────────────────────────────────────────────

async def process_url(
    crawler,
    config,
    semaphore,
    url: str,
    reg_file,
    chunk_file,
    validation_file,
    coverage_agg: CoverageAggregator,
) -> None:
    async with semaphore:
        try:
            result = await crawler.arun(url=url, config=config)

            if not result.success:
                print(f"[FAIL]  {url}")
                coverage_agg.record_fail()
                validation_file.write(
                    json.dumps(build_skip_record(url, "failed"), ensure_ascii=False) + "\n"
                )
                validation_file.flush()
                return

            raw_markdown = (
                result.markdown.raw_markdown
                if hasattr(result.markdown, "raw_markdown")
                else str(result.markdown or "")
            )

            if len(raw_markdown.strip()) < 100:
                print(f"[SKIP]  {url}")
                coverage_agg.record_skip()
                validation_file.write(
                    json.dumps(build_skip_record(url, "skipped", "content too short"), ensure_ascii=False) + "\n"
                )
                validation_file.flush()
                return

            page_title = (
                result.metadata.get("title")
                if isinstance(result.metadata, dict)
                else None
            )

            record = build_record(url=url, raw_markdown=raw_markdown, page_title=page_title)

            issues = validate_record(record)
            tag    = "[WARN]" if issues else "[OK]  "
            warn   = f"  ⚠ {'; '.join(issues)}" if issues else ""
            print(f"{tag} §{record['section_number'] or 'UNRESOLVED'}  {record['section_title'] or '—'}{warn}")

            coverage = build_coverage_record(record, issues)
            validation_file.write(json.dumps(coverage, ensure_ascii=False) + "\n")
            validation_file.flush()

            coverage_agg.record_page(record, issues)

            reg_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            reg_file.flush()

            for chunk in build_chunks(record):
                chunk_file.write(json.dumps(chunk, ensure_ascii=False) + "\n")
            chunk_file.flush()

        except Exception as exc:
            print(f"[ERROR] {url}  →  {exc}")
            coverage_agg.record_error()
            validation_file.write(
                json.dumps(build_skip_record(url, "error", str(exc)), ensure_ascii=False) + "\n"
            )
            validation_file.flush()


async def main() -> None:
    input_path = Path(INPUT_FILE)
    if not input_path.exists():
        print(f"Error: input file not found: {input_path}")
        return

    with input_path.open(encoding="utf-8") as f:
        urls = [json.loads(line)["url"] for line in f if line.strip()]

    print(f"Loaded {len(urls)} URLs.")

    browser_cfg = BrowserConfig(headless=True)
    crawl_cfg = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        remove_overlay_elements=True,
        exclude_external_links=True,
        exclude_social_media_links=True,
        wait_for="js:() => document.readyState === 'complete'",
        wait_for_timeout=10000,
        excluded_tags=["nav", "footer", "header", "aside", "form"],
        word_count_threshold=50,
        magic=True,
    )

    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
    Path(OUTPUT_FILE).parent.mkdir(parents=True, exist_ok=True)

    coverage_agg = CoverageAggregator()
    coverage_agg.record_total(len(urls))

    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        with (
            open(OUTPUT_FILE, "w", encoding="utf-8") as reg_file,
            open(CHUNKS_FILE, "w", encoding="utf-8") as chunk_file,
            open(VALIDATION_FILE, "w", encoding="utf-8") as validation_file,
            open(SUMMARY_FILE, "w", encoding="utf-8") as summary_file,
        ):
            await asyncio.gather(*[
                process_url(
                    crawler,
                    crawl_cfg,
                    semaphore,
                    url,
                    reg_file,
                    chunk_file,
                    validation_file,
                    coverage_agg,
                )
                for url in urls
            ])

            # Append crawl-wide aggregate summary as the final line of coverage.jsonl
            validation_file.write(
                json.dumps(coverage_agg.build_summary(), ensure_ascii=False) + "\n"
            )
            validation_file.flush()

            # Write compact summary stats to summary.jsonl
            summary_file.write(
                json.dumps(coverage_agg.build_summary_stats(), ensure_ascii=False) + "\n"
            )
            summary_file.flush()

    print(
        f"\nDone.\n"
        f"  Regulations : {OUTPUT_FILE}\n"
        f"  Chunks      : {CHUNKS_FILE}\n"
        f"  Coverage    : {VALIDATION_FILE}\n"
        f"  Summary     : {SUMMARY_FILE}\n"
        f"  Processed={coverage_agg.processed}  "
        f"Failed={coverage_agg.failed}  "
        f"Skipped={coverage_agg.skipped}  "
        f"Errors={coverage_agg.errors}"
    )


if __name__ == "__main__":
    asyncio.run(main())