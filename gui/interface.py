import streamlit as st
from agent import answer_question

def main():
    # --------------------------------------------------
    # Page Configuration
    # --------------------------------------------------
    st.set_page_config(
        page_title="CCR Compliance Agent",
        page_icon="⚖️",
        layout="wide"
    )

    # --------------------------------------------------
    # Header
    # --------------------------------------------------
    st.title("⚖️ CCR Compliance Agent")

    st.markdown(
        "Ask questions about the California Code of Regulations (CCR).\n\n"
        "The assistant retrieves relevant regulations from a vector database, "
        "grounds responses in retrieved text, and provides citations."
    )

    st.info("Educational use only. Responses are not legal advice.")

    # --------------------------------------------------
    # Sidebar
    # --------------------------------------------------
    with st.sidebar:
        st.header("About")
        st.markdown(
            "**Features**\n"
            "- CCR Retrieval-Augmented Generation (RAG)\n"
            "- Semantic Search\n"
            "- Citation Grounding\n"
            "- Query Expansion\n"
            "- Metadata-Aware Retrieval"
        )

        st.divider()
        st.subheader("Example Questions")

        examples = [
            "What is an AME?",
            "What is a comprehensive medical legal evaluation?",
            "What is the role of the Appeals Board?",
            "What regulations apply to workplace injury reporting?",
            "Explain civil penalty investigations."
        ]

        for ex in examples:
            st.caption(f"• {ex}")

    # --------------------------------------------------
    # Chat State & History
    # --------------------------------------------------
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # --------------------------------------------------
    # User Input & Assistant Response
    # --------------------------------------------------
    if question := st.chat_input("Ask a CCR compliance question..."):
        
        # Append and display user message
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        # Generate and display assistant response
        with st.chat_message("assistant"):
            with st.spinner("Searching California regulations..."):
                try:
                    result = answer_question(question)
                    
                    answer = result.get("answer", "")
                    sources = result.get("sources", [])
                    matches = result.get("matches", [])

                    st.markdown(answer)

                    # Display Citations
                    if sources:
                        st.divider()
                        st.subheader("Citations")
                        for source in sources:
                            st.markdown(f"- **{source}**")

                    # Display Retrieval Debug Info
                    if matches:
                        with st.expander("Retrieved Regulations"):
                            for i, match in enumerate(matches, start=1):
                                citation = match.get("citation", "Unknown")
                                similarity = round(match.get("similarity", 0), 3)

                                st.markdown(f"### {i}. {citation}")
                                st.caption(f"Similarity: {similarity}")

                                metadata = {
                                    "title": match.get("title_number"),
                                    "division": match.get("division_number"),
                                    "chapter": match.get("chapter_number"),
                                    "article": match.get("article_number"),
                                    "section": match.get("section_number")
                                }
                                st.json(metadata)

                                st.text_area(
                                    label=f"chunk_{i}",
                                    value=match.get("text", ""),
                                    height=180,
                                    disabled=True
                                )

                    # Append assistant response to state
                    st.session_state.messages.append({"role": "assistant", "content": answer})

                except Exception as e:
                    error_message = f"Error: {str(e)}"
                    st.error(error_message)
                    st.session_state.messages.append({"role": "assistant", "content": error_message})

    # --------------------------------------------------
    # Footer
    # --------------------------------------------------
    st.divider()
    st.caption("CCR Compliance Agent • RAG + Supabase + Gemini + BGE-M3")

if __name__ == "__main__":
    main()