import asyncio
import json
import re
from pathlib import Path
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

# ── Title 8 entry point (single source of truth) ─────────────────
T8_TOC = "https://dir.ca.gov/samples/search/query.htm"

# ── Other TOC seeds (non-T8) ──────────────────────────────────────
OTHER_SEEDS = [
    "https://dir.ca.gov/samples/search/querydwc.htm",   # Workers' Comp
    "https://dir.ca.gov/samples/search/querydlse.htm",  # Labor Standards
    "https://dir.ca.gov/samples/search/querysip.htm",   # Self Insurance
    "https://dir.ca.gov/samples/search/querydlsr.htm",  # Labor Statistics
    "https://dir.ca.gov/samples/search/querycac.htm",   # Apprenticeship
    "https://dir.ca.gov/samples/search/queryod.htm",    # Office of Director
]

# ── Leginfo Labor Code entry point ───────────────────────────────
LEGINFO_LAB_TOC = "https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=LAB"

OUTPUT_FILE = "../data/urls.jsonl"

# ─────────────────────────────────────────────────────────────────
# URL classifiers — T8 hierarchy has THREE levels:
#
#   Level 0  query.htm          (TOC seed)
#   Level 1  sub1.html          subchapter  →  is_t8_subchapter()
#            ch3_2sb1.html
#            T8/ch7sb1.html
#   Level 2  sb1a1.html         article/group  →  is_t8_article()
#            sb7g1.html
#            sb7intro.html
#            ch3_2sb1a1.html
#   Level 3  450.html           leaf section  →  is_t8_section()
#            3203.html
# ─────────────────────────────────────────────────────────────────

_T8_HOST = "dir.ca.gov"

def _is_t8_url(url: str) -> bool:
    return _T8_HOST in url and re.search(r"/[Tt](?:itle)?8/", url) is not None

def is_t8_section(url: str) -> bool:
    """Leaf section — purely numeric filename (with optional letter suffix)."""
    if not _is_t8_url(url):
        return False
    filename = url.rstrip("/").split("/")[-1]
    return bool(re.match(r"^\d+[\w.-]*\.html?$", filename, re.IGNORECASE))

def is_t8_article(url: str) -> bool:
    """
    Article / group index — non-numeric named pages that are NOT subchapters.
    Examples: sb1a1.html, sb7g1.html, sb7intro.html, ch3_2sb1a1.html
    Pattern: starts with 'sb' (but NOT the pure sub\\d form) OR
             looks like ch…sb…a… / ch…sb…g…
    """
    if not _is_t8_url(url):
        return False
    filename = url.rstrip("/").split("/")[-1].lower()
    # must be non-numeric
    if re.match(r"^\d+", filename):
        return False
    # exclude subchapter pages (sub\d+, ch\w+sb\d+.html without a/g suffix)
    if is_t8_subchapter(url):
        return False
    # article/group filenames: sb<n>a<n>, sb<n>g<n>, sb<n>intro, ch…sb…a…, ch…sb…g…
    if re.match(r"^sb\d+[ag]\w+\.html?$", filename):   # sb1a1, sb7g1
        return True
    if re.match(r"^sb\d+intro\.html?$", filename):      # sb7intro
        return True
    if re.match(r"^ch\w+sb\w+[ag]\w+\.html?$", filename):  # ch3_2sb1a1
        return True
    return False

def is_t8_subchapter(url: str) -> bool:
    """
    Subchapter index pages — one level below the TOC.
    Examples: sub1.html, sub7.html, ch3_2sb1.html, ch3_5sb1.html, ch7sb1.html
    """
    if not _is_t8_url(url):
        return False
    filename = url.rstrip("/").split("/")[-1].lower()
    if re.match(r"^\d+", filename):
        return False
    # sub\d+ variants
    if re.match(r"^sub\d+[\w_.-]*\.html?$", filename):
        return True
    # ch…sb… WITHOUT a trailing a/g group marker  (ch3_2sb1.html but not ch3_2sb1a1.html)
    if re.match(r"^ch\w+sb\d+[\w_.-]*\.html?$", filename):
        # exclude if it has an article/group suffix after the sb number
        if not re.search(r"sb\d+[ag]", filename):
            return True
    return False

def is_labor_section(url: str) -> bool:
    """Leaf-level Labor Code section pages."""
    u = url.lower()
    return (
        "leginfo.legislature.ca.gov" in u
        and "codes_displaytext.xhtml" in u
        and "lawcode=lab" in u
    )

def is_labor_toc(url: str) -> bool:
    """Intermediate Labor Code TOC/index pages."""
    u = url.lower()
    if "leginfo.legislature.ca.gov" not in u:
        return False
    return any(x in u for x in [
        "codedisplayexpand.xhtml",
        "codestocselected.xhtml",
        "codes_displayexpandedbranch.xhtml",
    ])

# ── Crawler helper ────────────────────────────────────────────────

async def crawl_page(crawler, url: str, run_cfg) -> list[str]:
    try:
        result = await crawler.arun(url, config=run_cfg)
        if not result.success:
            print(f"  [FAIL] {url}: {result.error_message}")
            return []
        return [l["href"] for l in result.links.get("internal", [])]
    except Exception as e:
        print(f"  [ERR]  {url}: {e}")
        return []

# ── Main ──────────────────────────────────────────────────────────

