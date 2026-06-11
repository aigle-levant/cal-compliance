import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CacheMode,
    CrawlerRunConfig,
)

INPUT = "../data/urls.jsonl"
OUTPUT = "../data/extract.jsonl"
LOG_FILE = "../data/log.jsonl"
COVERAGE_FILE = "../data/coverage.json"

MAX_CONCURRENCY = 3
MAX_RETRIES = 3
MIN_CONTENT_LENGTH = 100

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("../data/crawler.log"),
        logging.StreamHandler()
    ]
)

def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    return (
        f"{parsed.scheme}://"
        f"{parsed.netloc}"
        f"{path}"
    )

def load_processed_urls() -> set[str]:
    processed = set()

    if not Path(LOG_FILE).exists():
        return processed

    with open(LOG_FILE, "r", encoding="utf8") as f:
        for line in f:
            if not line.strip():
                continue

            try:
                record = json.loads(line)
                if record.get("status") == "success":
                    processed.add(record["url"])
            except Exception:
                pass

    return processed

def write_log(record: dict):
    with open(LOG_FILE, "a", encoding="utf8") as f:
        f.write(json.dumps(record) + "\n")

def parse_regulatory_metadata(title: str, url: str) -> dict:
    return {
        "title_number": None,
        "title_name": None,
        "division": None,
        "chapter": None,
        "subchapter": None,
        "section_number": None,
        "section_heading": title,
        "breadcrumb_path": None
    }

async def crawl_url(crawler, run_config, semaphore, url):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with semaphore:
                result = await crawler.arun(
                    url=url,
                    config=run_config
                )

            if not result.success:
                raise Exception(
                    result.error_message or "Unknown crawl failure"
                )

            return result

        except Exception as e:
            if attempt == MAX_RETRIES:
                raise e

        delay = 2 ** attempt
        logging.warning(
            f"Retry {attempt}/{MAX_RETRIES} for {url} after {delay}s"
        )
        await asyncio.sleep(delay)

async def main():
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
    success_count = 0
    failure_count = 0

    processed_urls = load_processed_urls()
    logging.info(
        f"Checkpoint loaded. {len(processed_urls)} URLs already processed."
    )

    if not Path(INPUT).exists():
        logging.error(f"Input file not found: {INPUT}")
        return

    with open(INPUT, "r", encoding="utf8") as f:
        discovered_urls = []
        for line in f:
            if not line.strip():
                continue
            try:
                url = normalize_url(json.loads(line)["url"])
                discovered_urls.append(url)
            except Exception:
                continue

    discovered_urls = list(dict.fromkeys(discovered_urls))
    urls_to_crawl = [
        url for url in discovered_urls if url not in processed_urls
    ]

    logging.info(
        f"Discovered={len(discovered_urls)} Remaining={len(urls_to_crawl)}"
    )

    browser_config = BrowserConfig(headless=True, verbose=False)
    run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)

    async with AsyncWebCrawler(config=browser_config) as crawler:
        async def worker(url):
            nonlocal success_count
            nonlocal failure_count

            try:
                result = await crawl_url(
                    crawler,
                    run_config,
                    semaphore,
                    url
                )

                metadata = result.metadata or {}
                markdown = ""

                if result.markdown:
                    fit_markdown = getattr(result.markdown, "fit_markdown", None)
                    markdown = fit_markdown if fit_markdown else result.markdown.raw_markdown

                # Debug a single page only
                DEBUG = False
                if DEBUG:
                    print("\n" + "=" * 80)
                    print(f"TITLE: {metadata.get('title', 'NO TITLE')}")
                    print("=" * 80)
                    print("\nRAW MARKDOWN:\n")
                    print(result.markdown.raw_markdown[:1000])

                    fit_markdown = getattr(result.markdown, "fit_markdown", None)
                    if fit_markdown:
                        print("\nFIT MARKDOWN:\n")
                        print(fit_markdown[:1000])
                    print("\n" + "=" * 80)

                if len(markdown.strip()) < MIN_CONTENT_LENGTH:
                    write_log({
                        "url": url,
                        "status": "skipped",
                        "reason": "low_content"
                    })
                    logging.warning(f"Skipped: {url}")
                    return

                parsed = parse_regulatory_metadata(
                    metadata.get("title", ""),
                    url
                )

                record = {
                    "title_number": parsed["title_number"],
                    "title_name": parsed["title_name"],
                    "division": parsed["division"],
                    "chapter": parsed["chapter"],
                    "subchapter": parsed["subchapter"],
                    "section_number": parsed["section_number"],
                    "section_heading": parsed["section_heading"],
                    "citation": (
                        f"{parsed['title_number']} CCR § {parsed['section_number']}"
                        if parsed["title_number"] and parsed["section_number"]
                        else None
                    ),
                    "breadcrumb_path": parsed["breadcrumb_path"],
                    "source_url": url,
                    "content_markdown": markdown,
                    "retrieved_at": datetime.now(timezone.utc).isoformat()
                }

                with open(OUTPUT, "a", encoding="utf8") as out:
                    out.write(json.dumps(record) + "\n")

                write_log({
                    "url": url,
                    "status": "success"
                })
                success_count += 1
                logging.info(f"SUCCESS: {metadata.get('title', '')}")

            except Exception as e:
                failure_count += 1
                write_log({
                    "url": url,
                    "status": "failed",
                    "error": str(e)
                })
                logging.error(f"FAILED: {url}")
                logging.error(str(e))

        tasks = [worker(url) for url in urls_to_crawl]
        await asyncio.gather(*tasks)

    coverage = {
        "total_discovered": len(discovered_urls),
        "already_processed": len(processed_urls),
        "attempted": len(urls_to_crawl),
        "successful": success_count,
        "failed": failure_count
    }

    with open(COVERAGE_FILE, "w", encoding="utf8") as f:
        json.dump(coverage, f, indent=2)

    logging.info(f"Coverage report saved to {COVERAGE_FILE}")


if __name__ == "__main__":
    asyncio.run(main())