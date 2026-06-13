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
BATCH_SIZE = 25

supabase = get_supabase()
client = get_gemini()

def get_embedding(text: str) -> list[float]:
    """
    Generate a Gemini embedding for a document chunk.
    """
    result = client.models.embed_content(
        model=EMBED_MODEL,
        contents=text,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=EMBED_DIM,
        ),
    )
    return result.embeddings[0].values

def build_record(chunk: dict, embedding: list[float]) -> dict:
    """
    Convert chunk.jsonl format -> Supabase row format.
    """
    return {
        "chunk_id": chunk["chunk_id"],
        "chunk_index": chunk["chunk_index"],
        "chunk_total": chunk["chunk_total"],
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

def main():
    print("Loading chunks...")
    batch = []
    processed = 0

    for chunk in load_chunks():
        try:
            embedding = get_embedding(chunk["text"])
            row = build_record(chunk, embedding)
            batch.append(row)

            if len(batch) >= BATCH_SIZE:
                supabase.table(TABLE_NAME).upsert(
                    batch,
                    on_conflict="chunk_id",
                ).execute()
                
                processed += len(batch)
                print(f"Inserted {processed} chunks")
                batch = []
                time.sleep(1)

        except Exception as e:
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
            print(f"Failed to flush final batch -> {e}")

    print(f"Finished. Uploaded {processed} chunks.")

if __name__ == "__main__":
    main()