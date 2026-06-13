from agent.config import (
    get_supabase,
    get_gemini,
    EMBED_MODEL,
    EMBED_DIM,
    LLM_MODEL,
)

import sys
supabase = get_supabase()
client = get_gemini()
from google.genai import types


EMBED_MODEL = "gemini-embedding-001"
EMBED_DIM = 768
LLM_MODEL = "gemini-2.0-flash"

SYSTEM_PROMPT = """You are a compliance assistant that helps facility operators \
(restaurants, theaters, farms, etc.) understand which California Code of \
Regulations (CCR) sections apply to them.

Rules:
- Only use the retrieved context.
- If a regulation is not present in the context, do not mention it.
- Never invent citations or section numbers.
- Ask follow-up questions when the facility type or scenario is unclear.
- If the retrieved context is insufficient, explicitly say so.
- For every regulation you mention, cite its citation (e.g. "8 CCR § 6120") and \
include the source_url if available.
- Briefly explain WHY each cited section applies to the operator's situation.
- If the context doesn't contain enough information to answer confidently, say so \
and ask a clarifying follow-up question instead of guessing.
- Always end your answer with: "This is not legal advice. Consult a qualified \
professional for compliance decisions."

Context:
{context}

Question: {question}
"""


# 1. Gemini Embeddings -----------------------------------------------------
def embed_query(text: str) -> list[float]:
    result = client.models.embed_content(
        model=EMBED_MODEL,
        contents=text,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",   # asymmetric: query side
            output_dimensionality=EMBED_DIM,
        ),
    )
    return result.embeddings[0].values


# 2. Supabase pgvector similarity search -----------------------------------
def search_chunks(query_embedding: list[float], match_count: int = 8,
                   title_id: str | None = None) -> list[dict]:
    response = supabase.rpc("match_compliance_data", {
        "query_embedding": query_embedding,
        "match_count": match_count,
        "filter_title_id": title_id,
        "filter_division_id": None,
        "filter_chapter_id": None,
        "filter_section_number": None,
    }).execute()
    return response.data or []


# 3. Format retrieved chunks for the LLM prompt -----------------------------
def format_context(chunks: list[dict]) -> str:
    parts = []

    for c in chunks:
        parts.append(
            f"""
Citation: {c.get("citation", "Unknown")}

Section Title:
{c.get("section_title", "")}

Breadcrumb:
{c.get("breadcrumb_path", "")}

Source URL:
{c.get("source_url", "")}

Content:
{c.get("text", "")}
"""
        )

    return "\n\n====================\n\n".join(parts)


# 4. Gemini LLM answer -------------------------------------------------------
def generate_answer(question: str, context: str) -> str:
    prompt = SYSTEM_PROMPT.format(context=context, question=question)
    response = client.models.generate_content(
        model=LLM_MODEL,
        contents=prompt,
    )
    return response.text


# Full pipeline --------------------------------------------------------------
def answer_question(question: str, title_id: str | None = None, k: int = 15) -> str:
    query_embedding = embed_query(question)
    chunks = search_chunks(query_embedding, match_count=k, title_id=title_id)
    MIN_SIMILARITY = 0.65

    chunks = [
        c for c in chunks
        if c.get("similarity", 0) >= MIN_SIMILARITY
    ]
    if not chunks:
        return ("No relevant CCR sections found in the index. Try rephrasing, "
                "or the relevant regulations may not be indexed yet.")

    context = format_context(chunks)
    answer = generate_answer(question, context)

    print(f"\n--- Retrieved {len(chunks)} chunks ---")
    for c in chunks:
        print(f"- {c.get('citation')}: {c.get('section_title')} "
              f"(similarity={c['similarity']:.3f})")

    return answer


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: python rag_pipeline.py "your question" [title_id]')
        sys.exit(1)

    question = sys.argv[1]
    title_id = sys.argv[2] if len(sys.argv) > 2 else None

    print(f"Question: {question}\n")
    answer = answer_question(question, title_id=title_id)
    print("\n--- Answer ---")
    print(answer)