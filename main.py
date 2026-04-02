import os
import sys

# --- PATCH EXTREM PENTRU PILLOW ---
import PIL
import PIL.Image

if not hasattr(PIL.Image, 'ANTIALIAS'):
    try:
        PIL.Image.ANTIALIAS = PIL.Image.Resampling.LANCZOS
    except AttributeError:
        PIL.Image.ANTIALIAS = 1

try:
    import setuptools
except ImportError:
    os.system(f"{sys.executable} -m pip install setuptools")

import streamlit as st
import requests
import json
from datetime import datetime
import glob

# --- 🎬 SETĂRI MOVIEPY & IMAGEMAGICK ---
from moviepy.config import change_settings

change_settings({"IMAGEMAGICK_BINARY": "/usr/bin/convert"})
from moviepy.editor import TextClip, ImageClip, concatenate_videoclips, ColorClip, CompositeVideoClip

# --- 👑 UI: CONFIGURARE INTERFAȚĂ ---
st.set_page_config(page_title="DailyHistory Viral Engine", page_icon="🔥", layout="centered")
st.title("👑 DailyHistory Viral Engine")
st.markdown("Generare automată de clipuri 9:16 cu subtitrări profesionale și descrieri SEO perfecte.")

# --- 🔑 VERIFICARE CHEI API ---
groq_key = os.getenv("GROQ_API_KEY")
pexels_key = os.getenv("PEXELS_API_KEY")

if not groq_key or not pexels_key:
    st.error("⚠️ Lipsesc cheile API! Asigură-te că ai GROQ_API_KEY și PEXELS_API_KEY în Variables pe Railway.")
    st.stop()

# --- 🧠 CREIERUL SEO & RETENȚIE ---
SYSTEM_PROMPT = """You are a top-tier social media strategist and video producer. Your goal is MAXIMIZING VIEWS, RETENTION, and ENGAGEMENT.
Given a historical event, generate a highly viral short-form video concept. 

RULES FOR SLIDES (CRITICAL):
- 'text' must be PUNCHY and SHORT (Max 5-8 words per slide). People swipe if there's too much text!
- Make the text sound like a dramatic hook or shocking fact.

Respond strictly in VALID JSON format:
{
  "title": "Extremely clickbaity title",
  "slides": [
    {"text": "They lied to you...", "image_query": "dark mysterious historical background"},
    {"text": "In 1912, the unthinkable happened.", "image_query": "ocean disaster dramatic"},
    {"text": "But the real secret...", "image_query": "secret documents classified"}
  ],
  "posts": {
    "instagram": "Incredible hook + short storytelling + CTA (Save this!) + top explore page hashtags.",
    "tiktok": "Engaging caption + trending SEO hashtags for algorithm.",
    "youtube": "Title + keyword-rich description for YouTube Shorts search."
  }
}"""


# --- ⚙️ FUNCȚII GENERARE ---

def generate_groq_content(topic, api_key):
    today = datetime.now().strftime("%B %d")
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Today is {today}. Create a viral short video about: {topic}"}
        ],
        "temperature": 0.8,
        "response_format": {"type": "json_object"}
    }
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    return json.loads(response.json()["choices"][0]["message"]["content"])


def get_image_url(query, pexels_key):
    url = f"https://api.pexels.com/v1/search?query={query}&per_page=1&orientation=portrait"
    headers = {"Authorization": pexels_key}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        if data.get('photos'):
            return data['photos'][0]['src']['large']
    except:
        return None
    return None


