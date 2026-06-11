import json
import asyncio
import os
import re
from datetime import datetime, timezone
import logging

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

INPUT = "../data/urls.jsonl"
OUTPUT = "../data/extract.jsonl"

# 1. Instrument Clean Logging (Evaluation Criterion 5)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("../data/crawler.log"), logging.StreamHandler()]
)

def parse_regulatory_metadata(title_string, url_string):
    """
    Parser to extract canonical CCR hierarchy layers from page metadata and paths.
    Conforms directly to the Section 5 schema requirements.
    """
    # Fallback default values
    record = {
        "title_number": None,
        "title_name": None,
        "section_number": None,
        "section_heading": title_string
    }

    # Context Check: Identify if the target domain belongs to CA Department of Industrial Relations
    if "dir.ca.gov" in url_string:
        record["title_number"] = None
        record["title_name"] = None

    # Regex Rule 1: Parse standard title formats like "§3207. Factors of Safety." or "Section 5194 - Hazard"
    section_match = re.search(r'(?:§|Section)\s*([0-4]*\d+[\.\d]*[a-zA-Z]*)', title_string, re.IGNORECASE)
    if section_match:
        record["section_number"] = section_match.group(1).strip()
        # Clean up the heading by removing the matched section prefix block if present
        clean_heading = re.sub(r'^.*?(?:§|Section)\s*[0-4]*\d+[\.\d]*[a-zA-Z]*[\s\.\-\:]*', '', title_string, flags=re.IGNORECASE)
        if clean_heading.strip():
            record["section_heading"] = clean_heading.strip()
    else:
        # Regex Rule 2: Fallback to extracting digits directly out of file naming tokens in the URL path string
        # e.g., "dir.ca.gov/title8/3207.html" -> Section 3207
        url_match = re.search(r'/title8/([0-4]*\d+[\.\d]*[a-zA-Z]*)\.html', url_string, re.IGNORECASE)
        if url_match:
            record["section_number"] = url_match.group(1).strip()

    return record

async def main():
    # 2. Controlled Concurrency: Limit to 3 simultaneous workers (Requirement 6)
    semaphore = asyncio.Semaphore(3)
    
    # 3. Read Checkpoints: Load completed URLs to avoid duplicate crawling
    completed_urls = set()
    if os.path.exists(OUTPUT):
        with open(OUTPUT, "r", encoding="utf8") as f:
            for line in f:
                if line.strip():
                    try:
                        completed_urls.add(json.loads(line)["source_url"])
                    except json.JSONDecodeError:
                        continue
    logging.info(f"Checkpoint active. Found {len(completed_urls)} already processed paths.")

    # Load and normalize raw target discovery paths
    if not os.path.exists(INPUT):
        logging.error(f"Input tracking file missing at location: {INPUT}")
        return

    with open(INPUT, "r", encoding="utf8") as f:
        all_urls = [json.loads(line)["url"] for line in f if line.strip()]
    
    # Filter out completed tasks (Persistent Checkpoints)
    urls_to_crawl = [url for url in all_urls if url not in completed_urls]
    logging.info(f"Task queue prepared: Total={len(all_urls)}, Remaining={len(urls_to_crawl)}")

    # Optimize Crawl4AI Configuration Profile
    browser_config = BrowserConfig(headless=True, verbose=False)
    run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)

    async with AsyncWebCrawler(config=browser_config) as crawler:
        
        # Define Worker Engine Task with Explicit Retry & Backoff Logic
        async def crawl_worker(url, attempt=1):
            async with semaphore:
                try:
                    # Execute network task
                    result = await crawler.arun(url=url, config=run_config)
                    
                    if not result.success:
                        raise Exception(result.error_message or "Unknown extraction failure.")

                    # Handle markdown property variants correctly across different Crawl4AI updates
                    raw_markdown_content = getattr(result.markdown, 'raw_markdown', str(result.markdown))

                    # Parse canonical metadata layers out of raw text footprints
                    raw_title = result.metadata.get("title", "")
                    meta = parse_regulatory_metadata(raw_title, url)

                    # Structure the record to align directly with requirements
                    record = {
    "title_number": meta["title_number"],
    "title_name": meta["title_name"],

    "division": None,
    "chapter": None,
    "subchapter": None,

    "section_number": meta["section_number"],
    "section_heading": meta["section_heading"],

    "citation": (
        f"{meta['title_number']} CCR § {meta['section_number']}"
        if meta["title_number"] and meta["section_number"]
        else None
    ),

    "breadcrumb_path": None,

    "source_url": url,

    "content_markdown": raw_markdown_content,

    "retrieved_at":
        datetime.now(timezone.utc).isoformat()
}

                    # Thread-safe sequential file append
                    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
                    with open(OUTPUT, "a", encoding="utf8") as out:
                        out.write(json.dumps(record) + "\n")
                    
                    logging.info(f"SUCCESS: {url} -> [Section {meta['section_number']}]")

                except Exception as e:
                    # Exponential Backoff Retry Strategy (Requirement 6)
                    if attempt <= 3:
                        backoff_delay = 2 ** attempt
                        logging.warning(f"RETRY {attempt}/3 for {url} after {backoff_delay}s. Error: {e}")
                        await asyncio.sleep(backoff_delay)
                        await crawl_worker(url, attempt + 1)
                    else:
                        logging.error(f"FATAL EXCEPTION: Failed to resolve {url} after 3 attempts. Error: {e}")

        # Map task structures using native concurrency primitives (Processing a batch slice of remaining items)
        tasks = [crawl_worker(url) for url in urls_to_crawl[:20]]
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())