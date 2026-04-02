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
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

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
            "temperature": 0.75,
            "max_tokens": 3500,
            "response_format": {"type": "json_object"},
        },
        timeout=30,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return json.loads(content)


# ═══════════════════════════════════════════════════════════════
# CONTENT GENERATION PROMPTS
# ═══════════════════════════════════════════════════════════════
SYSTEM_PROMPT = """You are an elite social media content creator for DailyHistory, 
a viral history brand. Your content gets MILLIONS of views because you:

1. Write HOOKS that stop the scroll instantly (first 2 seconds = everything)
2. Use psychological triggers: curiosity gaps, contrarian takes, emotional stakes
3. Structure for RETENTION: hook → tension → payoff → twist/CTA
4. Know SEO inside out: trending sounds, optimal posting times, algorithm hacks

Respond in VALID JSON only. No markdown, no backticks, no extra text.

JSON structure:
{
  "title": "short punchy title for the video (max 60 chars)",
  "hook": "the first line people see/hear - must stop the scroll (max 15 words)",
  "slides": [
    {
      "text_overlay": "bold text shown on screen (max 12 words, impactful)",
      "narration": "what the voiceover/text says for this segment (1-2 sentences)",
      "duration_sec": 4,
      "image_search": "precise search query for a dramatic relevant image"
    }
  ],
  "tiktok_description": "EXACTLY under 3000 characters. Must include: hook line, key facts teased (not spoiled), strong CTA, then exactly 5 hashtags. Format: engaging text first, then hashtags at the end separated by spaces. The description should make people NEED to watch. Use line breaks for readability.",
  "instagram_description": "optimized for Instagram Reels, under 2200 chars, 20-30 hashtags mixed (big + niche)",
  "youtube_title": "YouTube Shorts title, max 100 chars, SEO keyword-rich",
  "youtube_description": "YouTube Shorts description with keywords, 2-3 paragraphs, relevant tags",
  "facebook_post": "Facebook post text, conversational, question-based for comments",
  "twitter_post": "Tweet under 280 chars, provocative/surprising angle, 2-3 hashtags",
  "seo_keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"]
}

RULES:
- Slides: 4-6 slides for slideshow, 5-8 for video format
- Total video duration: 30-60 seconds (sweet spot for algorithm)
- TikTok description: MUST be under 3000 characters total, EXACTLY 5 hashtags
- Hashtags must be currently trending + niche relevant (mix of 100K-1M and 1M-100M usage)
- Hook must create a CURIOSITY GAP - never give the answer in the hook
- End with a "follow for more" or controversial opinion CTA
- All content in English
- Think like a creator with 1M+ followers"""


def generate_content(topic: str, format_type: str) -> dict:
    """Generate all social media content from a topic."""
    today = datetime.date.today().strftime("%B %d")
    slide_count = "4-6" if format_type == "Slideshow" else "5-8"

    user_prompt = f"""Today is {today}. Create viral content about: {topic}

Format: {format_type} ({slide_count} slides)
Make it absolutely VIRAL. The hook should be impossible to scroll past.
Remember: TikTok description MUST be under 3000 chars with EXACTLY 5 hashtags."""

    return call_groq(SYSTEM_PROMPT, user_prompt)


# ═══════════════════════════════════════════════════════════════
# IMAGE HELPERS
# ═══════════════════════════════════════════════════════════════
def download_image(query: str, idx: int = 0) -> Image.Image:
    """Try to fetch a relevant image from Wikimedia Commons, fallback to gradient."""
    try:
        url = "https://commons.wikimedia.org/w/api.php"
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": f"File: {query}",
            "gsrlimit": "3",
            "prop": "imageinfo",
            "iiprop": "url|mime",
            "iiurlwidth": "1080",
            "format": "json",
        }
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})

        for page_id, page in pages.items():
            info = page.get("imageinfo", [{}])[0]
            mime = info.get("mime", "")
            if "image" in mime and "svg" not in mime:
                img_url = info.get("thumburl") or info.get("url")
                if img_url:
                    img_resp = requests.get(img_url, timeout=10)
                    img = Image.open(BytesIO(img_resp.content)).convert("RGB")
                    return img
    except Exception:
        pass

    # Fallback: dramatic gradient
    return create_gradient_bg(idx)


def create_gradient_bg(idx: int = 0) -> Image.Image:
    """Create a cinematic gradient background."""
    palettes = [
        [(15, 12, 8), (45, 25, 12)],
        [(8, 15, 25), (12, 30, 50)],
        [(20, 8, 8), (50, 15, 15)],
        [(8, 18, 12), (15, 40, 25)],
        [(18, 10, 25), (35, 18, 50)],
        [(20, 18, 10), (50, 42, 15)],
    ]
    c1, c2 = palettes[idx % len(palettes)]
    img = Image.new("RGB", (VIDEO_W, VIDEO_H))
    draw = ImageDraw.Draw(img)
    for y in range(VIDEO_H):
        r = int(c1[0] + (c2[0] - c1[0]) * y / VIDEO_H)
        g = int(c1[1] + (c2[1] - c1[1]) * y / VIDEO_H)
        b = int(c1[2] + (c2[2] - c1[2]) * y / VIDEO_H)
        draw.line([(0, y), (VIDEO_W, y)], fill=(r, g, b))
    return img


