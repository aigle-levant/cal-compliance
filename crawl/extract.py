import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from crawl4ai import (
    AsyncWebCrawler,
    BrowserConfig,
    CrawlerRunConfig,
    CacheMode,
)

INPUT_FILE = "../data/urls.jsonl"
OUTPUT_FILE = "../data/extract.jsonl"

MAX_CONCURRENCY = 5


def extract_title_metadata(url: str):
    url_lower = url.lower()

    if "dir.ca.gov/title8" in url_lower or "/t8/" in url_lower:
        return {
            "title_number": "8",
            "title_name": "Title 8. Industrial Relations",
        }

    if "leginfo.legislature.ca.gov" in url_lower and "lawcode=lab" in url_lower:
        return {
            "title_number": "LAB",
            "title_name": "California Labor Code",
        }

    return {
        "title_number": None,
        "title_name": None,
    }


def parse_ccr_hierarchy_from_title(title_str: str) -> dict:
    """
    Extracts canonical CCR layout hierarchy components using regex mappings over the HTML page title string.
    Gracefully returns None for missing structural node levels.
    """
    hierarchy = {
        "division": None,
        "chapter": None,
        "subchapter": None,
    }
    
    if not title_str:
        return hierarchy

    # Extract Division (captures alphanumeric indices like Division 1, Division 1.5)
    div_match = re.search(r"Division\s+([0-9A-Za-z\.-]+[^.]+)", title_str)
    if div_match:
        hierarchy["division"] = div_match.group(0).strip()

    # Extract Chapter
    chap_match = re.search(r"Chapter\s+([0-9A-Za-z\.-]+[^.]+)", title_str)
    if chap_match:
        hierarchy["chapter"] = chap_match.group(0).strip()

    # Extract Subchapter and Article, combining them into a canonical string payload if both exist
    sub_match = re.search(r"Subchapter\s+([0-9A-Za-z\.-]+[^.]+)", title_str)
    art_match = re.search(r"Article\s+([0-9A-Za-z\.-]+[^.]+)", title_str)
    
    sub_parts = []
    if sub_match:
        sub_parts.append(sub_match.group(0).strip())
    if art_match:
        sub_parts.append(art_match.group(0).strip())
        
    if sub_parts:
        hierarchy["subchapter"] = " | ".join(sub_parts)

    return hierarchy


def extract_section_header(markdown: str):
    # Analyze the initial portion where definitions and headers sit
    text = "\n".join(markdown.splitlines()[:40])

    # Upgraded pattern matching handles complex sections (e.g., 5194.1, 3395-A) safely
    patterns = [
        r"§\s*([A-Za-z0-9\.-]+)\.?\s+(.+)",
        r"Section\s+([A-Za-z0-9\.-]+)\.?\s+(.+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return (
                match.group(1).strip().rstrip("."),
                match.group(2).strip(),
            )

    return None, None


def clean_markdown(markdown: str):
    markdown = re.sub(
        r"^\s*(\*\s*\*\s *\*)+",
        "",
        markdown,
        flags=re.MULTILINE,
    )

    markdown = re.sub(
        r"\[Skip to Main Content\].*?\n",
        "",
        markdown,
        flags=re.IGNORECASE | re.DOTALL,
    )

    markdown = re.sub(
        r"This information is provided free of charge.*?full disclaimer.*?\n",
        "",
        markdown,
        flags=re.IGNORECASE | re.DOTALL,
    )

    markdown = re.sub(
        r"\n{3,}",
        "\n\n",
        markdown,
    )

    return markdown.strip()


def trim_before_section(markdown: str):
    idx = markdown.find("§")
    if idx != -1:
        return markdown[idx:]
    return markdown


