"""
Test script - Instagram Graph API se ek test image post karta hai.
Isse chalake confirm karo ki token aur IG Business ID sahi se kaam kar rahe hain.

Chalane se pehle:
1. .env.example ko copy karke .env banao
2. .env mein apna real IG_ACCESS_TOKEN aur IG_BUSINESS_ID daalo
3. pip install -r requirements.txt
4. python test_post.py
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_ID = os.getenv("IG_BUSINESS_ID")

if not TOKEN or not IG_ID:
    print("ERROR: .env file mein IG_ACCESS_TOKEN ya IG_BUSINESS_ID missing hai.")
    print("Pehle .env.example ko .env mein copy karke values fill karo.")
    exit(1)

# Test ke liye koi bhi publicly accessible image URL
image_url = "https://picsum.photos/1080/1080"

def create_media_container():
    """Step A: Media container banata hai (photo upload karne se pehle)."""
    url = f"https://graph.facebook.com/v19.0/{IG_ID}/media"
    params = {
        "image_url": image_url,
        "caption": "Test post - automation setup check",
        "access_token": TOKEN,
    }
    response = requests.post(url, params=params)
    data = response.json()
    print("Create container response:", data)
    return data.get("id")


def publish_media(creation_id):
    """Step B: Container ko actually publish karta hai Instagram par."""
    url = f"https://graph.facebook.com/v19.0/{IG_ID}/media_publish"
    params = {
        "creation_id": creation_id,
        "access_token": TOKEN,
    }
    response = requests.post(url, params=params)
    data = response.json()
    print("Publish response:", data)
    return data


if __name__ == "__main__":
    creation_id = create_media_container()

    if creation_id:
        publish_media(creation_id)
        print("\nDone. Instagram page check karo - test post dikhna chahiye.")
    else:
        print("\nContainer creation fail hui - publish nahi hua. Upar ka error dekho.")
