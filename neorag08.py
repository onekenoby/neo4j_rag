import os
import streamlit as st
from dotenv import load_dotenv
from neo4j import GraphDatabase
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAI
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from pyvis.network import Network
import streamlit.components.v1 as components
from langdetect import detect

# Load env variables
load_dotenv()
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Neo4j driver
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))

# Gemini LLM setup
llm = ChatGoogleGenerativeAI(model="gemini-pro", google_api_key=GOOGLE_API_KEY)
vision_llm = GoogleGenerativeAI(model="gemini-pro-vision", google_api_key=GOOGLE_API_KEY)

# Prompts
cypher_prompt = PromptTemplate.from_template("""
You are an expert Cypher engineer. Convert the user's natural language question into a Cypher query.
Try to return fields like title, name, and poster if they exist.
Only output the Cypher.

Question: {question}
Cypher:
""")
summary_prompt = PromptTemplate.from_template("""
Use the following database result to answer the user's question in the same language it was asked.

Language: {language}
Question: {question}
Result: {records}
Answer:
""")

cypher_chain = LLMChain(llm=llm, prompt=cypher_prompt)
summary_chain = LLMChain(llm=llm, prompt=summary_prompt)

# Language display mapping
language_flags = {
    "en": "English \U0001F1EC\U0001F1E7",
    "it": "Italiano \U0001F1EE\U0001F1F9",
    "fr": "Français \U0001F1EB\U0001F1F7",
    "es": "Español \U0001F1EA\U0001F1F8",
    "de": "Deutsch \U0001F1E9\U0001F1EA",
    "pt": "Português \U0001F1F5\U0001F1F9",
    "nl": "Nederlands \U0001F1F3\U0001F1F1"
}

# Streamlit UI
st.set_page_config(page_title="Gemini + Neo4j Movie Assistant", layout="wide")
st.title("Gemini + Neo4j Movie Assistant")

# Session State
if "chat_history" not in st.session_state:
    st.session_state.chat_history = {}

# User input
user_question = st.text_input("Ask something about movies or actors...")

# Manual language override (optional)
available_langs = list(language_flags.keys())
def_lang = detect(user_question) if user_question else "en"
manual_lang = st.selectbox("Choose language (or auto-detect):", options=["auto"] + available_langs, index=0)

if st.button("Ask") and user_question:
    language = detect(user_question) if manual_lang == "auto" else manual_lang

    if language not in st.session_state.chat_history:
        st.session_state.chat_history[language] = []

    with st.spinner("Generating Cypher with Gemini..."):
        cypher_query = cypher_chain.run(user_question)
        st.code(cypher_query, language="cypher")

    with driver.session() as session:
        try:
            result = session.run(cypher_query)
            records = [record.data() for record in result]
        except Exception as e:
            st.error(f"Neo4j error: {e}")
            records = []

    if records:
        with st.spinner("Generating answer with Gemini..."):
            answer = summary_chain.run({"language": language, "question": user_question, "records": records})
            st.success(answer)
            st.session_state.chat_history[language].append((user_question, answer))

        with st.expander("Posters (if available)"):
            for record in records:
                for k, v in record.items():
                    if isinstance(v, dict) and "title" in v and "poster" in v:
                        st.image(v["poster"], caption=v["title"], width=200)

        def draw_graph(records):
            net = Network(height="600px", width="100%", notebook=False)
            seen = set()
            for record in records:
                nodes = []
                for k, v in record.items():
                    if isinstance(v, dict) and "name" in v:
                        name = v["name"]
                        if name not in seen:
                            net.add_node(name, label=name)
                            seen.add(name)
                        nodes.append(name)
                if len(nodes) == 2:
                    net.add_edge(nodes[0], nodes[1])
            net.save_graph("graph.html")
            components.html(open("graph.html", "r").read(), height=600)

        with st.expander("Graph Visualization"):
            draw_graph(records)

        with st.expander("Generate a Scene with Gemini Pro Vision"):
            movie_titles = [v["title"] for r in records for v in r.values() if isinstance(v, dict) and "title" in v]
            if movie_titles:
                selected_title = st.selectbox("Pick a movie to visualize:", movie_titles)
                vision_prompt = f"Generate a cinematic poster-style image representing a scene from the movie '{selected_title}'."
                if st.button("Generate Scene Image"):
                    with st.spinner("Creating scene with Gemini Pro Vision..."):
                        response = vision_llm.invoke(vision_prompt)
                        st.image(response.image, caption=selected_title)
    else:
        st.warning("No results found.")

# Show chat history
with st.expander("Chat History"):
    for lang, chats in st.session_state.chat_history.items():
        flag_label = language_flags.get(lang, lang)
        st.subheader(f"Language: {flag_label}")
        for q, a in reversed(chats):
            st.markdown(f"**You:** {q}")
            st.markdown(f"**Gemini:** {a}")
