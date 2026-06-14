import json
import os
import time
from tqdm import tqdm
from dotenv import load_dotenv
from supabase import create_client
from langchain_google_genai import GoogleGenerativeAIEmbeddings

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
GOOGLE_API_KEY = os.getenv("GEMINI_API_KEY")

INPUT_FILE = "../data/chunks.jsonl"
BATCH_SIZE = 50

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

embeddings = GoogleGenerativeAIEmbeddings(
    model="models/gemini-embedding-001",
    google_api_key=GOOGLE_API_KEY,
)

def load_chunks(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)

def get_existing_ids():
    """
    Fetch already indexed chunk_ids.
    """
    existing = set()
    page_size = 1000
    offset = 0

    while True:
        result = (
            supabase.table("compliance_data")
            .select("chunk_id")
            .range(offset, offset + page_size - 1)
            .execute()
        )

        rows = result.data or []

        if not rows:
            break

        existing.update(row["chunk_id"] for row in rows)
        offset += page_size

    return existing

def insert_batch(chunks, vectors):
    rows = []

    for chunk, vector in zip(chunks, vectors):
        meta = chunk.get("metadata", {})

        rows.append({
            "chunk_id": chunk["id"],
            "content": chunk["content"],
            "embedding": vector,
            "citation": meta.get("citation"),
            "section_id": meta.get("section_id"),
            "section_heading": meta.get("section_heading"),
            "title_number": meta.get("title_number"),
            "title_name": meta.get("title_name"),
            "division_number": meta.get("division_number"),
            "division_name": meta.get("division_name"),
            "chapter_number": meta.get("chapter_number"),
            "chapter_name": meta.get("chapter_name"),
            "article_id": meta.get("article_id"),
            "article_name": meta.get("article_name"),
            "jurisdiction": meta.get("jurisdiction"),
            "source_url": meta.get("source_url"),
            "chunk_index": meta.get("chunk_index"),
            "chunk_count": meta.get("chunk_count"),
        })

    supabase.table("compliance_data").insert(rows).execute()

def main():
    print("Loading chunks...")
    all_chunks = list(load_chunks(INPUT_FILE))
    print(f"Total chunks: {len(all_chunks)}")

    print("Checking existing vectors...")
    existing_ids = get_existing_ids()
    print(f"Already indexed: {len(existing_ids)}")

    pending = [chunk for chunk in all_chunks if chunk["id"] not in existing_ids]
    print(f"Remaining: {len(pending)}")

    if not pending:
        print("Nothing to ingest.")
        return

    for i in tqdm(range(0, len(pending), BATCH_SIZE), desc="Embedding"):
        batch = pending[i:i + BATCH_SIZE]
        texts = [chunk["content"] for chunk in batch]

        try:
            vectors = embeddings.embed_documents(texts)
            insert_batch(batch, vectors)
            
        except Exception as e:
            print(f"Failed batch {i // BATCH_SIZE + 1}: {e}")
            time.sleep(30)
            continue

    print("Done.")

if __name__ == "__main__":
    main()