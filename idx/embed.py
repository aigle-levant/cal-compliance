"""
CCR -> Supabase indexing pipeline.

Reads JSONL records (one chunk per line), generates embeddings, and
upserts into the `ccr_sections` table using `chunk_id` as the idempotency key.

Usage:
    export SUPABASE_URL=https://xxxx.supabase.co
    export SUPABASE_SERVICE_KEY=...
    export OPENAI_API_KEY=...
    python index_to_supabase.py data/sections.jsonl
"""

import os
import sys
import json
import time
import logging
from typing import Iterable

from supabase import create_client, Client
from openai import OpenAI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("indexer")

EMBED_MODEL = "text-embedding-3-small"  # 1536 dims, matches schema
BATCH_SIZE = 50
MAX_RETRIES = 3


def get_clients():
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    supabase: Client = create_client(url, key)
    openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return supabase, openai_client


def read_jsonl(path: str) -> Iterable[dict]:
    with open(path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                log.warning("Skipping malformed line %d: %s", line_num, e)


def embed_batch(openai_client: OpenAI, texts: list[str]) -> list[list[float]]:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = openai_client.embeddings.create(model=EMBED_MODEL, input=texts)
            return [d.embedding for d in resp.data]
        except Exception as e:
            wait = 2 ** attempt
            log.warning("Embedding batch failed (attempt %d/%d): %s. Retrying in %ds",
                        attempt, MAX_RETRIES, e, wait)
            time.sleep(wait)
    raise RuntimeError("Embedding failed after max retries")


def to_row(record: dict, embedding: list[float]) -> dict:
    # chunk_id is required for idempotent upserts; fall back to a derived key
    chunk_id = record.get("chunk_id") or f"{record.get('section_number')}_1"

    return {
        "chunk_id": chunk_id,
        "chunk_index": record.get("chunk_index", 1),
        "chunk_total": record.get("chunk_total", 1),

        "title_id": record.get("title_id"),
        "title_name": record.get("title_name"),
        "division_id": record.get("division_id"),
        "division_name": record.get("division_name"),
        "chapter_id": record.get("chapter_id"),
        "chapter_name": record.get("chapter_name"),
        "subchapter_id": record.get("subchapter_id"),
        "subchapter_name": record.get("subchapter_name"),
        "article_id": record.get("article_id"),
        "article_name": record.get("article_name"),

        "section_number": record.get("section_number"),
        "section_title": record.get("section_title"),
        "citation": record.get("citation"),
        "breadcrumb_path": record.get("breadcrumb_path"),
        "source_url": record.get("source_url"),
        "document_type": record.get("document_type"),
        "source_type": record.get("source_type"),

        "text": record.get("text") or record.get("content_markdown", ""),
        "content_markdown": record.get("content_markdown"),
        "retrieved_at": record.get("retrieved_at"),

        "embedding": embedding,
    }


def main(path: str):
    supabase, openai_client = get_clients()

    records = list(read_jsonl(path))
    log.info("Loaded %d records from %s", len(records), path)

    total_upserted = 0
    total_failed = 0

    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i:i + BATCH_SIZE]
        texts = [r.get("text") or r.get("content_markdown", "") for r in batch]

        try:
            embeddings = embed_batch(openai_client, texts)
        except Exception as e:
            log.error("Skipping batch %d-%d, embedding failed: %s", i, i + len(batch), e)
            total_failed += len(batch)
            continue

        rows = [to_row(r, e) for r, e in zip(batch, embeddings)]

        try:
            # upsert on chunk_id -> idempotent re-indexing
            supabase.table("compliance_data").upsert(rows, on_conflict="chunk_id").execute()
            total_upserted += len(rows)
            log.info("Upserted batch %d-%d (%d rows)", i, i + len(batch), len(rows))
        except Exception as e:
            log.error("Upsert failed for batch %d-%d: %s", i, i + len(batch), e)
            total_failed += len(rows)

    log.info("Done. Upserted=%d Failed=%d Total=%d", total_upserted, total_failed, len(records))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python index_to_supabase.py <path_to_jsonl>")
        sys.exit(1)
    main(sys.argv[1])