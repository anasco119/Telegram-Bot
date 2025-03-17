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

@app.route(f"/{TELEGRAM_BOT_TOKEN}", methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return 'OK', 200
    else:
        abort(403)

def generate_gemini_response(prompt):
    try:
        model = genai.GenerativeModel('gemini-1.5-pro')
        response = model.generate_content(prompt)
        return response.text if response.text else "No response from Gemini."
    except Exception as e:
        return f"Error: {str(e)}"

@bot.message_handler(func=lambda message: True)
def chat_with_gemini(message):
    try:
        chat_id = str(message.chat.id)
        message_text = message.text

        if message.chat.type == "private":
            if message.from_user.id == ALLOWED_USER_ID:
                response_text = generate_gemini_response(message_text)
                bot.send_message(message.chat.id, response_text)
            else:
                bot.send_message(message.chat.id, "هذا البوت مخصص للاستخدام في المجموعة فقط.")
            return

        if chat_id == GROUP_CHAT_ID:
            if "@Genie" in message_text or any(keyword in message_text.lower() for keyword in ["translate", "meaning", "grammar", "vocabulary", "explain"]):
                response_text = generate_gemini_response(message_text)
                bot.send_message(message.chat.id, response_text)

    except Exception as e:
        bot.send_message(message.chat.id, f"حدث خطأ: {str(e)}")

if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    app.run(host="0.0.0.0", port=8080)
