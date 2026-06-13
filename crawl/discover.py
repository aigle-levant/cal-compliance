import asyncio
import json
from pathlib import Path

from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CrawlerRunConfig,
)

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


def is_dir_t8(url: str) -> bool:
    url = url.lower()
    return (
        "dir.ca.gov" in url
        and (
            "/t8/" in url
            or "/title8/" in url
        )
    )


async def fetch_links(crawler, url, cfg):
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
    browser_cfg = BrowserConfig(
        headless=True,
        java_script_enabled=False,
    )

    run_cfg = CrawlerRunConfig(
        wait_until="domcontentloaded",
        exclude_external_links=True,
    )

    seen = set()
    discovered = set()

    queue = {
        normalize_url(url)
        for url in SEEDS
    }

    sem = asyncio.Semaphore(MAX_CONCURRENCY)

    async with AsyncWebCrawler(config=browser_cfg) as crawler:

        while queue:

            batch = list(queue)
            queue.clear()

            print(
                f"\nProcessing {len(batch)} URLs "
                f"(seen={len(seen)})"
            )

            async def worker(url):

                async with sem:

                    if url in seen:
                        return []

                    seen.add(url)

                    links = await fetch_links(
                        crawler,
                        url,
                        run_cfg,
                    )

                    return links

            results = await asyncio.gather(
                *[worker(url) for url in batch]
            )

            for links in results:

                for link in links:

                    if not is_dir_t8(link):
                        continue

                    discovered.add(link)

                    if link not in seen:
                        queue.add(link)

    print(f"\nDiscovered {len(discovered)} URLs")

    Path(OUTPUT).parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(OUTPUT, "w", encoding="utf-8") as f:

        for url in sorted(discovered):

            f.write(
                json.dumps({"url": url})
                + "\n"
            )

    print(f"Saved to {OUTPUT}")


if __name__ == "__main__":
    asyncio.run(discover())