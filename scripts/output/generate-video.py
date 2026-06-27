"""
AI Briefing Video Generator — English slideshow with narration.

Generates a visually rich slideshow video with gradient backgrounds,
optional stock photos per slide, and TTS narration.

Usage:
  1. Agent writes slides JSON (see schema below)
  2. Run: python generate-video.py slides.json
  3. Output: C:/reports/ai/YYYY-MM-DD/ai-briefing.mp4

Dependencies: pip install edge-tts moviepy Pillow requests
Also needs: FFmpeg on PATH

Slides JSON schema:
{
  "slides": [
    {
      "title": "Section title",
      "bullets": ["point 1", "point 2"],
      "duration": 15,
      "image_query": "artificial intelligence brain network"
    }
  ],
  "narration": "Full English narration text (conversational style)"
}
"""
import asyncio
import json
import math
import os
import sys
import textwrap
from datetime import date
from io import BytesIO

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from config import REPORTS_ROOT

DATE_FOLDER = date.today().strftime("%Y-%m-%d")
OUTPUT_DIR = os.path.join(REPORTS_ROOT, DATE_FOLDER)
OUTPUT_VIDEO = os.path.join(OUTPUT_DIR, "ai-briefing.mp4")
TEMP_AUDIO = os.path.join(OUTPUT_DIR, "_temp_narration.mp3")

VOICE = "en-IN-PrabhatNeural"  # India English male; see routes.ai_news.TTS_VOICE_EN
RATE = "-5%"
PITCH = "+0Hz"

WIDTH, HEIGHT = 1280, 720
FPS = 12

GRADIENT_PALETTES = [
    [(10, 15, 40), (20, 50, 100)],
    [(15, 10, 45), (60, 20, 80)],
    [(5, 30, 50), (10, 70, 90)],
    [(30, 10, 35), (80, 30, 60)],
    [(10, 25, 30), (20, 80, 70)],
    [(20, 15, 50), (50, 30, 100)],
    [(5, 20, 45), (15, 60, 100)],
    [(25, 10, 30), (70, 25, 50)],
    [(10, 30, 40), (30, 90, 80)],
    [(15, 20, 55), (40, 50, 110)],
    [(20, 10, 40), (90, 40, 70)],
    [(5, 25, 35), (25, 70, 60)],
]

PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY", "")


async def generate_tts(text: str, output_path: str):
    import edge_tts
    communicate = edge_tts.Communicate(text, VOICE, rate=RATE, pitch=PITCH)
    await communicate.save(output_path)


def draw_gradient(draw, width, height, color_top, color_bot):
    for y in range(height):
        ratio = y / height
        r = int(color_top[0] + (color_bot[0] - color_top[0]) * ratio)
        g = int(color_top[1] + (color_bot[1] - color_top[1]) * ratio)
        b = int(color_top[2] + (color_bot[2] - color_top[2]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))


def fetch_stock_photo(query: str, width: int, height: int):
    """Fetch a stock photo from Pixabay. Returns a PIL Image or None."""
    if not PIXABAY_API_KEY:
        return None
    try:
        import requests
        url = "https://pixabay.com/api/"
        params = {
            "key": PIXABAY_API_KEY,
            "q": query,
            "image_type": "photo",
            "orientation": "horizontal",
            "min_width": width,
            "per_page": 3,
            "safesearch": "true",
        }
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        hits = data.get("hits", [])
        if not hits:
            return None
        img_url = hits[0].get("webformatURL", "")
        if not img_url:
            return None
        img_resp = requests.get(img_url, timeout=15)
        from PIL import Image
        return Image.open(BytesIO(img_resp.content)).convert("RGB")
    except Exception:
        return None


