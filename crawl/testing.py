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
OUTPUT = "../data/sections.jsonl"

CONCURRENCY = 5


def load_urls():
    with open(INPUT, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)["url"]


def extract_section_info(markdown: str):
    """
    Extract:
        §232.63. Preparation of Record for Review

    Returns:
        section_number
        section_title
    """

    patterns = [
        r"§\s*([\d._]+)\.?\s*(.+)",
        r"^([\d._]+)\.\s+(.+)",
    ]

    lines = [
        x.strip()
        for x in markdown.splitlines()
        if x.strip()
    ]

    for line in lines[:30]:

        for pat in patterns:

            m = re.search(pat, line)

            if m:
                return (
                    m.group(1).strip(),
                    m.group(2).strip(),
                )

    return None, None


def clean_text(markdown: str):

    text = markdown

    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


async def extract_page(crawler, url, cfg):

    try:

        result = await crawler.arun(
            url,
            config=cfg,
        )

        if not result.success:
            print(f"[FAIL] {url}")
            return None

        markdown = result.markdown or ""

        section_number, section_title = (
            extract_section_info(markdown)
        )

        return {
            "url": url,
            "section_number": section_number,
            "section_title": section_title,
            "text": clean_text(markdown),
        }

    except Exception as e:

        print(f"[ERR] {url}: {e}")

        return None


async def main():

    urls = list(load_urls())

    print(f"Leaf URLs: {len(urls)}")

    browser_cfg = BrowserConfig(
        headless=True,
        java_script_enabled=False,
    )

    run_cfg = CrawlerRunConfig(
        wait_until="domcontentloaded",
    )

    sem = asyncio.Semaphore(CONCURRENCY)

    Path(OUTPUT).parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    async with AsyncWebCrawler(
        config=browser_cfg
    ) as crawler:

        async def worker(url):

            async with sem:

                return await extract_page(
                    crawler,
                    url,
                    run_cfg,
                )

        results = await asyncio.gather(
            *[worker(url) for url in urls]
        )

    saved = 0

    with open(
        OUTPUT,
        "w",
        encoding="utf-8",
    ) as f:

        for row in results:

            if not row:
                continue

            f.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                )
                + "\n"
            )

            saved += 1

    print(f"Saved {saved} sections")
    print(f"Output: {OUTPUT}")


if __name__ == "__main__":
    asyncio.run(main())