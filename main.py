import google.generativeai as genai
from flask import Flask
import threading
import os
import re
import telebot
from keep_alive import keep_alive

keep_alive()

# احضار مفاتيح الـ API من متغيرات البيئة
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
GROUP_CHAT_ID = os.environ.get('GROUP_CHAT_ID')
ADMIN_USER_ID = os.environ.get('ADMIN_USER_ID')  # معرفك الشخصي في تليغرام

# تهيئة Gemini API
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")

# تهيئة بوت تليغرام
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# إنشاء خادم Flask
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

@app.route('/health')
def health():
    return "OK"

# قائمة الكلمات المفتاحية للرد التلقائي
keywords = ["translate", "meaning", "grammarG", "vocabularyG", "explain"]

# اسم البوت في المجموعة
bot_nickname = "@Genie"

def run_bot():
    @bot.message_handler(func=lambda message: True)
    def chat_with_gemini(message):
        try:
            chat_id = str(message.chat.id)
            message_text = message.text
            user_id = str(message.from_user.id)

            # التعامل مع الرسائل الخاصة
            if message.chat.type == "private":
                if user_id == ADMIN_USER_ID:  # السماح فقط لك بمراسلة البوت في الخاص
                    prompt = f"""أجب على هذا السؤال برد متوسط الطول ومناسب لمجموعة لتعلم اللغة الإنجليزية.
حاول أن تكون الإجابة شاملة لتغطية النقاط الأساسية، ولكن حافظ على الإيجاز والمرونة في نفس الوقت.
إذا كان السؤال معقداً ويحتاج شرحاً أطول قليلاً، لا تتردد في التوضيح باعتدال.

السؤال هو: {message_text}"""
                    response = model.generate_content(prompt=prompt, max_output_tokens=200)
                    response_text = response.text if hasattr(response, 'text') else str(response.candidates[0].content.parts[0].text)

                    # تقليل حجم الرد إذا كان طويلاً
                    if len(response_text.split('\n')) > 5:
                        response_text = '\n'.join(response_text.split('\n')[:5]) + "..."
                    
                    bot.send_message(message.chat.id, response_text)
                else:
                    # إرسال رسالة توضيحية لأي شخص آخر يحاول مراسلة البوت
                    bot.send_message(message.chat.id, "هذا البوت خاص بمجموعة تليغرام وليس عاماً. لا يمكنك استخدامه هنا.")
                return  # إنهاء الدالة هنا لمنع الاستمرار في المعالجة

            # التحقق من سؤال عن الاسم
            name_query_pattern = r"\b(what('s|\s?is)? your name|who are you|your name\?|what is your name|may I know your name|ما\s*اسمك|اسمك)\b"
            if re.search(name_query_pattern, message_text.lower()):
                bot.send_message(message.chat.id, "My name is Genie, at your service!")
                return

            response_text = ""
            # التعامل مع الرسائل داخل المجموعة فقط
            if chat_id == GROUP_CHAT_ID:
                if bot_nickname.lower() in message_text.lower() or "genie" in message_text.lower():
                    command = message_text.replace(bot_nickname, "").strip()
                    if command:
                        prompt = f"""أجب على هذا السؤال برد متوسط الطول ومناسب لمجموعة لتعلم اللغة الإنجليزية.
حاول أن تكون الإجابة شاملة لتغطية النقاط الأساسية، ولكن حافظ على الإيجاز والمرونة في نفس الوقت.
إذا كان السؤال معقداً ويحتاج شرحاً أطول قليلاً، لا تتردد في التوضيح باعتدال.

السؤال هو: {command}"""
                        response = model.generate_content(prompt=prompt, max_output_tokens=200)
                        response_text = response.text if hasattr(response, 'text') else str(response.candidates[0].content.parts[0].text)
                    else:
                        response_text = "Please mention your question or command after my name."
                elif any(keyword in message_text.lower() for keyword in keywords):
                    prompt = f"""أجب على هذا السؤال برد متوسط الطول ومناسب لمجموعة لتعلم اللغة الإنجليزية.
حاول أن تكون الإجابة شاملة لتغطية النقاط الأساسية، ولكن حافظ على الإيجاز والمرونة في نفس الوقت.
إذا كان السؤال معقداً ويحتاج شرحاً أطول قليلاً، لا تتردد في التوضيح باعتدال.

السؤال هو: {message_text}"""
                    response = model.generate_content(prompt=prompt, max_output_tokens=200)
                    response_text = response.text if hasattr(response, 'text') else str(response.candidates[0].content.parts[0].text)

            if response_text:
                if len(response_text.split('\n')) > 5:
                    response_text = '\n'.join(response_text.split('\n')[:5]) + "..."
                
                bot.send_message(message.chat.id, response_text)

        except Exception as e:
            bot.send_message(message.chat.id, f"Error: {str(e)}")

    bot.polling()

bot_thread = threading.Thread(target=run_bot)
bot_thread.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)