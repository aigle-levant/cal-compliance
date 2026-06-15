import os
from dotenv import load_dotenv

from supabase import create_client
from langchain_ollama import OllamaEmbeddings

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

embeddings = OllamaEmbeddings(
    model="bge-m3"
)

TEST_CASES = [
    {
        "query": "What is Accreditation?",
        "expected": "8 CCR § 1"
    },
    {
        "query": "What is an Appeals Board?",
        "expected": "8 CCR § 1"
    },
    {
        "query": "What is a Claims Administrator?",
        "expected": "8 CCR § 1"
    },
    {
        "query": "What is an Agreed Medical Evaluator?",
        "expected": "8 CCR § 1"
    },
    {
        "query": "What is a Qualified Medical Evaluator?",
        "expected": "8 CCR § 1"
    },
    {
        "query": "What is a Panel QME?",
        "expected": "8 CCR § 1"
    },
    {
        "query": "What is a Treating Physician?",
        "expected": "8 CCR § 1"
    },
    {
        "query": "Appointment of QMEs",
        "expected": "8 CCR § 10"
    }
]


def search(query, top_k=10):
    vector = embeddings.embed_query(query)

    result = supabase.rpc(
        "match_compliance_chunks",
        {
            "query_embedding": vector,
            "match_count": top_k
        }
    ).execute()

    return result.data or []


def evaluate():
    top1 = 0
    top3 = 0
    top5 = 0

    total = len(TEST_CASES)

    for test in TEST_CASES:

        query = test["query"]
        expected = test["expected"]

        print("\n" + "=" * 80)
        print(query)
        print("=" * 80)

        results = search(query)

        citations = [
            row["citation"]
            for row in results
        ]

        for idx, row in enumerate(results[:5], start=1):

            print(
                f"{idx}. "
                f"{row['citation']} "
                f"({row['similarity']:.4f})"
            )

        if len(citations) > 0 and citations[0] == expected:
            top1 += 1

        if expected in citations[:3]:
            top3 += 1

        if expected in citations[:5]:
            top5 += 1

    print("\n")
    print("=" * 80)
    print("RETRIEVAL REPORT")
    print("=" * 80)

    print(
        f"Top-1 Accuracy: "
        f"{top1}/{total} "
        f"({100*top1/total:.1f}%)"
    )

    print(
        f"Top-3 Accuracy: "
        f"{top3}/{total} "
        f"({100*top3/total:.1f}%)"
    )

    print(
        f"Top-5 Accuracy: "
        f"{top5}/{total} "
        f"({100*top5/total:.1f}%)"
    )


if __name__ == "__main__":
    evaluate()