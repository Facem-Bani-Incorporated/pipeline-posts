"""
DailyHistory Content Pipeline v4.0
───────────────────────────────────
Natural TTS + Image Preview + Cinematic Storytelling
"""

import os, json, re, textwrap, tempfile, math, datetime, asyncio
from pathlib import Path
from io import BytesIO

import gradio as gr
import requests
from PIL import Image, ImageDraw, ImageFont

from moviepy import (
    ImageClip, CompositeVideoClip, CompositeAudioClip,
    concatenate_videoclips, AudioFileClip, vfx
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

# More natural-sounding voices (multilingual neural = best quality)
VOICES = {
    "Brian (US, Natural Deep)": "en-US-BrianMultilingualNeural",
    "Andrew (US, Warm)": "en-US-AndrewMultilingualNeural",
    "Guy (US, Serious)": "en-US-GuyNeural",
    "Ryan (UK, Documentary)": "en-GB-RyanNeural",
    "Ava (US, Female)": "en-US-AvaMultilingualNeural",
    "Emma (UK, Female)": "en-GB-SoniaNeural",
}
DEFAULT_VOICE = "en-US-BrianMultilingualNeural"

# ═══════════════════════════════════════════════════════════════
# CENSOR (same as before, collapsed for readability)
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

def censor_text(text):
    if not text: return text
    for word in sorted(CENSOR_MAP.keys(), key=len, reverse=True):
        repl = CENSOR_MAP[word]
        pat = re.compile(re.escape(word), re.IGNORECASE)
        def _r(m):
            o = m.group(0)
            if o.isupper(): return repl.upper()
            if o[0].isupper(): return repl[0].upper() + repl[1:]
            return repl
        text = pat.sub(_r, text)
    return text

def censor_content(content):
    for f in ["title","hook","comment_bait","tiktok_description",
              "instagram_description","youtube_title","youtube_description",
              "facebook_post","twitter_post"]:
        if f in content and isinstance(content[f], str):
            content[f] = censor_text(content[f])
    for s in content.get("slides", []):
        if "punch_text" in s: s["punch_text"] = censor_text(s["punch_text"])
    return content

def uncensor_for_tts(text):
    for c, cl in [("k!ll","kill"),("murd3r","murder"),("d3ath","death"),
        ("d3ad","dead"),("d!ed","died"),("d!e","die"),("dy!ng","dying"),
        ("su!c!de","suicide"),("3xecut","execut"),("a$$a$$in","assassin"),
        ("ma$$acre","massacre"),("sl@ughter","slaughter"),("g3noc!de","genocide"),
        ("h0locaust","holocaust"),("beh3ad","behead"),("h@ng","hang"),
        ("str@ngl","strangl"),("st@bb","stabb"),("sh0t","shot"),("bl00d","blood"),
        ("w@r","war"),("we@pon","weapon"),("b0mb","bomb"),("expl0sion","explosion"),
        ("nucle@r","nuclear"),("t0rture","torture"),("@buse","abuse"),("r@pe","rape"),
        ("sl@ve","slave"),("dr*g","drug"),("c0caine","cocaine"),("0verdos","overdos"),
        ("terr0rist","terrorist"),("terr0rism","terrorism"),("n@zi","nazi"),
        ("c0ncentration","concentration"),("c@mp","camp"),("bl00dy","bloody"),
        ("c0rpse","corpse"),("pl@gue","plague"),("p@ndemic","pandemic"),
        ("v!rus","virus"),("cr!me","crime"),("cr!minal","criminal"),
        ("pr!son","prison"),("@rrested","arrested"),("sh00ting","shooting"),
        ("sh00ter","shooter"),("g*n","gun"),("v!ctim","victim"),
        ("@trocit","atrocit"),("d!sturb","disturb")]:
        text = text.replace(c, cl).replace(c.capitalize(), cl.capitalize())
    return text


# ═══════════════════════════════════════════════════════════════
# GROQ API
# ═══════════════════════════════════════════════════════════════
def call_groq(system_prompt, user_prompt):
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
            resp = requests.post(GROQ_URL,
                headers={"Content-Type":"application/json","Authorization":f"Bearer {api_key}"},
                json=body, timeout=120)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
            return json.loads(content)
        except requests.exceptions.Timeout:
            continue
        except Exception as e:
            if model == models[-1]: raise
            continue
    raise ValueError("All models failed")


# ═══════════════════════════════════════════════════════════════
# STORYTELLING PROMPT — the secret sauce
# ═══════════════════════════════════════════════════════════════
SYSTEM_PROMPT = """You are a MASTER STORYTELLER for DailyHistory, a viral dark history brand.
Your videos feel like mini-documentaries that people can't stop watching.

THE KEY: You don't just list facts. You make people FEEL like they're THERE.

═══ VIDEO STRUCTURE ═══

This video has VOICEOVER. A real voice narrates. On screen = SHORT punch text (3-8 words).

Two separate fields per slide:
- "punch_text": What APPEARS on screen. 3-8 words MAX. Bold. ALL CAPS. Like a movie tagline.
- "narration": What the VOICE SAYS. 2-3 sentences. Conversational. Dramatic. Like a true crime podcast host.

═══ STORYTELLING TECHNIQUE (this is what makes 100K+ views) ═══

1. OPEN WITH A PERSON, NOT A FACT:
   BAD: "In 1945, an experiment took place"
   GOOD: "In 1945, a 23-year-old soldier named David volunteered for what he was told would be a routine medical checkup. He never came home."

2. USE SENSORY DETAILS:
   BAD: "The conditions were terrible"  
   GOOD: "The room was so cold that frost formed on the walls. The only sound was the hum of machines and the scratching of pens on clipboards."

3. CREATE MINI-CLIFFHANGERS BETWEEN SLIDES:
   End slides with: "But what happened next..." / "And then they discovered something worse." / "That wasn't even the darkest part."

4. USE THE 'AND THE CRAZY THING IS' TECHNIQUE:
   After a shocking fact, add "And the crazy thing is..." to escalate. People physically cannot scroll away from this.

5. MAKE IT PERSONAL:
   Add "Imagine YOU were there" or "Picture this" moments. Pull the viewer INTO the story.

6. THE PAUSE TECHNIQUE FOR NARRATION:
   Write natural speech pauses using "..." in narration.
   "He opened the door... and what he saw... changed everything."
   This creates dramatic pacing in the TTS voice.

═══ SLIDE STRUCTURE (9 slides) ═══

Slide 1 — THE HOOK: Start with the most WTF moment or a person in danger. NOT chronological. Jump to the most interesting part first.
Slides 2-3 — REWIND: "But let's rewind." Give the context. Who, where, when. Make us care about the people involved.
Slides 4-6 — THE ESCALATION: Each slide reveals something worse. Use "And it gets worse..." transitions.
Slides 7-8 — THE REVEAL: The darkest part. The cover-up. The thing nobody knows. Use specific quotes if possible.
Slide 9 — THE HAUNTING END: Don't wrap it up neatly. End with something that LINGERS. A disturbing question. A fact that connects to today.

═══ IMAGE SEARCH QUERIES ═══

CRITICAL: The image_search field must find RELEVANT images on Pexels.
- Be SPECIFIC and VISUAL: "dark hospital corridor", "old military bunker", "abandoned laboratory"
- Think about MOOD not literal content: for a story about experiments, search "dark medical room" not "human experiment"
- Use ATMOSPHERIC queries: "foggy graveyard night", "empty prison cell", "burned ruins building"
- For people stories: "soldier portrait vintage", "woman 1940s portrait", "crowd protest black white"
- NEVER search for gore, violence, or graphic content
- Each slide should have a DIFFERENT image query — variety keeps viewers watching

═══ JSON FORMAT ═══

{
  "title": "max 60 chars, punchy",
  "hook": "max 12 words, curiosity gap",
  "slides": [
    {
      "punch_text": "3-8 WORDS ONLY. ALL CAPS. Like a movie poster tagline.",
      "narration": "2-3 sentences the voice SAYS. Use '...' for dramatic pauses. Conversational, not academic. Make people feel something.",
      "duration_sec": 8,
      "image_search": "specific atmospheric Pexels query, 3-5 words, think MOOD and VISUAL",
      "text_color": "#FF4444 for shocking, #FFD700 for important, white for default"
    }
  ],
  "comment_bait": "the ending line designed to force comments",
  "tiktok_description": "2500-3000 chars. Mini-article format: hook paragraph, then EXTRA details not in video (names, dates, aftermath), then connection to today, then provocative question. Exactly 5 hashtags at end.",
  "instagram_description": "under 2200 chars + 25-30 hashtags",
  "youtube_title": "SEO title with year, max 100 chars",
  "youtube_description": "3 keyword-rich paragraphs",
  "facebook_post": "opens with question, debate starter",
  "twitter_post": "under 280 chars, most shareable single fact",
  "seo_keywords": ["kw1","kw2","kw3","kw4","kw5"]
}

CENSORSHIP: Censor punch_text and descriptions (kill→k!ll, death→d3ath, etc). Do NOT censor narration — TikTok can't scan audio."""


def generate_content(topic, format_type, angle):
    today = datetime.date.today().strftime("%B %d")
    user_prompt = f"""Today is {today}. Create VIRAL content about: {topic}

ANGLE: {angle}
FORMAT: 9 slides, voice-narrated, 60-90 seconds total

STORYTELLING CHECKLIST:
☐ Slide 1 starts with a PERSON or a shocking moment, NOT a date
☐ Narration uses "..." for dramatic pauses
☐ Each slide ends with a mini-cliffhanger that makes you NEED the next slide
☐ At least one "And the crazy thing is..." moment
☐ At least one "Imagine you were there..." moment
☐ Specific names, dates, numbers, quotes — NOT vague statements
☐ image_search queries are atmospheric and specific (mood-based, not literal)
☐ punch_text is 3-8 words, ALL CAPS, different from narration
☐ TikTok description is 2500-3000 chars with extra details

ANGLE "{angle}":
- Dark History: focus on cruelty, cover-ups, things that make people uncomfortable
- Controversial Take: challenge what people think they know
- Shocking Facts: every slide = "no way that's real"
- They Lied To You: textbook myths destroyed
- What They Don't Tell You: hidden details, real motivations"""

    return censor_content(call_groq(SYSTEM_PROMPT, user_prompt))


# ═══════════════════════════════════════════════════════════════
# TTS — Natural voice with SSML pauses
# ═══════════════════════════════════════════════════════════════
def _add_ssml_pauses(text):
    """Convert '...' into SSML break tags for natural pausing."""
    # Replace "..." with a 500ms pause
    text = re.sub(r'\.{3,}', '<break time="500ms"/>', text)
    # Add small pause after sentences ending with period
    text = re.sub(r'\.(\s+)([A-Z])', '.<break time="300ms"/>\\1\\2', text)
    # Add pause after "—"
    text = text.replace(' — ', ' <break time="400ms"/> ')
    return text


async def _generate_tts(text, path, voice):
    """Generate natural-sounding TTS with SSML pauses."""
    # Build SSML for more natural speech
    ssml_text = _add_ssml_pauses(text)
    ssml = f"""<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">
    <voice name="{voice}">
        <prosody rate="-8%" pitch="-3Hz">
            {ssml_text}
        </prosody>
    </voice>
</speak>"""

    try:
        communicate = edge_tts.Communicate(ssml, voice)
        await communicate.save(path)
    except Exception:
        # Fallback to plain text if SSML fails
        communicate = edge_tts.Communicate(text, voice, rate="-8%", pitch="-3Hz")
        await communicate.save(path)


def generate_voiceover(slides, voice=DEFAULT_VOICE):
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
# IMAGE — Pexels with better search + preview
# ═══════════════════════════════════════════════════════════════
def download_image(query, idx=0):
    api_key = PEXELS_API_KEY or os.environ.get("PEXELS_API_KEY", "")
    if api_key:
        img = _try_pexels(query, api_key)
        if img: return img
        # Try simplified query
        words = query.split()
        if len(words) > 2:
            img = _try_pexels(" ".join(words[:2]), api_key)
            if img: return img
    img = _try_wikimedia(" ".join(query.split()[:3]))
    if img: return img
    return create_gradient_bg(idx)


def _try_pexels(query, api_key):
    try:
        r = requests.get("https://api.pexels.com/v1/search",
            headers={"Authorization": api_key},
            params={"query": query, "per_page": 5, "orientation": "portrait", "size": "medium"},
            timeout=8)
        if r.status_code != 200: return None
        photos = r.json().get("photos", [])
        if not photos: return None
        # Pick the best quality photo
        for p in photos:
            src = p.get("src", {})
            url = src.get("portrait") or src.get("large") or src.get("original")
            if url:
                ir = requests.get(url, timeout=8)
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
        t = (y/VIDEO_H)**2*(3-2*(y/VIDEO_H))
        draw.line([(0,y),(VIDEO_W,y)], fill=(
            int(c1[0]+(c2[0]-c1[0])*t),
            int(c1[1]+(c2[1]-c1[1])*t),
            int(c1[2]+(c2[2]-c1[2])*t)))
    return img


def preview_images(slides):
    """Download and return preview images for all slides."""
    previews = []
    for i, slide in enumerate(slides):
        query = slide.get("image_search", "dark background")
        img = download_image(query, i)
        # Save as temp file for gallery
        path = str(OUTPUT_DIR / f"preview_{i}.jpg")
        img.resize((540, 960), Image.LANCZOS).save(path, quality=85)
        label = f"Slide {i+1}: {query}"
        previews.append((path, label))
    return previews


# ═══════════════════════════════════════════════════════════════
# TEXT OVERLAY + VISUAL
# ═══════════════════════════════════════════════════════════════
def _get_font(size):
    for fp in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
               "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
               "C:/Windows/Fonts/arialbd.ttf","C:/Windows/Fonts/impact.ttf",
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
    usable_w = int(VIDEO_W * 0.72)
    max_chars = max(10, int(usable_w / (font_size * 0.55)))
    lines = textwrap.wrap(text, width=max_chars)
    line_h = int(font_size * 1.5)
    total_h = len(lines) * line_h

    if position == "center": start_y = (VIDEO_H - total_h) // 2
    elif position == "top": start_y = 100
    else: start_y = VIDEO_H - total_h - 200

    if text_bg and lines:
        pad = 55
        bg = Image.new("RGBA", img.size, (0,0,0,0))
        ImageDraw.Draw(bg).rounded_rectangle(
            [110, start_y-pad, VIDEO_W-110, start_y+total_h+pad],
            radius=16, fill=(0,0,0,185))
        img = Image.alpha_composite(img.convert("RGBA"), bg).convert("RGB")
        draw = ImageDraw.Draw(img)

    if isinstance(color, str) and color.startswith("#"):
        try: color = tuple(int(color[i:i+2],16) for i in (1,3,5))
        except: color = (255,255,255)
    elif color == "white": color = (255,255,255)
    elif color == "red": color = (255,68,68)
    elif color == "gold": color = (255,215,0)

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0,0), line, font=font)
        x = (VIDEO_W - (bbox[2]-bbox[0])) // 2
        y = start_y + i*line_h
        if shadow:
            for ox in range(-3,4):
                for oy in range(-3,4):
                    if ox==0 and oy==0: continue
                    draw.text((x+ox,y+oy), line, font=font, fill=(0,0,0))
        draw.text((x,y), line, font=font, fill=color)
    return img

