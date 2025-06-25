from flask import Flask, request, render_template
import os
import google.generativeai as genai
import telebot
import re
import logging
import sqlite3
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
import requests
from moviepy.editor import VideoFileClip
from pydub import AudioSegment
import time
import json


# الحصول على مفاتيح الـ API من المتغيرات البيئية
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')  # معرف القناة
GROUP_ID = os.getenv('GROUP_ID')  # معرف المجموعة
ALLOWED_USER_ID = int(os.getenv('USER_ID'))
WEBHOOK_URL = os.getenv('WEBHOOK_URL')
ASSEMBLY_API_KEY = os.getenv("ASSEMBLY_API_KEY")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

PROMO_MESSAGE = "📢 تابعنا على قناة English Convs لتعلم الإنجليزية!"
VIDEO_PATH = "input_video.mp4"
AUDIO_PATH = "temp_audio.wav"
SRT_PATH = "output.srt"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
COHERE_API_KEY = os.getenv("COHERE_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")



# إعداد Flask
app = Flask(__name__)

@app.route('/')
def index():
    return "البوت يعمل ✔️"
# إعداد السجل
logging.basicConfig(level=logging.INFO)

# إعداد البوت
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

DB_FILE = 'lessons.db'

def init_db():
    try:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS lessons (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL
            )''')
            conn.commit()
        logging.info(f"✅ Database created at: {os.path.abspath(DB_FILE)}")
    except Exception as e:
        logging.error(f"❌ Database init error: {e}")

def upgrade_database():
    try:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            columns = [
                'lesson_number', 'video_id', 'srt_content', 'summary',
                'title', 'link', 'type'
            ]
            for col in columns:
                try:
                    c.execute(f"ALTER TABLE lessons ADD COLUMN {col} TEXT")
                    print(f"✅ تمت إضافة العمود {col}")
                except sqlite3.OperationalError:
                    print(f"ℹ️ العمود {col} موجود مسبقًا - تم تجاهله")
            conn.commit()
    except Exception as e:
        print(f"❌ خطأ أثناء تعديل قاعدة البيانات: {e}")

def insert_old_lessons_from_json(json_file):
    with open(json_file, 'r', encoding='utf-8') as f:
        lessons = json.load(f)

    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        for i, lesson in enumerate(lessons, start=1):
            lesson_id = f"oldvid_{i:03}"  # يمكن تغييره لاحقًا
            lesson_number = i
            title = lesson.get('title')
            link = lesson.get('link')
            lesson_type = lesson.get('type', 'video')

            c.execute('''INSERT OR IGNORE INTO lessons
                         (id, lesson_number, title, link, type)
                         VALUES (?, ?, ?, ?, ?)''',
                      (lesson_id, lesson_number, title, link, lesson_type))
        conn.commit()
    print("✅ تم إدخال دروس JSON بنجاح.")



# حذف قاعدة البيانات عند استلام أمر reset
@bot.message_handler(commands=['reset_db'])
def reset_database(message):
    if message.from_user.id == ALLOWED_USER_ID:  # فقط للمسؤول
        if os.path.exists(DB_FILE):
            os.remove(DB_FILE)
            bot.send_message(message.chat.id, f"✅ تم حذف قاعدة البيانات: {DB_FILE}")
            init_db()  # إعادة إنشاء القاعدة بعد الحذف
            bot.send_message(message.chat.id, "✅ تم إعادة إنشاء قاعدة البيانات.")
        else:
            bot.send_message(message.chat.id, "❌ قاعدة البيانات غير موجودة.")
    else:
        bot.send_message(message.chat.id, "هذا الأمر متاح فقط للمسؤول.")

# تأكد من استدعاء `init_db()` في البداية أيضًا عند بدء البوت
init_db()

@bot.message_handler(commands=['post_lesson'])
def handle_post_lesson(message):
    try:
        if message.chat.type == "private" and message.from_user.id == ALLOWED_USER_ID:
            parts = message.text.split(maxsplit=2)
            if len(parts) < 3:
                bot.send_message(message.chat.id, "يرجى إرسال الأمر بهذا الشكل:\n/post_lesson lesson_id النص")
                return

            lesson_id = parts[1]
            lesson_text = parts[2]

            with sqlite3.connect(DB_FILE) as conn:
                c = conn.cursor()
                c.execute("REPLACE INTO lessons (id, content) VALUES (?, ?)", (lesson_id, lesson_text))
                conn.commit()

            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("📖 قراءة تفاعلية", url=f"{WEBHOOK_URL}/reader?text_id={lesson_id}")
            ]])

            bot.send_message(CHANNEL_ID, lesson_text, reply_markup=keyboard)
            bot.send_message(message.chat.id, "✅ تم نشر الدرس مع زر القراءة.")

        else:
            bot.send_message(message.chat.id, "هذا الأمر متاح فقط للمسؤول.")
    except Exception as e:
        logging.error(f"خطأ في post_lesson: {e}")
        bot.send_message(USER_ID, f"حدث خطأ: {e}")

@app.route('/reader')
def reader():
    text_id = request.args.get("text_id")
    
    # تحقق من أن النص موجود في قاعدة البيانات
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT content FROM lessons WHERE id=?", (text_id,))
        lesson = c.fetchone()
    
    if lesson:
        return render_template("reader.html", text=lesson[0])
    else:
        return "❌ الدرس غير موجود"




# --- إعداد المفاتيح والعمل

# 1. إعداد Google Gemini
gemini_model = None
if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        gemini_model = genai.GenerativeModel('gemini-1.5-flash')
        logging.info("✅ 1. Gemini configured successfully")
    except Exception as e:
        logging.warning(f"⚠️ Could not configure Gemini: {e}")

# 2. إعداد Groq
groq_client = None
if GROQ_API_KEY:
    try:
        groq_client = Groq(api_key=GROQ_API_KEY)
        logging.info("✅ 2. Groq configured successfully")
    except Exception as e:
        logging.warning(f"⚠️ Could not configure Groq: {e}")

# 3. إعداد OpenRouter (سيتم استخدامه لنموذجين مختلفين)
if OPENROUTER_API_KEY:
    logging.info("✅ 3. OpenRouter is ready")

# 4. إعداد Cohere
cohere_client = None
if COHERE_API_KEY:
    try:
        cohere_client = cohere.Client(COHERE_API_KEY)
        logging.info("✅ 4. Cohere configured successfully")
    except Exception as e:
        logging.warning(f"⚠️ Could not configure Cohere: {e}")





# --- الدالة الموحدة لتوليد الردود ---

def generate_gemini_response(prompt: str) -> str:
    """
    Tries to generate a response by attempting a chain of services silently.
    It logs errors for the developer but does not send progress messages to the user.
    """
    timeout_seconds = 45


    #  1️⃣ Cohere
    if cohere_client:
        try:
            logging.info("Attempting request with: 5. Cohere...")
            response = cohere_client.chat(model='command-r', message=prompt)
            logging.info("✅ Success with Cohere.")
            return response.text
        except Exception as e:
            logging.warning(f"❌ Cohere failed: {e}")



    # 2️⃣ Google Gemini
    if gemini_model:
        try:
            logging.info("Attempting request with: 4. Google Gemini...")
            request_options = {"timeout": timeout_seconds}
            response = gemini_model.generate_content(prompt, request_options=request_options)
            if response.text:
                logging.info("✅ Success with Gemini.")
                return response.text
            else:
                logging.warning("❌ Gemini returned no text. Trying fallback...")
        except Exception as e:
            logging.warning(f"❌ Gemini failed: {e}")


    #  3️⃣  Groq (LLaMA 3)
    if groq_client:
        try:
            logging.info("Attempting request with: 2. Groq (LLaMA 3)...")
            chat_completion = groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama3-8b-8192",
                temperature=0.7,
                timeout=timeout_seconds
            )
            if chat_completion.choices[0].message.content:
                logging.info("✅ Success with Groq.")
                return chat_completion.choices[0].message.content
            else:
                logging.warning("❌ Groq returned no text. Trying fallback...")
        except Exception as e:
            logging.warning(f"❌ Groq failed: {e}")

    # 4️⃣# 5️⃣ OpenRouter - Gemma
    if OPENROUTER_API_KEY:
        try:
            logging.info("Attempting request with: 3. OpenRouter (Gemma)...")
            headers = {
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "HTTP-Referer": "https://t.me/Oiuhelper_bot",  # Replace with your bot's link
                "X-Title": "AI Quiz Bot"
            }
            model_identifier = "google/gemma-7b-it:free"
            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json={"model": model_identifier, "messages": [{"role": "user", "content": prompt}]},
                timeout=timeout_seconds
            )
            response.raise_for_status()
            result_text = response.json()['choices'][0]['message']['content']
            logging.info("✅ Success with OpenRouter (Gemma).")
            return result_text
        except Exception as e:
            logging.warning(f"❌ OpenRouter (Gemma) failed: {e}")

    # 🚫 All models failed
    logging.error("❌ All API providers failed. Returning empty string.")
    return ""


# ✅ استخراج الصوت وضغطه
def extract_and_compress_audio(video_path, audio_path):
    clip = VideoFileClip(video_path)
    clip.audio.write_audiofile("temp_raw.wav")
    sound = AudioSegment.from_wav("temp_raw.wav")
    sound = sound.set_channels(1).set_frame_rate(16000)
    sound.export(audio_path, format="wav")
    os.remove("temp_raw.wav")

# ✅ تحويل باستخدام AssemblyAI
def transcribe_with_assembly(audio_path):
    try:
        headers = {'authorization': ASSEMBLY_API_KEY}
        with open(audio_path, 'rb') as f:
            upload_res = requests.post('https://api.assemblyai.com/v2/upload', headers=headers, files={'file': f})
        upload_url = upload_res.json()['upload_url']

        transcript_res = requests.post(
            "https://api.assemblyai.com/v2/transcript",
            headers=headers,
            json={"audio_url": upload_url, "format_text": True}
        )
        transcript_id = transcript_res.json()['id']

        while True:
            status = requests.get(f"https://api.assemblyai.com/v2/transcript/{transcript_id}", headers=headers).json()
            if status['status'] == 'completed':
                return requests.get(status['srt_url']).text
            elif status['status'] == 'error':
                raise Exception("AssemblyAI failed")
            time.sleep(3)
    except Exception as e:
        print(f"❌ AssemblyAI فشل: {e}")
        return None

# ✅ تحويل باستخدام Deepgram
def transcribe_with_deepgram(audio_path):
    try:
        with open(audio_path, 'rb') as f:
            response = requests.post(
                "https://api.deepgram.com/v1/listen?punctuate=true&format=srt",
                headers={
                    "Authorization": f"Token {DEEPGRAM_API_KEY}",
                    "Content-Type": "audio/wav"
                },
                data=f
            )
        if response.status_code == 200:
            return response.text
        else:
            raise Exception(response.text)
    except Exception as e:
        print(f"❌ Deepgram فشل: {e}")
        return None

# ✅ تعديل srt بإضافة الجملة الترويجية
def add_promo_to_srt(srt_content, promo):
    blocks = srt_content.strip().split('\n\n')
    promo_block = f"0\n00:00:00,000 --> 00:00:02,000\n{promo}"
    updated = [promo_block]
    for block in blocks:
        lines = block.strip().split('\n')
        if lines and lines[0].isdigit():
            lines[0] = str(int(lines[0]) + 1)
        updated.append('\n'.join(lines))
    return '\n\n'.join(updated)

# ✅ المعالجة الكاملة
def process_video_to_srt():
    extract_and_compress_audio(VIDEO_PATH, AUDIO_PATH)
    srt_data = transcribe_with_assembly(AUDIO_PATH)
    if not srt_data:
        srt_data = transcribe_with_deepgram(AUDIO_PATH)

    if srt_data:
        final_srt = add_promo_to_srt(srt_data, PROMO_MESSAGE)
        with open(SRT_PATH, 'w', encoding='utf-8') as f:
            f.write(final_srt)
        return True
    return False


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
            "Create 3 English language quizzes for beginner learners based on the following video or audio script. "
            "This script represents a scene that students are watching or listening to enhance their learning. "
            "The quizzes should be familiar and relevant to a video-watching or audio listening context. "
            "Each quiz should have 4 options and one correct answer. "
            "The quizzes should be varied, including fill-in-the-blank, multiple-choice, and sentence completion questions. "
            "The questions should be phrased appropriately for a video or audio context, such as 'What is mentioned in the video...' or 'What is mentioned in the audio clip...' according to what specified later. "
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



# ✅ أمر /start
@bot.message_handler(commands=['subtitle'])
def handle_start(message):
    if message.from_user.id == ADMIN_ID:
        bot.reply_to(message, "👋 أرسل فيديو وسأقوم بتحويله إلى ملف ترجمة.")
    else:
        bot.reply_to(message, "❌ هذا البوت مخصص فقط للأدمن.")

# ✅ استقبال فيديو من الأدمن فقط
@bot.message_handler(content_types=['video'])
def handle_video(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ هذا الأمر متاح فقط للأدمن.")
        return

    bot.reply_to(message, "📥 تم استلام الفيديو. جاري المعالجة...")

    try:
        file_info = bot.get_file(message.video.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        with open(VIDEO_PATH, 'wb') as f:
            f.write(downloaded_file)

        success = process_video_to_srt()

        if success:
            with open(SRT_PATH, 'r', encoding='utf-8') as srt_file:
                srt_content = srt_file.read()

            # توليد رقم الدرس تلقائيًا
            with sqlite3.connect(DB_FILE) as conn:
                c = conn.cursor()
                c.execute("SELECT MAX(lesson_number) FROM lessons")
                result = c.fetchone()
                last_number = result[0] if result and result[0] else 0
                new_number = last_number + 1

            # تخزين مؤقت
            temp_data['lesson_number'] = new_number
            temp_data['lesson_id'] = datetime.now().strftime("%Y%m%d%H%M%S")
            temp_data['video_id'] = message.video.file_id
            temp_data['srt_content'] = srt_content

            bot.send_document(message.chat.id, open(SRT_PATH, 'rb'), caption="✅ ملف الترجمة جاهز.")
            bot.reply_to(message, "📝 أرسل الآن الشرح التمهيدي (لن يُنشر، فقط للتخزين).")
    except Exception as e:
        bot.reply_to(message, f"❌ خطأ أثناء التنزيل أو المعالجة:\n{e}")


@bot.message_handler(commands=['import_old_lessons'])
def import_lessons_command(message):
    if message.from_user.id != ADMIN_ID:
        bot.reply_to(message, "❌ هذا الأمر مخصص فقط للأدمن.")
        return

    try:
        insert_old_lessons_from_json("videos_list.json")
        bot.reply_to(message, "✅ تم استيراد الدروس القديمة بنجاح.")
    except Exception as e:
        bot.reply_to(message, f"❌ حدث خطأ أثناء الاستيراد:\n{e}")


@bot.channel_post_handler(content_types=['video'])
def handle_channel_video(message):
    try:
        if message.chat.username != "EnglishConvs":
            return

        caption = message.caption or ""
        match = re.search(r'Lesson\s+(\d+):\s*(.+)', caption, re.IGNORECASE)
        if not match:
            print("⚠️ لا توجد كلمات مفتاحية مطابقة في الكابشن.")
            return

        lesson_number = int(match.group(1))
        title = match.group(2).strip()
        video_id = message.video.file_id
        lesson_id = f"chan_{message.message_id}"

        # ✅ توليد الرابط المباشر للمنشور
        link = f"https://t.me/{message.chat.username}/{message.message_id}"

        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute('''INSERT OR IGNORE INTO lessons 
                         (id, lesson_number, video_id, title, link, type) 
                         VALUES (?, ?, ?, ?, ?, ?)''',
                      (lesson_id, lesson_number, video_id, title, link, 'video'))
            conn.commit()

        print(f"✅ تم حفظ درس جديد من القناة: Lesson {lesson_number}")
    except Exception as e:
        print(f"❌ خطأ أثناء معالجة فيديو من القناة: {e}")


# نقطة نهاية الويب هوك
@app.route('/' + os.getenv('TELEGRAM_BOT_TOKEN'), methods=['POST'])
def webhook():
    if request.method == "POST":
        update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
        bot.process_new_updates([update])
        return 'ok', 200
    return 'Method Not Allowed', 405

def set_webhook():
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL + '/' + TELEGRAM_BOT_TOKEN)
    logging.info(f"🌍 تم تعيين الويب هوك على: {WEBHOOK_URL}/{TELEGRAM_BOT_TOKEN}")

if __name__ == "__main__":
    set_webhook()
    port = int(os.environ.get('PORT', 10000))  # Render يستخدم 10000
    app.run(host='0.0.0.0', port=port)
