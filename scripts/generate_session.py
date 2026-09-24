"""
Ye script SIRF EK BAAR apne local phone/laptop pe chalani hai (GitHub Actions pe nahi).
Isse ek session string milega - GitHub Secrets mein TELEGRAM_SESSION naam se daalna hai.
"""

from telethon.sync import TelegramClient
from telethon.sessions import StringSession

api_id = input("Apna API ID daalo: ")
api_hash = input("Apna API Hash daalo: ")

with TelegramClient(StringSession(), int(api_id), api_hash) as client:
    session_string = client.session.save()
    print("\n\n=== Ye session string GitHub Secrets mein TELEGRAM_SESSION naam se daalo ===\n")
    print(session_string)
    print("\n=== Isse kisi ke saath share mat karna ===\n")
