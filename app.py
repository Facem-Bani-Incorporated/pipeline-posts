"""
DailyHistory Content Pipeline v3.0
───────────────────────────────────
TTS Voiceover + Short Punch Text + Ambient Music + Multi-platform
Groq (Qwen3 32B) → Edge TTS → MoviePy → Viral TikTok Content
"""

import os, json, re, textwrap, tempfile, math, datetime, asyncio
from pathlib import Path
from io import BytesIO

import gradio as gr
import requests
from PIL import Image, ImageDraw, ImageFont

from moviepy import (
    ImageClip, CompositeVideoClip, CompositeAudioClip,
    concatenate_videoclips, AudioFileClip, ColorClip,
    vfx
)

import edge_tts

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ═══════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "qwen/qwen3-32b"

OUTPUT_DIR = Path(tempfile.mkdtemp(prefix="dailyhistory_"))
VIDEO_W, VIDEO_H = 1080, 1920
FPS = 30

# TTS Voice options — dramatic male voices for dark history
VOICES = {
    "Guy (US, Deep)": "en-US-GuyNeural",
    "Ryan (UK, Documentary)": "en-GB-RyanNeural",
    "Christopher (US, Calm)": "en-US-ChristopherNeural",
    "William (AU, Unique)": "en-AU-WilliamNeural",
    "Liam (US, Storyteller)": "en-US-AndrewNeural",
}
DEFAULT_VOICE = "en-US-GuyNeural"

# ═══════════════════════════════════════════════════════════════
# TIKTOK WORD CENSOR
# ═══════════════════════════════════════════════════════════════
CENSOR_MAP = {
    "killed": "k!lled", "killing": "k!lling", "kill": "k!ll", "kills": "k!lls",
    "murder": "murd3r", "murdered": "murd3red", "murders": "murd3rs",
    "death": "d3ath", "deaths": "d3aths", "dead": "d3ad",
    "died": "d!ed", "die": "d!e", "dying": "dy!ng",
    "suicide": "su!c!de", "executed": "3xecuted", "execution": "3xecution",
    "assassinated": "a$$a$$inated", "assassination": "a$$a$$ination",
    "massacre": "ma$$acre", "massacred": "ma$$acred",
    "slaughter": "sl@ughter", "genocide": "g3noc!de",
    "holocaust": "h0locaust", "homicide": "h0mic!de",
    "beheaded": "beh3aded", "hanged": "h@nged", "strangled": "str@ngled",
    "stabbed": "st@bbed", "shot dead": "sh0t d3ad",
    "bomb": "b0mb", "bombs": "b0mbs", "bombed": "b0mbed", "bombing": "b0mbing",
    "explosion": "expl0sion", "nuclear": "nucle@r",
    "weapon": "we@pon", "weapons": "we@pons",
    "torture": "t0rture", "tortured": "t0rtured",
    "abuse": "@buse", "abused": "@bused",
    "rape": "r@pe", "raped": "r@ped",
    "slave": "sl@ve", "slaves": "sl@ves", "slavery": "sl@very",
    "drug": "dr*g", "drugs": "dr*gs",
    "cocaine": "c0caine", "overdose": "0verdose",
    "terrorist": "terr0rist", "terrorism": "terr0rism",
    "nazi": "n@zi", "nazis": "n@zis",
    "concentration camp": "c0ncentration c@mp",
    "war crime": "w@r cr!me", "ethnic cleansing": "ethn!c cleans!ng",
    "blood": "bl00d", "bloody": "bl00dy", "corpse": "c0rpse",
    "plague": "pl@gue", "pandemic": "p@ndemic", "virus": "v!rus",
    "crime": "cr!me", "criminal": "cr!minal",
    "prison": "pr!son", "prisoner": "pr!soner",
    "shooting": "sh00ting", "shooter": "sh00ter",
    "gun": "g*n", "guns": "g*ns",
    "victim": "v!ctim", "victims": "v!ctims",
    "atrocity": "@trocity", "atrocities": "@trocities",
    "disturbing": "d!sturbing",
}


