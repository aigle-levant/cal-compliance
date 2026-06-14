# extract.py

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

INPUT_FILE = "../data/discovery.jsonl"
OUTPUT_FILE = "../data/sections.jsonl"
CONCURRENCY = 5

def load_urls():
    with open(INPUT_FILE, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)["url"]

def extract_section(markdown: str):
    """
    Example:
    # §232.63.Preparation of Record for Review
    """
    m = re.search(
    r"^#\s*§\s*([\d.]+)\.?\s*(.*?)\s*$",
    markdown,
    re.MULTILINE
)

    if not m:
        return None, None

    return (
        m.group(1).rstrip("."),
        m.group(2).strip(),
    )

def extract_hierarchy(markdown: str):
    hierarchy = {
        "title_number": "8",
        "title_name": "Industrial Relations",
        "division_number": None,
        "division_name": None,
        "chapter_number": None,
        "chapter_name": None,
        "subchapter_number": None,
        "subchapter_name": None,
        "article_number": None,
        "article_name": None,
    }
    
    m = re.search(r"#\s*§", markdown)

    header = markdown[:m.start()] if m else markdown
    article_hits = []

    for line in header.splitlines():
        line = line.strip()

        if not line:
            continue

        m = re.match(r"Division\s+([\w.]+)\.\s*(.+)", line, re.IGNORECASE)
        if m:
            hierarchy["division_number"] = m.group(1)
            hierarchy["division_name"] = m.group(2)
            continue

        m = re.match(r"Chapter\s+([\w.]+)\.\s*(.+)", line, re.IGNORECASE)
        if m:
            hierarchy["chapter_number"] = m.group(1)
            hierarchy["chapter_name"] = m.group(2)
            continue

        m = re.match(r"Subchapter\s+([\w.]+)\.\s*(.+)", line, re.IGNORECASE)
        if m:
            hierarchy["subchapter_number"] = m.group(1)
            hierarchy["subchapter_name"] = m.group(2)
            continue

        m = re.match(
    r"Article\s+(\d+(?:\.\d+)*)\.?\s*(.+)",
    line,
    re.IGNORECASE
)
        if m:
            article_hits.append((m.group(1), m.group(2)))

    if article_hits:
        hierarchy["article_number"] = article_hits[-1][0]
        hierarchy["article_name"] = article_hits[-1][1]

    return hierarchy

def build_breadcrumb(meta):
    parts = [f"Title {meta['title_number']}: {meta['title_name']}"]
    
    if meta["division_number"]:
        parts.append(f"Division {meta['division_number']}: {meta['division_name']}")

    if meta["chapter_number"]:
        parts.append(f"Chapter {meta['chapter_number']}: {meta['chapter_name']}")

    if meta["subchapter_number"]:
        parts.append(f"Subchapter {meta['subchapter_number']}: {meta['subchapter_name']}")

    if meta["article_number"]:
        parts.append(f"Article {meta['article_number']}: {meta['article_name']}")

    return " > ".join(parts)

def trim_content(markdown: str):
    """
    Keep only section content.
    Remove crawler/navigation noise.
    """
    match = re.search(r"#\s*§", markdown)

    if not match:
        return markdown.strip()

    content = markdown[match.start():]

    content = re.sub(r"!\[.*?\]\(.*?\)", "", content, flags=re.DOTALL)
    content = re.sub(r"\[Go Back.*?\)", "", content, flags=re.DOTALL)
    content = re.sub(r"\* \* \*", "", content)
    content = re.sub(
    r"\n\|\s*\|\s*\n\|\s*---\s*\|.*$",
    "",
    content,
    flags=re.S
)
    content = re.sub(
    r"#\s*§\s*",
    "# § ",
    content
)

    return content.strip()

def split_legal_sections(content: str):
    """
    Splits regulation into:
      - body
      - authority/reference note
      - history
    """

    history = None
    authority_note = None

    history_match = re.search(
        r"\nHISTORY\b",
        content,
        flags=re.IGNORECASE
    )

    if history_match:
        history = content[history_match.start():].strip()
        content = content[:history_match.start()].rstrip()

    note_match = re.search(
        r"\n(?:NOTE|Note):?\s*Authority cited:",
        content,
        flags=re.IGNORECASE
    )

    if note_match:
        authority_note = content[note_match.start():].strip()
        content = content[:note_match.start()].rstrip()

    return {
        "body": content.strip(),
        "authority_note": authority_note,
        "history": history
    }

async def process_url(crawler, url, run_cfg):
    try:
        result = await crawler.arun(url, config=run_cfg)
        
        if not result.success:
            print(f"[FAIL] {url}")
            return None

        markdown = result.markdown or ""
        section_number, section_heading = extract_section(markdown)
        content = trim_content(markdown)

        parts = split_legal_sections(content)

        if not section_number:
            print(f"[WARN] No section found: {url}")
            return None

        hierarchy = extract_hierarchy(markdown)

        doc = {
    **hierarchy,
    "document_type": "regulation",
    "jurisdiction": "California",

    "section_number": section_number,
    "section_heading": section_heading,
    "citation": f"8 CCR § {section_number}",

    "breadcrumb_path": build_breadcrumb(hierarchy),
    "source_url": url,

    "content_markdown": parts["body"],
    "authority_note": parts["authority_note"],
    "history": parts["history"],

    "retrieved_at": datetime.now(timezone.utc).isoformat(),
}

        print(f"[OK] {section_number}")
        return doc

    except Exception as e:
        print(f"[ERR] {url}: {e}")
        return None

async def main():
    urls = list(load_urls())
    
    print(f"Loaded {len(urls)} URLs")

    browser_cfg = BrowserConfig(headless=True, java_script_enabled=False)
    run_cfg = CrawlerRunConfig(wait_until="domcontentloaded")
    sem = asyncio.Semaphore(CONCURRENCY)

    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        async def worker(url):
            async with sem:
                return await process_url(crawler, url, run_cfg)

        docs = await asyncio.gather(*[worker(url) for url in urls])

    docs = [d for d in docs if d]

    Path(OUTPUT_FILE).parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for doc in docs:
            f.write(json.dumps(doc, ensure_ascii=False) + "\n")

    print(f"\nSaved {len(docs)} documents")
    print(f"Output: {OUTPUT_FILE}")

if __name__ == "__main__":
    asyncio.run(main())