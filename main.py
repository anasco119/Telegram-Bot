import os
import google.generativeai as genai
import telebot
from flask import Flask, request, abort

# الحصول على مفاتيح الـ API من المتغيرات البيئية
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GROUP_CHAT_ID = os.getenv('GROUP_CHAT_ID')
ALLOWED_USER_ID = int(os.getenv('USER_ID'))

# تهيئة مكتبة Gemini
genai.configure(api_key=GEMINI_API_KEY)

# تهيئة بوت Telegram
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# إنشاء تطبيق Flask
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

@app.route('/health')
def health():
    return "OK"

# إعداد Webhook للبوت
WEBHOOK_URL = os.getenv('WEBHOOK_URL')  # ضع رابط الـ Render هنا مع مسار webhook
# دالة استدعاء Gemini بشكل صحيح
def generate_gemini_response(prompt):
    try:
        response = genai.generate(model='models/gemini-2.0', prompt=prompt)  # استخدم genai.generate() بشكل مباشر
        return response.generations[0].text if response.generations else "No response from Gemini."
    except Exception as e:
        return f"Error: {str(e)}"
@app.route(f"/{TELEGRAM_BOT_TOKEN}", methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return 'OK', 200
    else:
        abort(403)

if __name__ == "__main__":
    # إعداد المنفذ من المتغيرات البيئية أو استخدام 8080 كقيمة افتراضية
    port = int(os.getenv('PORT', 8080))
    
    # إعداد الـ Webhook
    bot.remove_webhook()
    bot.set_webhook(url=f"https://telegram-bot-qzmd.onrender.com/{TELEGRAM_BOT_TOKEN}")

    # تشغيل التطبيق على Render
    app.run(host="0.0.0.0", port=port)