def censor_text(text: str) -> str:
    if not text:
        return text
    sorted_words = sorted(CENSOR_MAP.keys(), key=len, reverse=True)
    for word in sorted_words:
        replacement = CENSOR_MAP[word]
        pattern = re.compile(re.escape(word), re.IGNORECASE)
        def _repl(m):
            o = m.group(0)
            if o.isupper(): return replacement.upper()
            if o[0].isupper(): return replacement[0].upper() + replacement[1:]
            return replacement
        text = pattern.sub(_repl, text)
    return text


def censor_content(content: dict) -> dict:
    for field in ["title", "hook", "comment_bait", "tiktok_description",
                   "instagram_description", "youtube_title", "youtube_description",
                   "facebook_post", "twitter_post"]:
        if field in content and isinstance(content[field], str):
            content[field] = censor_text(content[field])
    for slide in content.get("slides", []):
        if "punch_text" in slide:
            slide["punch_text"] = censor_text(slide["punch_text"])
    return content


def uncensor_for_tts(text: str) -> str:
    """Remove censor chars so TTS pronounces words normally."""
    replacements = [
        ("k!ll", "kill"), ("murd3r", "murder"), ("d3ath", "death"),
        ("d3ad", "dead"), ("d!ed", "died"), ("d!e", "die"), ("dy!ng", "dying"),
        ("su!c!de", "suicide"), ("3xecut", "execut"), ("a$$a$$in", "assassin"),
        ("ma$$acre", "massacre"), ("sl@ughter", "slaughter"), ("g3noc!de", "genocide"),
        ("h0locaust", "holocaust"), ("h0mic!de", "homicide"), ("beh3ad", "behead"),
        ("h@ng", "hang"), ("str@ngl", "strangl"), ("st@bb", "stabb"),
        ("sh0t", "shot"), ("bl00d", "blood"), ("w@r", "war"), ("we@pon", "weapon"),
        ("b0mb", "bomb"), ("expl0sion", "explosion"), ("nucle@r", "nuclear"),
        ("t0rture", "torture"), ("@buse", "abuse"), ("r@pe", "rape"),
        ("sl@ve", "slave"), ("ensl@ve", "enslave"), ("dr*g", "drug"),
        ("c0caine", "cocaine"), ("0verdos", "overdos"), ("terr0rist", "terrorist"),
        ("terr0rism", "terrorism"), ("n@zi", "nazi"), ("c0ncentration", "concentration"),
        ("c@mp", "camp"), ("extr3mist", "extremist"), ("prop@ganda", "propaganda"),
        ("bl00dy", "bloody"), ("c0rpse", "corpse"), ("pl@gue", "plague"),
        ("p@ndemic", "pandemic"), ("v!rus", "virus"), ("inf3ction", "infection"),
        ("cr!me", "crime"), ("cr!minal", "criminal"), ("pr!son", "prison"),
        ("@rrested", "arrested"), ("sh00ting", "shooting"), ("sh00ter", "shooter"),
        ("g*n", "gun"), ("v!ctim", "victim"), ("@trocit", "atrocit"),
        ("d!sturb", "disturb"), ("h0rrif", "horrif"), ("gru3some", "gruesome"),
    ]
    for censored, clean in replacements:
        text = text.replace(censored, clean)
        text = text.replace(censored.capitalize(), clean.capitalize())
    return text


