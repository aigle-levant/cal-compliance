import os
import sys
from supabase import create_client, Client
import google.generativeai as genai

# ── Configuration ────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") # Or Anon key if RLS allows reads
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Initialize Clients
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
genai.configure(api_key=GEMINI_API_KEY)

def get_query_embedding(query: str) -> list[float]:
    """Generates an embedding for the user's question.
    
    CRUCIAL: Uses task_type="retrieval_query" to match Gemini's internal 
    asymmetric retrieval optimization.
    """
    result = genai.embed_content(
        model="models/text-embedding-004",
        content=query,
        task_type="retrieval_query",
    )
    return result['embedding']

def retrieve_legal_context(query: str, match_count: int = 8) -> list[dict]:
    """Embeds the query and calls the Supabase RPC to find relevant text chunks."""
    query_vector = get_query_embedding(query)
    
    # Call the stored procedure we created in Step 1
    response = supabase.rpc(
        "match_compliance_chunks",
        {
            "query_embedding": query_vector,
            "match_threshold": 0.3,  # Adjust based on data noise
            "match_count": match_count
        }
    ).execute()
    
    return response.data

def run_compliance_agent(user_query: str):
    print("🤖 Searching database for relevant sections...")
    matched_chunks = retrieve_legal_context(user_query)
    
    if not matched_chunks:
        print("❌ No matching regulations found in the database.")
        return

    # Build a clean context block for Gemini, attaching metadata to every chunk
    context_items = []
    print(f"📖 Retrieved {len(matched_chunks)} legal context chunks:")
    for chunk in matched_chunks:
        print(f"   - [{chunk['source_domain']}] {chunk['citation']} (Sim: {chunk['similarity']:.2f})")
        
        item_text = (
            f"Source Body: {chunk['source_domain']}\n"
            f"Citation: {chunk['citation']}\n"
            f"Path: {chunk['breadcrumb_path']}\n"
            f"URL: {chunk['source_url']}\n"
            f"Regulatory Text:\n{chunk['chunk_text']}"
        )
        context_items.append(item_text)
        
    context_block = "\n\n=================================\n\n".join(context_items)

    # Initialize Gemini 1.5 Flash (Massive context window ideal for legal context blocks)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    system_prompt = """
    You are a professional California Legal Compliance Agent specializing in Title 8 (Industrial Relations/Cal/OSHA) and the California Labor Code.
    Your task is to advise business owners and operators on which regulations apply to them based strictly on the provided text.

    CRITICAL INSTRUCTIONS:
    1. Rely ONLY on the provided legal text. Do not make up regulations, and do not use outside knowledge.
    2. If the context does not contain enough concrete information to confidently answer the user's scenario, state exactly:
       "Based on the currently indexed regulations, I lack sufficient specific details to confirm the complete requirements for this facility." Then ask targeted follow-up questions to clarify their operations.
    3. For EVERY requirement or rule you state, you must explicitly include its citation (e.g., "Under 8 CCR § 3203..." or "Per Lab. Code § 6401..."). 
    4. Provide the Source URL for each cited section at the end of its respective paragraph so the user can verify it.
    5. Explain clearly *why* each regulation applies to their specific operations (e.g., if they run a restaurant, tie it back to kitchen hazards or employee safety requirements).
    6. Conclude your answer with this exact legal disclaimer block verbatim:
       "\n\n***\n**Disclaimer:** This is an AI-generated regulatory summary for informational purposes only. It does not constitute formal legal advice. For binding interpretations, consult legal counsel or the respective California enforcement agencies."
    """

    user_prompt = f"""
    CONTEXT DATA FROM DATABASE:
    {context_block}
    
    USER QUERY:
    {user_query}
    """

    print("\n🧠 Brainstorming compliance requirements...")
    response = model.generate_content(
        contents=user_prompt,
        generation_config={"prompt_feedback": [], "temperature": 0.2} # Low temperature ensures accuracy
    )
    
    print("\n=== COMPLIANCE REPORT ===")
    print(response.text)

# ── Execution ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Test queries aligned with your assignment requirements
    sample_query = "What regulations should a restaurant operator in California be aware of regarding worker safety?"
    
    # If a query is provided via command line, use it
    if len(sys.argv) > 1:
        sample_query = " ".join(sys.argv[1:])
        
    run_compliance_agent(sample_query)