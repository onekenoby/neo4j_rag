import os
import streamlit as st
from neo4j import GraphDatabase
import google.generativeai as genai
import networkx as nx
from pyvis.network import Network
import streamlit.components.v1 as components
from io import StringIO

# CONFIG
os.environ["GEMINI_API_KEY"] = "AIzaSyBCdgHWrwSfxuYV1Bv_UtN2ZMKmAsOAujI"
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

model = genai.GenerativeModel(model_name="models/gemini-2.0-flash")

NEO4J_URI = "bolt://127.0.0.1:7690"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "onekenoby"

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

st.set_page_config(page_title="Advanced Neo4j + Gemini Chatbot", layout="wide")
st.title("🎬 Movie Graph-RAG Chatbot with Visualization")

if "history" not in st.session_state:
    st.session_state.history = []

def convert_to_cypher(user_query):
    prompt = f"""
You are an expert Cypher generator.

Convert the following user question into a valid Cypher query to retrieve data from a Neo4j database about movies.

Rules:
- ONLY output the Cypher query.
- NO explanation, NO comments, NO triple backticks.
- The query MUST start with MATCH, OPTIONAL MATCH or MERGE.
- Use WHERE, RETURN, ORDER BY, LIMIT clauses.
- Labels: Movie, Person
- Relationships: ACTED_IN, DIRECTED, PRODUCED, IN_GENRE

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
        records = result.data()
        context = ", ".join([str(record.values()) for record in records])
        return context, records

def visualize_graph(records):
    G = nx.Graph()

    for record in records:
        nodes = []

        for value in record.values():
            # Handle Nodes
            if hasattr(value, 'get'):
                if value.get('name'):
                    label = value.get('name')
                elif value.get('title'):
                    label = value.get('title')
                else:
                    label = str(value)
                G.add_node(label)
                nodes.append(label)

        # Create edges between nodes
        if len(nodes) >= 2:
            for i in range(len(nodes)):
                for j in range(i + 1, len(nodes)):
                    G.add_edge(nodes[i], nodes[j])

    net = Network(height="550px", width="100%", notebook=False)
    net.from_nx(G)

    html_data = net.generate_html()
    components.html(html_data, height=600, scrolling=True)


def query_with_context_and_generate_response(user_query):
    try:
        cypher_query = convert_to_cypher(user_query)
        context, records = query_with_cypher(cypher_query)

        if not context:
            return cypher_query, "I'm sorry, no data was found in the Neo4j database for your question.", records

        prompt = f"""
Use the following data from Neo4j to answer the user question.

Context:
{context}

User Question:
{user_query}

Answer:
"""
        response = model.generate_content(prompt)
        return cypher_query, response.text, records

    except ValueError as e:
        return "", str(e), []

user_query = st.text_input("Ask a movie-related question:")

if user_query:
    with st.spinner("Thinking..."):
        cypher_query, answer, records = query_with_context_and_generate_response(user_query)
        st.session_state.history.append((user_query, cypher_query, answer))
        st.markdown(f"**Generated Cypher Query:** `{cypher_query}`")
        st.markdown(f"**Answer:** {answer}")

        if records and any("type(r)" in record for record in records[0]):
            visualize_graph(records)

if st.session_state.history:
    st.markdown("---")
    st.markdown("### Chat History")
    for q, c, a in reversed(st.session_state.history):
        st.markdown(f"**Q:** {q}")
        st.markdown(f"**Cypher Query:** `{c}`")
        st.markdown(f"**A:** {a}")
