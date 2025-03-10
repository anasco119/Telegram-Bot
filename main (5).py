import telebot
import google.generativeai as genai
from flask import Flask
import threading
import os
from keep_alive import keep_alive
import re  # استيراد مكتبة re
keep_alive()

# Get API keys from environment variables
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

# Initialize Gemini API
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")

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

# Group chat ID where the bot will operate
group_chat_id = "-1002278148474"

def run_bot():
    @bot.message_handler(func=lambda message: True)
    def chat_with_gemini(message):
        try:
            chat_id = str(message.chat.id)  # تحويل معرف الدردشة إلى نص للمقارنة
            message_text = message.text

            # تحقق من وجود سؤال عن الاسم (بالإنجليزية والعربية)
            name_query_pattern = r"\b(what('s|\s?is)? your name|who are you|your name\?|what is your name|may I know your name|ما\s*اسمك|اسمك)\b"
            if re.search(name_query_pattern, message_text.lower()):
                bot.send_message(message.chat.id, "My name is Genie, at your service!")
                return  # إنهاء الدالة فوراً عند مطابقة السؤال

            # استمر في معالجة باقي الرسالة
            response_text = ""
            # التحقق من أن الرسالة في الخاص أو المجموعة المحددة
            if message.chat.type == "private" or chat_id == group_chat_id:
                if bot_nickname.lower() in message_text.lower() or "genie" in message_text.lower():
                    command = message_text.replace(bot_nickname, "").strip()
                    if command:
                        response = model.generate_content(command)
                        response_text = response.text if hasattr(response, 'text') else str(response.candidates[0].content.parts[0].text)
                    else:
                        response_text = "Please mention your question or command after my name."
                elif any(keyword in message_text.lower() for keyword in keywords):
                    response = model.generate_content(message_text)
                    response_text = response.text if hasattr(response, 'text') else str(response.candidates[0].content.parts[0].text)
                else:
                    response = model.generate_content(message_text)
                    response_text = response.text if hasattr(response, 'text') else str(response.candidates[0].content.parts[0].text)
            else:
                response = model.generate_content(message_text)
                response_text = response.text if hasattr(response, 'text') else str(response.candidates[0].content.parts[0].text)

            if response_text:
                bot.send_message(message.chat.id, response_text)

        except Exception as e:
            bot.send_message(message.chat.id, f"Error: {str(e)}")

    bot.polling()

bot_thread = threading.Thread(target=run_bot)
bot_thread.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)