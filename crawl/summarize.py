import json
from collections import defaultdict
from pathlib import Path

DISCOVERY = "../data/discovery.jsonl"
EXTRACT = "../sections.jsonl"
CHUNKS = "../data/chunks.jsonl"
OUTPUT = "../data/coverage.jsonl"


def load_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


discovered_urls = set()
extracted_urls = set()

titles = set()
divisions = set()
chapters = set()
articles = set()
citations = set()

chunk_count = 0

# discovery
for row in load_jsonl(DISCOVERY):
    url = row.get("url")
    if url:
        discovered_urls.add(url)

# extract
for row in load_jsonl(EXTRACT):
    url = row.get("source_url")

    if url:
        extracted_urls.add(url)

    citations.add(row.get("citation"))

    if row.get("title_number"):
        titles.add(row["title_number"])

    if row.get("division_number"):
        divisions.add(row["division_number"])

    if row.get("chapter_number"):
        chapters.add(row["chapter_number"])

    if row.get("article_number"):
        articles.add(row["article_number"])

# chunks
for _ in load_jsonl(CHUNKS):
    chunk_count += 1

failed_urls = sorted(discovered_urls - extracted_urls)

coverage = {
    "discovered_urls": len(discovered_urls),
    "extracted_urls": len(extracted_urls),
    "failed_urls": len(failed_urls),
    "coverage_percent": round(
        len(extracted_urls) / max(len(discovered_urls), 1) * 100,
        2,
    ),
    "unique_titles": len(titles),
    "unique_divisions": len(divisions),
    "unique_chapters": len(chapters),
    "unique_articles": len(articles),
    "unique_sections": len(citations),
    "total_chunks": chunk_count,
    "missing_urls": failed_urls,
}

with open(OUTPUT, "w", encoding="utf-8") as f:
    f.write(json.dumps(coverage, indent=None))
    f.write("\n")

print(json.dumps(coverage, indent=2))