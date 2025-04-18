
import os
import streamlit as st
from neo4j import GraphDatabase
import google.generativeai as genai
import networkx as nx
from pyvis.network import Network
import streamlit.components.v1 as components
from io import StringIO
from langdetect import detect

# CONFIG
os.environ["GEMINI_API_KEY"] = "AIzaSyBCdgHWrwSfxuYV1Bv_UtN2ZMKmAsOAujI"
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

model = genai.GenerativeModel(model_name="models/gemini-2.0-flash")

NEO4J_URI = "bolt://127.0.0.1:7690"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "onekenoby"

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

st.set_page_config(page_title="Neo4j RAG Chatbot", layout="wide")
st.title("🎬 Neo4j RAG Chatbot with Graph Visualization")

if "history" not in st.session_state:
    st.session_state.history = []


def convert_to_cypher(user_query):
    prompt = f"""
    Convert the following user question into a Cypher query to retrieve movie data from Neo4j.

    Rules:
    - Output only Cypher query.
    - No explanation, no comments.
    - The query MUST start with MATCH, OPTIONAL MATCH, or MERGE.
    - Always RETURN full relationships, never only type(r). Example: RETURN p, r, m
    - NEVER use size((...)-[...]-()) syntax; always use COUNT {{ ... }} instead.
    - Use labels: Person, Movie
    - Use relationships: ACTED_IN, DIRECTED, PRODUCED, WROTE, FOLLOWS, REVIEWED

    If unrelated to movies reply exactly:
    "I'm not allowed to reply outside of the movies domain."

    User Question:
    {user_query}

    Cypher Query:
    """
    response = model.generate_content(prompt)
    cypher_query = response.text.strip().replace("```cypher", "").replace("```", "").strip()

    # Handle the "I'm not allowed..." case directly here
    if "I'm not allowed" in cypher_query:
        return cypher_query  # Return the message, don't raise an error

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
        for key, value in record.items():
            # Handle Nodes
            if hasattr(value, 'get'):
                label = value.get('name') or value.get('title') or str(value)
                label_type = 'Node'
                if hasattr(value, 'labels') and value.labels:
                    label_type = list(value.labels)[0]
                G.add_node(label, label=label, group=label_type)

            # Handle Neo4j Relationship Object
            elif hasattr(value, 'type'):
                rel_name = value.type
                start_node = value.start_node.get('name') or value.start_node.get('title') or str(value.start_node)
                end_node = value.end_node.get('name') or value.end_node.get('title') or str(value.end_node)
                G.add_edge(start_node, end_node, label=rel_name)

            # Handle Tuple (start, rel_name, end)
            elif isinstance(value, tuple) and len(value) == 3:
                rel_name = value[1]
                start_node = value[0].get('name') or value[0].get('title') or str(value[0])
                end_node = value[2].get('name') or value[2].get('title') or str(value[2])
                G.add_edge(start_node, end_node, label=rel_name)

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

    # Show edge labels as hover & center
    for edge in net.edges:
        if 'label' in edge:
            edge['title'] = edge['label']
            edge['font'] = {'size': 14, 'align': 'horizontal'}

    html_data = net.generate_html()
    components.html(html_data, height=650, scrolling=True)


def query_with_context_and_generate_response(user_query):
    cypher_query = convert_to_cypher(user_query)
    if "I'm not allowed" in cypher_query:
        user_lang = detect(user_query)
        lang_messages = {
            "it": "Non sono autorizzato a rispondere al di fuori del dominio dei film.",
            "en": "I'm not allowed to reply outside of the movies domain.",
            "es": "No estoy autorizado a responder fuera del dominio de las películas.",
            "fr": "Je ne suis pas autorisé à répondre en dehors du domaine des films.",
            "de": "Ich bin nicht berechtigt, außerhalb des Filmbereichs zu antworten.",
            # Add more languages as needed
        }
        answer = lang_messages.get(user_lang, lang_messages["en"]) #defaults to english if the language is not found.
        return None, answer, None
    context, records = query_with_cypher(cypher_query)
    user_language = detect(user_query)
    prompt = f"""
    Use the following Neo4j data to answer the user's question. Respond STRICTLY and ONLY in {user_language}.
    Neo4j Data: {context}
    User Question: {user_query}
    Answer in {user_language}:
    """
    response = model.generate_content(prompt)
    return cypher_query, response.text, records


user_query = st.text_input("Ask your question about movies:")

if user_query:
    with st.spinner("Thinking..."):
        cypher_query, answer, records = query_with_context_and_generate_response(user_query)
        if cypher_query is None:
            st.markdown(f"**Answer:** {answer}")
        else:
            st.session_state.history.append((user_query, cypher_query, answer))
            st.markdown(f"**Generated Cypher Query:** `{cypher_query}`")
            st.markdown(f"**Answer:** {answer}")
            if records:
                visualize_graph(records)



if st.session_state.history:
    st.markdown("---")
    st.markdown("### Chat History")
    for q, c, a in reversed(st.session_state.history):
        st.markdown(f"**Q:** {q}")
        st.markdown(f"**Cypher Query:** `{c}`")
        st.markdown(f"**A:** {a}")
