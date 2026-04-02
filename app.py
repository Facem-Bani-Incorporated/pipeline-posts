"""
DailyHistory Content Pipeline
─────────────────────────────
Gradio web UI → Groq (Llama 3.3) → Video/Slideshow → Auto-post or manual
Deploy on Railway: set GROQ_API_KEY env var, `python app.py`
"""

import os, json, re, textwrap, tempfile, math, datetime, urllib.request, shutil
from pathlib import Path
from io import BytesIO

import gradio as gr
import requests
from PIL import Image, ImageDraw, ImageFont

# ── moviepy ──
from moviepy import (
    ImageClip, TextClip, CompositeVideoClip, VideoFileClip,
    concatenate_videoclips, AudioFileClip, ColorClip,
    vfx
)

# ═══════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "qwen/qwen3-32b"

OUTPUT_DIR = Path(tempfile.mkdtemp(prefix="dailyhistory_"))
VIDEO_W, VIDEO_H = 1080, 1920  # 9:16 vertical
FPS = 30

# ═══════════════════════════════════════════════════════════════
# GROQ HELPER
# ═══════════════════════════════════════════════════════════════
def call_groq(system_prompt: str, user_prompt: str) -> dict:
    """Call Groq API and return parsed JSON."""
    api_key = GROQ_API_KEY or os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set! Add it in Railway environment variables.")

    resp = requests.post(
        GROQ_URL,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        json={
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.6,
            "max_completion_tokens": 8192,
            "top_p": 0.95,
            "response_format": {"type": "json_object"},
        },
        timeout=60,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    # qwen3 may include <think>...</think> tags, strip them
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    return json.loads(content)


# ═══════════════════════════════════════════════════════════════
# CONTENT GENERATION PROMPTS
# ═══════════════════════════════════════════════════════════════
SYSTEM_PROMPT = """You are an elite social media content creator for DailyHistory, a viral history brand with millions of followers.

Your job: turn a historical event into SCROLL-STOPPING content.

Respond in VALID JSON only. No markdown, no backticks, no preamble, no explanation.

JSON structure:
{
  "title": "short punchy title (max 60 chars)",
  "hook": "the opening line that stops the scroll (max 15 words, curiosity gap)",
  "slides": [
    {
      "text_overlay": "2-4 sentences telling THIS PART of the story. Write it like a dramatic narrator. Each slide continues the story from the previous one. The viewer should be able to read these slides and understand the FULL story. Be specific with names, dates, numbers, dramatic details.",
      "duration_sec": 9,
      "image_search": "simple 2-3 word image search query (e.g. 'Titanic ship' or 'Pope John Paul')"
    }
  ],
  "tiktok_description": "A LONG, engaging description (2500-3000 characters). Structure: dramatic hook paragraph, then retell the story with fascinating details the video didn't cover, include surprising facts, end with a thought-provoking question and CTA. Then exactly 5 viral hashtags. Must feel like a mini-article that adds VALUE beyond the video.",
  "instagram_description": "engaging caption under 2200 chars with storytelling + 25-30 hashtags (mix of big 1M+ and niche 100K-500K tags)",
  "youtube_title": "SEO-rich YouTube Shorts title, max 100 chars, includes year and key terms",
  "youtube_description": "3 paragraphs: story summary, historical context, CTA. Include relevant search keywords naturally.",
  "facebook_post": "conversational, starts with a question, tells a condensed version of the story, asks for engagement in comments",
  "twitter_post": "under 280 chars, most shocking single fact from the story, 2-3 hashtags",
  "seo_keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"]
}

CRITICAL RULES:
- SLIDES TEXT: Each slide's text_overlay must be 2-4 full sentences that TELL THE STORY. NOT generic titles like "A Life of Service". Write actual narrative: "On April 2, 2005, at 9:37 PM, Pope John Paul II spoke his final words: 'Let me go to the house of the Father.' Two billion people around the world watched in silence."
- Generate 7-9 slides, each 8-10 seconds. Total: 60-90 seconds.
- TIKTOK DESCRIPTION: Must be 2500-3000 characters. This is a mini-article, not a caption. Tell extra facts, behind-the-scenes details, things the video didn't mention. Make people save the post.
- EXACTLY 5 hashtags on TikTok, placed at the very end.
- image_search must be SHORT and SPECIFIC: "Titanic sinking", "Berlin Wall fall", "Moon landing 1969". Max 4 words.
- Hook must create a CURIOSITY GAP.
- All content in English.
- Be DRAMATIC but FACTUALLY ACCURATE. Use real numbers, real names, real quotes when possible."""


def generate_content(topic: str, format_type: str) -> dict:
    """Generate all social media content from a topic."""
    today = datetime.date.today().strftime("%B %d")
    slide_count = "7-9" if format_type == "Slideshow" else "8-10"

    user_prompt = f"""Today is {today}. Create viral content about: {topic}

Format: {format_type} ({slide_count} slides, each 8-10 seconds, total 60-90 seconds)

IMPORTANT REMINDERS:
- Each slide text_overlay = 2-4 FULL SENTENCES telling the story. NOT titles. NOT headings. Actual dramatic narrative text.
- TikTok description = 2500-3000 characters minimum. Write a real mini-article.
- image_search = SHORT query, max 4 words, specific historical terms.
- 5 hashtags on TikTok, at the very end.

DO NOT write generic slide text like "A Life of Service" or "Remembering a Legend". 
WRITE the actual story: specific facts, dates, names, dramatic moments, quotes."""

    return call_groq(SYSTEM_PROMPT, user_prompt)


# ═══════════════════════════════════════════════════════════════
# IMAGE HELPERS
# ═══════════════════════════════════════════════════════════════
def download_image(query: str, idx: int = 0) -> Image.Image:
    """Fetch image: Pexels first, Wikimedia fallback, gradient last resort."""
    api_key = PEXELS_API_KEY or os.environ.get("PEXELS_API_KEY", "")

    search_queries = [
        query,
        " ".join(query.split()[:3]),
        " ".join(query.split()[:2]),
    ]

    # Try Pexels first
    if api_key:
        for sq in search_queries:
            img = _try_pexels(sq, api_key)
            if img:
                return img

    # Fallback: Wikimedia
    for sq in search_queries:
        img = _try_wikimedia(sq)
        if img:
            return img

    return create_gradient_bg(idx)


def _try_pexels(query: str, api_key: str) -> Image.Image | None:
    """Fetch a portrait-oriented image from Pexels."""
    try:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": api_key},
            params={
                "query": query,
                "per_page": 5,
                "orientation": "portrait",
                "size": "large",
            },
            timeout=10,
        )
        if resp.status_code != 200:
            return None

        photos = resp.json().get("photos", [])
        if not photos:
            return None

        # Pick the best portrait photo
        for photo in photos:
            src = photo.get("src", {})
            # portrait is 800x1200, large2x is bigger
            img_url = src.get("portrait") or src.get("large") or src.get("original")
            if img_url:
                img_resp = requests.get(img_url, timeout=10)
                if img_resp.status_code == 200 and len(img_resp.content) > 10000:
                    img = Image.open(BytesIO(img_resp.content)).convert("RGB")
                    if img.size[0] >= 400 and img.size[1] >= 400:
                        return img
    except Exception:
        pass
    return None


