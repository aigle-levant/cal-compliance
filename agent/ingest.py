import json
import os

from dotenv import load_dotenv
from tqdm import tqdm
from supabase import create_client
from langchain_ollama import OllamaEmbeddings

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

INPUT_FILE = "../data/chunks.jsonl"
BATCH_SIZE = 25

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

embeddings = OllamaEmbeddings(
    model="bge-m3"
)


def load_chunks(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if line:
                yield json.loads(line)


def get_existing_ids():
    existing = set()

    page_size = 1000
    offset = 0

    while True:
        result = (
            supabase
            .table("compliance_data")
            .select("chunk_id")
            .range(offset, offset + page_size - 1)
            .execute()
        )

        rows = result.data or []

        if not rows:
            break

        existing.update(
            row["chunk_id"]
            for row in rows
        )

        offset += page_size

    return existing


def build_row(chunk, vector):
    meta = chunk.get("metadata", {})

    return {
        "chunk_id": chunk["id"],

        "chunk_index": meta.get("chunk_index", 1),
        "chunk_total": meta.get("chunk_count", 1),

        "title_id": meta.get("title_number"),
        "title_name": meta.get("title_name"),

        "division_id": meta.get("division_number"),
        "division_name": meta.get("division_name"),

        "chapter_id": meta.get("chapter_number"),
        "chapter_name": meta.get("chapter_name"),

        "subchapter_id": meta.get("subchapter_number"),
        "subchapter_name": meta.get("subchapter_name"),

        "article_id": meta.get("article_number"),
        "article_name": meta.get("article_name"),

        "section_number": meta.get("section_number"),
        "section_title": meta.get("section_heading"),

        "citation": meta.get("citation"),
        "breadcrumb_path": meta.get("breadcrumb_path"),

        "source_url": meta.get("source_url"),

        "document_type": meta.get(
            "document_type",
            "regulation"
        ),

        "source_type": "california_ccr",

        "text": chunk["content"],
        "content_markdown": chunk["content"],

        "retrieved_at": meta.get("retrieved_at"),

        "embedding": vector
    }


def insert_batch(chunks):
    texts = [
        chunk["content"]
        for chunk in chunks
    ]

    vectors = embeddings.embed_documents(texts)

    rows = [
        build_row(chunk, vector)
        for chunk, vector in zip(chunks, vectors)
    ]

    result = (
    supabase
    .table("compliance_data")
    .upsert(
        rows,
        on_conflict="chunk_id"
    )
    .execute()
    )

    print(
        f"Inserted {len(result.data or [])} rows"
    )


def main():
    print("Loading chunks...")

    all_chunks = list(
        load_chunks(INPUT_FILE)
    )

    print(
        f"Total chunks: {len(all_chunks)}"
    )

    print(
        "Checking existing vectors..."
    )

    existing_ids = get_existing_ids()

    print(
        f"Already indexed: {len(existing_ids)}"
    )

    pending = [
        chunk
        for chunk in all_chunks
        if chunk["id"] not in existing_ids
    ]

    print(
        f"Remaining: {len(pending)}"
    )

    if not pending:
        print("Nothing to ingest.")
        return

    for i in tqdm(
        range(0, len(pending), BATCH_SIZE),
        desc="Embedding"
    ):
        batch = pending[i:i + BATCH_SIZE]

        try:
            insert_batch(batch)

        except Exception as e:
            print(
                f"\nFailed batch {i // BATCH_SIZE + 1}"
            )
            print(e)

    print("\nDone.")


if __name__ == "__main__":
    main()