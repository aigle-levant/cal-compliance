import json
import time
from pathlib import Path
from google.genai import types
from config import (
    get_supabase,
    get_gemini,
    EMBED_MODEL,
    EMBED_DIM,
)

CHUNKS_FILE = Path("../data/chunks.jsonl")
TABLE_NAME = "compliance_data"
BATCH_SIZE = 10            # rows per DB upsert (and embedding sub-batch)
EMBED_DELAY_SECONDS = 0.25    # delay between individual embedding calls
DB_DELAY_SECONDS = 1       # delay after each DB upsert
MAX_RETRIES = 5

supabase = get_supabase()
client = get_gemini()


def get_embedding(text: str) -> list[float]:
    """
    Generate a Gemini embedding for a document chunk, with retry/backoff
    for rate-limit (429) and transient errors.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = client.models.embed_content(
                model=EMBED_MODEL,
                contents=text,
                config=types.EmbedContentConfig(
                    task_type="RETRIEVAL_DOCUMENT",
                    output_dimensionality=EMBED_DIM,
                ),
            )
            return result.embeddings[0].values
        except Exception as e:
            msg = str(e).lower()
            is_rate_limit = "429" in msg or "rate" in msg or "quota" in msg
            wait = min(2 ** attempt, 60) if is_rate_limit else 2
            print(f"  embed attempt {attempt}/{MAX_RETRIES} failed ({e}); retrying in {wait}s")
            time.sleep(wait)
    raise RuntimeError("Embedding failed after max retries")


def build_record(chunk: dict, embedding: list[float]) -> dict:
    """
    Convert chunk.jsonl format -> Supabase row format.
    """
    return {
        "chunk_id": chunk["chunk_id"],
        "chunk_index": chunk.get("chunk_index", 1),
        "chunk_total": chunk.get("chunk_total", 1),
        "title_id": chunk.get("title_id"),
        "title_name": chunk.get("title_name"),
        "division_id": chunk.get("division_id"),
        "division_name": chunk.get("division_name"),
        "chapter_id": chunk.get("chapter_id"),
        "chapter_name": chunk.get("chapter_name"),
        "subchapter_id": chunk.get("subchapter_id"),
        "subchapter_name": chunk.get("subchapter_name"),
        "article_id": chunk.get("article_id"),
        "article_name": chunk.get("article_name"),
        "section_number": chunk.get("section_number"),
        "section_title": chunk.get("section_title"),
        "citation": chunk.get("citation"),
        "breadcrumb_path": chunk.get("breadcrumb_path"),
        "source_url": chunk.get("source_url"),
        "document_type": chunk.get("document_type"),
        "source_type": chunk.get("source_type"),
        "text": chunk["text"],
        "retrieved_at": chunk.get("retrieved_at"),
        "embedding": embedding,
    }


def load_chunks():
    with open(CHUNKS_FILE, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def get_already_indexed_ids() -> set[str]:
    """
    Fetch chunk_ids already present in Supabase so re-runs skip them
    (saves Gemini API calls and makes the run resumable after a crash
    or rate-limit abort).
    """
    ids = set()
    page_size = 1000
    start = 0
    while True:
        resp = (
            supabase.table(TABLE_NAME)
            .select("chunk_id")
            .range(start, start + page_size - 1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            break
        ids.update(r["chunk_id"] for r in rows)
        if len(rows) < page_size:
            break
        start += page_size
    return ids


def main():
    print("Loading chunks...")
    all_chunks = list(load_chunks())
    print(f"Total chunks in file: {len(all_chunks)}")

    print("Checking already-indexed chunk_ids in Supabase...")
    existing_ids = get_already_indexed_ids()
    print(f"Already indexed: {len(existing_ids)}")

    pending = [c for c in all_chunks if c["chunk_id"] not in existing_ids]
    print(f"Remaining to process: {len(pending)}")

    batch = []
    processed = 0
    failed = 0

    for i, chunk in enumerate(pending, 1):
        try:
            print(
    f"[{i}/{len(pending)}] "
    f"{chunk['chunk_id']}"
)
            embedding = get_embedding(chunk["text"])
            if len(embedding) != EMBED_DIM:
                raise ValueError(
                    f"Embedding dimension mismatch. "
                    f"Expected {EMBED_DIM}, got {len(embedding)}"
                )
            row = build_record(chunk, embedding)
            batch.append(row)

            # Delay between embedding calls to stay under free-tier rate limits
            time.sleep(EMBED_DELAY_SECONDS)

            if len(batch) >= BATCH_SIZE:
                supabase.table(TABLE_NAME).upsert(
                    batch,
                    on_conflict="chunk_id",
                ).execute()

                processed += len(batch)
                print(f"Inserted {processed}/{len(pending)} chunks")
                batch = []
                time.sleep(DB_DELAY_SECONDS)

        except Exception as e:
            failed += 1
            print(f"Failed chunk {chunk.get('chunk_id')} -> {e}")

    # Clean up any remaining records in the last partial batch
    if batch:
        try:
            supabase.table(TABLE_NAME).upsert(
                batch,
                on_conflict="chunk_id",
            ).execute()
            processed += len(batch)
        except Exception as e:
            failed += len(batch)
            print(f"Failed to flush final batch -> {e}")

    print(f"Finished. Uploaded={processed} Failed={failed} "
          f"AlreadyIndexed={len(existing_ids)} TotalInFile={len(all_chunks)}")


if __name__ == "__main__":
    main()