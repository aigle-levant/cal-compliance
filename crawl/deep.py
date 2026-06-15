import asyncio
import json
import re
from pathlib import Path
from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CrawlerRunConfig,
)

INPUT = "../data/discovery.jsonl"
LEAF_OUT = "../data/leaf_urls.jsonl"
TOC_OUT = "../data/toc_urls.jsonl"
SEM_LIMIT = 10

def load_urls():
    with open(INPUT, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)["url"]

def classify(markdown: str) -> str:
    md = markdown.lower()
    has_section_header = (
        "§" in markdown
        or re.search(r"§\s*\d", markdown)
        or re.search(r"\b\d+\.\d+\b", markdown)
    )
    toc_patterns = [
        "table of contents",
        "subarticle",
        "article ",
        "subchapter",
        "go back to",
    ]
    toc_hits = sum(
        1 for p in toc_patterns
        if p in md
    )
    word_count = len(markdown.split())
    if has_section_header and word_count > 150:
        return "leaf"
    if toc_hits >= 2 and word_count < 500:
        return "toc"
    return "unknown"

async def fetch(crawler, url, cfg):
    try:
        result = await crawler.arun(url, config=cfg)
        if not result.success:
            return url, "failed"
        md = result.markdown or ""
        return url, classify(md)
    except Exception:
        return url, "failed"

async def main():
    urls = list(load_urls())
    browser_cfg = BrowserConfig(
        headless=True,
        java_script_enabled=False,
    )
    run_cfg = CrawlerRunConfig(
        wait_until="domcontentloaded",
    )
    leafs = []
    tocs = []
    unknowns = []
    sem = asyncio.Semaphore(SEM_LIMIT)
    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        async def worker(url):
            async with sem:
                return await fetch(
                    crawler,
                    url,
                    run_cfg,
                )
        results = await asyncio.gather(
            *[worker(url) for url in urls]
        )
    for url, cls in results:
        if cls == "leaf":
            leafs.append(url)
        elif cls == "toc":
            tocs.append(url)
        else:
            unknowns.append(url)
    Path(LEAF_OUT).parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    with open(LEAF_OUT, "w") as f:
        for url in sorted(leafs):
            f.write(json.dumps({"url": url}) + "\n")
    with open(TOC_OUT, "w") as f:
        for url in sorted(tocs):
            f.write(json.dumps({"url": url}) + "\n")
    print("=" * 60)
    print("Leaf pages :", len(leafs))
    print("TOC pages  :", len(tocs))
    print("Unknown    :", len(unknowns))
    print("=" * 60)
    if unknowns:
        print("\nSample unknowns:\n")
        for u in unknowns[:25]:
            print(u)

if __name__ == "__main__":
    asyncio.run(main())