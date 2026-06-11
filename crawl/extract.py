
import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from crawl4ai import AsyncWebCrawler, CacheMode, CrawlerRunConfig
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy
from crawl4ai.deep_crawling import BestFirstCrawlingStrategy
from crawl4ai.deep_crawling.filters import ContentTypeFilter, DomainFilter, FilterChain, URLPatternFilter
from crawl4ai.deep_crawling.scorers import KeywordRelevanceScorer

# File Paths
INPUT_SEEDS = "../data/urls.jsonl"  # Your curated, high-signal seed file
OUTPUT_EXTRACT = "../data/extract.jsonl"
LOG_FILE = "../data/log.jsonl"
COVERAGE_FILE = "../data/coverage.json"

# Threshold Constraints
MIN_CONTENT_LENGTH = 150
MAX_DEPTH = 3             # Allows tracing from hubs down to rule sections safely
MAX_PAGES_LIMIT = 250     # Structural boundary guardrail to optimize processing limits

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

def load_seed_urls() -> list[str]:
    seeds = []
    if not Path(INPUT_SEEDS).exists():
        logging.error(f"Seed file missing at: {INPUT_SEEDS}")
        return seeds
    with open(INPUT_SEEDS, "r", encoding="utf8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                seeds.append(json.loads(line)["url"])
            except Exception:
                continue
    return seeds

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

def write_log(url: str, status: str, extra: dict = None):
    payload = {"url": url, "status": status, "timestamp": datetime.now(timezone.utc).isoformat()}
    if extra:
        payload.update(extra)
    with open(LOG_FILE, "a", encoding="utf8") as f:
        f.write(json.dumps(payload) + "\n")

async def execute_integrated_deep_crawl():
    print("\n🚀 LAUNCHING INTEGRATED BEST-FIRST SEED TRAVERSAL 🚀")
    
    # 1. Load your curated seeds and checkpoint tracking logs
    seed_urls = load_seed_urls()
    processed_urls = load_processed_urls()
    
    if not seed_urls:
        print("No input seeds detected. Halting execution loop.")
        return
        
    logging.info(f"Loaded {len(seed_urls)} verified start points from urls.jsonl.")
    logging.info(f"Checkpoint active: {len(processed_urls)} entries already indexed.")

    # 2. Configure Whitelist Path Filters
    filter_chain = FilterChain([
        DomainFilter(
            allowed_domains=["https://dir.ca.gov/sitemap/sitemap.html"],
            blocked_domains=["old.dir.ca.gov"]
        ),
        # Restrict graph exploration exclusively to regulatory tracks
        URLPatternFilter(patterns=["*/t8/*", "*/dlse/*", "*/dosh/*", "*regulations*", "*safety*"]),
        ContentTypeFilter(allowed_types=["text/html"])
    ])

    # 3. Configure Path Priority Scorers
    compliance_scorer = KeywordRelevanceScorer(
        keywords=["t8", "section", "order", "safety", "wages", "hours", "heat", "illness", "employer"],
        weight=1.0
    )

    # 4. Bind Settings into the Master Run Parameters object
    config = CrawlerRunConfig(
        deep_crawl_strategy=BestFirstCrawlingStrategy(
            max_depth=MAX_DEPTH,
            include_external=False,
            filter_chain=filter_chain,
            url_scorer=compliance_scorer,
            max_pages=MAX_PAGES_LIMIT,
            score_threshold=0.2,  # Drops irrelevant links automatically
            extra_seeds=seed_urls  # Ingests remaining list items into priority evaluation loops natively
        ),
        scraping_strategy=LXMLWebScrapingStrategy(),
        
        # Bypasses infinite network tracking scripts by monitoring structural parsing states
        wait_for="js:() => document.readyState === 'complete'",
        wait_for_timeout=10000, # 10-second circuit breaker per page
        
        excluded_tags=["nav", "footer", "header", "aside", "form", ".sidebar", "#sidebar"],
        word_count_threshold=20,
        remove_overlay_elements=True,
        exclude_external_links=True,
        delay_before_return_html=1.5,
        magic=True,
        stream=True  # Asynchronous stream mode writes data instantly to disk
    )

    success_count = 0
    failure_count = 0
    start_time = time.perf_counter()

    Path(OUTPUT_EXTRACT).parent.mkdir(parents=True, exist_ok=True)

    async with AsyncWebCrawler() as crawler:
        # Pass the first element as the positional url string requirement. 
        # Strategy pipeline fetches remaining extra_seeds automatically.
        crawl_stream = await crawler.arun(url=seed_urls[0], config=config)
        
        async for result in crawl_stream:
            url = result.url
            
            # Idempotency safety filter check
            if url in processed_urls:
                continue
                
            if not result.success:
                failure_count += 1
                write_log(url, "failed", {"error": result.error_message or "Execution block"})
                logging.error(f"❌ Target Node Failed: {url}")
                continue

            # Process Markdown content chunks
            markdown = ""
            if result.markdown:
                markdown = result.markdown.fit_markdown or result.markdown.raw_markdown or ""
                if len(markdown.strip()) < MIN_CONTENT_LENGTH:
                    markdown = result.markdown.raw_markdown or ""

            # Verify extraction density standards
            if len(markdown.strip()) >= MIN_CONTENT_LENGTH:
                record = {
                    "title_number": "8" if "title8" in url.lower() else None,
                    "title_name": "Title 8. Industrial Relations" if "title8" in url.lower() else None,
                    "section_heading": result.metadata.get("title", "Regulatory Rule Node"),
                    "source_url": url,
                    "content_markdown": markdown,
                    "retrieved_at": datetime.now(timezone.utc).isoformat()
                }
                
                with open(OUTPUT_EXTRACT, "a", encoding="utf8") as out:
                    out.write(json.dumps(record) + "\n")
                
                write_log(url, "success")
                processed_urls.add(url)
                success_count += 1
                
                score = result.metadata.get("score", 0.0)
                depth = result.metadata.get("depth", 0)
                logging.info(f"✨ [Depth {depth}][Score {score:.2f}] INDEXED: {url}")
            else:
                write_log(url, "skipped", {"reason": "low_content"})
                logging.warning(f"⚠️ Skipped (Low Content Signal): {url}")

    # Log operational telemetry metrics
    duration = time.perf_counter() - start_time
    coverage = {
        "duration_seconds": round(duration, 2),
        "successful_extractions": success_count,
        "failed_extractions": failure_count,
        "total_unique_indexed": len(processed_urls)
    }
    
    with open(COVERAGE_FILE, "w", encoding="utf8") as f:
        json.dump(coverage, f, indent=2)
        
    print(f"\n🎉 DATA INGESTION PIPELINE RUN RE-EXECUTED IN {duration:.2f} SECONDS 🎉")

if __name__ == "__main__":
    asyncio.run(execute_integrated_deep_crawl())