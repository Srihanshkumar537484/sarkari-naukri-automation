"""
Main automation - GitHub Actions har 10 min mein chalata hai.

Kaam:
1. Source channel (t.me/s/...) ke SAARE naye messages uthata hai (sirf latest nahi)
2. Har message ko parse karke saaf card-data banata hai (title, dates, posts...)
3. Har message ke liye: 1 POST (image) + 1 REEL (video), alag-alag template se
4. Instagram pe post + reel, Telegram channel pe post
5. State (last id + template counter) save karta hai
"""

import os
import random
import re
import subprocess
import sys
import time

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import designs as D  # noqa: E402

IG_ACCESS_TOKEN = os.environ["IG_ACCESS_TOKEN"]
IG_BUSINESS_ID = os.environ["IG_BUSINESS_ID"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

SOURCE_CHANNEL = "sarkariresulinfo"
OWN_CHANNEL = "@sarkarinaukriupdates2026"
IG_HANDLE = "@sarkarinaukari_oneover"
TG_LINK = "t.me/sarkarinaukriupdates2026"

GITHUB_REPO = "Srihanshkumar537484/sarkari-naukri-automation"
GITHUB_BRANCH = "main"

MAX_PER_RUN = 5        # ek run mein max itne naye messages (Instagram daily limit se bachne ke liye)
FIRST_RUN_LIMIT = 3    # state 0 ho to sirf latest itne
KEEP_MEDIA = 24        # repo mein itne purane media files rakhna

STATE_ID = "state/last_id.txt"
STATE_TPL = "state/template_idx.txt"
MEDIA_DIR = "posts"

API = "https://graph.facebook.com/v19.0"

HASHTAGS = "#SarkariNaukri #GovtJobs #SarkariResult #Jobs2026 #Recruitment #OnlineForm #LatestJobs #SarkariExam"

JOB_WORDS = ("recruitment", "vacancy", "online form", "result", "admit card", "exam date", "answer key",
             "notification", "syllabus", "apply", "posts", "bharti", "भर्ती", "परिणाम", "एडमिट", "आवेदन",
             "cut off", "merit list", "scorecard", "counselling")
PROMO_WORDS = ("click below", "join us", "official sarkari result", "since 2009", "follow us", "join our",
               "instagram.com", "telegram", "whatsapp", "check & apply", "check & download", "download link")


# ------------------------------------------------------------------ state
def read_int(path, default=0):
    try:
        with open(path) as f:
            return int(f.read().strip() or default)
    except (OSError, ValueError):
        return default


def write_int(path, val):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(str(val))


def git(*args, check=True):
    return subprocess.run(["git", *args], check=check, capture_output=True, text=True)


def commit_push(paths, message):
    try:
        git("config", "user.name", "github-actions")
        git("config", "user.email", "actions@github.com")
        git("add", "-A", *paths)
        r = git("commit", "-m", message, check=False)
        if "nothing to commit" in (r.stdout + r.stderr):
            return
        for _ in range(3):
            p = git("push", check=False)
            if p.returncode == 0:
                return
            git("pull", "--rebase", "--autostash", check=False)
        print("push fail:", p.stderr[-300:])
    except Exception as e:  # noqa: BLE001
        print("git error:", e)


# ---------------------------------------------------------------- scraping
def fetch_messages():
    """Channel ke preview page se [(id, text, links)] deta hai (purane -> naye)."""
    r = requests.get(f"https://t.me/s/{SOURCE_CHANNEL}", headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    soup = BeautifulSoup(r.text, "html.parser")
    out = []
    for m in soup.select("div.tgme_widget_message"):
        post = m.get("data-post", "")
        mm = re.match(rf"{re.escape(SOURCE_CHANNEL)}/(\d+)$", post)
        if not mm:
            continue
        t = m.select_one("div.tgme_widget_message_text")
        text, links = "", []
        if t:
            for br in t.find_all("br"):
                br.replace_with("\n")
            links = [a.get("href", "") for a in t.find_all("a") if a.get("href", "").startswith("http")]
            text = t.get_text()
        out.append((int(mm.group(1)), text.strip(), links))
    out.sort(key=lambda x: x[0])
    return out


# ----------------------------------------------------------------- parsing
KV = re.compile(r"^[\W_]*([A-Za-z][A-Za-z0-9 /&().'\-]{1,32}?)\s*[:：]\s*(.+)$")


def chip_for(blob):
    b = blob.lower()
    if "admit card" in b or "hall ticket" in b:
        return "ADMIT CARD OUT"
    if "answer key" in b:
        return "ANSWER KEY"
    if "result" in b or "merit list" in b or "cut off" in b:
        return "RESULT OUT"
    if "syllabus" in b:
        return "SYLLABUS"
    if "exam date" in b or "exam city" in b or "time table" in b:
        return "EXAM DATE"
    if any(w in b for w in ("recruitment", "vacancy", "online form", "bharti", "apply online", "notification")):
        return "NEW VACANCY"
    return "LATEST UPDATE"


def parse_message(text, links):
    """Raw telegram text -> dict(title, rows, chip, link, summary) ya None (agar job-post nahi)."""
    if not text or len(text) < 25:
        return None
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    apply_link = next((u for u in links if "instagram.com" not in u and "t.me" not in u), "")
    title, rows, extras = "", [], []
    for raw in lines:
        low = raw.lower()
        if raw.startswith("#") or low.startswith("http"):
            continue
        if any(p in low for p in PROMO_WORDS) and not KV.match(D.clean_text(raw, False) or ""):
            continue
        c = D.clean_text(raw)
        if not c:
            continue
        kv = KV.match(D.clean_text(raw, False))
        if kv and title:
            label = kv.group(1).strip().title()
            val = kv.group(2).strip()
            if not val.lower().startswith("http") and len(val) <= 90:
                hi = any(k in label.lower() for k in ("last date", "exam date", "closing", "end date", "last"))
                rows.append((label, val, hi))
            continue
        if not title:
            letters = re.findall(r"[A-Za-z]", D.clean_text(raw, False))
            if len(letters) >= 10:
                title = c.strip(" -:|")
                continue
            extras.append(c)  # hindi hook line etc
            continue
        extras.append(c)
    if not title:
        return None
    # sirf title + rows se decide karo (source ke hashtags/promo se nahi)
    blob = (title + " " + " ".join(f"{a} {b}" for a, b, _ in rows) + " " + " ".join(extras)).lower()
    if not any(w in blob for w in JOB_WORDS):
        return None
    if len(title) > 150:
        title = title[:147].rsplit(" ", 1)[0] + "..."
    if not rows and extras:
        body = " ".join(extras)
        if len(body) > 20:
            rows.append(("Details", body[:90].rsplit(" ", 1)[0] + "..." if len(body) > 90 else body, False))
    if rows and not any(r[2] for r in rows):
        rows = [(a, b, i == len(rows) - 1) if any(k in a.lower() for k in ("date", "last")) else (a, b, False)
                for i, (a, b, _) in enumerate(rows)]
    rows = rows[:5]
    return {"title": title, "rows": rows, "chip": chip_for(title.lower()) if chip_for(title.lower()) != "LATEST UPDATE" else chip_for(blob), "link": apply_link,
            "handle": IG_HANDLE, "tg": TG_LINK}


def build_caption(d, limit=2100):
    lines = [f"{d['chip']} | {d['title']}", ""]
    for lbl, val, _ in d["rows"]:
        lines.append(f"▪ {lbl}: {val}")
    if d["link"]:
        lines += ["", f"🔗 Apply / Details: {d['link']}"]
    lines += ["", f"📢 Daily updates: {TG_LINK}", f"📲 Follow {IG_HANDLE}", "", HASHTAGS]
    return "\n".join(lines)[:limit]


# ----------------------------------------------------------------- publishing
def cdn_urls(rel):
    return [f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{rel}",
            f"https://cdn.jsdelivr.net/gh/{GITHUB_REPO}@{GITHUB_BRANCH}/{rel}"]


def ig_post(url, path, params):
    r = requests.post(f"{API}/{IG_BUSINESS_ID}/{path}", data={**params, "access_token": IG_ACCESS_TOKEN}, timeout=60)
    return r.json()


def ig_wait_finished(cid, tries=40, delay=8):
    for _ in range(tries):
        j = requests.get(f"{API}/{cid}", params={"fields": "status_code", "access_token": IG_ACCESS_TOKEN}, timeout=30).json()
        st = j.get("status_code")
        if st == "FINISHED":
            return True
        if st in ("ERROR", "EXPIRED"):
            print("container status:", j)
            return False
        time.sleep(delay)
    return False


def ig_publish(cid):
    for _ in range(12):
        j = ig_post(None, "media_publish", {"creation_id": cid})
        if "id" in j:
            return j["id"]
        err = j.get("error", {})
        if err.get("code") in (9007, 2207027) or "not ready" in str(err).lower():
            time.sleep(10)
            continue
        print("publish error:", j)
        return None
    return None


def publish_image(rel, caption):
    for url in cdn_urls(rel):
        j = ig_post(None, "media", {"image_url": url, "caption": caption})
        if "id" in j and ig_wait_finished(j["id"], tries=12, delay=5):
            pid = ig_publish(j["id"])
            if pid:
                return pid
        else:
            print("image container fail:", url, j)
    return None


def publish_reel(rel, caption):
    for url in reversed(cdn_urls(rel)):   # video ke liye jsDelivr pehle (sahi MIME type)
        j = ig_post(None, "media", {"media_type": "REELS", "video_url": url, "caption": caption, "share_to_feed": "true"})
        if "id" in j and ig_wait_finished(j["id"]):
            pid = ig_publish(j["id"])
            if pid:
                return pid
        else:
            print("reel container fail:", url, j)
    return None


def telegram_photo(path, caption):
    with open(path, "rb") as f:
        r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto",
                          data={"chat_id": OWN_CHANNEL, "caption": caption[:1024]}, files={"photo": f}, timeout=60)
    print("telegram:", r.json().get("ok"), r.json().get("description", ""))


def tg_caption(d):
    lines = [f"🔔 {d['chip']}", d["title"], ""]
    lines += [f"▪ {l}: {v}" for l, v, _ in d["rows"]]
    if d["link"]:
        lines += ["", f"🔗 {d['link']}"]
    lines += ["", f"📲 Instagram: {IG_HANDLE}"]
    return "\n".join(lines)


# ------------------------------------------------------------------- main
def cleanup_media():
    try:
        files = sorted(f for f in os.listdir(MEDIA_DIR) if re.match(r"\d+_(post|reel)\.", f))
        ids = sorted({int(f.split("_")[0]) for f in files})
        for old in ids[:-KEEP_MEDIA]:
            for f in files:
                if f.startswith(f"{old}_"):
                    git("rm", "-q", "-f", os.path.join(MEDIA_DIR, f), check=False)
    except FileNotFoundError:
        pass


def main():
    msgs = fetch_messages()
    if not msgs:
        print("Channel page se koi message nahi mila.")
        return
    latest = msgs[-1][0]
    last_id = read_int(STATE_ID)
    if last_id > latest:      # purana/kharab state (bot wale time ka) -> reset
        last_id = 0
    new = [m for m in msgs if m[0] > last_id]
    if not new:
        print("Koi naya message nahi.")
        return
    limit = FIRST_RUN_LIMIT if last_id == 0 else MAX_PER_RUN
    skipped_older = max(0, len(new) - limit)
    new = new[-limit:]
    print(f"{len(new)} naye message process honge (last_id={last_id}, latest={latest}, older_skipped={skipped_older})")

    order = list(range(D.N_TEMPLATES))
    random.Random(2026).shuffle(order)     # fixed shuffle: 30 template ghoom-ghoom ke, repeat nahi
    tpl = read_int(STATE_TPL)

    jobs = []
    os.makedirs(MEDIA_DIR, exist_ok=True)
    for mid, text, links in new:
        d = parse_message(text, links)
        if not d:
            print(f"#{mid}: job-post nahi / text kam - skip")
            continue
        post_rel, reel_rel = f"{MEDIA_DIR}/{mid}_post.jpg", f"{MEDIA_DIR}/{mid}_reel.mp4"
        try:
            D.render_post(d, order[tpl % len(order)], post_rel)
            tpl += 1
            D.render_reel(d, order[tpl % len(order)], reel_rel)
            tpl += 1
        except Exception as e:  # noqa: BLE001
            print(f"#{mid}: media banane mein error: {e}")
            continue
        jobs.append((mid, d, post_rel, reel_rel))
        print(f"#{mid}: media ready -> {d['chip']} | {d['title'][:60]}")

    write_int(STATE_TPL, tpl)
    if jobs:
        commit_push([MEDIA_DIR, STATE_TPL], f"Add media for {len(jobs)} update(s)")
        time.sleep(20)     # CDN ko files dikhne mein thoda time

    for mid, d, post_rel, reel_rel in jobs:
        cap = build_caption(d)
        try:
            print(f"#{mid}: Instagram post ->", publish_image(post_rel, cap))
        except Exception as e:  # noqa: BLE001
            print(f"#{mid}: IG post error: {e}")
        try:
            print(f"#{mid}: Instagram reel ->", publish_reel(reel_rel, cap))
        except Exception as e:  # noqa: BLE001
            print(f"#{mid}: IG reel error: {e}")
        try:
            telegram_photo(post_rel, tg_caption(d))
        except Exception as e:  # noqa: BLE001
            print(f"#{mid}: Telegram error: {e}")
        write_int(STATE_ID, mid)
        commit_push([STATE_ID], f"Processed message {mid}")

    write_int(STATE_ID, latest)      # skip hue (non-job / purane) messages bhi aage badh jayein
    cleanup_media()
    commit_push([STATE_ID, MEDIA_DIR], "Update state")
    print("Done. last_id =", latest)


if __name__ == "__main__":
    main()