async def discover():
    browser_cfg = BrowserConfig(headless=True, java_script_enabled=False)
    run_cfg = CrawlerRunConfig(
        wait_until="domcontentloaded",
        exclude_external_links=True,
    )

    t8_section_urls:    set[str] = set()
    t8_article_urls:    set[str] = set()
    t8_subchapter_urls: set[str] = set()
    labor_section_urls: set[str] = set()
    sem = asyncio.Semaphore(5)

    async with AsyncWebCrawler(config=browser_cfg) as crawler:

        # ── Stage 1: T8 TOC → collect subchapters ────────────────
        print("=== Stage 1: T8 TOC ===")
        links = await crawl_page(crawler, T8_TOC, run_cfg)
        for l in links:
            if is_t8_subchapter(l):
                t8_subchapter_urls.add(l)
            elif is_t8_article(l):
                t8_article_urls.add(l)
            elif is_t8_section(l):
                t8_section_urls.add(l)
        print(f"  +{len(t8_subchapter_urls)} subchapters, "
              f"+{len(t8_article_urls)} articles, "
              f"+{len(t8_section_urls)} sections")

        # Also hit the other non-T8 seeds (workers comp etc.) —
        # they follow the same T8 URL structure if they link into Title 8
        for seed in OTHER_SEEDS:
            async with sem:
                links = await crawl_page(crawler, seed, run_cfg)
                for l in links:
                    if is_t8_subchapter(l):   t8_subchapter_urls.add(l)
                    elif is_t8_article(l):    t8_article_urls.add(l)
                    elif is_t8_section(l):    t8_section_urls.add(l)

        print(f"  After other seeds: {len(t8_subchapter_urls)} subchapters total")

        # ── Stage 2: Subchapters → collect articles (+ any direct sections) ──
        print(f"\n=== Stage 2: {len(t8_subchapter_urls)} subchapter pages ===")

        async def crawl_subchapter(url):
            async with sem:
                links = await crawl_page(crawler, url, run_cfg)
                new_art = [l for l in links if is_t8_article(l)]
                new_sec = [l for l in links if is_t8_section(l)]
                t8_article_urls.update(new_art)
                t8_section_urls.update(new_sec)
                print(f"  {url.split('/')[-1]:30s} → "
                      f"+{len(new_art)} articles, +{len(new_sec)} sections")

        await asyncio.gather(*[crawl_subchapter(u) for u in t8_subchapter_urls])
        print(f"  Articles to crawl: {len(t8_article_urls)}")

        # ── Stage 3: Articles/groups → collect leaf sections ─────
        print(f"\n=== Stage 3: {len(t8_article_urls)} article/group pages ===")

        async def crawl_article(url):
            async with sem:
                links = await crawl_page(crawler, url, run_cfg)
                new_sec = [l for l in links if is_t8_section(l)]
                t8_section_urls.update(new_sec)
                print(f"  {url.split('/')[-1]:30s} → +{len(new_sec)} sections")

        await asyncio.gather(*[crawl_article(u) for u in t8_article_urls])
        print(f"  T8 sections total: {len(t8_section_urls)}")

        # ── Stage 4: Leginfo Labor Code (BFS over TOC, then harvest) ──
        print("\n=== Stage 4: Leginfo Labor Code ===")

        labor_toc_urls: set[str] = set()
        frontier: set[str] = {LEGINFO_LAB_TOC}
        visited_toc: set[str] = set()

        for hop in range(2):
            async def crawl_lab_toc(url):
                async with sem:
                    links = await crawl_page(crawler, url, run_cfg)
                    return (
                        [l for l in links if is_labor_toc(l) and l not in visited_toc],
                        [l for l in links if is_labor_section(l)],
                    )

            results = await asyncio.gather(*[crawl_lab_toc(u) for u in frontier])
            next_frontier: set[str] = set()
            for url, (new_tocs, new_secs) in zip(frontier, results):
                visited_toc.add(url)
                labor_toc_urls.update(new_tocs)
                labor_section_urls.update(new_secs)
                next_frontier.update(t for t in new_tocs if t not in visited_toc)
                print(f"  [hop{hop}] …{url.split('?')[-1][:55]} "
                      f"→ +{len(new_tocs)} tocs, +{len(new_secs)} secs")
            frontier = next_frontier
            if not frontier:
                break

        print(f"  Labor TOC indexes: {len(labor_toc_urls)}")

        async def crawl_lab_index(url):
            async with sem:
                links = await crawl_page(crawler, url, run_cfg)
                new_secs = [l for l in links if is_labor_section(l)]
                labor_section_urls.update(new_secs)
                print(f"  [idx] …{url.split('?')[-1][:55]} → +{len(new_secs)} secs")

        await asyncio.gather(*[crawl_lab_index(u) for u in labor_toc_urls])
        print(f"  Labor Code sections total: {len(labor_section_urls)}")

    # ── Write output ──────────────────────────────────────────────
    all_urls = t8_section_urls | labor_section_urls
    Path(OUTPUT_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        for url in sorted(all_urls):
            f.write(json.dumps({"url": url, "depth": 1}) + "\n")

    print(f"\n{'='*50}")
    print(f"T8 sections:         {len(t8_section_urls)}")
    print(f"Labor Code sections: {len(labor_section_urls)}")
    print(f"Total:               {len(all_urls)}")
    print(f"Saved to:            {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(discover())