import json

from embeddings import embeddings
from db import supabase

BATCH_SIZE = 20

rows = []

with open("chunks.jsonl", encoding="utf8") as f:

    for line in f:

        chunk = json.loads(line)

        vector = embeddings.embed_query(
            chunk["text"]
        )

        rows.append({
            **chunk,
            "embedding": vector,
        })

        if len(rows) >= BATCH_SIZE:

            supabase.table(
                "regulation_chunks"
            ).insert(rows).execute()

            print(
                f"Inserted {len(rows)} chunks"
            )

            rows = []

if rows:

    supabase.table(
        "regulation_chunks"
    ).insert(rows).execute()

    print(
        f"Inserted {len(rows)} chunks"
    )