def add_darkening_overlay(img, opacity=0.5):
    ov = Image.new("RGBA", img.size, (0,0,0,int(255*opacity)))
    return Image.alpha_composite(img.copy().convert("RGBA"), ov).convert("RGB")

def add_vignette(img):
    img = img.copy().convert("RGBA")
    vig = Image.new("RGBA", img.size, (0,0,0,0))
    d = ImageDraw.Draw(vig)
    cx, cy = img.size[0]//2, img.size[1]//2
    mr = math.sqrt(cx**2+cy**2)
    for rs in range(100,0,-1):
        r = mr*rs/100
        a = int(200*(1-(rs/100)**2))
        d.ellipse([cx-r,cy-r,cx+r,cy+r], fill=(0,0,0,max(0,min(255,a))))
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
    clips = []
    for i, slide in enumerate(slides):
        text = slide.get("punch_text", slide.get("text_overlay", ""))
        text_color = slide.get("text_color", "white")

        voice_audio = None
        if voice_paths and i < len(voice_paths) and voice_paths[i]:
            try:
                voice_audio = AudioFileClip(voice_paths[i])
                duration = voice_audio.duration + 1.2
            except: duration = slide.get("duration_sec", 8)
        else:
            duration = slide.get("duration_sec", 8)

        bg = download_image(slide.get("image_search", title), i)
        bg = bg.resize((VIDEO_W, VIDEO_H), Image.LANCZOS)
        bg = add_darkening_overlay(bg, 0.45)
        bg = add_vignette(bg)

        font_size = 72 if i == 0 else 58
        frame = add_text_to_image(bg, text, position="center",
                                   font_size=font_size, color=text_color, text_bg=True)
        frame = add_text_to_image(frame, "@DailyHistory", position="top",
                                   font_size=28, color="#c8a44e")
        frame = add_text_to_image(frame, f"{i+1}/{len(slides)}",
                                   position="bottom", font_size=22, color="#666666")

        fpath = str(OUTPUT_DIR / f"frame_{i}.png")
        frame.save(fpath, quality=95)
        clip = ImageClip(fpath).with_duration(duration)

        if voice_audio:
            voice_audio = voice_audio.with_start(0.4)
            clip = clip.with_audio(voice_audio)
        clips.append(clip)

    final_clips = []
    for i, clip in enumerate(clips):
        if i > 0: clip = clip.with_effects([vfx.CrossFadeIn(0.3)])
        if i < len(clips)-1: clip = clip.with_effects([vfx.CrossFadeOut(0.3)])
        final_clips.append(clip)

    final = concatenate_videoclips(final_clips, method="compose")
    total_dur = final.duration

    music_path = create_ambient_music(total_dur)
    if music_path:
        try:
            bg_music = AudioFileClip(music_path).with_duration(total_dur)
            bg_music = bg_music.with_effects([vfx.MultiplyVolume(0.12)])
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
    token, pid = os.environ.get("FACEBOOK_PAGE_TOKEN"), os.environ.get("FACEBOOK_PAGE_ID")
    if not token or not pid: return "📋 MANUAL"
    try:
        r = requests.post(f"https://graph.facebook.com/v19.0/{pid}/feed",
            json={"message":text,"access_token":token}, timeout=10)
        return f"✅ POSTED — {r.json().get('id')}" if r.ok else f"❌ {r.text}"
    except Exception as e: return f"❌ {e}"


