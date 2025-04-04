import os
import google.generativeai as genai
import telebot
import re
import logging

# إعداد سجل الأخطاء
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot_errors.log"),
        logging.StreamHandler()
    ]
)

# الحصول على مفاتيح الـ API من المتغيرات البيئية
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')  # معرف القناة
GROUP_ID = os.getenv('GROUP_ID')  # معرف المجموعة
ALLOWED_USER_ID = int(os.getenv('USER_ID'))
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

# تهيئة مكتبة Gemini
try:
    genai.configure(api_key=GEMINI_API_KEY)
    logging.info("Gemini configured successfully")
except Exception as e:
    logging.error(f"Error configuring Gemini: {e}")
# تهيئة بوت Telegram
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
app = Flask(__name__)


# إنشاء نموذج GenerativeModel
model = genai.GenerativeModel('gemini-1.5-pro')

def generate_gemini_response(prompt):
    try:
        response = model.generate_content(prompt)
        if response.text:
            return response.text
        else:
            logging.error("No response text from Gemini.")
            return "No response from Gemini."
    except Exception as e:
        logging.error(f"Error in generate_gemini_response: {e}")
        return f"Error: {str(e)}"

def create_quiz(channel_id, question, options, correct_option_id):
    try:
        bot.send_poll(
            chat_id=channel_id,  # إرسال الاستطلاع إلى القناة
            question=question,
            options=options,
            type="quiz",
            correct_option_id=correct_option_id,
            is_anonymous=True  # تغيير إلى True لأنه لا يمكن إرسال استطلاعات غير مجهولة في القنوات
        )
        logging.info(f"Quiz sent: {question}")
    except Exception as e:
        logging.error(f"Error in create_quiz: {e}")
        bot.send_message(ALLOWED_USER_ID, f"حدث خطأ: {e}")  # إرسال الخطأ إلى المسؤول

# تعريف دالة التحقق من اللغة الإنجليزية
def is_english(text):
    """
    تحقق من أن النص مكتوب باللغة الإنجليزية مع السماح بمعظم الرموز والعلامات الشائعة.
    """
    # النمط المسموح به: أحرف إنجليزية، أرقام، مسافات، علامات ترقيم، ورموز شائعة.
    pattern = r"^[\w\s.,!?;:'\"()\-\n*/@#%&+=<>[\]{}|\\^~`$]*$"
    return bool(re.match(pattern, text))


def generate_quizzes_from_text(text):
    try:
        prompt = (
            "Create 3 English language quizzes for beginner learners based on the following video script. "
            "This script represents a scene that students are watching to enhance their learning. "
            "The quizzes should be familiar and relevant to a video-watching context. "
            "Each quiz should have 4 options and one correct answer. "
            "The quizzes should be varied, including fill-in-the-blank, multiple-choice, and sentence completion questions. "
            "The questions should be phrased appropriately for a video context, such as 'What is mentioned in the video...' instead of 'What is mentioned in the text...'. "
            "Format the response as follows:\n\n"
            "Question: [Your question here]\n"
            "Option 1: [Option 1]\n"
            "Option 2: [Option 2]\n"
            "Option 3: [Option 3]\n"
            "Option 4: [Option 4]\n"
            "Correct Answer: [Correct Answer]\n\n"
            f"Video Script: {text}"
        )
        response_text = generate_gemini_response(prompt)
        logging.debug(f"Raw response from Gemini: {response_text}")

        # طباعة النص الذي يتم التحقق منه
        logging.debug(f"Text to check for English: {response_text}")

        if not is_english(response_text):
            logging.error("Response contains non-English text.")
            return None

        # استخدام Regex لاستخراج كل سؤال مع خياراته
        pattern = r"Question: (.*?)\nOption 1: (.*?)\nOption 2: (.*?)\nOption 3: (.*?)\nOption 4: (.*?)\nCorrect Answer: (.*?)(?=\n\n|$)"
        matches = re.findall(pattern, response_text, re.DOTALL)
        if not matches:
            logging.error("No matches found in the response.")
            return None

        quizzes = []
        for match in matches:
            question, option1, option2, option3, option4, correct_answer = match
            options = [option1, option2, option3, option4]
            try:
                correct_option_id = options.index(correct_answer)
                quizzes.append((question, options, correct_option_id))
            except ValueError:
                logging.error(f"Skipping quiz due to incorrect answer format: {correct_answer}")

        return quizzes
    except Exception as e:
        logging.error(f"Error generating quizzes: {e}")
        return None

@bot.message_handler(commands=['autoquiz_from_text'])
def handle_autoquiz_from_text(message):
    try:
        if message.chat.type == "private" and message.from_user.id == ALLOWED_USER_ID:
            bot.send_message(message.chat.id, "أرسل النص الذي تريد توليد الأسئلة منه.")
            bot.register_next_step_handler(message, process_text_for_quiz)
        else:
            bot.send_message(message.chat.id, "هذا الأمر متاح للمسؤول فقط.")
    except Exception as e:
        logging.error(f"Error in handle_autoquiz_from_text: {e}")

def process_text_for_quiz(message):
    try:
        text = message.text
        quizzes = generate_quizzes_from_text(text)
        if quizzes:
            for quiz in quizzes:
                question, options, correct_option_id = quiz
                create_quiz(CHANNEL_ID, question, options, correct_option_id)  # إرسال الاستطلاع إلى القناة
        else:
            bot.send_message(message.chat.id, "حدث خطأ أثناء توليد الأسئلة.")
            logging.error("No quizzes generated.")
    except Exception as e:
        logging.error(f"Error in process_text_for_quiz: {e}")
        bot.send_message(ALLOWED_USER_ID, f"حدث خطأ: {e}")  # إرسال الخطأ إلى المسؤول

@bot.message_handler(func=lambda message: True)
def chat_with_gemini(message):
    try:
        chat_id = str(message.chat.id)
        message_text = message.text.lower()

        if message.chat.type == "private":
            if message.from_user.id == ALLOWED_USER_ID:
                response_text = generate_gemini_response(message_text)
                bot.send_message(message.chat.id, response_text)
            else:
                bot.send_message(message.chat.id, "هذا البوت مخصص للاستخدام في المجموعة فقط.")
            return

        if chat_id == GROUP_ID:  # التعامل مع الرسائل في المجموعة
            if any(keyword in message_text for keyword in ["genie", "@genie", "translate", "meaning", "grammar", "vocabulary", "explain"]):
                response_text = generate_gemini_response(message_text)
                bot.send_message(message.chat.id, response_text)
    except Exception as e:
        logging.error(f"Error in chat_with_gemini: {e}")
        bot.send_message(ALLOWED_USER_ID, f"حدث خطأ: {e}")  # إرسال الخطأ إلى المسؤول
        
@app.route('/' + TELEGRAM_BOT_TOKEN, methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
    bot.process_new_updates([update])
    return 'ok', 200

def set_webhook():
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL + '/' + TELEGRAM_BOT_TOKEN)
    logging.info(f"🌍 تم تعيين الويب هوك على: {WEBHOOK_URL}/{TELEGRAM_BOT_TOKEN}")

if __name__ == "__main__":
    try:
        logging.info("🚀 بدء تشغيل البوت...")
        set_webhook()
        PORT = int(os.environ.get('PORT', 5000))
        app.run(host='0.0.0.0', port=PORT)
    except Exception as e:
        logging.error(f"❌ فشل تشغيل البوت: {e}")
