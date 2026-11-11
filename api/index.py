import os
import re
import json
import base64
import urllib.parse
import requests
import feedparser
from bs4 import BeautifulSoup
from fastapi import FastAPI, Request
import google.generativeai as genai
from supabase import create_client

app = FastAPI()

# متغیرهای امنیتی سرور
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

SUPABASE_URL = "https://jyygdwigldlobcperron.supabase.co"
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

WP_URL = "https://teasevan.s3-tastewp.com/wp-json/wp/v2"
WP_USER = "admin"
WP_PASS = os.getenv("WP_APP_PASSWORD")
WP_CAT_IRAN = 2
WP_CAT_WORLD = 3

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
if SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# منابع خبری پایش
FEEDS = [
    {"url": "https://www.isna.ir/rss/tp/14", "is_iran": True},
    {"url": "https://www.enr.com/rss/all", "is_iran": False}
]

post_cache = {}

def send_telegram(text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    return requests.post(url, json=payload).json()

def send_telegram_photo(photo_url, caption, reply_markup=None):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
    payload = {"chat_id": TG_CHAT_ID, "photo": photo_url, "caption": caption, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    return requests.post(url, json=payload).json()

@app.get("/")
def home():
    return {"status": "Bot is running online"}

@app.get("/check-news")
def check_news():
    if not SUPABASE_KEY or not GEMINI_KEY:
        return {"error": "API keys are missing in environment variables"}

    for feed in FEEDS:
        try:
            d = feedparser.parse(feed["url"])
            for entry in d.entries[:3]:
                link = entry.link
                res = supabase.table("processed_news").select("id").eq("link", link).execute()
                if res.data:
                    continue

                title = entry.title
                summary = BeautifulSoup(getattr(entry, "summary", ""), "html.parser").get_text()[:400]
                is_iran = feed["is_iran"]
                region_name = "اخبار ایران" if is_iran else "اخبار جهان"

                eval_model = genai.GenerativeModel("gemini-1.5-flash")
                eval_prompt = (
                    f"آیا خبر زیر مرتبط با صنعت ساختمان، عمران، معماری، مسکن، بتن، فولاد یا مقررات ساختمانی است؟ "
                    f"فقط کلمه YES یا NO را بنویس.\nتیتر: {title}\nخلاصه: {summary}"
                )
                eval_res = eval_model.generate_content(eval_prompt).text.strip().upper()

                supabase.table("processed_news").insert({"link": link}).execute()

                if "YES" in eval_res:
                    cache_id = str(abs(hash(link)))[:8]
                    post_cache[cache_id] = {
                        "link": link,
                        "title": title,
                        "summary": summary,
                        "is_iran": is_iran
                    }

                    buttons = {
                        "inline_keyboard": [[
                            {"text": "✅ تأیید و تولید محتوا", "callback_data": f"gen_{cache_id}"},
                            {"text": "❌ رد خبر", "callback_data": "reject"}
                        ]]
                    }
                    msg = f"📍 <b>حوزه: {region_name}</b>\n\n📌 <b>{title}</b>\n\n{summary}\n\n🔗 <a href='{link}'>مشاهده منبع</a>"
                    send_telegram(msg, buttons)
                    return {"status": "Found news and sent to Telegram"}
        except Exception as e:
            print("Error in feed:", e)
    return {"status": "No new relevant news"}

@app.post("/webhook")
async def telegram_webhook(req: Request):
    data = await req.json()
    if "callback_query" in data:
        cq = data["callback_query"]
        action = cq["data"]

        if action == "reject":
            send_telegram("❌ خبر نادیده گرفته شد.")
            return {"ok": True}

        if action.startswith("gen_"):
            cache_id = action.split("_")[1]
            raw_item = post_cache.get(cache_id)
            if not raw_item:
                send_telegram("⚠️ این خبر منقضی شده است.")
                return {"ok": True}

            send_telegram("⏳ در حال بازنویسی حرفه‌ای با اصول سئو و خلق تصویر...")

            prompt = f"""
تو یک سردبیر ارشد و متخصص سئو در حوزه صنعت ساختمان در ایران هستی.
بر اساس خبر زیر یک مقاله تحلیلی جامع بین ۵۰۰ تا ۶۰۰ کلمه به زبان فارسی سلیس و روان بنویس:
عنوان اولیه: {raw_item['title']}
متن اولیه: {raw_item['summary']}
حوزه: {'ایران' if raw_item['is_iran'] else 'جهان'}

قوانین اجباری:
۱. کلمه کلیدی اصلی را مشخص کن. جمله اول متن حتماً و دقیقاً با همین کلمه کلیدی اصلی شروع شود.
۲. برای اخبار جهان، ترجمه کلمه‌به‌کلمه نکن؛ محتوا را کاملاً ایرانیزه و منطبق بر ادبیات مهندسی و مقررات ملی ساختمان ایران بازنویسی کن.
۳. اصول سئو، عنوان‌بندی با تگ‌های <h2> و حداقل یک نقل‌قول فنی با تگ <blockquote> رعایت شود.
۴. طول محتوا دقیقاً بین ۵۰۰ تا ۶۰۰ کلمه باشد.

خروجی را در یک JSON استاندارد با ۳ کلید زیر برگردان:
- title: تیتر جذاب و سئومحور فارسی
- content: متن کامل با تگ‌های تمیز HTML
- image_prompt: یک پرامپت انگلیسی فوتورئالیستیک بدون متن درباره این خبر با نسبت 16:9 برای مدل Flux
"""
            model = genai.GenerativeModel("gemini-1.5-flash", generation_config={"response_mime_type": "application/json"})
            resp = model.generate_content(prompt)
            result = json.loads(resp.text)

            encoded_img_p = urllib.parse.quote(result["image_prompt"])
            image_url = f"https://image.pollinations.ai/prompt/{encoded_img_p}?width=1280&height=720&model=flux&nologo=true"

            post_cache[cache_id]["final_title"] = result["title"]
            post_cache[cache_id]["final_content"] = result["content"]
            post_cache[cache_id]["image_url"] = image_url

            buttons = {
                "inline_keyboard": [[
                    {"text": "🚀 تأیید و انتشار در وردپرس", "callback_data": f"pub_{cache_id}"},
                    {"text": "❌ انصراف", "callback_data": "reject"}
                ]]
            }
            caption = f"📌 <b>{result['title']}</b>\n\nحوزه: {'اخبار ایران' if raw_item['is_iran'] else 'اخبار جهان'}\n✅ متن آماده شد. انتشار در وردپرس؟"
            send_telegram_photo(image_url, caption, buttons)

        elif action.startswith("pub_"):
            cache_id = action.split("_")[1]
            p = post_cache.get(cache_id)
            if not p or "final_title" not in p:
                send_telegram("⚠️ اطلاعات خبر یافت نشد.")
                return {"ok": True}

            send_telegram("🚀 در حال آپلود تصویر و انتشار خبر در وردپرس...")

            target_cat = WP_CAT_IRAN if p["is_iran"] else WP_CAT_WORLD
            token = base64.b64encode(f"{WP_USER}:{WP_PASS}".encode()).decode("utf-8")
            headers = {"Authorization": f"Basic {token}"}

            try:
                img_data = requests.get(p["image_url"]).content
                media_res = requests.post(
                    f"{WP_URL}/media",
                    headers={**headers, "Content-Disposition": 'attachment; filename="featured.jpg"', "Content-Type": "image/jpeg"},
                    data=img_data
                ).json()
                media_id = media_res.get("id")

                post_payload = {
                    "title": p["final_title"],
                    "content": p["final_content"],
                    "status": "publish",
                    "featured_media": media_id,
                    "categories": [target_cat]
                }
                post_res = requests.post(f"{WP_URL}/posts", headers=headers, json=post_payload).json()
                published_link = post_res.get("link", "لینک در دسترس نیست")
                send_telegram(f"🎉 خبر با موفقیت منتشر شد:\n{published_link}")
            except Exception as err:
                send_telegram(f"❌ خطا در ارسال به وردپرس: {str(err)}")

    return {"ok": True}