# ═══════════════════════════════════════════════════════════════
# PIPELINE — 3 STEPS: Text → Preview Images → Video
# ═══════════════════════════════════════════════════════════════
_state = {}

def step1_generate_text(topic, format_type, angle, voice_name):
    global _state
    if not topic.strip(): raise gr.Error("Scrie un topic!")

    content = generate_content(topic, format_type, angle)
    voice_id = VOICES.get(voice_name, DEFAULT_VOICE)
    voice_paths = generate_voiceover(content.get("slides", []), voice_id)

    _state = {"content": content, "format": format_type, "voice_paths": voice_paths}

    tw = post_to_twitter(content.get("twitter_post", ""))
    fb = post_to_facebook(content.get("facebook_post", ""))

    tiktok = content.get("tiktok_description", "")
    if len(tiktok) > 3000: tiktok = tiktok[:2995] + "..."

    # Generate image previews
    slides = content.get("slides", [])
    previews = preview_images(slides)

    status = f"""═══ STATUS ═══
  𝕏 Twitter: {tw}  |  f Facebook: {fb}
  ♪ TikTok / ◻ IG / ▶ YT: 📋 MANUAL

  🎤 Voice: {voice_name}
  🎯 Angle: {content.get('angle_used', angle)}
  💬 Bait: {content.get('comment_bait', 'N/A')}

  ✅ Text + voice + images ready!
  👀 Check image previews below.
  🎬 Click GENERATE VIDEO when ready."""

    return (
        content.get("title",""), content.get("hook",""), content.get("comment_bait",""),
        tiktok, f"{len(tiktok)} / 3000 chars",
        content.get("instagram_description",""),
        content.get("youtube_title",""), content.get("youtube_description",""),
        content.get("facebook_post",""), content.get("twitter_post",""),
        status, json.dumps(slides, indent=2, ensure_ascii=False),
        previews,
    )

