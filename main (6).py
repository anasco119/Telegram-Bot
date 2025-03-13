import os
import google.generativeai as genai
import telebot
from flask import Flask
import threading

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

# قائمة بالكلمات المفتاحية للردود التلقائية في المجموعة
keywords = ["translate", "meaning", "grammar", "vocabulary", "explain"]

# لقب البوت ليتم الإشارة إليه في المجموعة
bot_nickname = "@Genie"

def generate_gemini_response(prompt):
    try:
        # إنشاء نموذج GenerativeModel
        model = genai.GenerativeModel('gemini-1.5-pro')
        # استدعاء التفاعل مع Gemini باستخدام طريقة `generate_content`
        response = model.generate_content(prompt)
        return response.text if response.text else "No response from Gemini."
    except Exception as e:
        return f"Error: {str(e)}"

def run_bot():
    @bot.message_handler(func=lambda message: True)
    def chat_with_gemini(message):
        try:
            chat_id = str(message.chat.id)
            message_text = message.text

            # التعامل مع المحادثات الخاصة
            if message.chat.type == "private":
                if message.from_user.id == ALLOWED_USER_ID:
                    response_text = generate_gemini_response(message_text)
                    bot.send_message(message.chat.id, response_text)
                else:
                    bot.send_message(message.chat.id, "عذرًا، هذا البوت مُصمم خصيصًا للاستخدام داخل المجموعة فقط وليس للاستخدام الخاص. إذا كنت بحاجة إلى مساعدة أو دعم، يُرجى التواصل مع المطور مباشرة. شكرًا لتفهمك!")
                return

            # التعامل مع محادثات المجموعة
            if chat_id == GROUP_CHAT_ID:
                if bot_nickname.lower() in message_text.lower() or "genie" in message_text.lower():
                    command = message_text.replace(bot_nickname, "").strip()
                    if command:
                        response_text = generate_gemini_response(command)
                        if response_text.count('\n') <= 5:
                            bot.send_message(message.chat.id, response_text)
                        else:
                            bot.send_message(message.chat.id, "الإجابة طويلة جدًا، يُرجى توضيح السؤال بشكل أدق.")
                    else:
                        bot.send_message(message.chat.id, "يرجى ذكر سؤالك أو الأمر بعد اسمي.")
                elif any(keyword in message_text.lower() for keyword in keywords):
                    response_text = generate_gemini_response(message_text)
                    if response_text.count('\n') <= 5:
                        bot.send_message(message.chat.id, response_text)
                    else:
                        bot.send_message(message.chat.id, "الإجابة طويلة جدًا، يُرجى توضيح السؤال بشكل أدق.")

        except Exception as e:
            bot.send_message(message.chat.id, f"حدث خطأ: {str(e)}")

    bot.polling()

bot_thread = threading.Thread(target=run_bot)
bot_thread.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)