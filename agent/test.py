from langchain_ollama import OllamaEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings

import numpy as np


QUERY = "What is an Agreed Medical Evaluator?"


def cosine_similarity(a, b):
    a = np.array(a)
    b = np.array(b)

    return np.dot(a, b) / (
        np.linalg.norm(a) * np.linalg.norm(b)
    )


print("Loading embeddings...\n")

ollama_embeddings = OllamaEmbeddings(
    model="bge-m3"
)

hf_embeddings = HuggingFaceEmbeddings(
    model_name="BAAI/bge-m3"
)

print("Generating embeddings...\n")

ollama_vector = ollama_embeddings.embed_query(
    QUERY
)

hf_vector = hf_embeddings.embed_query(
    QUERY
)

print("=" * 60)
print("VECTOR INFORMATION")
print("=" * 60)

print(
    f"Ollama dimension: {len(ollama_vector)}"
)

print(
    f"HuggingFace dimension: {len(hf_vector)}"
)

similarity = cosine_similarity(
    ollama_vector,
    hf_vector
)

print(
    f"Cosine similarity: {similarity:.6f}"
)

print()

if len(ollama_vector) != len(hf_vector):
    print(
        "❌ Dimension mismatch. "
        "Do not switch models."
    )

elif similarity > 0.99:
    print(
        "✅ Embeddings are effectively identical."
    )
    print(
        "You can likely replace "
        "OllamaEmbeddings with "
        "HuggingFaceEmbeddings "
        "without re-embedding."
    )

elif similarity > 0.95:
    print(
        "⚠️ Very similar but not identical."
    )
    print(
        "Run retrieval tests before deploying."
    )

else:
    print(
        "❌ Embeddings differ significantly."
    )
    print(
        "Do NOT switch without re-embedding."
    )