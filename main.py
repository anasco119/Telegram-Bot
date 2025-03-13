import telebot
import google.generativeai as genai
from flask import Flask
import threading
import os
from keep_alive import keep_alive
import re  

keep_alive()

# Get API keys from environment variables
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

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

# Group chat ID where the bot will operate (store as environment variable)
group_chat_id = os.getenv('GROUP_CHAT_ID')

# Your Telegram username for private messaging (if you want to allow yourself to use it)
allowed_username = "YourUsername"

def generate_gemini_response(prompt):
    try:
        response = genai.chat(messages=[{"role": "user", "content": prompt}])
        return response["messages"][0]["content"]
    except Exception as e:
        return f"Error: {str(e)}"

def run_bot():
    @bot.message_handler(func=lambda message: True)
    def chat_with_gemini(message):
        try:
            chat_id = str(message.chat.id)
            message_text = message.text

            # Private chat handling
            if message.chat.type == "private":
                if message.from_user.username == allowed_username:
                    response_text = generate_gemini_response(message_text)
                    bot.send_message(message.chat.id, response_text)
                else:
                    bot.send_message(message.chat.id, "هذا البوت خاص بالمجموعة فقط وليس للاستخدام الخاص.")
                return

            # Group chat handling
            if chat_id == group_chat_id:
                if bot_nickname.lower() in message_text.lower() or "genie" in message_text.lower():
                    command = message_text.replace(bot_nickname, "").strip()
                    if command:
                        response_text = generate_gemini_response(command)
                        if response_text.count('\n') <= 5:  # قياس الطول بالسطر
                            bot.send_message(message.chat.id, response_text)
                        else:
                            bot.send_message(message.chat.id, "الإجابة طويلة جدًا، يُرجى توضيح السؤال بشكل أدق.")
                    else:
                        bot.send_message(message.chat.id, "Please mention your question or command after my name.")
                elif any(keyword in message_text.lower() for keyword in keywords):
                    response_text = generate_gemini_response(message_text)
                    if response_text.count('\n') <= 5:  # قياس الطول بالسطر
                        bot.send_message(message.chat.id, response_text)
                    else:
                        bot.send_message(message.chat.id, "الإجابة طويلة جدًا، يُرجى توضيح السؤال بشكل أدق.")

        except Exception as e:
            bot.send_message(message.chat.id, f"Error: {str(e)}")

    bot.polling()

bot_thread = threading.Thread(target=run_bot)
bot_thread.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
