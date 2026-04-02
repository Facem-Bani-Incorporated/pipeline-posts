import streamlit as st
import requests
import os
import json
from datetime import datetime
from moviepy.editor import TextClip, ImageClip, concatenate_videoclips, ColorClip, CompositeVideoClip
import glob  # Pentru curățenie

# --- CONFIGURARE INTERFAȚĂ ---
st.set_page_config(page_title="DailyHistory Full-Auto", page_icon="🎬", layout="centered")
st.title("👑 DailyHistory Full-Auto Video Engine")

# --- VERIFICARE CHEI API (Din Railway Variables) ---
groq_key = os.getenv("GROQ_API_KEY")
pexels_key = os.getenv("PEXELS_API_KEY")

if not groq_key or not pexels_key:
    st.error("⚠️ Lipsesc cheile API in Railway! Ai nevoie de GROQ_API_KEY si PEXELS_API_KEY in tab-ul Variables.")
    st.stop()

# --- PROMPTUL PENTRU VIRALITATE (SEO & Structură) ---
SYSTEM_PROMPT = """You are an elite social media strategist for "DailyHistory". Your goal is MAXIMIZING VIEWS, PROFIT, and ENGAGEMENT.
Given a historical event, generate highly viral content. Respond strictly in VALID JSON format.

{
  "title": "Short, extremely clickbaity title",
  "script": "Narration script (30-60s). Must start with a massive HOOK (e.g., 'They lied to you about...'). Keep sentences punchy.",
  "slides": [
    {"time": "0-3s", "text": "Viral Hook Overlay", "image_query": "high contrast dramatic image search term"}
  ],
  "posts": {
    "tiktok": "Engaging caption with a call to action + top trending SEO hashtags for the algorithm.",
    "instagram": "Aesthetic caption focusing on storytelling + explore page optimized hashtags.",
    "youtube": "Clickable title + heavy keyword-rich description for YouTube Search.",
    "facebook": "Conversational post designed to trigger comments.",
    "twitter": "Controversial or mind-blowing hook thread starter under 280 chars."
  }
}"""


# --- FUNCȚII PENTRU API-URI ---

def generate_groq_content(topic, api_key):
    """Cere de la Groq scriptul și postările SEO"""
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

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        return json.loads(response.json()["choices"][0]["message"]["content"])
    except Exception as e:
        raise Exception(f"Eroare la apelul Groq: {e}")


def get_image_url(query, pexels_key):
    """Caută o imagine relevantă pe Pexels (Verticală 9:16)"""
    # Adăugăm "vertical" la căutare pentru a obține imagini bune de TikTok
    url = f"https://api.pexels.com/v1/search?query={query}&per_page=1&orientation=portrait"
    headers = {"Authorization": pexels_key}

    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        if data['photos']:
            return data['photos'][0]['src']['large']
    except:
        pass  # Dacă pică căutarea, punem fundal negru
    return None


# --- FUNCȚIA PENTRU GENERARE VIDEO (Optimizată pentru Cloud) ---

def create_video(slides, output_filename="video_final.mp4"):
    """Generează videoclipul vertical 9:16 din slide-uri"""
    clips = []

    for i, slide in enumerate(slides):
        img_url = get_image_url(slide['image_query'], pexels_key)

        # 1. Creează fundalul (poza sau negru)
        if img_url:
            resp = requests.get(img_url, timeout=20)
            temp_img_name = f"temp_img_{i}.jpg"
            with open(temp_img_name, "wb") as f:
                f.write(resp.content)
            # Resize și Crop pentru a umple formatul 1080x1920
            bg = ImageClip(temp_img_name).set_duration(4).resize(height=1920).set_position('center')
        else:
            bg = ColorClip(size=(1080, 1920), color=(0, 0, 0)).set_duration(4)

        # 2. Adaugă textul overlay
        # NOTA: Folosim o setare specifică pentru Cloud ca să nu crape dacă lipsește ImageMagick full
        try:
            txt = TextClip(slide['text'], fontsize=80, color='white', font='Arial-Bold',
                           method='caption', size=(900, None), align='center').set_duration(4).set_position('center')
            video_slide = CompositeVideoClip([bg, txt], size=(1080, 1920))
        except:
            # Plan B: Dacă textul e o problemă, punem doar poza
            st.warning(f"Atenție: Nu am putut pune text pe slide-ul {i + 1}. Am folosit doar poza.")
            video_slide = CompositeVideoClip([bg], size=(1080, 1920))

        clips.append(video_slide)

    # 3. Compilează video-ul final
    with st.spinner("💥 Compilăm fișierul video final mp4..."):
        final_video = concatenate_videoclips(clips, method="compose")
        final_video.write_videofile(output_filename, fps=24, codec="libx264", audio=False)  # audio=False momentan

    return output_filename


def cleanup():
    """Șterge fișierele temporare pentru scalare curată"""
    for f in glob.glob("temp_img_*.jpg"):
        os.remove(f)


# --- LOGICA DE RULARE ÎN UI ---

topic = st.text_input("Ce s-a întâmplat azi în istorie?", placeholder="Ex: Prima aselenizare, 1969")

if st.button("🚀 GENEREAZĂ TOTUL: VIDEO & POSTĂRI"):
    if not topic:
        st.warning("Te rog scrie un topic!")
    else:
        try:
            # Cleanup preventiv
            cleanup()

            # 1. Groq Generare
            with st.spinner("1/3 Creierul Groq Llama 3.3 scrie scriptul viral..."):
                result = generate_groq_content(topic, groq_key)

            # 2. MoviePy Generare
            with st.spinner("2/3 Creăm videoclipul (slideshow vertical + text)..."):
                video_path = create_video(result['slides'])

                # Afișăm video-ul în interfață
                st.video(video_path)

                # Buton de download pentru video
                with open(video_path, "rb") as file:
                    st.download_button(label="📥 DESCARCĂ VIDEO GATA DE POSTARE",
                                       data=file, file_name="history_video.mp4", mime="video/mp4")

            # 3. Afișare Postări SEO
            with st.spinner("3/3 Pregătim caption-urile SEO..."):
                st.markdown("---")
                st.subheader("📱 Caption-uri Gata de Copy-Paste")
                platforms = result.get("posts", {})
                if platforms:
                    tabs = st.tabs(list(platforms.keys()))
                    for idx, (platform_name, post_text) in enumerate(platforms.items()):
                        with tabs[idx]:
                            st.code(post_text, language=None)

            # Cleanup final
            cleanup()

        except Exception as e:
            st.error(f"⚠️ A apărut o eroare neașteptată: {e}")
            cleanup()