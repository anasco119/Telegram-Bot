import telebot
import google.generativeai as genai
from flask import Flask
import threading
import os
from keep_alive import keep_alive
import re

keep_alive()

# Get API keys and user ID from environment variables
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
GROUP_CHAT_ID = os.environ.get('GROUP_CHAT_ID')
USER_ID = os.environ.get('USER_ID')  # يجب أن يكون نصًا

# تحقق من وجود القيم المطلوبة
if not all([GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, GROUP_CHAT_ID, USER_ID]):
    raise ValueError("يرجى التأكد من إعداد جميع متغيرات البيئة المطلوبة!")

# Initialize Gemini API
genai.configure(api_key=GEMINI_API_KEY)

# Initialize Telegram bot
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# Create Flask server
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

@app.route('/health')
def health():
    return "OK"

# Keyword list for group auto-responses
keywords = ["translate", "meaning", "grammar", "vocabulary", "explain"]

# Bot nickname to be mentioned in group
bot_nickname = "@Genie"

def generate_gemini_response(prompt):
    try:
        response = genai.generate_chat_message(
            model="chat-bison-001",
            messages=[{"role": "user", "content": prompt}]
        )
        
        if response and response.messages:
            return response.messages[0]['content']
        else:
            return "لم يتمكن البوت من توليد استجابة."
        
    except Exception as e:
        return f"خطأ في الاتصال بـ Gemini: {str(e)}"

def run_bot():
    @bot.message_handler(func=lambda message: True)
    def chat_with_gemini(message):
        try:
            chat_id = str(message.chat.id)
            user_id = str(message.from_user.id)
            message_text = message.text

            print(f"📩 Received message from {user_id} in chat {chat_id}: {message_text}")

            # Private chat handling
            if message.chat.type == "private":
                if user_id == USER_ID:
                    response_text = generate_gemini_response(message_text)
                    bot.send_message(message.chat.id, response_text)
                else:
                    bot.send_message(message.chat.id, "🚫 هذا البوت خاص بالمجموعة فقط وليس للاستخدام الخاص.")
                return

            # Group chat handling
            if chat_id == GROUP_CHAT_ID:
                if bot_nickname.lower() in message_text.lower() or "genie" in message_text.lower():
                    command = message_text.replace(bot_nickname, "").strip()
                    if command:
                        response_text = generate_gemini_response(command)
                        bot.send_message(message.chat.id, response_text)
                    else:
                        bot.send_message(message.chat.id, "⚠️ يرجى كتابة سؤالك أو طلبك بعد ذكر اسمي.")
                elif any(keyword in message_text.lower() for keyword in keywords):
                    response_text = generate_gemini_response(message_text)
                    bot.send_message(message.chat.id, response_text)

        except Exception as e:
            bot.send_message(message.chat.id, f"❌ Error: {str(e)}")

    bot.polling()

bot_thread = threading.Thread(target=run_bot)
bot_thread.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
