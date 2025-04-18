import os
import streamlit as st
from neo4j import GraphDatabase
import google.generativeai as genai

# === CONFIG ===
os.environ["GEMINI_API_KEY"] = "AIzaSyBCdgHWrwSfxuYV1Bv_UtN2ZMKmAsOAujI"
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

model = genai.GenerativeModel(model_name="models/gemini-2.0-flash")

NEO4J_URI = "bolt://127.0.0.1:7690"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "onekenoby"

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

st.set_page_config(page_title="Neo4j + Gemini Chatbot", layout="wide")
st.title("🎬 Movie RAG Chatbot with Neo4j + Gemini")

if "history" not in st.session_state:
    st.session_state.history = []

def convert_to_cypher(user_query):
    prompt = f"""
            Convert the following user question into a Cypher query to retrieve movie data from Neo4j.

            Rules:
            - ONLY output the Cypher query.
            - NO explanation, NO comments, NO triple backticks.
            - Output must start with MATCH, OPTIONAL MATCH or MERGE.

            Instructions:
            If the user question is NOT related to movies, reply exactly with:
            "I'm not allowed to reply outside of the movies domain."

            User Question:
            {user_query}

            Cypher Query:
            """
    response = model.generate_content(prompt)
    cypher_query = response.text.strip()
    cypher_query = cypher_query.replace("```cypher", "").replace("```", "").strip()

    if "I'm not allowed to reply" in cypher_query:
        raise ValueError("Sorry, I'm only able to answer questions about movies.")

    if not cypher_query.startswith(("MATCH", "OPTIONAL MATCH", "MERGE")):
        raise ValueError(f"Invalid Cypher generated: {cypher_query}")

    return cypher_query

def query_with_cypher(cypher_query):
    with driver.session() as session:
        result = session.run(cypher_query)
        values = []
        for record in result:
            for v in record.values():
                values.append(str(v))
        context = ", ".join(values)
        return context

def query_with_context_and_generate_response(user_query):
    try:
        cypher_query = convert_to_cypher(user_query)
        context = query_with_cypher(cypher_query)

        if not context:
            return "I'm sorry, no data was found in the Neo4j database for your question."

        prompt = f"""
                Use the following data from Neo4j to answer the user question.

                Instructions:
                - Always use ONLY the context provided.
                - List ALL items in the context without skipping any.
                - Be precise and complete.

                Context:
                {context}

                User Question:
                {user_query}

                Answer:
                """
        response = model.generate_content(prompt)
        return response.text

    except ValueError as e:
        return str(e)

user_query = st.text_input("Ask a movie-related question:")

if user_query:
    with st.spinner("Thinking..."):
        answer = query_with_context_and_generate_response(user_query)
        st.session_state.history.append((user_query, answer))
        st.markdown(f"**Answer:** {answer}")

if st.session_state.history:
    st.markdown("---")
    st.markdown("### Chat History")
    for q, a in reversed(st.session_state.history):
        st.markdown(f"**Q:** {q}")
        st.markdown(f"**A:** {a}")