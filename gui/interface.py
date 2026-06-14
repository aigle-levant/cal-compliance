import os
import streamlit as st
from supabase import create_client, Client
from langchain_google_genai import (
    GoogleGenAIEmbeddings,
    ChatGoogleGenerativeAI,
)
from langchain_postgres import PGVector

# -----------------------------
# PAGE CONFIG
# -----------------------------
st.set_page_config(
    page_title="CCR Compliance Assistant",
    page_icon="⚖️",
    layout="wide"
)

st.title("⚖️ California Compliance Assistant")
st.caption("Powered by Gemini + Supabase pgvector")

# -----------------------------
# ENV VARIABLES
# -----------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# -----------------------------
# CLIENTS
# -----------------------------
supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

embeddings = GoogleGenAIEmbeddings(
    model="models/text-embedding-004"
)

llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash",
    temperature=0.2
)

vector_store = PGVector(
    client=supabase,
    embedding=embeddings,
    table_name="documents",
    query_name="match_documents"
)

retriever = vector_store.as_retriever(
    search_kwargs={"k": 5}
)

# -----------------------------
# CHAT HISTORY
# -----------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# -----------------------------
# RAG FUNCTION
# -----------------------------
def ask_rag(question: str):
    # Note: get_relevant_documents is deprecated in newer LangChain versions, 
    # but kept here to match your original logic. (Use retriever.invoke(question) if needed).
    docs = retriever.get_relevant_documents(question)

    context = "\n\n".join(doc.page_content for doc in docs)

    prompt = f"""
    You are a California compliance assistant.
    Answer ONLY using the retrieved regulations.
    Rules:

    - Cite section numbers whenever possible.
    - Do not invent regulations.
    - If the answer is not present, say you do not know.
    - Keep answers concise but accurate.
    
    Context:
    {context}
    
    Question:
    {question}
    """
    
    response = llm.invoke(prompt)

    return response.content, docs

# -----------------------------
# USER INPUT & MAIN LOGIC
# -----------------------------
query = st.chat_input("Ask a compliance question...")

if query:
    # 1. Save and display user query
    st.session_state.messages.append({
        "role": "user",
        "content": query
    })

    with st.chat_message("user"):
        st.markdown(query)

    # 2. Process and display assistant response
    with st.chat_message("assistant"):
        with st.spinner("Searching regulations..."):
            try:
                answer, docs = ask_rag(query)
                st.markdown(answer)

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": answer
                })
            except Exception as e:
                st.error(str(e))
                docs = [] # Prevent NameError in the sidebar loop if RAG fails

    # -----------------------------
    # SOURCES SIDEBAR
    # -----------------------------
    st.sidebar.title("📚 Retrieved Sources")
    
    for doc in docs:
        section = doc.metadata.get("section_number", "Unknown")
        citation = doc.metadata.get("citation", "")
        heading = doc.metadata.get("section_heading", "")

        with st.sidebar.expander(f"§{section} {heading}"):
            st.caption(citation)
            st.markdown(doc.page_content[:2000])