import re
import json
from pathlib import Path


SUBSECTION_PATTERN = re.compile(
    r"\(([a-zA-Z0-9]+)\)"
)


def split_into_subsections(content: str):
    matches = list(
        SUBSECTION_PATTERN.finditer(content)
    )

    if not matches:
        return [content]

    chunks = []

    for i, match in enumerate(matches):
        start = match.start()

        if i + 1 < len(matches):
            end = matches[i + 1].start()
        else:
            end = len(content)

        chunk = content[start:end].strip()

        if chunk:
            chunks.append(chunk)

    return chunks


def build_chunks(record: dict):
    content = record["content_markdown"]

    subsection_chunks = split_into_subsections(
        content
    )

    results = []

    for idx, chunk in enumerate(
        subsection_chunks,
        start=1
    ):
        results.append(
            {
                "text": f"""
Citation: {record['citation']}

Section: {record['section_heading']}

{chunk}
""".strip(),
                "metadata": {
                    "citation": record.get(
                        "citation"
                    ),
                    "section_number": record.get(
                        "section_number"
                    ),
                    "section_heading": record.get(
                        "section_heading"
                    ),
                    "source_url": record.get(
                        "source_url"
                    ),
                    "jurisdiction": record.get(
                        "jurisdiction"
                    ),
                    "chunk_id": idx,
                },
            }
        )

    return results


def process_jsonl(
    input_file: str,
    output_file: str,
):
    all_chunks = []

    with open(
        input_file,
        "r",
        encoding="utf-8",
    ) as f:
        for line in f:
            record = json.loads(line)

            chunks = build_chunks(record)

            all_chunks.extend(chunks)

    with open(
        output_file,
        "w",
        encoding="utf-8",
    ) as f:
        for chunk in all_chunks:
            f.write(
                json.dumps(chunk)
                + "\n"
            )

    print(
        f"Created {len(all_chunks)} chunks"
    )


if __name__ == "__main__":
    process_jsonl(
        "data/regulations.jsonl",
        "data/chunks.jsonl",
    )