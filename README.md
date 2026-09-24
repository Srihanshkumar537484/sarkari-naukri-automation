# Sarkari Naukri Instagram Automation

Instagram page "Sarkari Naukri One Over" ke liye automation - naya sarkari naukri
update aane par auto post/reel banake publish karna.

## Setup

1. Repo clone karo:
   ```
   git clone <your-repo-url>
   cd sarkari-naukri-automation
   ```

2. Dependencies install karo:
   ```
   pip install -r requirements.txt
   ```

3. `.env.example` ko copy karke `.env` banao:
   ```
   cp .env.example .env
   ```

4. `.env` file khol ke apna real Instagram access token aur Business Account ID daalo.
   **Ye `.env` file kabhi commit/push mat karna** - `.gitignore` mein already add hai.

5. Test karo:
   ```
   python test_post.py
   ```
   Agar sab sahi hai, tumhari Instagram page pe ek test image post ho jayegi.

## Security

- `.env` file mein real token/secrets hote hain - ise kabhi GitHub par push mat karo.
- Agar koi token/secret galti se kahin expose ho jaye (chat, screenshot, public repo),
  usse turant Facebook Developer console mein regenerate/reset kar do.

## Next Steps (aage banana hai)

- Telegram listener (naya update detect karne ke liye)
- Auto image/reel generation (job details ke saath)
- Full pipeline: Telegram -> generate content -> Instagram publish