def _try_wikimedia(query: str) -> Image.Image | None:
    """Try Wikimedia Commons API for an image."""
    try:
        url = "https://commons.wikimedia.org/w/api.php"
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": f"File: {query}",
            "gsrlimit": "5",
            "prop": "imageinfo",
            "iiprop": "url|mime|size",
            "iiurlwidth": "1200",
            "format": "json",
        }
        resp = requests.get(url, params=params, timeout=8)
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})

        for page_id, page in pages.items():
            info = page.get("imageinfo", [{}])[0]
            mime = info.get("mime", "")
            width = info.get("width", 0)
            if "image" in mime and "svg" not in mime and width >= 400:
                img_url = info.get("thumburl") or info.get("url")
                if img_url:
                    img_resp = requests.get(img_url, timeout=8)
                    if img_resp.status_code == 200 and len(img_resp.content) > 5000:
                        img = Image.open(BytesIO(img_resp.content)).convert("RGB")
                        if img.size[0] >= 200 and img.size[1] >= 200:
                            return img
    except Exception:
        pass
    return None


def create_gradient_bg(idx: int = 0) -> Image.Image:
    """Create a visible, cinematic gradient background — NOT black."""
    palettes = [
        [(45, 30, 20), (120, 60, 30)],      # warm bronze
        [(20, 35, 60), (50, 90, 140)],       # deep blue
        [(50, 20, 20), (130, 40, 40)],       # crimson
        [(20, 45, 35), (40, 110, 70)],       # forest green
        [(40, 25, 55), (100, 50, 130)],      # royal purple
        [(55, 45, 20), (140, 110, 40)],      # golden
        [(30, 30, 40), (80, 80, 120)],       # slate
        [(50, 25, 10), (130, 70, 30)],       # copper
    ]
    c1, c2 = palettes[idx % len(palettes)]
    img = Image.new("RGB", (VIDEO_W, VIDEO_H))
    draw = ImageDraw.Draw(img)
    for y in range(VIDEO_H):
        t = y / VIDEO_H
        # Add slight curve for more dramatic gradient
        t = t * t * (3 - 2 * t)  # smoothstep
        r = int(c1[0] + (c2[0] - c1[0]) * t)
        g = int(c1[1] + (c2[1] - c1[1]) * t)
        b = int(c1[2] + (c2[2] - c1[2]) * t)
        draw.line([(0, y), (VIDEO_W, y)], fill=(r, g, b))
    return img


