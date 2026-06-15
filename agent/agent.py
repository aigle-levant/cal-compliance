import os

from dotenv import load_dotenv
from supabase import create_client

from langchain_ollama import OllamaEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

TOP_K_PER_QUERY = 5
FINAL_CONTEXT_SIZE = 15
SIMILARITY_THRESHOLD = 0.50

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

embeddings = OllamaEmbeddings(
    model="bge-m3"
)

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=GEMINI_API_KEY,
    temperature=0
)

def expand_query(question: str):

    prompt = f"""
You are helping retrieve CCR regulations.

Generate 5 search queries that would help
retrieve regulations relevant to this question.

Question:
{question}

Rules:
- one query per line
- no numbering
- no explanations
"""

    response = llm.invoke(prompt)

    queries = [
        line.strip()
        for line in response.content.split("\n")
        if line.strip()
    ]

    queries.insert(0, question)

    return queries[:6]

def retrieve(query):

    vector = embeddings.embed_query(query)

    result = (
        supabase.rpc(
            "match_compliance_chunks",
            {
                "query_embedding": vector,
                "match_count": TOP_K_PER_QUERY
            }
        )
        .execute()
    )

    rows = result.data or []

    rows = [
        row
        for row in rows
        if row["similarity"] >= SIMILARITY_THRESHOLD
    ]

    return rows

def search(question):

    queries = expand_query(question)

    all_results = []

    for q in queries:
        all_results.extend(
            retrieve(q)
        )

    dedup = {}

    for row in all_results:

        chunk_id = row["chunk_id"]

        if (
            chunk_id not in dedup
            or
            row["similarity"]
            >
            dedup[chunk_id]["similarity"]
        ):
            dedup[chunk_id] = row

    results = list(
        dedup.values()
    )

    results.sort(
        key=lambda x: x["similarity"],
        reverse=True
    )

    return results[:FINAL_CONTEXT_SIZE]

def build_context(results):

    context = []

    for r in results:

        context.append(
            f"""
Citation: {r['citation']}
Section Number: {r.get('section_number')}

Content:
{r['text']}
"""
        )

    return "\n\n".join(context)

def extract_sources(results):

    seen = set()
    sources = []

    for r in results:

        citation = r.get("citation")

        if citation and citation not in seen:
            seen.add(citation)
            sources.append(citation)

    return sources

def answer_question(question):

    results = search(question)

    if not results:

        return {
            "answer":
            "I could not find relevant CCR regulations.",
            "sources": []
        }

    context = build_context(results)

    prompt = f"""
You are a California Code of Regulations
Compliance Assistant.

You help facility operators identify
regulations that may apply to them.

Rules:

1. Use ONLY supplied regulations.
2. Never invent CCR sections.
3. Explain why regulations apply.
4. Ask follow-up questions if needed.
5. Include CCR citations.
6. If regulations are insufficient,
   explicitly say so.
7. End with:

This information is educational only
and is not legal advice.

QUESTION:

{question}

REGULATIONS:

{context}
"""

    response = llm.invoke(prompt)

    return {
        "answer": response.content,
        "sources": extract_sources(results),
        "matches": results
    }

if __name__ == "__main__":

    print("\nCCR Compliance Agent")
    print("Type exit to quit.\n")

    while True:

        question = input("Question: ")

        if question.lower() in [
            "exit",
            "quit"
        ]:
            break

        result = answer_question(
            question
        )

        print("\n" + "=" * 80)
        print("ANSWER")
        print("=" * 80)

        print(result["answer"])

        print("\n" + "=" * 80)
        print("SOURCES")
        print("=" * 80)

        for source in result["sources"]:
            print(source)