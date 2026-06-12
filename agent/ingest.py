import json
import os
import time
from supabase import create_client, Client
import google.generativeai as genai
from langchain_text_splitters import RecursiveCharacterTextSplitter

# ── Configuration ────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") 
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

INPUT_JSONL = "../data/extracted_legal_content.jsonl"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
genai.configure(api_key=GEMINI_API_KEY)

# Langchain splitter optimized for Legal Markdown
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=150,
    separators=["\n## ", "\n### ", "\n\n", "\n", " ", ""]
)

def generate_embedding(text: str) -> list[float]:
    """Generate embedding using Google's free text-embedding-004."""
    result = genai.embed_content(
        model="models/text-embedding-004",
        content=text,
        task_type="retrieval_document", # Optimized for DB storage
    )
    return result['embedding']

def process_and_upsert(section_data: dict):
    content = section_data.get("content_markdown", "")
    if not content:
        return

    chunks = text_splitter.split_text(content)
    records_to_insert = []
    
    # Determine the citation format based on the URL
    url = section_data.get("url", "").lower()
    if "dir.ca.gov" in url:
        source_domain = "Title 8"
        citation = f"8 CCR § {section_data.get('section_number', 'Unknown')}"
    elif "leginfo" in url:
        source_domain = "Labor Code"
        citation = f"Lab. Code § {section_data.get('section_number', 'Unknown')}"
    else:
        source_domain = "Unknown"
        citation = "Unknown Citation"
    
    for i, chunk in enumerate(chunks):
        # Generate the embedding
        embedding = generate_embedding(chunk)
        
        # Deterministic ID: e.g., "8_CCR_§_3203_chunk_0"
        record_id = f"{citation}_chunk_{i}".replace(" ", "_")
        
        record = {
            "id": record_id,
            "source_domain": source_domain,
            "citation": citation,
            "section_number": section_data.get("section_number"),
            "breadcrumb_path": section_data.get("breadcrumb_path", ""),
            "source_url": section_data.get("url"),
            "full_content_markdown": content, 
            "chunk_text": chunk,
            "embedding": embedding
        }
        records_to_insert.append(record)
    
    if records_to_insert:
        try:
            supabase.table("compliance_chunks").upsert(records_to_insert).execute()
            print(f"Upserted {len(records_to_insert)} chunks for {citation}")
        except Exception as e:
            print(f"Database Error on {citation}: {e}")

def main():
    print("Starting Gemini/Supabase ingestion for T8 & Labor Code...")
    
    with open(INPUT_JSONL, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            section_data = json.loads(line)
            process_and_upsert(section_data)
            
            # Rate Limiting for Gemini Free Tier (15 RPM limit applies to some accounts)
            # Adjust sleep time based on your specific free tier limits
            time.sleep(1.5) 
                
    print("Ingestion complete.")

if __name__ == "__main__":
    main()