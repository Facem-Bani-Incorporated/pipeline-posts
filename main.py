import os
import streamlit as st
import requests
import json
from datetime import datetime
import glob

# --- 🎬 IMPORTURI MOVIEPY v2.0 ---
from moviepy import TextClip, ImageClip, ColorClip, CompositeVideoClip, concatenate_videoclips
from moviepy.config import configure_settings

# Configurare ImageMagick pentru Railway
configure_settings({"IMAGEMAGICK_BINARY": "/usr/bin/convert"})

# --- 👑 CONFIGURARE UI ---
st.set_page_config(page_title="DailyHistory Viral Engine", page_icon="🔥", layout="centered")
st.title("👑 DailyHistory Viral Engine")

# --- 🔑 CHEI API ---
groq_key = os.getenv("GROQ_API_KEY")
pexels_key = os.getenv("PEXELS_API_KEY")

if not groq_key or not pexels_key:
    st.error("⚠️ Lipsesc cheile API! Verifică Variables în Railway (GROQ_API_KEY / PEXELS_API_KEY).")
    st.stop()

# --- 🧠 PROMPT SEO ---
SYSTEM_PROMPT = """You are a viral video strategist. Create a JSON response for a historical event.
Slides must have SHOCKING, SHORT text (max 6 words).
Format: {"title": "...", "slides": [{"text": "...", "image_query": "..."}], "posts": {"instagram": "..."}}"""


# --- ⚙️ FUNCȚII LOGICE ---

def get_image(query):
    url = f"https://api.pexels.com/v1/search?query={query}&per_page=1&orientation=portrait"
    headers = {"Authorization": pexels_key}
    try:
        r = requests.get(url, headers=headers, timeout=10).json()
        if r.get('photos'):
            return r['photos'][0]['src']['large']
    except:
        return None
    return None


def create_viral_video(slides, duration):
    clips = []
    for i, slide in enumerate(slides):
        img_url = get_image(slide['image_query'])

        # Fundal negru standard 1080x1920
        bg = ColorClip(size=(1080, 1920), color=(0, 0, 0)).with_duration(duration)

        if img_url:
            img_data = requests.get(img_url).content
            temp_name = f"temp_{i}.jpg"
            with open(temp_name, "wb") as f:
                f.write(img_data)
            # MoviePy 2.0: resized() și with_position()
            img_clip = ImageClip(temp_name).with_duration(duration).resized(width=1080).with_position("center")
            base = CompositeVideoClip([bg, img_clip])
        else:
            base = bg

        # Text Overlay Stil Profesional
        try:
            txt = TextClip(
                text=slide['text'],
                font_size=75,
                color='white',
                method='caption',
                size=(900, None)
            ).with_duration(duration).with_position("center")

            # Fundal negru pentru text (lizibilitate)
            txt_bg = ColorClip(size=(txt.w + 40, txt.h + 40), color=(0, 0, 0)).with_duration(duration)
            txt_bg = txt_bg.with_opacity(0.6).with_position("center")

            slide_clip = CompositeVideoClip([base, txt_bg, txt], size=(1080, 1920))
        except:
            slide_clip = base

        clips.append(slide_clip)

    final = concatenate_videoclips(clips, method="compose")
    output = "viral_history_video.mp4"
    final.write_videofile(output, fps=24, codec="libx264", audio=False)
    return output


def cleanup():
    for f in glob.glob("temp_*.jpg"):
        try:
            os.remove(f)
        except:
            pass


# --- 🚀 INTERFAȚA DE CONTROL ---
topic = st.text_input("Subiect istoric:", placeholder="Ex: Blestemul lui Tutankhamon")
format_v = st.radio("Viteză Slide-uri:", ["⚡ Rapid (2s)", "🎥 Poveste (4s)"])
dur = 2 if "Rapid" in format_v else 4

if st.button("🔥 GENEREAZĂ CLIPUL"):
    if topic:
        try:
            cleanup()
            # 1. Generare Script via Groq
            with st.spinner("🧠 Llama 3.3 concepe scriptul viral..."):
                res = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {groq_key}"},
                    json={
                        "model": "llama-3.3-70b-versatile",
                        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": topic}],
                        "response_format": {"type": "json_object"}
                    }
                ).json()
                data = json.loads(res['choices'][0]['message']['content'])

            # 2. Generare Video
            with st.spinner("🎬 Randăm video-ul (Pexels + MoviePy)..."):
                path = create_viral_video(data['slides'], dur)
                st.video(path)
                with open(path, "rb") as f:
                    st.download_button("📥 DESCARCĂ VIDEO", f, "viral_video.mp4", "video/mp4")

            # 3. SEO
            st.markdown("---")
            st.subheader("📱 Instagram/TikTok SEO")
            st.code(data['posts'].get('instagram', 'Descriere indisponibilă'), language=None)

            cleanup()
        except Exception as e:
            st.error(f"❌ Eroare: {e}")
            cleanup()
    else:
        st.warning("Te rog introdu un subiect!")