# ═══════════════════════════════════════════════════════════════
# GROQ API
# ═══════════════════════════════════════════════════════════════
def call_groq(system_prompt: str, user_prompt: str) -> dict:
    api_key = GROQ_API_KEY or os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set!")

    models = [GROQ_MODEL, "llama-3.3-70b-versatile"]
    for model in models:
        try:
            body = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.7,
                "max_completion_tokens": 8192,
                "top_p": 0.95,
                "response_format": {"type": "json_object"},
            }
            if "qwen" in model:
                body["chat_template_kwargs"] = {"enable_thinking": False}

            resp = requests.post(
                GROQ_URL,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
                json=body, timeout=120,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
            return json.loads(content)
        except requests.exceptions.Timeout:
            print(f"Timeout with {model}, trying next...")
            continue
        except Exception as e:
            print(f"Error with {model}: {e}")
            if model == models[-1]:
                raise
            continue
    raise ValueError("All models failed")


# ═══════════════════════════════════════════════════════════════
# CONTENT GENERATION
# ═══════════════════════════════════════════════════════════════
SYSTEM_PROMPT = """You are the content brain behind DailyHistory, a 10M+ follower dark history TikTok brand.

CRITICAL: This video has VOICEOVER NARRATION. The voice tells the full story.
The text on screen is just SHORT PUNCH PHRASES — 3-8 words that hit hard while the voice explains.

Think of it like a documentary: the narrator talks, and bold text flashes key phrases on screen.

Respond in VALID JSON only. No markdown, no backticks.

JSON structure:
{
  "title": "short title max 60 chars",
  "hook": "opening hook max 12 words",
  "slides": [
    {
      "punch_text": "3-8 WORDS ONLY. Bold. Shocking. Like a headline that punches you. Examples: 'THEY BURIED IT ALIVE', 'THE REAL DEATH COUNT', '800,000 IN 100 DAYS', 'NOBODY WAS PUNISHED', 'THE COVERUP WORKED'",
      "narration": "Full voiceover script for this slide. 2-3 sentences. Dramatic, conversational, like telling someone at 2AM. This is what the voice SAYS while the punch text shows on screen. Include specific names, dates, numbers.",
      "duration_sec": 8,
      "image_search": "2-4 word image query",
      "text_color": "white or #FF4444 or #FFD700 — use RED for shocking reveals, GOLD for important names/dates, WHITE for narration"
    }
  ],
  "comment_bait": "provocative ending statement that forces comments",
  "tiktok_description": "2500-3000 chars mini-article with EXTRA details not in video + exactly 5 hashtags at end",
  "instagram_description": "under 2200 chars + 25-30 hashtags",
  "youtube_title": "SEO title max 100 chars with year",
  "youtube_description": "3 keyword-rich paragraphs",
  "facebook_post": "debate starter, opens with question",
  "twitter_post": "under 280 chars, most WTF fact, 2-3 hashtags",
  "seo_keywords": ["kw1", "kw2", "kw3", "kw4", "kw5"]
}

SLIDE STRUCTURE (9 slides):
- Slide 1: HOOK punch text (big, red/gold) + voice sets up the mystery
- Slide 2-3: SETUP — voice gives context, punch text shows key facts/numbers
- Slide 4-6: ESCALATION — each more shocking, voice builds tension
- Slide 7-8: THE TWIST — darkest part, voice drops the bomb
- Slide 9: COMMENT BAIT — provocative ending, voice asks the question

PUNCH TEXT RULES:
- NEVER more than 8 words on screen
- Use ALL CAPS for impact
- Include NUMBERS when possible ("800,000 DEAD IN 100 DAYS")
- Contrast/irony works ("THEY CALLED IT MEDICINE")
- Questions that disturb ("WOULD YOU HAVE OBEYED?")
- The text should make sense EVEN WITHOUT the voiceover

NARRATION RULES:
- Write like you're WHISPERING a dark secret to someone
- Short sentences. "He agreed. That was his last mistake."
- Include details that make people FEEL something
- Each slide narration = 15-25 words (fits ~5-8 seconds of speech)
- DO NOT repeat the punch text word-for-word in narration

TIKTOK DESCRIPTION:
- 2500-3000 characters MINIMUM
- Structure: hook → extra shocking details not in video → modern relevance → divisive question → 5 hashtags
- Must make people SAVE the post for the extra info

APPLY WORD CENSORSHIP on punch_text, tiktok_description, and all text fields using these subs:
kill→k!ll, murder→murd3r, death→d3ath, dead→d3ad, died→d!ed, genocide→g3noc!de, holocaust→h0locaust, suicide→su!c!de, torture→t0rture, massacre→ma$$acre, bomb→b0mb, nuclear→nucle@r, slave→sl@ve, drug→dr*g, nazi→n@zi, gun→g*n, victim→v!ctim, crime→cr!me, blood→bl00d, shooting→sh00ting, prison→pr!son, etc.
Do NOT censor narration — that's for voice only, TikTok can't scan audio."""


def generate_content(topic: str, format_type: str, angle: str) -> dict:
    today = datetime.date.today().strftime("%B %d")
    user_prompt = f"""Today is {today}. Create VIRAL content about: {topic}

ANGLE: {angle}
FORMAT: {format_type} — 9 slides, voice-narrated, 60-90 seconds total

REMEMBER:
- punch_text = 3-8 WORDS ONLY (shown on screen)
- narration = full voiceover script (spoken by TTS)
- These are DIFFERENT. punch_text is bold headline, narration is the story.
- Slide 1 punch_text should be RED (#FF4444) or GOLD (#FFD700)
- TikTok description = 2500-3000 chars
- Censor punch_text and descriptions, NOT narration
- Apply the "{angle}" angle hard"""

    result = call_groq(SYSTEM_PROMPT, user_prompt)
    return censor_content(result)


# ═══════════════════════════════════════════════════════════════
# TTS VOICEOVER
# ═══════════════════════════════════════════════════════════════
async def _generate_tts(text: str, path: str, voice: str, rate: str = "-5%"):
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch="-2Hz")
    await communicate.save(path)


