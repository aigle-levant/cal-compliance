import streamlit as st

from agent import answer_question


st.set_page_config(
    page_title="Cal Compliance Agent",
    layout="wide"
)


st.title("Cal Compliance Agent")

st.markdown(
    """
Ask questions about the Californian Law.

The assistant retrieves relevant sections,
grounds answers in retrieved regulations,
and provides citations for transparency.
"""
)

st.info(
    "Educational use only. Responses are not legal advice."
)

with st.sidebar:

    st.header("About")

    st.markdown(
        """
**Features**

- RAG-based compliance assistant
- Semantic retrieval
- Citation-grounded responses
- Supabase vector database
- BGE-M3 embeddings
- Qwen generation model
"""
    )

    st.divider()

    st.subheader("Example Questions")

    examples = [
        "What is an AME?",
        "What is the Appeals Board?",
        "What is a comprehensive medical legal evaluation?",
        "Explain civil penalty investigations."
    ]

    for example in examples:
        st.caption(f"• {example}")


if "messages" not in st.session_state:
    st.session_state.messages = []


for message in st.session_state.messages:

    with st.chat_message(message["role"]):
        st.markdown(message["content"])


question = st.chat_input(
    "Ask me a compliance question..."
)

if question:

    st.session_state.messages.append(
        {
            "role": "user",
            "content": question
        }
    )

    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):

        with st.spinner(
            "Searching regulations..."
        ):

            try:

                result = answer_question(question)

                answer = result["answer"]
                sources = result["sources"]
                matches = result["matches"]

                st.markdown(answer)

                if sources:

                    st.divider()
                    st.subheader("Sources")

                    for source in sources:

                        citation = source.get(
                            "citation",
                            "Unknown Citation"
                        )

                        heading = source.get(
                            "section_heading"
                        )

                        url = source.get(
                            "source_url"
                        )

                        st.markdown(
                            f"**{citation}**"
                        )

                        if heading:
                            st.caption(heading)

                        if url:
                            st.caption(url)


                if matches:

                    with st.expander(
                        "Retrieved Regulations"
                    ):

                        for index, match in enumerate(
                            matches,
                            start=1
                        ):

                            citation = match.get(
                                "citation",
                                "Unknown Citation"
                            )

                            similarity = round(
                                match.get(
                                    "similarity",
                                    0
                                ),
                                3
                            )

                            text = match.get(
                                "text",
                                ""
                            )

                            st.markdown(
                                f"### {index}. {citation}"
                            )

                            st.caption(
                                f"Similarity: {similarity}"
                            )

                            st.text_area(
                                label=f"chunk_{index}",
                                value=text,
                                height=180,
                                disabled=True
                            )

                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": answer
                    }
                )

            except Exception as exc:

                st.error(
                    f"Error: {str(exc)}"
                )

st.divider()

st.caption(
    "Cal Compliance Agent, at your service!"
)