def create_slide_image(
    title: str,
    bullets: list,
    slide_num: int,
    total: int,
    palette_idx: int,
    stock_photo=None,
):
    from PIL import Image, ImageDraw, ImageFont, ImageFilter

    img = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(img)

    palette = GRADIENT_PALETTES[palette_idx % len(GRADIENT_PALETTES)]
    draw_gradient(draw, WIDTH, HEIGHT, palette[0], palette[1])

    if stock_photo:
        photo = stock_photo.copy()
        photo = photo.resize((WIDTH, HEIGHT), Image.LANCZOS)
        photo = photo.filter(ImageFilter.GaussianBlur(radius=6))
        from PIL import ImageEnhance
        photo = ImageEnhance.Brightness(photo).enhance(0.35)
        img.paste(photo, (0, 0))
        draw = ImageDraw.Draw(img)

    try:
        title_font = ImageFont.truetype("arial.ttf", 36)
        bullet_font = ImageFont.truetype("arial.ttf", 22)
        footer_font = ImageFont.truetype("arial.ttf", 16)
        label_font = ImageFont.truetype("arial.ttf", 14)
    except (OSError, IOError):
        title_font = ImageFont.load_default()
        bullet_font = ImageFont.load_default()
        footer_font = ImageFont.load_default()
        label_font = ImageFont.load_default()

    accent = (
        min(palette[1][0] + 80, 255),
        min(palette[1][1] + 80, 255),
        min(palette[1][2] + 80, 255),
    )
    draw.rectangle([(0, 0), (WIDTH, 5)], fill=accent)
    draw.rectangle([(0, HEIGHT - 5), (WIDTH, HEIGHT)], fill=accent)

    card_x, card_y = 40, 55
    card_w, card_h = WIDTH - 80, 90
    card_overlay = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 140))
    img.paste(
        Image.alpha_composite(
            img.crop((card_x, card_y, card_x + card_w, card_y + card_h)).convert("RGBA"),
            card_overlay,
        ).convert("RGB"),
        (card_x, card_y),
    )
    draw = ImageDraw.Draw(img)

    draw.rectangle([(card_x, card_y), (card_x + 5, card_y + card_h)], fill=accent)

    wrapped_title = textwrap.fill(title, width=55)
    draw.text((card_x + 20, card_y + 15), wrapped_title, fill=(255, 255, 255), font=title_font)

    slide_label = f"{slide_num:02d} / {total:02d}"
    draw.text((WIDTH - 120, card_y + 20), slide_label, fill=accent, font=label_font)

    y = card_y + card_h + 20
    content_x = 60

    for bullet in bullets[:7]:
        wrapped = textwrap.fill(bullet, width=65)
        lines = wrapped.split("\n")

        bullet_bg_h = len(lines) * 30 + 12
        bullet_overlay = Image.new("RGBA", (WIDTH - 100, bullet_bg_h), (0, 0, 0, 80))
        if y + bullet_bg_h < HEIGHT - 60:
            img.paste(
                Image.alpha_composite(
                    img.crop((50, y, WIDTH - 50, y + bullet_bg_h)).convert("RGBA"),
                    bullet_overlay,
                ).convert("RGB"),
                (50, y),
            )
        draw = ImageDraw.Draw(img)

        draw.text((content_x, y + 6), "▸", fill=accent, font=bullet_font)
        for j, line in enumerate(lines):
            text_x = content_x + 30 if j == 0 else content_x + 30
            draw.text((text_x, y + 6 + j * 30), line, fill=(220, 220, 235), font=bullet_font)

        y += bullet_bg_h + 8
        if y > HEIGHT - 70:
            break

    footer_text = f"AI Briefing {date.today().strftime('%Y-%m-%d')}"
    draw.text((40, HEIGHT - 40), footer_text, fill=(80, 80, 100), font=footer_font)

    if stock_photo:
        draw.text((WIDTH - 200, HEIGHT - 40), "Photo: Pixabay", fill=(60, 60, 80), font=footer_font)

    return img


def build_video(slides_data: list, audio_path: str):
    from moviepy import ImageClip, AudioFileClip, concatenate_videoclips

    audio = AudioFileClip(audio_path)
    total_duration = audio.duration

    total_slides = len(slides_data)
    if total_slides == 0:
        print("Error: no slides provided")
        return

    total_weight = sum(s.get("duration", 10) for s in slides_data)
    clips = []

    print(f"Creating {total_slides} slides at {WIDTH}x{HEIGHT} @ {FPS}fps...")

    photos = {}
    if PIXABAY_API_KEY:
        print("Fetching stock photos from Pixabay...")
        for i, slide in enumerate(slides_data):
            query = slide.get("image_query", "")
            if query:
                photo = fetch_stock_photo(query, WIDTH, HEIGHT)
                if photo:
                    photos[i] = photo
                    print(f"  Slide {i+1}: photo found for '{query}'")
                else:
                    print(f"  Slide {i+1}: no photo for '{query}'")
    else:
        print("No PIXABAY_API_KEY set — using gradient backgrounds only")

    for i, slide in enumerate(slides_data):
        weight = slide.get("duration", 10)
        slide_duration = (weight / total_weight) * total_duration

        img = create_slide_image(
            slide.get("title", ""),
            slide.get("bullets", []),
            i + 1,
            total_slides,
            i,
            stock_photo=photos.get(i),
        )

        temp_img_path = f"{OUTPUT_DIR}/_temp_slide_{i}.png"
        img.save(temp_img_path)

        clip = ImageClip(temp_img_path).with_duration(slide_duration)
        clips.append(clip)

    video = concatenate_videoclips(clips, method="compose")
    video = video.with_audio(audio)

    est_frames = int(total_duration * FPS)
    est_minutes = math.ceil(est_frames / 14 / 60)
    print(f"Encoding {est_frames} frames — estimated ~{est_minutes} min...")

    video.write_videofile(
        OUTPUT_VIDEO,
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        threads=4,
        logger="bar",
    )

    for i in range(total_slides):
        temp = f"{OUTPUT_DIR}/_temp_slide_{i}.png"
        if os.path.exists(temp):
            os.remove(temp)
    if os.path.exists(audio_path):
        os.remove(audio_path)

    print(f"Video saved to: {OUTPUT_VIDEO}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python generate-video.py <slides.json>")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    data_path = sys.argv[1]
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    slides = data.get("slides", [])
    narration = data.get("narration", "")

    if not narration:
        print("Error: narration text is empty")
        sys.exit(1)
    if not slides:
        print("Error: no slides provided")
        sys.exit(1)

    print("Generating TTS audio...")
    asyncio.run(generate_tts(narration, TEMP_AUDIO))

    print("Building video...")
    build_video(slides, TEMP_AUDIO)


if __name__ == "__main__":
    main()
