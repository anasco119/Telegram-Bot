import telebot
import google.generativeai as genai
from flask import Flask
import threading
import os

# Get API keys from environment variables
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

# تهيئة Gemini API
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")

# تهيئة بوت تيليغرام
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# إنشاء خادم Flask
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

@app.route('/health')
def health():
    return "OK"

# تشغيل البوت في Thread مستقل
def run_bot():
    @bot.message_handler(func=lambda message: True)
    def chat_with_gemini(message):
        try:
            response = model.generate_content(message.text)
            response_text = response.text if hasattr(response, 'text') else str(response.candidates[0].content.parts[0].text)
            bot.send_message(message.chat.id, response_text)
        except Exception as e:
            bot.send_message(message.chat.id, f"Error: {str(e)}")
            from keep_alive import keep_alive
            keep_alive()

            bot.polling()


    bot.polling()

bot_thread = threading.Thread(target=run_bot)
bot_thread.start()

# Start Flask server
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)