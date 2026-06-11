import json
from pathlib import Path

from langchain_text_splitters import (
    RecursiveCharacterTextSplitter
)

INPUT = Path("../data/extract.jsonl")
OUTPUT = Path("../data/chunks.jsonl")

OUTPUT.parent.mkdir(
    parents=True,
    exist_ok=True
)

# Fresh run
OUTPUT.write_text("", encoding="utf8")

splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200,
    length_function=len
)

chunk_count = 0

with open(INPUT, "r", encoding="utf8") as infile, \
     open(OUTPUT, "a", encoding="utf8") as outfile:

    for line in infile:

        if not line.strip():
            continue

        record = json.loads(line)

        content = (
            record.get("content_markdown", "")
            .strip()
        )

        if not content:
            continue

        chunks = splitter.split_text(content)

        for idx, chunk in enumerate(chunks):

            chunk_record = {
                "chunk_id":
                    f"{record['source_url']}#{idx}",

                "chunk_index":
                    idx,

                "source_url":
                    record["source_url"],

                "section_heading":
                    record.get(
                        "section_heading"
                    ),

                "citation":
                    record.get(
                        "citation"
                    ),

                "title_number":
                    record.get(
                        "title_number"
                    ),

                "section_number":
                    record.get(
                        "section_number"
                    ),

                "chunk_text":
                    chunk
            }

            outfile.write(
                json.dumps(chunk_record)
                + "\n"
            )

            chunk_count += 1

print(
    f"Created {chunk_count} chunks"
)