def generate_voiceover(slides: list, voice: str = DEFAULT_VOICE) -> list:
    """Generate voiceover audio for each slide. Returns list of paths."""
    paths = []
    for i, slide in enumerate(slides):
        narration = slide.get("narration", slide.get("punch_text", ""))
        narration = uncensor_for_tts(narration)

        if not narration.strip():
            paths.append(None)
            continue

        audio_path = str(OUTPUT_DIR / f"voice_{i}.mp3")
        try:
            asyncio.run(_generate_tts(narration, audio_path, voice))
            paths.append(audio_path)
        except Exception as e:
            print(f"TTS error slide {i}: {e}")
            paths.append(None)
    return paths


# ═══════════════════════════════════════════════════════════════
# IMAGE HELPERS
# ═══════════════════════════════════════════════════════════════
def download_image(query: str, idx: int = 0) -> Image.Image:
    api_key = PEXELS_API_KEY or os.environ.get("PEXELS_API_KEY", "")
    if api_key:
        img = _try_pexels(query, api_key)
        if img:
            return img
        short = " ".join(query.split()[:2])
        if short != query:
            img = _try_pexels(short, api_key)
            if img:
                return img
    img = _try_wikimedia(" ".join(query.split()[:3]))
    if img:
        return img
    return create_gradient_bg(idx)


def _try_pexels(query, api_key):
    try:
        r = requests.get("https://api.pexels.com/v1/search",
            headers={"Authorization": api_key},
            params={"query": query, "per_page": 3, "orientation": "portrait", "size": "medium"},
            timeout=6)
        if r.status_code != 200: return None
        for p in r.json().get("photos", []):
            url = p.get("src", {}).get("portrait") or p.get("src", {}).get("large")
            if url:
                ir = requests.get(url, timeout=6)
                if ir.status_code == 200 and len(ir.content) > 5000:
                    img = Image.open(BytesIO(ir.content)).convert("RGB")
                    if img.size[0] >= 300: return img
    except Exception: pass
    return None


def _try_wikimedia(query):
    try:
        r = requests.get("https://commons.wikimedia.org/w/api.php",
            params={"action":"query","generator":"search","gsrsearch":f"File: {query}",
                    "gsrlimit":"3","prop":"imageinfo","iiprop":"url|mime",
                    "iiurlwidth":"1080","format":"json"}, timeout=5)
        for p in r.json().get("query",{}).get("pages",{}).values():
            info = p.get("imageinfo",[{}])[0]
            if "image" in info.get("mime","") and "svg" not in info.get("mime",""):
                url = info.get("thumburl") or info.get("url")
                if url:
                    ir = requests.get(url, timeout=5)
                    if ir.status_code == 200:
                        img = Image.open(BytesIO(ir.content)).convert("RGB")
                        if img.size[0] >= 200: return img
    except Exception: pass
    return None


