"""
DailyHistory Content Pipeline v2.0
───────────────────────────────────
Gradio web UI → Groq → Video/Slideshow → Multi-platform content
Optimized for VIRAL history content on TikTok
Run locally: python app.py → http://localhost:7860
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
from dotenv import load_dotenv
load_dotenv()

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
# TIKTOK WORD CENSOR — bypass TikTok's content filters
# ═══════════════════════════════════════════════════════════════
# Format: "original word" → "censored version"
# TikTok OCR + NLP scans both video text AND descriptions
CENSOR_MAP = {
    # Violence / death
    "killed": "k!lled",
    "killing": "k!lling",
    "kill": "k!ll",
    "kills": "k!lls",
    "murder": "murd3r",
    "murdered": "murd3red",
    "murders": "murd3rs",
    "murderer": "murd3rer",
    "murderers": "murd3rers",
    "death": "d3ath",
    "deaths": "d3aths",
    "dead": "d3ad",
    "died": "d!ed",
    "die": "d!e",
    "dying": "dy!ng",
    "suicide": "su!c!de",
    "suicides": "su!c!des",
    "executed": "3xecuted",
    "execution": "3xecution",
    "executions": "3xecutions",
    "assassinated": "a$$a$$inated",
    "assassination": "a$$a$$ination",
    "assassin": "a$$a$$in",
    "massacre": "ma$$acre",
    "massacred": "ma$$acred",
    "massacres": "ma$$acres",
    "slaughter": "sl@ughter",
    "slaughtered": "sl@ughtered",
    "genocide": "g3noc!de",
    "holocaust": "h0locaust",
    "homicide": "h0mic!de",
    "manslaughter": "mansl@ughter",
    "beheaded": "beh3aded",
    "beheading": "beh3ading",
    "decapitated": "d3capitated",
    "hanged": "h@nged",
    "hanging": "h@nging",
    "strangled": "str@ngled",
    "stabbed": "st@bbed",
    "stabbing": "st@bbing",
    "shot dead": "sh0t d3ad",
    "gunshot": "gunsh0t",
    "bloodbath": "bl00dbath",
    "bloodshed": "bl00dshed",
    # War / weapons
    "war crime": "w@r cr!me",
    "war crimes": "w@r cr!mes",
    "weapon": "we@pon",
    "weapons": "we@pons",
    "bomb": "b0mb",
    "bombs": "b0mbs",
    "bombed": "b0mbed",
    "bombing": "b0mbing",
    "bombings": "b0mbings",
    "explosion": "expl0sion",
    "nuclear": "nucle@r",
    "atomic bomb": "at0mic b0mb",
    "chemical weapon": "chem!cal we@pon",
    "biological weapon": "b!ological we@pon",
    "sniper": "sn!per",
    "rifle": "r!fle",
    "bullet": "bull3t",
    "bullets": "bull3ts",
    "ammunition": "ammun!tion",
    "grenade": "gren@de",
    "missile": "m!ssile",
    "airstrike": "a!rstr!ke",
    "shelling": "sh3lling",
    # Abuse / torture
    "torture": "t0rture",
    "tortured": "t0rtured",
    "tortures": "t0rtures",
    "abuse": "@buse",
    "abused": "@bused",
    "abuses": "@buses",
    "rape": "r@pe",
    "raped": "r@ped",
    "rapist": "r@pist",
    "sexual assault": "s3xual @ssault",
    "molestation": "mol3station",
    "slave": "sl@ve",
    "slaves": "sl@ves",
    "slavery": "sl@very",
    "enslaved": "ensl@ved",
    "human trafficking": "human tr@fficking",
    "kidnapped": "k!dnapped",
    "kidnapping": "k!dnapping",
    # Drugs / substances
    "drug": "dr*g",
    "drugs": "dr*gs",
    "cocaine": "c0caine",
    "heroin": "her0in",
    "methamphetamine": "m3th",
    "overdose": "0verdose",
    "overdosed": "0verdosed",
    # Sensitive political / ethnic
    "terrorist": "terr0rist",
    "terrorists": "terr0rists",
    "terrorism": "terr0rism",
    "nazi": "n@zi",
    "nazis": "n@zis",
    "concentration camp": "c0ncentration c@mp",
    "concentration camps": "c0ncentration c@mps",
    "ethnic cleansing": "ethn!c cleans!ng",
    "hate crime": "h@te cr!me",
    "extremist": "extr3mist",
    "extremists": "extr3mists",
    "propaganda": "prop@ganda",
    # Medical / body
    "blood": "bl00d",
    "bloody": "bl00dy",
    "corpse": "c0rpse",
    "corpses": "c0rpses",
    "body parts": "b0dy p@rts",
    "organs": "0rgans",
    "dissection": "d!ssection",
    "autopsy": "@utopsy",
    "plague": "pl@gue",
    "pandemic": "p@ndemic",
    "virus": "v!rus",
    "infection": "inf3ction",
    # Crime
    "crime": "cr!me",
    "crimes": "cr!mes",
    "criminal": "cr!minal",
    "criminals": "cr!minals",
    "prison": "pr!son",
    "prisoner": "pr!soner",
    "prisoners": "pr!soners",
    "arrested": "@rrested",
    "shooting": "sh00ting",
    "shootings": "sh00tings",
    "shooter": "sh00ter",
    "gun": "g*n",
    "guns": "g*ns",
    "gunman": "g*nman",
    "victim": "v!ctim",
    "victims": "v!ctims",
    # Misc flagged
    "porn": "p0rn",
    "pornography": "p0rnography",
    "prostitution": "prost!tution",
    "prostitute": "prost!tute",
    "naked": "n@ked",
    "nude": "nud3",
    "explicit": "expl!cit",
    "graphic": "gr@phic",
    "gruesome": "gru3some",
    "disturbing": "d!sturbing",
    "horrifying": "h0rrifying",
    "atrocity": "@trocity",
    "atrocities": "@trocities",
}


def censor_text(text: str) -> str:
    """Replace flagged words with TikTok-safe censored versions.

    Case-insensitive replacement that preserves original casing pattern.
    Longer phrases are replaced first to avoid partial matches.
    """
    if not text:
        return text

    # Sort by length descending so multi-word phrases get matched first
    sorted_words = sorted(CENSOR_MAP.keys(), key=len, reverse=True)

    for word in sorted_words:
        replacement = CENSOR_MAP[word]
        # Case-insensitive replacement preserving surrounding text
        pattern = re.compile(re.escape(word), re.IGNORECASE)

        def _replace_match(match):
            original = match.group(0)
            # If original is ALL CAPS, make replacement uppercase
            if original.isupper():
                return replacement.upper()
            # If original is Title Case, capitalize first letter
            if original[0].isupper():
                return replacement[0].upper() + replacement[1:] if len(replacement) > 1 else replacement.upper()
            return replacement

        text = pattern.sub(_replace_match, text)

    return text


def censor_content(content: dict) -> dict:
    """Apply censorship to all text fields in the generated content."""
    text_fields = [
        "title", "hook", "comment_bait",
        "tiktok_description", "instagram_description",
        "youtube_title", "youtube_description",
        "facebook_post", "twitter_post",
    ]
    for field in text_fields:
        if field in content and isinstance(content[field], str):
            content[field] = censor_text(content[field])

    # Censor slide text overlays
    if "slides" in content:
        for slide in content["slides"]:
            if "text_overlay" in slide:
                slide["text_overlay"] = censor_text(slide["text_overlay"])

    return content


# ═══════════════════════════════════════════════════════════════
# GROQ HELPER
# ═══════════════════════════════════════════════════════════════
def call_groq(system_prompt: str, user_prompt: str) -> dict:
    """Call Groq API and return parsed JSON."""
    api_key = GROQ_API_KEY or os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set! Add it in your .env file.")

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
            "temperature": 0.7,
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
# VIRAL CONTENT GENERATION SYSTEM
# ═══════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are the content strategist behind a 10M+ follower dark history TikTok brand called DailyHistory. Your videos routinely hit 5-50 MILLION views because you understand exactly what makes people stop scrolling, watch till the end, comment angrily, tag friends, and share.

You specialize in: dark history, disturbing facts, controversial takes, "things they don't teach you in school", moral dilemmas from history, and shocking revelations that make people question everything.

═══ THE VIRAL FORMULA (non-negotiable) ═══

HOOK (slide 1): Must be ONE of these proven patterns:
- "The [person/country/company] did something so [dark/insane/disturbing] that [consequence]"
- "In [year], [shocking thing] happened and nobody talks about it"  
- "This is the most [disturbing/insane/controversial] thing in history and it's 100% real"
- "They literally [shocking verb] and got away with it"
- "Why does nobody talk about what [country/person] did in [year]?"
- "POV: you just learned what [thing] actually means"
- "This fact about [topic] will make you physically uncomfortable"
- "[Number] people [died/suffered/were affected] because of [surprising cause]"

SLIDE TEXT RULES:
- Slides 1-2: HOOK + setup. Short. Punchy. 1-2 sentences MAX. Create the curiosity gap.
- Slides 3-6: STORY ESCALATION. Each slide reveals something MORE shocking. 2-3 sentences. Build tension. Use specific numbers, names, dates, quotes.
- Slides 7-8: THE TWIST or DARKEST PART. The thing that makes people gasp. The detail everyone will comment about.
- Slide 9 (final): COMMENT BAIT. End with a provocative question or statement that FORCES people to comment. Examples: "And they never apologized.", "This is still legal today.", "Would you have done the same?", "The craziest part? This happened [surprisingly recently]."

TEXT STYLE:
- Write like you're TELLING someone this story at 2AM and watching their face change
- Use dramatic pauses via short sentences: "He agreed. Big mistake."
- Include SPECIFIC details that feel like insider knowledge
- Make the reader feel like they're learning something forbidden
- NEVER use generic phrases like "A Life of Service" or "The Legacy Lives On"
- Each slide must be readable in 6-8 seconds (40-80 words max per slide)

═══ DESCRIPTION STRATEGY ═══

TIKTOK (2500-3000 chars): Write like a mini-article that provides EXTRA shocking details NOT in the video. Structure:
1. Opening line that re-hooks: "Most people have no idea that..."
2. 2-3 paragraphs of ADDITIONAL disturbing/fascinating details
3. A paragraph that connects it to TODAY (modern relevance)
4. A divisive question that splits the audience ("Do you think this was justified?")
5. Exactly 5 hashtags at the very end — mix of big (#history #darkhistory) and niche

INSTAGRAM: Storytelling caption with a cliffhanger opening. 25-30 hashtags.

YOUTUBE: SEO-heavy title with year + key terms. Description with timestamps feel.

TWITTER/X: The single most WTF fact from the story. Must make someone say "wait WHAT" and retweet.

FACEBOOK: Start with a question. Make it feel like a debate starter.

═══ CONTENT ANGLES (apply based on the angle parameter) ═══

"Dark History": Focus on the disturbing, cruel, or horrifying aspects. Things that make people uncomfortable. Government coverups, war crimes, medical experiments, forgotten atrocities.

"Controversial Take": Present the event from an unexpected perspective. Challenge the mainstream narrative. Make people DEBATE in comments. "Actually, [villain] had a point..." or "Everyone blames X but Y was actually worse."

"Shocking Facts": Rapid-fire WTF moments. Numbers that don't seem real. Details that sound fake but are 100% verified. "The [thing] was actually invented because..."

"They Lied To You": School textbook myths debunked. Sanitized history exposed. "Your teacher told you X but the truth is..."

"What They Don't Tell You": Hidden details, classified info that got declassified, behind-the-scenes of famous events, the REAL reason things happened.

Respond in VALID JSON only. No markdown, no backticks.

═══ TIKTOK WORD CENSORSHIP (MANDATORY) ═══

TikTok's AI scans text overlays, descriptions, and even OCR on video frames. To avoid shadowbans and reduced reach, you MUST censor sensitive words in ALL text outputs using these substitutions:

- kill/killed/killing → k!ll/k!lled/k!lling
- murder/murdered → murd3r/murd3red  
- death/dead/died → d3ath/d3ad/d!ed
- genocide → g3noc!de
- holocaust → h0locaust
- suicide → su!c!de
- torture/tortured → t0rture/t0rtured
- massacre → ma$$acre
- executed/execution → 3xecuted/3xecution
- assassinated → a$$a$$inated
- bomb/bombed/bombing → b0mb/b0mbed/b0mbing
- nuclear → nucle@r
- war crime → w@r cr!me
- slave/slavery → sl@ve/sl@very
- rape/raped → r@pe/r@ped
- drug/drugs → dr*g/dr*gs
- terrorist/terrorism → terr0rist/terr0rism
- nazi/nazis → n@zi/n@zis
- concentration camp → c0ncentration c@mp
- shooting → sh00ting
- gun/guns → g*n/g*ns
- victim/victims → v!ctim/v!ctims
- prison/prisoner → pr!son/pr!soner
- blood/bloody → bl00d/bl00dy
- corpse → c0rpse
- crime/crimes → cr!me/cr!mes
- abuse/abused → @buse/@bused
- plague → pl@gue
- disturbing → d!sturbing
- atrocity → @trocity

RULE: Apply these substitutions in EVERY text field — slides, descriptions, titles, tweets, everything. The censored words are still perfectly readable to humans but bypass TikTok's automated filters.

Example: "The genocide killed 800,000 people" → "The g3noc!de k!lled 800,000 people"

JSON structure:
{
  "title": "short punchy title (max 60 chars)",
  "hook": "the opening hook line — max 12 words, must create curiosity gap",
  "angle_used": "which angle was applied",
  "slides": [
    {
      "text_overlay": "slide text following the rules above",
      "duration_sec": 8,
      "image_search": "2-4 word specific image query"
    }
  ],
  "comment_bait": "the provocative ending question/statement designed to force comments",
  "tiktok_description": "2500-3000 char mini-article with extra details + 5 hashtags at end",
  "instagram_description": "engaging caption under 2200 chars + 25-30 hashtags",
  "youtube_title": "SEO-rich title, max 100 chars, includes year",
  "youtube_description": "3 paragraphs with keywords",
  "facebook_post": "debate-starting post, opens with question",
  "twitter_post": "under 280 chars, most WTF single fact, 2-3 hashtags",
  "seo_keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"]
}"""