def add_text_to_image(
    img: Image.Image,
    text: str,
    position: str = "center",
    font_size: int = 64,
    color: str = "white",
    shadow: bool = True,
    text_bg: bool = False,
) -> Image.Image:
    """Add styled text overlay to an image."""
    img = img.copy().resize((VIDEO_W, VIDEO_H), Image.LANCZOS)
    draw = ImageDraw.Draw(img)

    # Try to load a good font, fallback to default
    font = None
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, font_size)
                break
            except Exception:
                continue
    if font is None:
        font = ImageFont.load_default()

    # Word wrap — keep text well inside margins (80% of width)
    usable_width = int(VIDEO_W * 0.75)
    max_chars = max(18, int(usable_width / (font_size * 0.52)))
    lines = textwrap.wrap(text, width=max_chars)
    line_height = int(font_size * 1.4)

    total_h = len(lines) * line_height
    if position == "center":
        start_y = (VIDEO_H - total_h) // 2
    elif position == "top":
        start_y = 120
    else:
        start_y = VIDEO_H - total_h - 180

    # Optional semi-transparent background behind text
    if text_bg and lines:
        padding = 50
        bg_top = start_y - padding
        bg_bottom = start_y + total_h + padding
        bg_overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        bg_draw = ImageDraw.Draw(bg_overlay)
        bg_draw.rounded_rectangle(
            [100, bg_top, VIDEO_W - 100, bg_bottom],
            radius=20,
            fill=(0, 0, 0, 170),
        )
        img = img.convert("RGBA")
        img = Image.alpha_composite(img, bg_overlay)
        img = img.convert("RGB")
        draw = ImageDraw.Draw(img)

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = (VIDEO_W - tw) // 2
        y = start_y + i * line_height

        # Shadow / outline for readability
        if shadow:
            for ox in range(-2, 3):
                for oy in range(-2, 3):
                    if ox == 0 and oy == 0:
                        continue
                    draw.text((x + ox, y + oy), line, font=font, fill=(0, 0, 0))

        draw.text((x, y), line, font=font, fill=color)

    return img