def create_video(slides, duration_per_slide, output_filename="video_final.mp4"):
    clips = []

    for i, slide in enumerate(slides):
        img_url = get_image_url(slide['image_query'], pexels_key)

        # 1. Background Video/Image (1080x1920 fix pentru a nu crăpa)
        bg_black = ColorClip(size=(1080, 1920), color=(0, 0, 0)).set_duration(duration_per_slide)

        if img_url:
            resp = requests.get(img_url, timeout=20)
            temp_img = f"temp_img_{i}.jpg"
            with open(temp_img, "wb") as f:
                f.write(resp.content)
            # Punem poza peste fundalul negru, centrată
            img_clip = ImageClip(temp_img).set_duration(duration_per_slide).resize(width=1080).set_position('center')
            base_bg = CompositeVideoClip([bg_black, img_clip])
        else:
            base_bg = bg_black

        # 2. Text Overlay Profesional (Uriaș, Centrat, Alb, Bold)
        try:
            # Creăm textul efectiv
            txt_clip = TextClip(slide['text'], fontsize=85, color='white', font='Arial-Bold',
                                method='caption', size=(900, None), align='center')
            txt_clip = txt_clip.set_duration(duration_per_slide).set_position('center')

            # Creăm un fundal negru semi-transparent fix pe mărimea textului + puțin padding
            txt_bg = ColorClip(size=(txt_clip.w + 60, txt_clip.h + 40), color=(0, 0, 0))
            txt_bg = txt_bg.set_opacity(0.6).set_duration(duration_per_slide).set_position('center')

            # Compunem slide-ul final: Poza -> Cutie Neagră Transparentă -> Text
            video_slide = CompositeVideoClip([base_bg, txt_bg, txt_clip], size=(1080, 1920))
        except:
            # Fallback dacă pică TextClip
            video_slide = base_bg

        clips.append(video_slide)

    final_video = concatenate_videoclips(clips, method="compose")
    final_video.write_videofile(output_filename, fps=24, codec="libx264", audio=False)
    return output_filename


def cleanup():
    for f in glob.glob("temp_img_*.jpg"):
        try:
            os.remove(f)
        except:
            pass


# --- 🚀 ZONA DE COMANDĂ ---
st.subheader("1. Ce subiect atacăm azi?")
topic = st.text_input("Subiectul istoric:", placeholder="Ex: Căderea Imperiului Roman, Misterul Piramidelor, etc.")

st.subheader("2. Alege Formatul Clipului")
format_video = st.radio(
    "Cum vrei să se miște clipul?",
    ("⚡ Slideshow Rapid - Stil TikTok (2 secunde/slide)",
     "🎥 Documentar Poveste - Stil YouTube Shorts (4 secunde/slide)")
)
slide_duration = 2 if "Rapid" in format_video else 4

if st.button("🔥 GENEREAZĂ CLIPUL & SEO PERFECT 🔥", use_container_width=True):
    if not topic:
        st.error("❗ Scrie un subiect istoric mai întâi!")
    else:
        try:
            cleanup()

            # PASUL 1
            with st.spinner(f"🧠 Llama 3.3 scrie scriptul viral pentru '{topic}'..."):
                result = generate_groq_content(topic, groq_key)

            # PASUL 2
            with st.spinner("🎬 Randăm clipul profesional (Aplicăm filtre, text, poziționare)..."):
                video_path = create_video(result['slides'], slide_duration)

                st.success("✅ Clipul tău viral este GATA!")

                # Afișare Video + Buton Uriaș de Download
                st.video(video_path)
                with open(video_path, "rb") as file:
                    st.download_button(
                        label="📥 DESCARCĂ CLIPUL (.MP4)",
                        data=file,
                        file_name=f"Viral_History_{topic[:10].replace(' ', '_')}.mp4",
                        mime="video/mp4",
                        use_container_width=True
                    )

            # PASUL 3
            st.markdown("---")
            st.subheader("📈 Descrierile SEO & Hashtag-uri (Gata de Copy-Paste)")
            st.info(
                "Algoritmul a generat textele de mai jos pentru a maximiza algoritmul de căutare (SEO) pe fiecare platformă.")

            tabs = st.tabs(list(result['posts'].keys()))
            for idx, (plat, txt) in enumerate(result['posts'].items()):
                with tabs[idx]:
                    st.code(txt, language=None)

            cleanup()
        except Exception as e:
            st.error(f"❌ A apărut o eroare la randare: {e}")
            cleanup()