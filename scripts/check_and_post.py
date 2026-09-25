"""
Main automation script - GitHub Actions har 15 min mein isse chalata hai.
"""

import os
import re
import random
import subprocess
import time
import requests

from PIL import Image, ImageDraw, ImageFont

IG_ACCESS_TOKEN = os.environ["IG_ACCESS_TOKEN"]
IG_BUSINESS_ID = os.environ["IG_BUSINESS_ID"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

SOURCE_CHANNEL = "sarkariresulinfo"
OWN_CHANNEL = "@sarkarinaukriupdates2026"

GITHUB_REPO = "Srihanshkumar537484/sarkari-naukri-automation"
GITHUB_BRANCH = "main"

STATE_FILE = "state/last_id.txt"
POSTS_DIR = "posts"

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

THEMES = [
    {"bg": (18, 32, 68), "accent": (255, 187, 51)},
    {"bg": (12, 74, 58), "accent": (255, 255, 255)},
    {"bg": (120, 20, 30), "accent": (255, 210, 0)},
    {"bg": (30, 30, 30), "accent": (0, 200, 120)},
    {"bg": (25, 60, 110), "accent": (255, 120, 40)},
]


def get_last_seen_id():
    if not os.path.exists(STATE_FILE):
        return 0
    with open(STATE_FILE, "r") as f:
        content = f.read().strip()
        return int(content) if content else 0


def save_last_seen_id(msg_id):
    os.makedirs("state", exist_ok=True)
    with open(STATE_FILE, "w") as f:
        f.write(str(msg_id))


def get_new_channel_message():
    last_id = get_last_seen_id()

    url = f"https://t.me/s/{SOURCE_CHANNEL}"
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    html = response.text

    post_ids = [int(m) for m in re.findall(rf'data-post="{SOURCE_CHANNEL}/(\d+)"', html)]
    if not post_ids:
        return None, last_id

    latest_id = max(post_ids)
    if latest_id <= last_id:
        return None, last_id

    blocks = html.split('class="tgme_widget_message ')
    latest_block = blocks[-1]

    text_match = re.search(
        r'class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
        latest_block, re.DOTALL,
    )
    if not text_match:
        return None, latest_id

    raw_text = text_match.group(1)
    text = re.sub(r"<br\s*/?>", "\n", raw_text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").strip()

    if not text:
        return None, latest_id

    return text, latest_id


def wrap_text(draw, text, font, max_width):
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def generate_image(text, msg_id):
    theme = random.choice(THEMES)
    bg_color = theme["bg"]
    accent = theme["accent"]

    size = 1080
    img = Image.new("RGB", (size, size), color=bg_color)
    draw = ImageDraw.Draw(img)

    title_font = ImageFont.truetype(FONT_BOLD, 54)
    body_font = ImageFont.truetype(FONT_BOLD, 40)
    footer_font = ImageFont.truetype(FONT_REGULAR, 28)

    margin = 70

    draw.rectangle([0, 0, size, 160], fill=accent)
    title_color = bg_color if sum(accent) > 400 else (255, 255, 255)
    draw.text((margin, 45), "SARKARI NAUKRI UPDATE", font=title_font, fill=title_color)

    draw.rectangle([0, 160, size, 168], fill=(255, 255, 255))

    max_width = size - 2 * margin
    lines = wrap_text(draw, text, body_font, max_width)

    y = 260
    line_height = 58
    max_lines = 12
    for line in lines[:max_lines]:
        draw.text((margin, y), line, font=body_font, fill=(255, 255, 255))
        y += line_height

    footer_y = size - 90
    draw.rectangle([0, footer_y, size, size], fill=accent)
    footer_text_color = bg_color if sum(accent) > 400 else (255, 255, 255)
    draw.text((margin, footer_y + 25), "Follow @sarkarinaukari_oneover", font=footer_font, fill=footer_text_color)

    os.makedirs(POSTS_DIR, exist_ok=True)
    filename = f"{msg_id}.jpg"
    output_path = os.path.join(POSTS_DIR, filename)
    img.save(output_path, "JPEG", quality=90)
    return output_path, filename


def commit_and_push(image_path, msg_id):
    subprocess.run(["git", "config", "user.name", "github-actions"], check=True)
    subprocess.run(["git", "config", "user.email", "actions@github.com"], check=True)
    subprocess.run(["git", "add", image_path, STATE_FILE], check=True)

    result = subprocess.run(
        ["git", "commit", "-m", f"Add post for message {msg_id}"],
        capture_output=True, text=True,
    )
    print("Commit output:", result.stdout, result.stderr)

    subprocess.run(["git", "push"], check=True)


def get_raw_url(filename):
    return f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{POSTS_DIR}/{filename}"


def post_to_instagram(image_url, caption):
    create_url = f"https://graph.facebook.com/v19.0/{IG_BUSINESS_ID}/media"
    r1 = requests.post(create_url, params={
        "image_url": image_url,
        "caption": caption,
        "access_token": IG_ACCESS_TOKEN,
    })
    data1 = r1.json()
    creation_id = data1.get("id")
    if not creation_id:
        raise Exception(f"Media container creation failed: {data1}")

    publish_url = f"https://graph.facebook.com/v19.0/{IG_BUSINESS_ID}/media_publish"
    r2 = requests.post(publish_url, params={
        "creation_id": creation_id,
        "access_token": IG_ACCESS_TOKEN,
    })
    data2 = r2.json()
    print("Instagram publish response:", data2)
    return data2


def post_to_telegram(image_path, caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    with open(image_path, "rb") as f:
        response = requests.post(
            url,
            data={"chat_id": OWN_CHANNEL, "caption": caption[:1024]},
            files={"photo": f},
        )
    data = response.json()
    print("Telegram post response:", data)
    return data


def main():
    text, new_id = get_new_channel_message()

    if text is None:
        print("Koi naya message nahi mila.")
        if new_id and new_id != get_last_seen_id():
            save_last_seen_id(new_id)
            subprocess.run(["git", "config", "user.name", "github-actions"], check=True)
            subprocess.run(["git", "config", "user.email", "actions@github.com"], check=True)
            subprocess.run(["git", "add", STATE_FILE], check=True)
            subprocess.run(["git", "commit", "-m", "Update last seen id (no text post)"], check=False)
            subprocess.run(["git", "push"], check=False)
        return

    print(f"Naya message mila (id={new_id}):", text[:100])

    image_path, filename = generate_image(text, new_id)
    save_last_seen_id(new_id)
    commit_and_push(image_path, new_id)

    time.sleep(10)

    image_url = get_raw_url(filename)
    print("Image URL:", image_url)

    caption = text[:2000]
    post_to_instagram(image_url, caption)
    post_to_telegram(image_path, caption)

    print("Done, last_id =", new_id)


if __name__ == "__main__":
    main()
