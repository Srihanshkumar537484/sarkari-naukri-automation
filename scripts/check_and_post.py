"""
Main automation script - GitHub Actions har 15 min mein isse chalata hai.
"""

import os
import requests
from PIL import Image, ImageDraw, ImageFont

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

IMGBB_API_KEY = os.environ["IMGBB_API_KEY"]

IG_ACCESS_TOKEN = os.environ["IG_ACCESS_TOKEN"]
IG_BUSINESS_ID = os.environ["IG_BUSINESS_ID"]

STATE_FILE = "state/last_id.txt"


def get_last_seen_id():
    if not os.path.exists(STATE_FILE):
        return 0
    with open(STATE_FILE, "r") as f:
        content = f.read().strip()
        return int(content) if content else 0


def save_last_seen_id(update_id):
    os.makedirs("state", exist_ok=True)
    with open(STATE_FILE, "w") as f:
        f.write(str(update_id))


def get_new_telegram_message():
    last_id = get_last_seen_id()

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    params = {"offset": last_id + 1} if last_id else {}
    response = requests.get(url, params=params)
    data = response.json()

    if not data.get("ok") or not data.get("result"):
        return None, last_id

    latest_update = data["result"][-1]
    update_id = latest_update["update_id"]
    message = latest_update.get("message", {})
    text = message.get("text", "")

    if not text:
        return None, update_id

    return text, update_id


def generate_image(text):
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

    output_path = "generated_post.jpg"
    img.save(output_path, "JPEG")
    return output_path


def upload_to_imgbb(image_path):
    with open(image_path, "rb") as f:
        response = requests.post(
            "https://api.imgbb.com/1/upload",
            params={"key": IMGBB_API_KEY},
            files={"image": f},
        )
    data = response.json()
    if not data.get("success"):
        raise Exception(f"ImgBB upload failed: {data}")
    return data["data"]["url"]


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
    text, new_id = get_new_telegram_message()

    if text is None:
        print("Koi naya message nahi mila.")
        if new_id:
            save_last_seen_id(new_id)
        return

    print(f"Naya message mila (update_id={new_id}):", text[:100])

    image_path = generate_image(text)
    image_url = upload_to_imgbb(image_path)
    print("Image uploaded:", image_url)

    caption = text[:2000]
    post_to_instagram(image_url, caption)

    save_last_seen_id(new_id)
    print("State update ho gaya, last_id =", new_id)


if __name__ == "__main__":
    main()
