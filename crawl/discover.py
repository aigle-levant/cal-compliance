import asyncio
import json
import re
from pathlib import Path

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from normalize import normalize_url

# --- seeds ---------------------------------------------------------------

SEEDS = [
    # search portals (may link to numeric sections directly)
    "https://dir.ca.gov/samples/search/query.htm",
    "https://dir.ca.gov/samples/search/querydwc.htm",
    "https://dir.ca.gov/samples/search/querydlse.htm",
    "https://dir.ca.gov/samples/search/querysip.htm",
    "https://dir.ca.gov/samples/search/querydlsr.htm",
    "https://dir.ca.gov/samples/search/querycac.htm",
    "https://dir.ca.gov/samples/search/queryod.htm",
]

OUTPUT = "../data/discovery.jsonl"
MAX_CONCURRENCY = 10

# --- URL classifiers -----------------------------------------------------

# Numeric section pages: /t8/1234.html or /t8/1234_5.html etc.
# Must be digits (with optional underscores/dots) — NOT alpha-leading like ch1a2
_NUMERIC_SECTION = re.compile(
    r"/t8/\d[\w.]*\.html?$", re.IGNORECASE
)

# Subchapter / structural pages we should crawl but NOT collect
_SUBCHAPTER = re.compile(
    r"/t[8i]tle?8?/(ch|sub|v)\w*\.html?$"  # ch1a2, sub3, etc.
    r"|/t8/(ch|sub|v)\w*\.html?$",
    re.IGNORECASE,
)

# Index / TOC pages
_INDEX = re.compile(
    r"/t8/index/", re.IGNORECASE
)

# Hard-reject: PDFs, .doc, .docx, query forms, anchor-only fragments
_REJECT = re.compile(
    r"\.(pdf|docx?|xls\w*|zip|doc)$"
    r"|samples/search/"
    r"|#",
    re.IGNORECASE,
)


def is_dir_t8(url: str) -> bool:
    """Is this URL on dir.ca.gov and under /t8/ or /title8/ ?"""
    u = url.lower()
    return "dir.ca.gov" in u and ("/t8/" in u or "/title8/" in u)


def is_numeric_section(url: str) -> bool:
    return bool(_NUMERIC_SECTION.search(url))


def should_crawl(url: str) -> bool:
    """Should we follow this URL to find more links?"""
    if _REJECT.search(url):
        return False
    return _SUBCHAPTER.search(url) is not None or _INDEX.search(url) is not None


# --- crawler helpers -----------------------------------------------------

async def fetch_links(crawler, url: str, cfg: CrawlerRunConfig) -> list[str]:
    try:
        result = await crawler.arun(url, config=cfg)
        if not result.success:
            print(f"[FAIL] {url}")
            return []
        return [
            normalize_url(link["href"])
            for link in result.links.get("internal", [])
        ]
    except Exception as e:
        print(f"[ERR] {url}: {e}")
        return []


# --- main ----------------------------------------------------------------

async def discover():
    browser_cfg = BrowserConfig(headless=True, java_script_enabled=False)
    run_cfg = CrawlerRunConfig(
        wait_until="domcontentloaded",
        exclude_external_links=True,
    )

    seen: set[str] = set()           # URLs we've already fetched
    collected: set[str] = set()      # numeric section URLs we want to keep
    queue: set[str] = {normalize_url(u) for u in SEEDS}

    sem = asyncio.Semaphore(MAX_CONCURRENCY)

    async with AsyncWebCrawler(config=browser_cfg) as crawler:

        while queue:
            batch = list(queue)
            queue.clear()

            print(f"\nCrawling {len(batch)} pages  (seen={len(seen)}, collected={len(collected)})")

            async def worker(url: str) -> list[str]:
                async with sem:
                    if url in seen:
                        return []
                    seen.add(url)
                    return await fetch_links(crawler, url, run_cfg)

            results = await asyncio.gather(*[worker(u) for u in batch])

            for links in results:
                for raw in links:
                    if not is_dir_t8(raw):
                        continue
                    if _REJECT.search(raw):
                        continue

                    # Always collect numeric section pages
                    if is_numeric_section(raw):
                        collected.add(raw)

                    # Crawl subchapter / index pages to find more numeric sections
                    if should_crawl(raw) and raw not in seen:
                        queue.add(raw)

    print(f"\nDone — {len(collected)} numeric section URLs collected")

    Path(OUTPUT).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        for url in sorted(collected):
            f.write(json.dumps({"url": url}) + "\n")

    print(f"Saved → {OUTPUT}")


if __name__ == "__main__":
    asyncio.run(discover())