def step2_generate_video():
    global _state
    if "content" not in _state: raise gr.Error("Generate text first!")
    slides = _state["content"].get("slides", [])
    title = _state["content"].get("title", "DailyHistory")
    return create_slideshow(slides, title, _state.get("voice_paths", []))


# ═══════════════════════════════════════════════════════════════
# GRADIO UI
# ═══════════════════════════════════════════════════════════════
THEME = gr.themes.Base(
    primary_hue=gr.themes.Color(
        c50="#fdf8ef",c100="#fcefd5",c200="#f8dca6",c300="#f3c56e",
        c400="#edb244",c500="#c8a44e",c600="#a88532",c700="#886a24",
        c800="#6e5520",c900="#5a451c",c950="#332710"),
    neutral_hue=gr.themes.Color(
        c50="#f5f0e8",c100="#ebe3d6",c200="#d6ccb8",c300="#b8a890",
        c400="#9a8a6e",c500="#7a6e58",c600="#5e5442",c700="#443c2e",
        c800="#2a2418",c900="#1a1610",c950="#111009"),
    font=["Source Serif 4","Georgia","serif"],
    font_mono=["JetBrains Mono","monospace"],
)

CSS = """
.gradio-container { max-width: 1000px !important; }
.main-title { text-align:center; font-size:2.4em; font-weight:700;
    color:#c8a44e !important; letter-spacing:0.08em; text-transform:uppercase; }
.sub-title { text-align:center; font-size:0.85em; letter-spacing:0.3em;
    text-transform:uppercase; color:#7a6e58 !important; }
footer { display:none !important; }
"""

