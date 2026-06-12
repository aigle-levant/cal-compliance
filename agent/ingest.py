import os
import json
import time
from dotenv import load_dotenv
from supabase import create_client, Client
from google import genai
from google.genai import types

# Load environment variables from .env file
load_dotenv()

# 1. Initialize Environment & Clients
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") 
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
client = genai.Client()

def get_embedding(text: str) -> list[float]:
    """Generates a 768-dimension vector embedding using the new GenAI SDK."""
    try:
        result = client.models.embed_content(
            model='gemini-embedding-2',
            contents=text,
            config=types.EmbedContentConfig(
                output_dimensionality=768,
            )
        )
        if result.embeddings:
            return result.embeddings[0].values
        return None
    except Exception as e:
        print(f"Embedding generation failed: {e}")
        return None

def index_title8_chunks(chunks: list[dict], table_name: str = "title8_sections"):
    """Iterates through Title 8 chunks, generates embeddings, and upserts to Supabase."""
    print(f"Initializing indexing for {len(chunks)} Title 8 chunks...")
    batch = []
    
    for i, chunk in enumerate(chunks):
        embedding = get_embedding(chunk["text"])
        if not embedding:
            continue
            
        record = {
            "id": chunk["chunk_id"], 
            "document_type": chunk.get("document_type"),
            "source_type": chunk.get("source_type"),
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
            "retrieved_at": chunk.get("retrieved_at"),
            "content_markdown": chunk["text"], 
            "embedding": embedding,
            "chunk_index": chunk.get("chunk_index"),
            "chunk_total": chunk.get("chunk_total")
        }
        
        batch.append(record)
        
        if len(batch) >= 50 or i == len(chunks) - 1:
            try:
                supabase.table(table_name).upsert(batch).execute()
                print(f"Successfully upserted batch up to index {i}")
                batch = []
                time.sleep(1) # Prevent free tier rate limiting
            except Exception as e:
                print(f"Database upsert failed for batch ending at index {i}: {e}")

# ---- ADD THIS EXECUTION BLOCK AT THE BOTTOM ----
if __name__ == "__main__":
    # Change 'chunks.jsonl' to whatever your chunked file is named
    chunks_file_path = "../data/chunks.jsonl" 
    
    if not os.path.exists(chunks_file_path):
        print(f"Error: Could not find your chunks file at '{chunks_file_path}'. Check the path.")
    else:
        # Load your chunks from your JSONL file
        print(f"Loading chunks from {chunks_file_path}...")
        loaded_chunks = []
        with open(chunks_file_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    loaded_chunks.append(json.loads(line))
        
        # Run the indexing pipeline
        if loaded_chunks:
            index_title8_chunks(loaded_chunks)
        else:
            print("No chunks found in file.")