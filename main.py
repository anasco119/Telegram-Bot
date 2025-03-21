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

# إنشاء نموذج GenerativeModel
model = genai.GenerativeModel('gemini-1.5-pro')

def generate_gemini_response(prompt):
    try:
        # استدعاء التفاعل مع Gemini باستخدام طريقة generate_content
        response = model.generate_content(prompt)
        return response.text if response.text else "No response from Gemini."
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

# تعامل مع الرسائل
@bot.message_handler(func=lambda message: True)
def chat_with_gemini(message):
    try:
        chat_id = str(message.chat.id)
        message_text = message.text.lower()  # تحويل النص إلى حروف صغيرة لتجاهل حساسية حالة الأحرف

        # التعامل مع المحادثات الخاصة
        if message.chat.type == "private":
            if message.from_user.id == ALLOWED_USER_ID:
                response_text = generate_gemini_response(message_text)
                bot.send_message(message.chat.id, response_text)
            else:
                bot.send_message(message.chat.id, "هذا البوت مخصص للاستخدام في المجموعة فقط.")
            return

        # التعامل مع محادثات المجموعة
        if chat_id == GROUP_CHAT_ID:
            # التحقق من وجود اسم البوت أو كلمات رئيسية محددة في الرسالة
            if any(keyword in message_text for keyword in ["genie", "@genie", "translate", "meaning", "grammar", "vocabulary", "explain"]):
                response_text = generate_gemini_response(message_text)
                bot.send_message(message.chat.id, response_text)

    except Exception as e:
        bot.send_message(message.chat.id, f"حدث خطأ: {str(e)}")

if __name__ == "__main__":
    # إعداد المنفذ من المتغيرات البيئية أو استخدام 8080 كقيمة افتراضية
    port = int(os.getenv('PORT', 8080))
    
        # إعداد الـ Webhook
    bot.remove_webhook()
    bot.set_webhook(url=f"https://telegram-bot-qzmd.onrender.com/{TELEGRAM_BOT_TOKEN}")
    # تشغيل التطبيق على Render
    app.run(host="0.0.0.0", port=port)