def build_record(url: str, markdown: str, page_title: str = None):
    metadata = extract_title_metadata(url)
    markdown = clean_markdown(markdown)

    if metadata["title_number"] == "8":
        markdown = trim_before_section(markdown)

    section_number, section_heading = extract_section_header(markdown)

    # Resolve structural hierarchy maps from metadata title layers
    hierarchy = parse_ccr_hierarchy_from_title(page_title)

    citation = None
    if section_number:
        if metadata["title_number"] == "LAB":
            citation = f"Labor Code § {section_number}"
        elif metadata["title_number"]:
            citation = f"{metadata['title_number']} CCR § {section_number}"

    # Construct canonical runtime breadcrumbs dynamically
    crumbs = []
    if metadata["title_number"]:
        crumbs.append(f"Title {metadata['title_number']}")
    if hierarchy["division"]:
        crumbs.append(hierarchy["division"])
    if hierarchy["chapter"]:
        crumbs.append(hierarchy["chapter"])
    if hierarchy["subchapter"]:
        crumbs.append(hierarchy["subchapter"])
    if section_number:
        crumbs.append(f"§ {section_number}")
        
    breadcrumb_path = " -> ".join(crumbs) if crumbs else None

    return {
        "title_number": metadata["title_number"],
        "title_name": metadata["title_name"],

        "division": hierarchy["division"],
        "chapter": hierarchy["chapter"],
        "subchapter": hierarchy["subchapter"],

        "section_number": section_number,
        "section_heading": section_heading,

        "citation": citation,
        "breadcrumb_path": breadcrumb_path,

        "source_url": url,
        "content_markdown": markdown,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }


# --------------------------------------------------
# Crawl
# --------------------------------------------------

async def process_url(
    crawler,
    config,
    semaphore,
    url,
    outfile
):
    async with semaphore:
        try:
            result = await crawler.arun(
                url=url,
                config=config
            )

            if not result.success:
                print(f"[FAIL] {url}")
                return

            markdown = ""
            if result.markdown:
                markdown = (
                    result.markdown.raw_markdown
                    if hasattr(result.markdown, "raw_markdown")
                    else str(result.markdown)
                )

            if not markdown.strip():
                print(f"[EMPTY] {url}")
                return

            if len(markdown.strip()) < 100:
                print(f"[SKIP] {url}")
                return

            # Capture runtime HTML metadata titles natively
            page_title = None
            if result.metadata and isinstance(result.metadata, dict):
                page_title = result.metadata.get("title")

            record = build_record(
                url=url,
                markdown=markdown,
                page_title=page_title
            )

            outfile.write(
                json.dumps(record, ensure_ascii=False) + "\n"
            )
            outfile.flush()  # Ensures atomic writes onto disk after a success

            print(
                f"[OK] {record['section_number'] or 'UNRESOLVED'} - "
                f"{record['section_heading'] or 'No Heading Found'}"
            )

        except Exception as e:
            print(f"[ERROR] {url}")
            print(e)


# --------------------------------------------------
# Main
# --------------------------------------------------

async def main():
    urls = []

    if not Path(INPUT_FILE).exists():
        print(f"Error: Input target file not found at {INPUT_FILE}")
        return

    with open(INPUT_FILE, "r", encoding="utf8") as f:
        for line in f:
            if not line.strip():
                continue
            urls.append(json.loads(line)["url"])

    print(f"Loaded {len(urls)} URLs for content extraction.")

    browser_cfg = BrowserConfig(headless=True)
    
    crawl_cfg = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        remove_overlay_elements=True,
        exclude_external_links=True,
        exclude_social_media_links=True,
        
        # Bypasses infinite network scripts using dynamic readyState indicators
        wait_for="js:() => document.readyState === 'complete'",
        wait_for_timeout=10000,
        
        excluded_tags=[
            "nav",
            "footer",
            "header",
            "aside",
            "form",
        ],
        word_count_threshold=50,
        magic=True
    )

    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    Path(OUTPUT_FILE).parent.mkdir(
        parents=True,
        exist_ok=True
    )

    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        with open(OUTPUT_FILE, "w", encoding="utf8") as outfile:
            tasks = [
                process_url(
                    crawler,
                    crawl_cfg,
                    semaphore,
                    url,
                    outfile,
                )
                for url in urls
            ]
            await asyncio.gather(*tasks)

    print(f"\nFinished. Output successfully saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())