def add_text_to_image(
    img: Image.Image,
    text: str,
    position: str = "center",
    font_size: int = 64,
    color: str = "white",
    shadow: bool = True,
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

    # Word wrap
    max_chars = max(18, VIDEO_W // (font_size // 2 + 2))
    lines = textwrap.wrap(text, width=max_chars)
    line_height = font_size + 12

    total_h = len(lines) * line_height
    if position == "center":
        start_y = (VIDEO_H - total_h) // 2
    elif position == "top":
        start_y = 120
    else:
        start_y = VIDEO_H - total_h - 180

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = (VIDEO_W - tw) // 2
        y = start_y + i * line_height

        # Shadow / outline
        if shadow:
            for ox in range(-3, 4):
                for oy in range(-3, 4):
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
# VIDEO / SLIDESHOW CREATION
# ═══════════════════════════════════════════════════════════════
def create_slideshow(slides: list, title: str) -> str:
    """Create a slideshow video with Ken Burns effect."""
    clips = []

    for i, slide in enumerate(slides):
        duration = slide.get("duration_sec", 5)
        text = slide.get("text_overlay", "")

        # Get background image
        bg_img = download_image(slide.get("image_search", title), i)
        bg_img = bg_img.resize((VIDEO_W, VIDEO_H), Image.LANCZOS)
        bg_img = add_darkening_overlay(bg_img, 0.5)
        bg_img = add_vignette(bg_img)

        # Add text
        final_img = add_text_to_image(bg_img, text, position="center", font_size=72)

        # Add DailyHistory watermark
        final_img = add_text_to_image(
            final_img, "@DailyHistory", position="top", font_size=32, color="#c8a44e"
        )

        # Save frame
        frame_path = str(OUTPUT_DIR / f"frame_{i}.png")
        final_img.save(frame_path, quality=95)

        # Create clip with subtle zoom (Ken Burns)
        clip = ImageClip(frame_path).with_duration(duration)

        # Gentle zoom in
        zoom_factor = 1.08
        clip = clip.resized(
            lambda t: 1 + (zoom_factor - 1) * t / duration
        )

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

    output_path = str(OUTPUT_DIR / f"dailyhistory_{datetime.date.today()}.mp4")
    final.write_videofile(
        output_path,
        fps=FPS,
        codec="libx264",
        audio=False,
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
        duration = slide.get("duration_sec", 5)
        text = slide.get("text_overlay", "")

        # Use uploaded clip if available, else create image-based slide
        if uploaded_clips and i < len(uploaded_clips) and uploaded_clips[i] is not None:
            try:
                base_clip = VideoFileClip(uploaded_clips[i]).subclipped(0, min(duration, VideoFileClip(uploaded_clips[i]).duration))
                base_clip = base_clip.resized(height=VIDEO_H).cropped(
                    x_center=base_clip.w // 2, width=VIDEO_W
                )
            except Exception:
                bg_img = download_image(slide.get("image_search", title), i)
                bg_img = bg_img.resize((VIDEO_W, VIDEO_H), Image.LANCZOS)
                bg_img = add_darkening_overlay(bg_img, 0.5)
                frame_path = str(OUTPUT_DIR / f"vframe_{i}.png")
                bg_img.save(frame_path)
                base_clip = ImageClip(frame_path).with_duration(duration)
        else:
            bg_img = download_image(slide.get("image_search", title), i)
            bg_img = bg_img.resize((VIDEO_W, VIDEO_H), Image.LANCZOS)
            bg_img = add_darkening_overlay(bg_img, 0.5)
            bg_img = add_vignette(bg_img)
            frame_path = str(OUTPUT_DIR / f"vframe_{i}.png")
            bg_img.save(frame_path)
            base_clip = ImageClip(frame_path).with_duration(duration)

        clips.append(base_clip)

    final = concatenate_videoclips(clips, method="compose")
    output_path = str(OUTPUT_DIR / f"dailyhistory_video_{datetime.date.today()}.mp4")
    final.write_videofile(output_path, fps=FPS, codec="libx264", audio=False, preset="medium", threads=2, logger=None)

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
    with gr.Blocks(theme=THEME, css=CSS, title="DailyHistory Pipeline") as app:

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
            label="♪ TikTok Description (copy this exactly)",
            lines=8,
            show_copy_button=True,
            interactive=False,
            elem_classes=["platform-box"],
        )
        tiktok_chars = gr.Textbox(label="Character count", interactive=False)

        # ── OUTPUT: OTHER PLATFORMS ──
        gr.Markdown("---")
        gr.Markdown("### ④ Other Platforms — Copy & Post")

        with gr.Tab("Instagram"):
            ig_desc = gr.Textbox(
                label="◻ Instagram Reels Description",
                lines=6, show_copy_button=True, interactive=False,
            )

        with gr.Tab("YouTube Shorts"):
            yt_title = gr.Textbox(
                label="▶ YouTube Title", show_copy_button=True, interactive=False,
            )
            yt_desc = gr.Textbox(
                label="▶ YouTube Description",
                lines=5, show_copy_button=True, interactive=False,
            )

        with gr.Tab("Facebook"):
            fb_post = gr.Textbox(
                label="f Facebook Post",
                lines=4, show_copy_button=True, interactive=False,
            )

        with gr.Tab("X / Twitter"):
            tw_post = gr.Textbox(
                label="𝕏 Tweet",
                lines=3, show_copy_button=True, interactive=False,
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
    )