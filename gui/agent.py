import os
from dotenv import load_dotenv
from supabase import create_client

from langchain_huggingface import HuggingFaceEmbeddings
from huggingface_hub import InferenceClient

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")
TOP_K = 15
SIMILARITY_THRESHOLD = 0.50


supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

embeddings = HuggingFaceEmbeddings(
    model_name="BAAI/bge-m3"
)

llm = InferenceClient(
    api_key=HF_TOKEN
)

def generate(prompt: str) -> str:
    response = llm.chat.completions.create(
        model="Qwen/Qwen3-8B-Instruct",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        max_tokens=1024,
        temperature=0
    )

    return response.choices[0].message.content


def retrieve(query: str):
    query_embedding = embeddings.embed_query(query)

    result = (
        supabase.rpc(
            "match_compliance_chunks",
            {
                "query_embedding": query_embedding,
                "match_count": TOP_K
            }
        )
        .execute()
    )

    matches = result.data or []

    matches = [
        row
        for row in matches
        if row["similarity"] >= SIMILARITY_THRESHOLD
    ]

    matches.sort(
        key=lambda x: x["similarity"],
        reverse=True
    )

    return matches[:TOP_K]


def build_context(matches):
    sections = []

    for row in matches:
        sections.append(
            f"""
Citation: {row.get('citation')}

Section Number:
{row.get('section_number')}

Section Heading:
{row.get('section_heading')}

Content:
{row.get('text')}
"""
        )

    return "\n\n".join(sections)


def extract_sources(matches):
    seen = set()
    sources = []

    for row in matches:
        citation = row.get("citation")

        if citation in seen:
            continue

        seen.add(citation)

        sources.append(
            {
                "citation": citation,
                "section_number": row.get("section_number"),
                "section_heading": row.get("section_heading"),
                "source_url": row.get("source_url")
            }
        )

    return sources

def answer_question(question: str):
    matches = retrieve(question)

    if not matches:
        return {
            "answer": "I could not find relevant CCR regulations.",
            "sources": [],
            "matches": []
        }

    context = build_context(matches)

    prompt = f"""
You are a California Code of Regulations Compliance Assistant.

Use ONLY the supplied CCR regulations.

Rules:
1. Never invent CCR citations.
2. Explain why regulations apply.
3. Cite regulations.
4. If information is missing, say so.
5. End every answer with:

This information is educational only and is not legal advice.

QUESTION:
{question}

REGULATIONS:
{context}
"""

    answer = generate(prompt)

    return {
        "answer": answer,
        "sources": extract_sources(matches),
        "matches": matches
    }

if __name__ == "__main__":
    while True:
        query = input("\nQuestion: ").strip()

        if query.lower() in {"exit", "quit"}:
            break

        response = answer_question(query)

        print("\n=== ANSWER ===\n")
        print(response["answer"])

        print("\n=== SOURCES ===\n")
        for source in response["sources"]:
            print(
                f"{source['citation']} | "
                f"{source['section_number']} | "
                f"{source['section_heading']}"
            )