def build_ui():
    with gr.Blocks(title="DailyHistory v4") as app:

        gr.Markdown("<h1 class='main-title'>DailyHistory</h1>")
        gr.Markdown("<p class='sub-title'>v4 — Natural Voice + Image Preview + Storytelling</p>")
        gr.Markdown("---")

        with gr.Group():
            gr.Markdown("### ① Topic")
            topic_input = gr.Textbox(label="Topic (English)",
                placeholder='"Unit 731 experiments", "What really sank the Titanic"', lines=2)
            with gr.Row():
                angle_select = gr.Radio(
                    ["Dark History","Controversial Take","Shocking Facts",
                     "They Lied To You","What They Don't Tell You"],
                    value="Dark History", label="🎯 Angle", scale=2)
                format_type = gr.Radio(["Slideshow","Video Clip"],
                    value="Slideshow", label="Format", scale=1)
            voice_select = gr.Dropdown(choices=list(VOICES.keys()),
                value="Brian (US, Natural Deep)", label="🎤 Voice")
            gen_text_btn = gr.Button("⚡ STEP 1 — GENERATE TEXT + VOICE + IMAGES",
                variant="primary", size="lg")

        gr.Markdown("---")
        with gr.Row():
            title_out = gr.Textbox(label="📌 Title", interactive=False)
            hook_out = gr.Textbox(label="🪝 Hook", interactive=False)
        comment_out = gr.Textbox(label="💬 Comment Bait", interactive=False)

        gr.Markdown("---")
        gr.Markdown("### ② TikTok")
        tiktok_out = gr.Textbox(label="♪ Description (copy → paste)", lines=10, interactive=False)
        tiktok_chars = gr.Textbox(label="Chars", interactive=False)

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

        gr.Markdown("---")
        status_out = gr.Textbox(label="📊 Status", lines=12, interactive=False)

        with gr.Accordion("🔧 Slides JSON", open=False):
            slides_out = gr.Code(language="json", label="Slides")

        # ── IMAGE PREVIEW ──
        gr.Markdown("---")
        gr.Markdown("### 👀 Image Preview (ce va apărea în clip)")
        gr.Markdown("*Verifică pozele înainte de a genera video-ul. Dacă nu-ți plac, schimbă topic-ul sau regenerează.*")
        image_gallery = gr.Gallery(label="Slide Images", columns=3, height=400)

        # ── VIDEO ──
        gr.Markdown("---")
        gr.Markdown("### ④ Generate Video")
        gr.Markdown("*Verifică pozele sus, apoi click aici. ~1-3 min.*")
        gen_video_btn = gr.Button("🎬 STEP 2 — GENERATE VIDEO",
            variant="secondary", size="lg")
        video_out = gr.Video(label="Download → upload to TikTok/IG/YT")

        # ── WIRE ──
        gen_text_btn.click(
            fn=step1_generate_text,
            inputs=[topic_input, format_type, angle_select, voice_select],
            outputs=[title_out, hook_out, comment_out,
                     tiktok_out, tiktok_chars, ig_out, yt_title, yt_desc,
                     fb_out, tw_out, status_out, slides_out,
                     image_gallery],
            concurrency_limit=1)
        gen_video_btn.click(
            fn=step2_generate_video, inputs=[], outputs=[video_out],
            concurrency_limit=1)

        gr.Markdown("---")
        gr.Markdown("<p style='text-align:center;color:#5a451c;font-size:0.8em'>"
                    "DAILYHISTORY v4 — NATURAL VOICE + STORYTELLING ENGINE</p>")
    return app

if __name__ == "__main__":
    app = build_ui()
    app.queue(default_concurrency_limit=1)
    app.launch(server_name="0.0.0.0",
        server_port=int(os.environ.get("PORT", 7860)),
        share=False, theme=THEME, css=CSS)