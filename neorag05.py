
import os
import streamlit as st
from neo4j import GraphDatabase
import google.generativeai as genai
import networkx as nx
from pyvis.network import Network
import streamlit.components.v1 as components

from io import StringIO

# CONFIG
os.environ["GEMINI_API_KEY"] = "xxx"
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
            Convert the following user question into a Cypher query to retrieve movie data from Neo4j.

            Rules:
            - Output only Cypher query.
            - No explanation, no comments.
            - The query MUST start with MATCH, OPTIONAL MATCH or MERGE.

            Use labels: Person, Movie
            Use relationships: ACTED_IN, DIRECTED, PRODUCED, WROTE, FOLLOWS, REVIEWED

            If unrelated to movies reply exactly:
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
    import networkx as nx
    from pyvis.network import Network
    import streamlit.components.v1 as components

    G = nx.DiGraph()

    for record in records:
        start_node = None
        end_node = None
        rel_name = ""

        print("DEBUG record:", record)

        for key, value in record.items():
            if hasattr(value, 'get'):
                label = value.get('name') or value.get('title') or str(value)
                label_type = 'Node'
                if hasattr(value, 'labels') and value.labels:
                    label_type = list(value.labels)[0]
                G.add_node(label, label=label, group=label_type)

                if key.lower().startswith('p'):
                    start_node = label
                elif key.lower().startswith('m'):
                    end_node = label

            # CASE: r is a tuple like ({start}, 'ACTED_IN', {end})
            elif isinstance(value, tuple) and len(value) == 3:
                rel_name = value[1]

        if start_node and end_node and rel_name:
            G.add_edge(start_node, end_node, label=rel_name)
        else:
            print(f"WARNING: missing edge info in record: p={start_node}, m={end_node}, relType={rel_name}")

    net = Network(height="600px", width="100%", notebook=False, directed=True)
    net.from_nx(G)

    net.set_options("""
    var options = {
      "nodes": {
        "shape": "dot",
        "size": 16
      },
      "edges": {
        "arrows": {
          "to": {
            "enabled": true
          }
        },
        "font": {
          "size": 14,
          "align": "horizontal"
        }
      },
      "physics": {
        "barnesHut": {
          "gravitationalConstant": -30000,
          "centralGravity": 0.3,
          "springLength": 100,
          "springConstant": 0.04,
          "damping": 0.09,
          "avoidOverlap": 1
        },
        "minVelocity": 0.75
      }
    }
    """)

    for edge in net.edges:
        if 'label' in edge:
            edge['title'] = edge['label']
            edge['font'] = {'size': 14, 'align': 'horizontal'}

    html_data = net.generate_html()
    components.html(html_data, height=650, scrolling=True)









def query_with_context_and_generate_response(user_query):
    try:
        cypher_query = convert_to_cypher(user_query)
        context, records = query_with_cypher(cypher_query)

        if not context:
            return cypher_query, "No data found.", records

        prompt = f"""
                Use only this Neo4j context to answer the question.

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


user_query = st.text_input("Ask your movie-related question:")

if user_query:
    with st.spinner("Thinking..."):
        cypher_query, answer, records = query_with_context_and_generate_response(user_query)
        st.session_state.history.append((user_query, cypher_query, answer))
        st.markdown(f"**Cypher Query:** `{cypher_query}`")
        st.markdown(f"**Answer:** {answer}")

        if records:
            visualize_graph(records)

if st.session_state.history:
    st.markdown("---")
    st.markdown("### Chat History")
    for q, c, a in reversed(st.session_state.history):
        st.markdown(f"**Q:** {q}")
        st.markdown(f"**Cypher:** `{c}`")
        st.markdown(f"**A:** {a}")
