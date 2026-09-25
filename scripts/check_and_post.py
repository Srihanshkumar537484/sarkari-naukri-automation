
"""
Main automation script - GitHub Actions har 15 min mein isse chalata hai.
"""

import os
import re
import subprocess
import time
import requests

from PIL import Image, ImageDraw, ImageFont

IG_ACCESS_TOKEN = os.environ["IG_ACCESS_TOKEN"]
IG_BUSINESS_ID = os.environ["IG_BUSINESS_ID"]

TELEGRAM_CHANNEL = "sarkariresulinfo"

GITHUB_REPO = "Srihanshkumar537484/sarkari-naukri-automation"
GITHUB_BRANCH = "main"

STATE_FILE = "state/last_id.txt"
POSTS_DIR = "posts"


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

    url = f"https://t.me/s/{TELEGRAM_CHANNEL}"
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    html = response.text

    post_ids = [int(m) for m in re.findall(rf'data-post="{TELEGRAM_CHANNEL}/(\d+)"', html)]
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


def generate_image(text, msg_id):
    img = Image.new("RGB", (1080, 1080), color=(20, 60, 130))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 42)
    except Exception:
        font = ImageFont.load_default()

    margin = 60
    max_width = 1080 - 2 * margin
    words = text.split()
    lines = []
    current_line = ""
    for word in words:
        test_line = f"{current_line} {word}".strip()
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current_line = test_line
        else:
            lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)

    y = 300
    for line in lines[:12]:
        draw.text((margin, y), line, font=font, fill=(255, 255, 255))
        y += 55

    os.makedirs(POSTS_DIR, exist_ok=True)
    filename = f"{msg_id}.jpg"
    output_path = os.path.join(POSTS_DIR, filename)
    img.save(output_path, "JPEG")
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

    print("Done, last_id =", new_id)


if __name__ == "__main__":
    main()