def create_gradient_bg(idx=0):
    palettes = [
        [(20,10,10),(80,20,20)], [(10,10,25),(30,30,80)],
        [(25,10,10),(100,40,15)], [(10,20,15),(25,70,40)],
        [(20,10,30),(60,20,80)], [(30,25,10),(90,70,20)],
        [(15,15,20),(45,45,65)], [(30,15,5),(85,45,15)],
    ]
    c1, c2 = palettes[idx % len(palettes)]
    img = Image.new("RGB", (VIDEO_W, VIDEO_H))
    draw = ImageDraw.Draw(img)
    for y in range(VIDEO_H):
        t = (y/VIDEO_H)**2 * (3 - 2*(y/VIDEO_H))
        r = int(c1[0]+(c2[0]-c1[0])*t)
        g = int(c1[1]+(c2[1]-c1[1])*t)
        b = int(c1[2]+(c2[2]-c1[2])*t)
        draw.line([(0,y),(VIDEO_W,y)], fill=(r,g,b))
    return img


# ═══════════════════════════════════════════════════════════════
# TEXT OVERLAY
# ═══════════════════════════════════════════════════════════════
def _get_font(size):
    for fp in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
               "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
               "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/impact.ttf",
               "/System/Library/Fonts/Helvetica.ttc"]:
        if os.path.exists(fp):
            try: return ImageFont.truetype(fp, size)
            except: continue
    return ImageFont.load_default()


def add_text_to_image(img, text, position="center", font_size=64,
                       color="white", shadow=True, text_bg=False):
    img = img.copy().resize((VIDEO_W, VIDEO_H), Image.LANCZOS)
    draw = ImageDraw.Draw(img)
    font = _get_font(font_size)

    # Keep text well inside margins
    usable_w = int(VIDEO_W * 0.75)
    max_chars = max(12, int(usable_w / (font_size * 0.55)))
    lines = textwrap.wrap(text, width=max_chars)
    line_h = int(font_size * 1.5)
    total_h = len(lines) * line_h

    if position == "center":
        start_y = (VIDEO_H - total_h) // 2
    elif position == "top":
        start_y = 100
    else:
        start_y = VIDEO_H - total_h - 200

    # Semi-transparent bg box
    if text_bg and lines:
        pad = 50
        bg = Image.new("RGBA", img.size, (0,0,0,0))
        bgd = ImageDraw.Draw(bg)
        bgd.rounded_rectangle(
            [100, start_y - pad, VIDEO_W - 100, start_y + total_h + pad],
            radius=16, fill=(0,0,0,180))
        img = Image.alpha_composite(img.convert("RGBA"), bg).convert("RGB")
        draw = ImageDraw.Draw(img)

    # Parse color
    if isinstance(color, str) and color.startswith("#"):
        try:
            color = tuple(int(color[i:i+2], 16) for i in (1,3,5))
        except: color = (255,255,255)
    elif color == "white": color = (255,255,255)
    elif color == "red": color = (255,68,68)
    elif color == "gold": color = (255,215,0)

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0,0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = (VIDEO_W - tw) // 2
        y = start_y + i * line_h

        if shadow:
            for ox in range(-3,4):
                for oy in range(-3,4):
                    if ox==0 and oy==0: continue
                    draw.text((x+ox, y+oy), line, font=font, fill=(0,0,0))
        draw.text((x,y), line, font=font, fill=color)

    return img


def add_darkening_overlay(img, opacity=0.5):
    img = img.copy()
    ov = Image.new("RGBA", img.size, (0,0,0,int(255*opacity)))
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def add_vignette(img):
    img = img.copy().convert("RGBA")
    vig = Image.new("RGBA", img.size, (0,0,0,0))
    d = ImageDraw.Draw(vig)
    cx, cy = img.size[0]//2, img.size[1]//2
    mr = math.sqrt(cx**2 + cy**2)
    for rs in range(100, 0, -1):
        r = mr * rs/100
        a = int(200 * (1-(rs/100)**2))
        d.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(0,0,0,max(0,min(255,a))))
    return Image.alpha_composite(img, vig).convert("RGB")


