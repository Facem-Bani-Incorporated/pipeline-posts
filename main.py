import streamlit as st
import requests
import os
import json
from datetime import datetime

# 1. Configurare pagină (UI)
st.set_page_config(page_title="DailyHistory Viral", page_icon="📜", layout="centered")

# 2. Promptul agresiv pentru SEO și Viralitate
SYSTEM_PROMPT = """You are an elite social media strategist for "DailyHistory". Your goal is MAXIMIZING VIEWS and ENGAGEMENT.
Given a historical event, generate viral content. Respond strictly in VALID JSON format.

{
  "title": "Short, extremely clickbaity title",
  "script": "Narration script (30-60s). Must start with a massive HOOK (e.g., 'They lied to you about...'). Keep sentences punchy.",
  "slides": [
    {"time": "0-3s", "text": "Viral Hook Overlay", "image_query": "high contrast dramatic image search term"}
  ],
  "posts": {
    "tiktok": "Engaging caption with a call to action + top trending SEO hashtags.",
    "instagram": "Aesthetic caption focusing on storytelling + explore page optimized hashtags.",
    "youtube": "Clickable title + heavy keyword-rich description for YouTube Search.",
    "facebook": "Conversational post designed to trigger comments.",
    "twitter": "Controversial or mind-blowing hook thread starter under 280 chars."
  }
}"""


def generate_groq_content(topic, api_key):
    today = datetime.now().strftime("%B %d")
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Today is {today}. Create extremely viral content about: {topic}"}
        ],
        "temperature": 0.8,
        "response_format": {"type": "json_object"}
    }

    response = requests.post(url, headers=headers, json=payload)
    if response.status_code != 200:
        raise Exception(f"Eroare Groq: {response.text}")

    return json.loads(response.json()["choices"][0]["message"]["content"])


# --- INTERFAȚA WEB (UI) ---

st.title("👑 DailyHistory Viral Pipeline")
st.markdown(
    "Scrie evenimentul de azi, iar Groq îți generează scriptul video și postările SEO. Ai buton de **Copy** la fiecare text!")

# Preia cheia API din Environment Variables (Railway)
# Dacă vrei să testezi local pe PC, poți pune cheia temporar în locul lui None: os.getenv("GROQ_API_KEY", "gsk_cheia_ta...")
api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    st.error("⚠️ Nu am găsit GROQ_API_KEY. Setează variabila în secțiunea 'Variables' din Railway.")
    st.stop()

topic = st.text_input("Ce s-a întâmplat azi în istorie?", placeholder="Ex: Prima aselenizare, 1969")

if st.button("🚀 Generează Tot (SEO & Script)"):
    if not topic:
        st.warning("Te rog scrie un topic mai întâi!")
    else:
        with st.spinner("Creierul Groq Llama 3.3 scrie postările virale..."):
            try:
                result = generate_groq_content(topic, api_key)

                st.success("Generare completă!")

                # Afișare Script Video
                st.subheader(f"🎬 Video Script: {result.get('title', '')}")
                # st.code afișează textul frumos, cu un buton de COPY integrat în dreapta sus
                st.code(result.get("script", ""), language=None)

                st.markdown("---")
                st.subheader("📱 Postări pe platforme (Gata de Copy-Paste)")

                # Facem tab-uri pentru fiecare platformă (foarte elegant vizual)
                platforms = result.get("posts", {})
                if platforms:
                    tabs = st.tabs(list(platforms.keys()))
                    for idx, (platform_name, post_text) in enumerate(platforms.items()):
                        with tabs[idx]:
                            # Aici e magia: fiecare tab are textul lui cu buton de Copy
                            st.code(post_text, language=None)

                # Afișare idei de imagini pentru CapCut
                with st.expander("🔍 Vezi sugestiile de imagini pentru slide-uri"):
                    for slide in result.get("slides", []):
                        st.write(
                            f"**[{slide['time']}]** Overlay: *{slide['text']}* ➔ Caută poza: `{slide['image_query']}`")

            except Exception as e:
                st.error(f"A apărut o eroare: {e}")