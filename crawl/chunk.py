import json
import re
from pathlib import Path

INPUT_FILE = "../data/sections.jsonl"
OUTPUT_FILE = "../data/chunks.jsonl"

TARGET_SIZE = 1200
MAX_SIZE = 1600

SUBSECTION_RE = re.compile(
    r"(?=^\(([a-z]{1,2})\)\s)",
    re.MULTILINE,
)


def split_into_units(text: str):
    text = text.strip()

    matches = list(SUBSECTION_RE.finditer(text))

    if not matches:
        return [text]

    units = []

    # Keep heading/preamble
    first_start = matches[0].start()
    preamble = text[:first_start].strip()

    if preamble:
        units.append(preamble)

    for i, match in enumerate(matches):
        start = match.start()

        if i + 1 < len(matches):
            end = matches[i + 1].start()
        else:
            end = len(text)

        units.append(text[start:end].strip())

    return units


def build_chunks(units):
    chunks = []
    current = ""

    for unit in units:
        candidate = f"{current}\n\n{unit}".strip()

        if current and len(candidate) > TARGET_SIZE:
            chunks.append(current.strip())
            current = unit
        else:
            current = candidate

        if len(current) > MAX_SIZE:
            chunks.append(current.strip())
            current = ""

    if current:
        chunks.append(current.strip())

    return chunks


def process_section(record):
    text = record["content_markdown"]

    units = split_into_units(text)
    chunks = build_chunks(units)

    results = []

    chunk_count = len(chunks)

    for idx, chunk in enumerate(chunks, start=1):
        chunk_record = {
            "id": f"{record['title_number']}_{record['section_number']}_{idx}",
            "content": chunk,
            "metadata": {
                "citation": record["citation"],
                "section_number": record["section_number"],
                "section_heading": record["section_heading"],
                "title_number": record["title_number"],
                "title_name": record["title_name"],
                "division_number": record["division_number"],
                "division_name": record["division_name"],
                "chapter_number": record["chapter_number"],
                "chapter_name": record["chapter_name"],
                "subchapter_number": record["subchapter_number"],
                "subchapter_name": record["subchapter_name"],
                "article_number": record["article_number"],
                "article_name": record["article_name"],
                "jurisdiction": record["jurisdiction"],
                "source_url": record["source_url"],
                "chunk_index": idx,
                "chunk_count": chunk_count,
            },
        }

        results.append(chunk_record)

    return results


def process_jsonl(input_path, output_path):
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    total_chunks = 0

    with open(input_path, "r", encoding="utf-8") as infile, \
         open(output_path, "w", encoding="utf-8") as outfile:

        for line in infile:
            if not line.strip():
                continue

            record = json.loads(line)

            chunks = process_section(record)

            for chunk in chunks:
                outfile.write(
                    json.dumps(chunk, ensure_ascii=False) + "\n"
                )

            total_chunks += len(chunks)

    print(f"Created {total_chunks:,} chunks")


if __name__ == "__main__":
    process_jsonl(
        "../data/sections.jsonl",
        "../data/chunks.jsonl",
    )