# ═══════════════════════════════════════════════════════════════
# BACKGROUND MUSIC
# ═══════════════════════════════════════════════════════════════
def create_ambient_music(duration_sec):
    try:
        from pydub import AudioSegment
        from pydub.generators import Sine
        ms = int(duration_sec * 1000)
        base = Sine(82.41).to_audio_segment(duration=ms).apply_gain(-26)
        tension = Sine(87.31).to_audio_segment(duration=ms).apply_gain(-34)
        sub = Sine(41.20).to_audio_segment(duration=ms).apply_gain(-28)
        eerie = Sine(493.88).to_audio_segment(duration=ms).apply_gain(-38)
        mix = base.overlay(tension).overlay(sub).overlay(eerie)
        fade = min(4000, ms//3)
        mix = mix.fade_in(fade).fade_out(fade).apply_gain(-6)
        path = str(OUTPUT_DIR / "ambient.wav")
        mix.export(path, format="wav")
        return path
    except Exception as e:
        print(f"Music error: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
# VIDEO CREATION
# ═══════════════════════════════════════════════════════════════
def create_slideshow(slides, title, voice_paths):
    """Create slideshow synced to voiceover with punch text overlays."""
    clips = []

    for i, slide in enumerate(slides):
        text = slide.get("punch_text", slide.get("text_overlay", ""))
        text_color = slide.get("text_color", "white")
        is_first = (i == 0)
        is_last = (i == len(slides) - 1)

        # Duration: match to voiceover length, or use default
        voice_audio = None
        if voice_paths and i < len(voice_paths) and voice_paths[i]:
            try:
                voice_audio = AudioFileClip(voice_paths[i])
                duration = voice_audio.duration + 1.2  # breathing room
            except Exception:
                duration = slide.get("duration_sec", 8)
        else:
            duration = slide.get("duration_sec", 8)

        # Build frame
        bg = download_image(slide.get("image_search", title), i)
        bg = bg.resize((VIDEO_W, VIDEO_H), Image.LANCZOS)
        bg = add_darkening_overlay(bg, 0.5)
        bg = add_vignette(bg)

        # Punch text — BIG and SHORT
        font_size = 72 if is_first else 58  # first slide bigger
        frame = add_text_to_image(bg, text, position="center",
                                   font_size=font_size, color=text_color, text_bg=True)

        # Watermark
        frame = add_text_to_image(frame, "@DailyHistory", position="top",
                                   font_size=28, color="#c8a44e")

        # Slide counter
        frame = add_text_to_image(frame, f"{i+1}/{len(slides)}",
                                   position="bottom", font_size=22, color="#666666")

        fpath = str(OUTPUT_DIR / f"frame_{i}.png")
        frame.save(fpath, quality=95)

        clip = ImageClip(fpath).with_duration(duration)

        # Attach voice to this clip
        if voice_audio:
            voice_audio = voice_audio.with_start(0.4)
            clip = clip.with_audio(voice_audio)

        clips.append(clip)

    # Transitions
    final_clips = []
    for i, clip in enumerate(clips):
        if i > 0:
            clip = clip.with_effects([vfx.CrossFadeIn(0.3)])
        if i < len(clips) - 1:
            clip = clip.with_effects([vfx.CrossFadeOut(0.3)])
        final_clips.append(clip)

    final = concatenate_videoclips(final_clips, method="compose")
    total_dur = final.duration

    # Layer ambient music underneath voice
    music_path = create_ambient_music(total_dur)
    if music_path:
        try:
            bg_music = AudioFileClip(music_path).with_duration(total_dur)
            bg_music = bg_music.with_effects([vfx.MultiplyVolume(0.15)])
            if final.audio:
                final = final.with_audio(CompositeAudioClip([final.audio, bg_music]))
            else:
                final = final.with_audio(bg_music)
        except Exception as e:
            print(f"Music mix error: {e}")

    out = str(OUTPUT_DIR / f"dailyhistory_{datetime.date.today()}.mp4")
    final.write_videofile(out, fps=FPS, codec="libx264", audio_codec="aac",
                          preset="medium", threads=2, logger=None)

    for c in final_clips:
        try: c.close()
        except: pass

    return out


# ═══════════════════════════════════════════════════════════════
# AUTO-POST
# ═══════════════════════════════════════════════════════════════
def post_to_twitter(text):
    bearer = os.environ.get("TWITTER_BEARER_TOKEN")
    if not bearer: return "📋 MANUAL"
    try:
        r = requests.post("https://api.twitter.com/2/tweets",
            headers={"Authorization":f"Bearer {bearer}","Content-Type":"application/json"},
            json={"text":text}, timeout=10)
        return f"✅ POSTED — {r.json().get('data',{}).get('id')}" if r.ok else f"❌ {r.text}"
    except Exception as e: return f"❌ {e}"


def post_to_facebook(text):
    token = os.environ.get("FACEBOOK_PAGE_TOKEN")
    pid = os.environ.get("FACEBOOK_PAGE_ID")
    if not token or not pid: return "📋 MANUAL"
    try:
        r = requests.post(f"https://graph.facebook.com/v19.0/{pid}/feed",
            json={"message":text,"access_token":token}, timeout=10)
        return f"✅ POSTED — {r.json().get('id')}" if r.ok else f"❌ {r.text}"
    except Exception as e: return f"❌ {e}"


# ═══════════════════════════════════════════════════════════════
# PIPELINE — SPLIT IN 2 STEPS (no timeout)
# ═══════════════════════════════════════════════════════════════
_state = {}


def step1_generate_text(topic, format_type, angle, voice_name):
    """Step 1: AI content + TTS voiceover (~15-30 sec)."""
    global _state
    if not topic.strip():
        raise gr.Error("Scrie un topic!")

    content = generate_content(topic, format_type, angle)
    _state["content"] = content
    _state["format"] = format_type

    # Generate voiceover
    voice_id = VOICES.get(voice_name, DEFAULT_VOICE)
    voice_paths = generate_voiceover(content.get("slides", []), voice_id)
    _state["voice_paths"] = voice_paths

    # Auto-post text platforms
    tw = post_to_twitter(content.get("twitter_post", ""))
    fb = post_to_facebook(content.get("facebook_post", ""))

    tiktok = content.get("tiktok_description", "")
    if len(tiktok) > 3000:
        tiktok = tiktok[:2995] + "..."

    status = f"""═══ POSTING STATUS ═══

  𝕏 Twitter: {tw}
  f Facebook: {fb}
  ♪ TikTok: 📋 Upload video + paste description
  ◻ Instagram: 📋 Upload reel + paste description
  ▶ YouTube: 📋 Upload Short + paste title/desc

  🎤 Voice: {voice_name}
  🎯 Angle: {content.get('angle_used', angle)}
  💬 Comment bait: {content.get('comment_bait', 'N/A')}

  ✅ Text + voice ready! Click GENERATE VIDEO below."""

    return (
        content.get("title", ""),
        content.get("hook", ""),
        content.get("comment_bait", ""),
        tiktok,
        f"{len(tiktok)} / 3000 chars",
        content.get("instagram_description", ""),
        content.get("youtube_title", ""),
        content.get("youtube_description", ""),
        content.get("facebook_post", ""),
        content.get("twitter_post", ""),
        status,
        json.dumps(content.get("slides", []), indent=2, ensure_ascii=False),
    )


def step2_generate_video():
    """Step 2: Build video with voiceover (~1-3 min)."""
    global _state
    if "content" not in _state:
        raise gr.Error("Generate text first!")

    slides = _state["content"].get("slides", [])
    title = _state["content"].get("title", "DailyHistory")
    voice_paths = _state.get("voice_paths", [])

    video_path = create_slideshow(slides, title, voice_paths)
    return video_path


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
.gradio-container { max-width: 1000px !important; }
.main-title {
    text-align: center; font-size: 2.4em; font-weight: 700;
    color: #c8a44e !important; letter-spacing: 0.08em;
    text-transform: uppercase; margin-bottom: 0 !important;
}
.sub-title {
    text-align: center; font-size: 0.85em; letter-spacing: 0.3em;
    text-transform: uppercase; color: #7a6e58 !important;
}
footer { display: none !important; }
"""


def build_ui():
    with gr.Blocks(title="DailyHistory v3 — Viral Pipeline") as app:

        gr.Markdown("<h1 class='main-title'>DailyHistory</h1>")
        gr.Markdown("<p class='sub-title'>Viral Pipeline v3 — TTS Voiceover Edition</p>")
        gr.Markdown("---")

        # ── INPUT ──
        with gr.Group():
            gr.Markdown("### ① Topic + Settings")
            topic_input = gr.Textbox(
                label="Topic (English)",
                placeholder='e.g. "Unit 731 experiments", "What really sank the Titanic"',
                lines=2,
            )
            with gr.Row():
                angle_select = gr.Radio(
                    ["Dark History", "Controversial Take", "Shocking Facts",
                     "They Lied To You", "What They Don't Tell You"],
                    value="Dark History",
                    label="🎯 Angle",
                    scale=2,
                )
                format_type = gr.Radio(
                    ["Slideshow", "Video Clip"],
                    value="Slideshow",
                    label="Format",
                    scale=1,
                )
            voice_select = gr.Dropdown(
                choices=list(VOICES.keys()),
                value="Guy (US, Deep)",
                label="🎤 Voice",
            )
            generate_text_btn = gr.Button(
                "⚡ STEP 1 — GENERATE TEXT + VOICE",
                variant="primary", size="lg",
            )

        # ── TITLE + HOOK ──
        gr.Markdown("---")
        with gr.Row():
            title_out = gr.Textbox(label="📌 Title", interactive=False)
            hook_out = gr.Textbox(label="🪝 Hook", interactive=False)
        comment_out = gr.Textbox(label="💬 Comment Bait", interactive=False)

        # ── TIKTOK ──
        gr.Markdown("---")
        gr.Markdown("### ② TikTok Description")
        tiktok_out = gr.Textbox(label="♪ TikTok (select all → copy → paste)", lines=10, interactive=False)
        tiktok_chars = gr.Textbox(label="Chars", interactive=False)

        # ── OTHER PLATFORMS ──
        gr.Markdown("---")
        gr.Markdown("### ③ Other Platforms")
        with gr.Tab("Instagram"):
            ig_out = gr.Textbox(label="◻ Instagram", lines=6, interactive=False)
        with gr.Tab("YouTube"):
            yt_title = gr.Textbox(label="▶ Title", interactive=False)
            yt_desc = gr.Textbox(label="▶ Description", lines=5, interactive=False)
        with gr.Tab("Facebook"):
            fb_out = gr.Textbox(label="f Post", lines=4, interactive=False)
        with gr.Tab("X / Twitter"):
            tw_out = gr.Textbox(label="𝕏 Tweet", lines=3, interactive=False)

        # ── STATUS ──
        gr.Markdown("---")
        status_out = gr.Textbox(label="📊 Status", lines=14, interactive=False)

        # ── SLIDES ──
        with gr.Accordion("🔧 Slides JSON", open=False):
            slides_out = gr.Code(language="json", label="Slides")

        # ── VIDEO ──
        gr.Markdown("---")
        gr.Markdown("### ④ Generate Video (voiceover + music)")
        gr.Markdown("*Click after Step 1 completes. Takes 1-3 minutes.*")
        generate_video_btn = gr.Button(
            "🎬 STEP 2 — GENERATE VIDEO",
            variant="secondary", size="lg",
        )
        video_out = gr.Video(label="Download → upload to TikTok/IG/YT")

        # ── WIRE ──
        generate_text_btn.click(
            fn=step1_generate_text,
            inputs=[topic_input, format_type, angle_select, voice_select],
            outputs=[
                title_out, hook_out, comment_out,
                tiktok_out, tiktok_chars,
                ig_out, yt_title, yt_desc,
                fb_out, tw_out,
                status_out, slides_out,
            ],
            concurrency_limit=1,
        )
        generate_video_btn.click(
            fn=step2_generate_video,
            inputs=[],
            outputs=[video_out],
            concurrency_limit=1,
        )

        gr.Markdown("---")
        gr.Markdown("<p style='text-align:center;color:#5a451c;font-size:0.8em;letter-spacing:0.15em'>"
                    "DAILYHISTORY v3 — VOICEOVER + VIRAL PIPELINE — GROQ + QWEN3</p>")

    return app


if __name__ == "__main__":
    app = build_ui()
    app.queue(default_concurrency_limit=1)
    app.launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("PORT", 7860)),
        share=False,
        theme=THEME,
        css=CSS,
    )