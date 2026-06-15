import asyncio
import json
import re
from pathlib import Path

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from normalize import normalize_url
SEEDS = [
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
_NUMERIC_SECTION = re.compile(
    r"/t8/\d[\w.]*\.html?$", re.IGNORECASE
)
_SUBCHAPTER = re.compile(
    r"/t[8i]tle?8?/(ch|sub|v)\w*\.html?$"  # ch1a2, sub3, etc.
    r"|/t8/(ch|sub|v)\w*\.html?$",
    re.IGNORECASE,
)
_INDEX = re.compile(
    r"/t8/index/", re.IGNORECASE
)
_REJECT = re.compile(
    r"\.(pdf|docx?|xls\w*|zip|doc)$"
    r"|samples/search/"
    r"|#",
    re.IGNORECASE,
)


def is_dir_t8(url: str) -> bool:
    u = url.lower()
    return "dir.ca.gov" in u and ("/t8/" in u or "/title8/" in u)


def is_numeric_section(url: str) -> bool:
    return bool(_NUMERIC_SECTION.search(url))


def should_crawl(url: str) -> bool:
    if _REJECT.search(url):
        return False
    return _SUBCHAPTER.search(url) is not None or _INDEX.search(url) is not None

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

async def discover():
    browser_cfg = BrowserConfig(headless=True, java_script_enabled=False)
    run_cfg = CrawlerRunConfig(
        wait_until="domcontentloaded",
        exclude_external_links=True,
    )

    seen: set[str] = set()
    collected: set[str] = set()
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

                    if is_numeric_section(raw):
                        collected.add(raw)

                    if should_crawl(raw) and raw not in seen:
                        queue.add(raw)

    print(f"\n{len(collected)} numeric section URLs collected")

    Path(OUTPUT).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        for url in sorted(collected):
            f.write(json.dumps({"url": url}) + "\n")

    print(f"Saved to {OUTPUT}")


if __name__ == "__main__":
    asyncio.run(discover())