def generate_content(topic: str, format_type: str, angle: str) -> dict:
    """Generate viral content from a topic + angle."""
    today = datetime.date.today().strftime("%B %d")

    user_prompt = f"""Today is {today}. Create VIRAL content about: {topic}

ANGLE: {angle}
FORMAT: {format_type} (9 slides, 7-9 seconds each, total ~70-80 seconds)

CRITICAL CHECKLIST — verify before responding:
☐ Slide 1 hook uses one of the proven hook patterns
☐ Each slide has 40-80 words MAX (readable in 6-8 sec)
☐ Story ESCALATES — each slide more shocking than the last
☐ Final slide is COMMENT BAIT (provocative question or statement)
☐ Specific numbers, names, dates, quotes included
☐ TikTok description is 2500-3000 characters
☐ TikTok description adds NEW details not in the video
☐ Twitter post is the single most shareable fact
☐ image_search queries are 2-4 words, specific

APPLY THE "{angle}" ANGLE:
- If "Dark History": go for the throat. Disturbing details. Things people don't want to hear.
- If "Controversial Take": challenge the popular narrative. Make people ARGUE in comments.
- If "Shocking Facts": every slide should make someone say "no way that's real."
- If "They Lied To You": contrast what people THINK happened vs what ACTUALLY happened.
- If "What They Don't Tell You": hidden details, declassified info, real motivations.

DO NOT write boring educational content. Write content that makes people FEEL something — anger, shock, disbelief, fascination. That's what gets shared.

FINAL CHECK: Did you censor ALL sensitive words using the substitution table above? If not, go back and fix them NOW."""

    result = call_groq(SYSTEM_PROMPT, user_prompt)
    # Safety net: censor any words the LLM missed
    return censor_content(result)


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

    if api_key:
        for sq in search_queries:
            img = _try_pexels(sq, api_key)
            if img:
                return img

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

        for photo in photos:
            src = photo.get("src", {})
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
    """Create a cinematic gradient background."""
    palettes = [
        [(20, 10, 10), (80, 20, 20)],       # blood red (dark history)
        [(10, 10, 25), (30, 30, 80)],        # midnight blue
        [(25, 10, 10), (100, 40, 15)],       # burning amber
        [(10, 20, 15), (25, 70, 40)],        # dark forest
        [(20, 10, 30), (60, 20, 80)],        # deep purple
        [(30, 25, 10), (90, 70, 20)],        # aged gold
        [(15, 15, 20), (45, 45, 65)],        # steel grey
        [(30, 15, 5), (85, 45, 15)],         # dark copper
    ]
    c1, c2 = palettes[idx % len(palettes)]
    img = Image.new("RGB", (VIDEO_W, VIDEO_H))
    draw = ImageDraw.Draw(img)
    for y in range(VIDEO_H):
        t = y / VIDEO_H
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

    font = None
    font_paths = [
        # Linux
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        # Windows
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/impact.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        # macOS
        "/System/Library/Fonts/Helvetica.ttc",
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

    usable_width = int(VIDEO_W * 0.78)
    max_chars = max(18, int(usable_width / (font_size * 0.52)))
    lines = textwrap.wrap(text, width=max_chars)
    line_height = int(font_size * 1.45)

    total_h = len(lines) * line_height
    if position == "center":
        start_y = (VIDEO_H - total_h) // 2
    elif position == "top":
        start_y = 100
    else:
        start_y = VIDEO_H - total_h - 180

    # Semi-transparent background for readability
    if text_bg and lines:
        padding = 45
        bg_top = start_y - padding
        bg_bottom = start_y + total_h + padding
        bg_overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        bg_draw = ImageDraw.Draw(bg_overlay)
        bg_draw.rounded_rectangle(
            [80, bg_top, VIDEO_W - 80, bg_bottom],
            radius=16,
            fill=(0, 0, 0, 190),
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

        # Strong outline for readability on any background
        if shadow:
            for ox in range(-3, 4):
                for oy in range(-3, 4):
                    if ox == 0 and oy == 0:
                        continue
                    draw.text((x + ox, y + oy), line, font=font, fill=(0, 0, 0))

        draw.text((x, y), line, font=font, fill=color)

    return img


def add_darkening_overlay(img: Image.Image, opacity: float = 0.55) -> Image.Image:
    """Add a dark overlay to make text readable."""
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
        alpha = int(200 * (1 - (r_step / 100) ** 2))
        alpha = max(0, min(255, alpha))
        bbox = [cx - r, cy - r, cx + r, cy + r]
        draw.ellipse(bbox, fill=(0, 0, 0, alpha))
    img = Image.alpha_composite(img, vignette)
    return img.convert("RGB")


# ═══════════════════════════════════════════════════════════════
# BACKGROUND MUSIC
# ═══════════════════════════════════════════════════════════════
def create_ambient_music(duration_sec: float) -> str:
    """Create a dark, tension-building ambient track."""
    try:
        from pydub import AudioSegment
        from pydub.generators import Sine

        duration_ms = int(duration_sec * 1000)

        # Dark drone — lower, more ominous
        base = Sine(82.41).to_audio_segment(duration=duration_ms).apply_gain(-26)  # Low E
        # Dissonant minor second for tension
        tension = Sine(87.31).to_audio_segment(duration=duration_ms).apply_gain(-34)  # F
        # Deep sub bass
        sub = Sine(41.20).to_audio_segment(duration=duration_ms).apply_gain(-28)  # Low E octave down
        # Eerie high tone
        eerie = Sine(493.88).to_audio_segment(duration=duration_ms).apply_gain(-38)  # B4

        mix = base.overlay(tension).overlay(sub).overlay(eerie)

        fade_ms = min(4000, duration_ms // 3)
        mix = mix.fade_in(fade_ms).fade_out(fade_ms)
        mix = mix.apply_gain(-6)

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
    """Create a slideshow video with dark, cinematic feel."""
    clips = []

    for i, slide in enumerate(slides):
        duration = slide.get("duration_sec", 8)
        text = slide.get("text_overlay", "")

        bg_img = download_image(slide.get("image_search", title), i)
        bg_img = bg_img.resize((VIDEO_W, VIDEO_H), Image.LANCZOS)
        bg_img = add_darkening_overlay(bg_img, 0.45)  # darker for more drama
        bg_img = add_vignette(bg_img)

        # Main story text
        final_img = add_text_to_image(
            bg_img, text, position="center", font_size=46, text_bg=True
        )

        # Watermark
        final_img = add_text_to_image(
            final_img, "@DailyHistory", position="top", font_size=30, color="#c8a44e"
        )

        # Slide counter (bottom)
        if len(slides) > 1:
            counter_text = f"{i + 1}/{len(slides)}"
            final_img = add_text_to_image(
                final_img, counter_text, position="bottom", font_size=24, color="#888888"
            )

        frame_path = str(OUTPUT_DIR / f"frame_{i}.png")
        final_img.save(frame_path, quality=95)

        clip = ImageClip(frame_path).with_duration(duration)
        clips.append(clip)

    # Cross-dissolve transitions
    final_clips = []
    for i, clip in enumerate(clips):
        if i > 0:
            clip = clip.with_effects([vfx.CrossFadeIn(0.4)])
        if i < len(clips) - 1:
            clip = clip.with_effects([vfx.CrossFadeOut(0.4)])
        final_clips.append(clip)

    final = concatenate_videoclips(final_clips, method="compose")

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

    for clip in final_clips:
        clip.close()

    return output_path


def create_video_clip(slides: list, title: str, uploaded_clips: list = None) -> str:
    """Create a video clip with text overlays."""
    clips = []

    for i, slide in enumerate(slides):
        duration = slide.get("duration_sec", 8)

        bg_img = download_image(slide.get("image_search", title), i)
        bg_img = bg_img.resize((VIDEO_W, VIDEO_H), Image.LANCZOS)
        bg_img = add_darkening_overlay(bg_img, 0.4)
        bg_img = add_vignette(bg_img)
        frame_path = str(OUTPUT_DIR / f"vframe_{i}.png")
        bg_img.save(frame_path)
        base_clip = ImageClip(frame_path).with_duration(duration)

        clips.append(base_clip)

    final = concatenate_videoclips(clips, method="compose")

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
    bearer = os.environ.get("TWITTER_BEARER_TOKEN")
    if not bearer:
        return "📋 MANUAL — Copy tweet below"
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
    token = os.environ.get("FACEBOOK_PAGE_TOKEN")
    page_id = os.environ.get("FACEBOOK_PAGE_ID")
    if not token or not page_id:
        return "📋 MANUAL — Copy post below"
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
def run_pipeline(topic: str, format_type: str, angle: str, progress=gr.Progress()):
    """Main pipeline: topic + angle → viral content → video → descriptions."""

    if not topic.strip():
        raise gr.Error("Scrie un topic! Ex: 'Unit 731 human experiments' or 'CIA MKUltra program'")

    progress(0.1, desc="🧠 Generating viral content...")
    try:
        content = generate_content(topic, format_type, angle)
    except Exception as e:
        raise gr.Error(f"Groq API error: {e}")

    progress(0.4, desc="🎨 Building cinematic frames...")

    slides = content.get("slides", [])
    title = content.get("title", topic)

    progress(0.5, desc=f"🎬 Rendering {format_type.lower()}...")
    try:
        if format_type == "Slideshow":
            video_path = create_slideshow(slides, title)
        else:
            video_path = create_video_clip(slides, title)
    except Exception as e:
        video_path = None
        print(f"Video creation error: {e}")

    progress(0.8, desc="📱 Preparing platform posts...")

    twitter_status = post_to_twitter(content.get("twitter_post", ""))
    facebook_status = post_to_facebook(content.get("facebook_post", ""))

    tiktok_desc = content.get("tiktok_description", "")
    if len(tiktok_desc) > 3000:
        tiktok_desc = tiktok_desc[:2995] + "..."

    progress(1.0, desc="✅ Done!")

    posting_status = f"""═══════════════════════════════════════
  📊 POSTING STATUS
═══════════════════════════════════════

  🎯 Angle:       {content.get('angle_used', angle)}
  💬 Comment Bait: {content.get('comment_bait', 'N/A')}

  𝕏  Twitter:     {twitter_status}
  f  Facebook:    {facebook_status}
  ♪  TikTok:      📋 MANUAL — Upload video + paste description
  ◻  Instagram:   📋 MANUAL — Upload reel + paste description
  ▶  YouTube:     📋 MANUAL — Upload Short + paste title/desc
  @  Threads:     📋 MANUAL — Paste description

═══════════════════════════════════════
  💡 Add API keys in .env to enable auto-posting:
     TWITTER_BEARER_TOKEN, FACEBOOK_PAGE_TOKEN
═══════════════════════════════════════"""

    return (
        video_path,
        content.get("title", ""),
        content.get("hook", ""),
        content.get("comment_bait", ""),
        tiktok_desc,
        f"{len(tiktok_desc)} / 3000 chars",
        content.get("instagram_description", ""),
        content.get("youtube_title", ""),
        content.get("youtube_description", ""),
        content.get("facebook_post", ""),
        content.get("twitter_post", ""),
        posting_status,
        json.dumps(content.get("slides", []), indent=2),
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
.gradio-container { max-width: 1000px !important; }
.main-title {
    text-align: center; font-size: 2.4em; font-weight: 700;
    color: #c8a44e !important; letter-spacing: 0.08em;
    text-transform: uppercase; margin-bottom: 0 !important;
    font-family: 'Playfair Display', Georgia, serif !important;
}
.sub-title {
    text-align: center; font-size: 0.85em; letter-spacing: 0.3em;
    text-transform: uppercase; color: #7a6e58 !important;
    margin-top: 4px !important;
}
.angle-info {
    background: linear-gradient(135deg, #1a1610 0%, #2a2418 100%);
    border: 1px solid #c8a44e33;
    border-radius: 8px; padding: 12px 16px;
    color: #b8a890; font-size: 0.85em; margin-top: 8px;
}
footer { display: none !important; }
"""

def build_ui():
    with gr.Blocks(title="DailyHistory — Viral Pipeline") as app:

        gr.Markdown("<h1 class='main-title'>DailyHistory</h1>")
        gr.Markdown("<p class='sub-title'>Viral Content Pipeline — Dark History Edition</p>")
        gr.Markdown("---")

        # ── INPUT ──
        with gr.Group():
            gr.Markdown("### ① Topic + Viral Angle")
            with gr.Row():
                topic_input = gr.Textbox(
                    label="Topic (English)",
                    placeholder='e.g. "Unit 731 experiments", "CIA MKUltra", "Radium Girls", "What really sank the Titanic"',
                    lines=2,
                    scale=3,
                )
            with gr.Row():
                angle_select = gr.Radio(
                    [
                        "Dark History",
                        "Controversial Take",
                        "Shocking Facts",
                        "They Lied To You",
                        "What They Don't Tell You",
                    ],
                    value="Dark History",
                    label="🎯 Content Angle (how to frame it for max engagement)",
                    scale=2,
                )
                format_type = gr.Radio(
                    ["Slideshow", "Video Clip"],
                    value="Slideshow",
                    label="Format",
                    scale=1,
                )

            gr.Markdown(
                "<div class='angle-info'>"
                "💡 <b>Dark History</b> = disturbing facts & atrocities · "
                "<b>Controversial Take</b> = challenge mainstream narrative · "
                "<b>Shocking Facts</b> = WTF rapid-fire · "
                "<b>They Lied To You</b> = debunk textbook myths · "
                "<b>What They Don't Tell You</b> = hidden details & real reasons"
                "</div>"
            )

            generate_btn = gr.Button(
                "⚡ GENERATE VIRAL CONTENT",
                variant="primary",
                size="lg",
            )

        # ── OUTPUT: VIDEO ──
        gr.Markdown("---")
        gr.Markdown("### ② Your Video")
        video_output = gr.Video(label="Generated Video — download → upload to TikTok")

        with gr.Row():
            title_output = gr.Textbox(label="📌 Title", interactive=False)
            hook_output = gr.Textbox(label="🪝 Hook", interactive=False)

        comment_bait_output = gr.Textbox(
            label="💬 Comment Bait (last slide — forces engagement)",
            interactive=False,
        )

        # ── OUTPUT: TIKTOK ──
        gr.Markdown("---")
        gr.Markdown("### ③ TikTok — Copy & Post")
        tiktok_desc = gr.Textbox(
            label="♪ TikTok Description (select all → copy → paste in TikTok)",
            lines=10,
            interactive=False,
        )
        tiktok_chars = gr.Textbox(label="Character count", interactive=False)

        # ── OUTPUT: OTHER PLATFORMS ──
        gr.Markdown("---")
        gr.Markdown("### ④ Other Platforms")

        with gr.Tab("Instagram"):
            ig_desc = gr.Textbox(label="◻ Instagram Reels", lines=6, interactive=False)

        with gr.Tab("YouTube Shorts"):
            yt_title = gr.Textbox(label="▶ YouTube Title", interactive=False)
            yt_desc = gr.Textbox(label="▶ YouTube Description", lines=5, interactive=False)

        with gr.Tab("Facebook"):
            fb_post = gr.Textbox(label="f Facebook Post", lines=4, interactive=False)

        with gr.Tab("X / Twitter"):
            tw_post = gr.Textbox(label="𝕏 Tweet", lines=3, interactive=False)

        # ── STATUS ──
        gr.Markdown("---")
        gr.Markdown("### ⑤ Status")
        posting_status = gr.Textbox(label="Pipeline results", lines=16, interactive=False)

        # ── SLIDES DATA ──
        with gr.Accordion("🔧 Slides JSON (for CapCut import)", open=False):
            slides_json = gr.Code(language="json", label="Slides data")

        # ── CONNECT ──
        generate_btn.click(
            fn=run_pipeline,
            inputs=[topic_input, format_type, angle_select],
            outputs=[
                video_output, title_output, hook_output,
                comment_bait_output,
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
            "DAILYHISTORY v2.0 — VIRAL DARK HISTORY PIPELINE — GROQ + QWEN3 32B</p>"
        )

    return app


# ═══════════════════════════════════════════════════════════════
# LAUNCH
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = build_ui()
    app.launch(
        server_name="127.0.0.1",
        server_port=int(os.environ.get("PORT", 7860)),
        share=False,
        theme=THEME,
        css=CSS,
    )