def add_darkening_overlay(img: Image.Image, opacity: float = 0.55) -> Image.Image:
    """Add a dark overlay to make text more readable."""
    img = img.copy()
    overlay = Image.new("RGBA", img.size, (0, 0, 0, int(255 * opacity)))
    img = img.convert("RGBA")
    img = Image.alpha_composite(img, overlay)
    return img.convert("RGB")


def add_vignette(img: Image.Image) -> Image.Image:
    """Add cinematic vignette effect."""
    img = img.copy().convert("RGBA")
    vignette = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(vignette)
    cx, cy = img.size[0] // 2, img.size[1] // 2
    max_r = math.sqrt(cx**2 + cy**2)
    for r_step in range(100, 0, -1):
        r = max_r * r_step / 100
        alpha = int(180 * (1 - (r_step / 100) ** 2))
        alpha = max(0, min(255, alpha))
        bbox = [cx - r, cy - r, cx + r, cy + r]
        draw.ellipse(bbox, fill=(0, 0, 0, alpha))
    img = Image.alpha_composite(img, vignette)
    return img.convert("RGB")


# ═══════════════════════════════════════════════════════════════
# BACKGROUND MUSIC
# ═══════════════════════════════════════════════════════════════
def create_ambient_music(duration_sec: float) -> str:
    """Create a subtle ambient background track using pydub."""
    try:
        from pydub import AudioSegment
        from pydub.generators import Sine
        import random

        # Create layered ambient pad
        duration_ms = int(duration_sec * 1000)

        # Base drone — low C note
        base = Sine(130.81).to_audio_segment(duration=duration_ms).apply_gain(-28)

        # Harmonic layer — G note
        harmony = Sine(196.00).to_audio_segment(duration=duration_ms).apply_gain(-32)

        # High shimmer — E note
        shimmer = Sine(329.63).to_audio_segment(duration=duration_ms).apply_gain(-36)

        # Sub bass
        sub = Sine(65.41).to_audio_segment(duration=duration_ms).apply_gain(-30)

        # Mix all layers
        mix = base.overlay(harmony).overlay(shimmer).overlay(sub)

        # Fade in/out for cinematic feel
        fade_ms = min(3000, duration_ms // 4)
        mix = mix.fade_in(fade_ms).fade_out(fade_ms)

        # Overall volume down so it's background
        mix = mix.apply_gain(-8)

        music_path = str(OUTPUT_DIR / "ambient_bg.wav")
        mix.export(music_path, format="wav")
        return music_path
    except Exception as e:
        print(f"Music generation error: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
# VIDEO / SLIDESHOW CREATION
# ═══════════════════════════════════════════════════════════════
def create_slideshow(slides: list, title: str) -> str:
    """Create a slideshow video with Ken Burns effect."""
    clips = []

    for i, slide in enumerate(slides):
        duration = slide.get("duration_sec", 9)
        text = slide.get("text_overlay", "")

        # Get background image
        bg_img = download_image(slide.get("image_search", title), i)
        bg_img = bg_img.resize((VIDEO_W, VIDEO_H), Image.LANCZOS)
        bg_img = add_darkening_overlay(bg_img, 0.25)
        bg_img = add_vignette(bg_img)

        # Add story text with semi-transparent background
        final_img = add_text_to_image(
            bg_img, text, position="center", font_size=44, text_bg=True
        )

        # Add DailyHistory watermark
        final_img = add_text_to_image(
            final_img, "@DailyHistory", position="top", font_size=32, color="#c8a44e"
        )

        # Save frame
        frame_path = str(OUTPUT_DIR / f"frame_{i}.png")
        final_img.save(frame_path, quality=95)

        # Create clip (no zoom to keep text within safe margins)
        clip = ImageClip(frame_path).with_duration(duration)

        clips.append(clip)

    # Add transitions by cross-dissolving
    final_clips = []
    for i, clip in enumerate(clips):
        if i > 0:
            clip = clip.with_effects([vfx.CrossFadeIn(0.5)])
        if i < len(clips) - 1:
            clip = clip.with_effects([vfx.CrossFadeOut(0.5)])
        final_clips.append(clip)

    final = concatenate_videoclips(final_clips, method="compose")

    # Add background music
    total_duration = final.duration
    music_path = create_ambient_music(total_duration)
    if music_path:
        try:
            audio = AudioFileClip(music_path).with_duration(total_duration)
            final = final.with_audio(audio)
        except Exception as e:
            print(f"Audio attach error: {e}")

    output_path = str(OUTPUT_DIR / f"dailyhistory_{datetime.date.today()}.mp4")
    final.write_videofile(
        output_path,
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        threads=2,
        logger=None,
    )

    # Cleanup
    for clip in final_clips:
        clip.close()

    return output_path


def create_video_clip(slides: list, title: str, uploaded_clips: list = None) -> str:
    """Create a video with uploaded clips + text overlays."""
    clips = []

    for i, slide in enumerate(slides):
        duration = slide.get("duration_sec", 8)
        text = slide.get("text_overlay", "")

        bg_img = download_image(slide.get("image_search", title), i)
        bg_img = bg_img.resize((VIDEO_W, VIDEO_H), Image.LANCZOS)
        bg_img = add_darkening_overlay(bg_img, 0.3)
        bg_img = add_vignette(bg_img)
        frame_path = str(OUTPUT_DIR / f"vframe_{i}.png")
        bg_img.save(frame_path)
        base_clip = ImageClip(frame_path).with_duration(duration)

        clips.append(base_clip)

    final = concatenate_videoclips(clips, method="compose")

    # Add background music
    total_duration = final.duration
    music_path = create_ambient_music(total_duration)
    if music_path:
        try:
            audio = AudioFileClip(music_path).with_duration(total_duration)
            final = final.with_audio(audio)
        except Exception as e:
            print(f"Audio attach error: {e}")

    output_path = str(OUTPUT_DIR / f"dailyhistory_video_{datetime.date.today()}.mp4")
    final.write_videofile(output_path, fps=FPS, codec="libx264", audio_codec="aac", preset="medium", threads=2, logger=None)

    for clip in clips:
        clip.close()

    return output_path


# ═══════════════════════════════════════════════════════════════
# AUTO-POST FUNCTIONS
# ═══════════════════════════════════════════════════════════════
def post_to_twitter(text: str) -> str:
    """Post to X/Twitter if API keys are configured."""
    bearer = os.environ.get("TWITTER_BEARER_TOKEN")
    if not bearer:
        return "❌ MANUAL — Twitter API keys not configured"
    try:
        resp = requests.post(
            "https://api.twitter.com/2/tweets",
            headers={"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"},
            json={"text": text},
            timeout=10,
        )
        if resp.ok:
            return f"✅ POSTED — Tweet ID: {resp.json().get('data', {}).get('id')}"
        return f"❌ FAILED — {resp.json().get('detail', resp.text)}"
    except Exception as e:
        return f"❌ ERROR — {e}"


def post_to_facebook(text: str) -> str:
    """Post to Facebook Page if configured."""
    token = os.environ.get("FACEBOOK_PAGE_TOKEN")
    page_id = os.environ.get("FACEBOOK_PAGE_ID")
    if not token or not page_id:
        return "❌ MANUAL — Facebook Page token not configured"
    try:
        resp = requests.post(
            f"https://graph.facebook.com/v19.0/{page_id}/feed",
            json={"message": text, "access_token": token},
            timeout=10,
        )
        if resp.ok:
            return f"✅ POSTED — Post ID: {resp.json().get('id')}"
        return f"❌ FAILED — {resp.json().get('error', {}).get('message', resp.text)}"
    except Exception as e:
        return f"❌ ERROR — {e}"


# ═══════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ═══════════════════════════════════════════════════════════════
def run_pipeline(topic: str, format_type: str, progress=gr.Progress()):
    """Main pipeline: topic → content → video → post descriptions."""

    if not topic.strip():
        raise gr.Error("Scrie un topic! Ex: 'Titanic sank in 1912'")

    progress(0.1, desc="🧠 Generating content with Groq...")
    try:
        content = generate_content(topic, format_type)
    except Exception as e:
        raise gr.Error(f"Groq API error: {e}")

    progress(0.4, desc="🎨 Creating images & frames...")

    slides = content.get("slides", [])
    title = content.get("title", topic)

    progress(0.5, desc=f"🎬 Building {format_type.lower()}...")
    try:
        if format_type == "Slideshow":
            video_path = create_slideshow(slides, title)
        else:
            video_path = create_video_clip(slides, title)
    except Exception as e:
        video_path = None
        print(f"Video creation error: {e}")

    progress(0.8, desc="📱 Preparing platform posts...")

    # Auto-post where possible
    twitter_status = post_to_twitter(content.get("twitter_post", ""))
    facebook_status = post_to_facebook(content.get("facebook_post", ""))

    # Validate TikTok description
    tiktok_desc = content.get("tiktok_description", "")
    if len(tiktok_desc) > 3000:
        tiktok_desc = tiktok_desc[:2995] + "..."

    progress(1.0, desc="✅ Done!")

    # Build posting status
    posting_status = f"""═══════════════════════════════════════
  📊 POSTING STATUS
═══════════════════════════════════════

  𝕏  Twitter:     {twitter_status}
  f  Facebook:    {facebook_status}
  ♪  TikTok:      📋 MANUAL — Copy description below, upload video
  ◻  Instagram:   📋 MANUAL — Copy description below, upload reel
  ▶  YouTube:     📋 MANUAL — Copy title + description below
  @  Threads:     📋 MANUAL — Copy description below

═══════════════════════════════════════
  💡 To enable auto-posting, add API keys
     in Railway environment variables:
     TWITTER_BEARER_TOKEN, FACEBOOK_PAGE_TOKEN
═══════════════════════════════════════"""

    return (
        video_path,                                      # video player
        content.get("title", ""),                         # title
        content.get("hook", ""),                          # hook
        tiktok_desc,                                      # tiktok desc
        f"{len(tiktok_desc)} / 3000 chars",              # tiktok char count
        content.get("instagram_description", ""),         # instagram
        content.get("youtube_title", ""),                 # yt title
        content.get("youtube_description", ""),           # yt desc
        content.get("facebook_post", ""),                 # facebook
        content.get("twitter_post", ""),                  # twitter
        posting_status,                                   # status
        json.dumps(content.get("slides", []), indent=2),  # slides JSON
    )


# ═══════════════════════════════════════════════════════════════
# GRADIO UI
# ═══════════════════════════════════════════════════════════════
THEME = gr.themes.Base(
    primary_hue=gr.themes.Color(
        c50="#fdf8ef", c100="#fcefd5", c200="#f8dca6",
        c300="#f3c56e", c400="#edb244", c500="#c8a44e",
        c600="#a88532", c700="#886a24", c800="#6e5520",
        c900="#5a451c", c950="#332710",
    ),
    neutral_hue=gr.themes.Color(
        c50="#f5f0e8", c100="#ebe3d6", c200="#d6ccb8",
        c300="#b8a890", c400="#9a8a6e", c500="#7a6e58",
        c600="#5e5442", c700="#443c2e", c800="#2a2418",
        c900="#1a1610", c950="#111009",
    ),
    font=["Source Serif 4", "Georgia", "serif"],
    font_mono=["JetBrains Mono", "monospace"],
)

CSS = """
.gradio-container { max-width: 960px !important; }
.main-title {
    text-align: center; font-size: 2.2em; font-weight: 600;
    color: #c8a44e !important; letter-spacing: 0.08em;
    text-transform: uppercase; margin-bottom: 0 !important;
    font-family: 'Playfair Display', Georgia, serif !important;
}
.sub-title {
    text-align: center; font-size: 0.85em; letter-spacing: 0.3em;
    text-transform: uppercase; color: #7a6e58 !important;
    margin-top: 4px !important;
}
footer { display: none !important; }
.platform-box { border-left: 3px solid #c8a44e !important; }
"""

def build_ui():
    with gr.Blocks(title="DailyHistory Pipeline") as app:

        gr.Markdown("<h1 class='main-title'>DailyHistory</h1>")
        gr.Markdown("<p class='sub-title'>Content Automation Pipeline</p>")
        gr.Markdown("---")

        # ── INPUT ──
        with gr.Group():
            gr.Markdown("### ① What happened today?")
            with gr.Row():
                topic_input = gr.Textbox(
                    label="Topic (English)",
                    placeholder='e.g. "The Titanic sank on April 15, 1912" or "First email ever sent"',
                    lines=2,
                    scale=3,
                )
                format_type = gr.Radio(
                    ["Slideshow", "Video Clip"],
                    value="Slideshow",
                    label="Format",
                    scale=1,
                )

            generate_btn = gr.Button(
                "⚡ GENERATE EVERYTHING",
                variant="primary",
                size="lg",
            )

        # ── OUTPUT: VIDEO ──
        gr.Markdown("---")
        gr.Markdown("### ② Your Video")
        video_output = gr.Video(label="Generated Video — download and upload to platforms")

        with gr.Row():
            title_output = gr.Textbox(label="📌 Title", interactive=False)
            hook_output = gr.Textbox(label="🪝 Hook (first line)", interactive=False)

        # ── OUTPUT: TIKTOK ──
        gr.Markdown("---")
        gr.Markdown("### ③ TikTok — Copy & Post")
        tiktok_desc = gr.Textbox(
            label="♪ TikTok Description (select all + copy)",
            lines=8,
            interactive=False,
        )
        tiktok_chars = gr.Textbox(label="Character count", interactive=False)

        # ── OUTPUT: OTHER PLATFORMS ──
        gr.Markdown("---")
        gr.Markdown("### ④ Other Platforms — Copy & Post")

        with gr.Tab("Instagram"):
            ig_desc = gr.Textbox(
                label="◻ Instagram Reels Description",
                lines=6, interactive=False,
            )

        with gr.Tab("YouTube Shorts"):
            yt_title = gr.Textbox(
                label="▶ YouTube Title", interactive=False,
            )
            yt_desc = gr.Textbox(
                label="▶ YouTube Description",
                lines=5, interactive=False,
            )

        with gr.Tab("Facebook"):
            fb_post = gr.Textbox(
                label="f Facebook Post",
                lines=4, interactive=False,
            )

        with gr.Tab("X / Twitter"):
            tw_post = gr.Textbox(
                label="𝕏 Tweet",
                lines=3, interactive=False,
            )

        # ── POSTING STATUS ──
        gr.Markdown("---")
        gr.Markdown("### ⑤ Posting Status")
        posting_status = gr.Textbox(
            label="Auto-post results",
            lines=14, interactive=False,
        )

        # ── SLIDES DATA ──
        with gr.Accordion("🔧 Slides JSON (for CapCut import)", open=False):
            slides_json = gr.Code(language="json", label="Slides data")

        # ── CONNECT ──
        generate_btn.click(
            fn=run_pipeline,
            inputs=[topic_input, format_type],
            outputs=[
                video_output, title_output, hook_output,
                tiktok_desc, tiktok_chars,
                ig_desc, yt_title, yt_desc,
                fb_post, tw_post,
                posting_status, slides_json,
            ],
        )

        # ── FOOTER ──
        gr.Markdown("---")
        gr.Markdown(
            "<p style='text-align:center; color:#5a451c; font-size:0.8em; letter-spacing:0.15em'>"
            "DAILYHISTORY PIPELINE — GROQ + LLAMA 3.3 70B — DEPLOY ON RAILWAY</p>"
        )

    return app


# ═══════════════════════════════════════════════════════════════
# LAUNCH
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = build_ui()
    app.launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("PORT", 7860)),
        share=False,
        theme=THEME,
        css=CSS,
    )