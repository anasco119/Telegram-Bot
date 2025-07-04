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
import cohere
from groq import Groq
from dotenv import load_dotenv
from moviepy.config import change_settings
import zipfile
import stat  # ضعه أعلى الملف مع الاستيرادات
from datetime import datetime


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

import sqlite3
import os
import logging
import json

DB_FILE = 'lessons.db'

def init_db():
    try:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS lessons (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                lesson_number INTEGER,
                video_id TEXT,
                srt_content TEXT,
                summary TEXT,
                title TEXT,
                link TEXT,
                type TEXT
            )''')
            conn.commit()
            logging.info(f"Database created or already exists at: {os.path.abspath(DB_FILE)}")
    except Exception as e:
        logging.error(f"Database initialization error: {e}")

def insert_old_lessons_from_json(json_path):
    if not os.path.exists(json_path):
        print(f"File {json_path} not found.")
        return

    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM lessons WHERE lesson_number IS NOT NULL")
        count = c.fetchone()[0]

        if count > 0:
            print("Lessons already imported. Skipping.")
            return

        with open(json_path, "r", encoding="utf-8") as f:
            lessons = json.load(f)

        for i, lesson in enumerate(lessons, start=1):
            lesson_id = f"old_lesson_{i}"
            content = f"{lesson['title']}\n{lesson['link']}"
            c.execute(
                "INSERT INTO lessons (id, content, video_id, srt_content, summary, lesson_number, title, link) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (lesson_id, content, None, None, None, i, lesson.get('title'), lesson.get('link'))
            )
        conn.commit()
        print(f"Imported {len(lessons)} lessons from JSON.")


temp_data = {}
init_db()
insert_old_lessons_from_json("videos_list.json")
        
def download_and_extract_ffmpeg():
    url = "https://github.com/anasco119/Telegram-Bot/releases/download/GenieV3/bin.zip"
    zip_path = "bin.zip"
    
    if not os.path.exists("bin/ffmpeg"):
        print("⏬ Downloading ffmpeg...")
        r = requests.get(url)
        with open(zip_path, 'wb') as f:
            f.write(r.content)

        print("📦 Extracting...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(".")

        os.remove(zip_path)

download_and_extract_ffmpeg()
# بعد فك الضغط مباشرة، أضف:
os.chmod("bin/ffmpeg", stat.S_IRWXU)  # يعطيه صلاحيات القراءة والكتابة والتنفيذ للمالك

# إعداد ffmpeg/ffprobe
change_settings({
    "FFMPEG_BINARY": os.path.abspath("bin/ffmpeg"),
    "FFPROBE_BINARY": os.path.abspath("bin/ffprobe")
})


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

            # حفظ البيانات مؤقتًا لاستخدامها في حالة التأكيد
            user_data = {
                'lesson_id': lesson_id,
                'lesson_text': lesson_text
            }
            

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

            # حفظ البيانات في المتغير المؤقت
            msg = bot.send_message(
                message.chat.id,
                f"⚠️ هل تريد حقًا إرسال هذا الدرس إلى القناة؟\n\n"
                f"معرف الدرس: {lesson_id}\n"
                f"النص: {lesson_text[:300]}...",  # عرض 300 حرف للمعاينة
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ تأكيد الإرسال", callback_data=f"confirm_post:{lesson_id}:{message.message_id}"),
                        InlineKeyboardButton("❌ إلغاء", callback_data="cancel_post")
                    ]
                ])
            )
            
            # حفظ البيانات المؤقتة في الذاكرة
            with sqlite3.connect(DB_FILE) as conn:
                c = conn.cursor()
                c.execute("""
                    CREATE TABLE IF NOT EXISTS temp_lessons (
                        user_id INTEGER,
                        message_id INTEGER,
                        lesson_id TEXT,
                        lesson_text TEXT,
                        PRIMARY KEY (user_id, message_id)
                    )
                """)
                c.execute("""
                    REPLACE INTO temp_lessons (user_id, message_id, lesson_id, lesson_text)
                    VALUES (?, ?, ?, ?)
                """, (message.from_user.id, msg.message_id, lesson_id, lesson_text))
                conn.commit()

        else:
            bot.send_message(message.chat.id, "هذا الأمر متاح فقط للمسؤول.")
    except Exception as e:
        logging.error(f"خطأ في post_lesson: {e}")
        bot.send_message(USER_ID, f"حدث خطأ: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_post:'))
def confirm_post(call):
    try:
        # استخراج البيانات من callback_data
        _, lesson_id, original_msg_id = call.data.split(':')
        
        # استعادة النص الكامل من قاعدة البيانات المؤقتة
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("""
                SELECT lesson_text FROM temp_lessons 
                WHERE user_id = ? AND message_id = ?
            """, (call.from_user.id, int(original_msg_id)))
            result = c.fetchone()
            
            if not result:
                bot.answer_callback_query(call.id, "❌ لم يتم العثور على بيانات الدرس", show_alert=True)
                return
                
            lesson_text = result[0]
            
            # حفظ الدرس في قاعدة البيانات الرئيسية
            c.execute("""
                REPLACE INTO lessons (id, content) 
                VALUES (?, ?)
            """, (lesson_id, lesson_text))
            conn.commit()
            
            # تنظيف البيانات المؤقتة
            c.execute("""
                DELETE FROM temp_lessons 
                WHERE user_id = ? AND message_id = ?
            """, (call.from_user.id, int(original_msg_id)))
            conn.commit()

        # إرسال الدرس إلى القناة
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("📖 قراءة تفاعلية", url=f"{WEBHOOK_URL}/reader?text_id={lesson_id}")
        ]])
        
        bot.send_message(CHANNEL_ID, lesson_text, reply_markup=keyboard)
        bot.edit_message_text(
            "✅ تم نشر الدرس بنجاح في القناة وحفظه في قاعدة البيانات.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )
        
    except Exception as e:
        logging.error(f"خطأ في confirm_post: {e}")
        bot.answer_callback_query(call.id, f"حدث خطأ: {e}", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == 'cancel_post')
def cancel_post(call):
    try:
        # تنظيف البيانات المؤقت
        bot.edit_message_text(
            "❌ تم إلغاء نشر الدرس.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )
    except Exception as e:
        logging.error(f"خطأ في cancel_post: {e}")
        bot.answer_callback_query(call.id, f"حدث خطأ أثناء الإلغاء: {e}", show_alert=True)


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
        with open(audio_path, 'rb') as audio_file:
            response = requests.post(
                "https://api.deepgram.com/v1/listen?punctuate=true&utterances=true&diarize=true",
                headers={
                    "Authorization": f"Token {DEEPGRAM_API_KEY}",
                    "Content-Type": "audio/wav"
                },
                data=audio_file
            )

        if response.status_code == 200:
            return response.json()  # ✅ يرجع dict
        else:
            print("Deepgram Error:", response.text)
            return None
    except Exception as e:
        print("❌ Deepgram فشل:", str(e))
        return None

def format_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    millis = int((secs - int(secs)) * 1000)
    return f"{hours:02}:{minutes:02}:{int(secs):02},{millis:03}"

def assembly_to_srt(assembly_json, promo=None):
    srt_output = []
    index = 1
    
    # ✅ إضافة الجملة الترويجية بدون تعديل توقيت أي شيء
    if promo:
        srt_output.append(f"{index}\n00:00:00,000 --> 00:00:02,000\n{promo}")
        index += 1

    words = assembly_json['words']
    max_words_per_line = 10
    i = 0

    while i < len(words):
        start_time = words[i]['start'] / 1000  # Assembly يعطي الوقت بالملي ثانية
        line_words = [words[i]['text']]
        end_time = words[i]['end'] / 1000

        j = i + 1
        while j < len(words) and len(line_words) < max_words_per_line:
            line_words.append(words[j]['text'])
            end_time = words[j]['end'] / 1000
            j += 1

        start_str = format_time(start_time)
        end_str = format_time(end_time)
        text_line = ' '.join(line_words)

        srt_output.append(f"{index}\n{start_str} --> {end_str}\n{text_line}")
        index += 1
        i = j

    return '\n\n'.join(srt_output)

# ✅ تحويل Deepgram JSON إلى SRT
def deepgram_json_to_srt(transcript_data):
    srt_blocks = []
    index = 1

    for utterance in transcript_data['results']['utterances']:
        start = format_time(utterance['start'])
        end = format_time(utterance['end'])
        speaker = f"المتحدث {utterance['speaker']}:" if 'speaker' in utterance else ""
        text = f"{speaker} {utterance['transcript']}"

        srt_blocks.append(f"{index}\n{start} --> {end}\n{text.strip()}")
        index += 1

    return '\n\n'.join(srt_blocks)

# ✅ تحويل الثواني إلى تنسيق SRT
def format_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}".replace('.', ',')
    
def process_video_to_srt():
    extract_and_compress_audio(VIDEO_PATH, AUDIO_PATH)

    # ✅ المحاولة الأولى: AssemblyAI
    srt_data = transcribe_with_assembly(AUDIO_PATH)
    
    if srt_data and isinstance(srt_data, str):
        final_srt = add_promo_to_raw_srt(srt_data, PROMO_MESSAGE)

    else:
        # ✅ المحاولة الثانية: Deepgram
        transcript_json = transcribe_with_deepgram(AUDIO_PATH)
        if transcript_json:
            srt_data = deepgram_json_to_srt(transcript_json)
            final_srt = add_promo_to_raw_srt(srt_data, PROMO_MESSAGE)
        else:
            print("❌ فشل إنشاء SRT من Assembly و Deepgram")
            return False

    with open(SRT_PATH, 'w', encoding='utf-8') as f:
        f.write(final_srt)
    
    print("✅ تم إنشاء ملف SRT متزامن: ", SRT_PATH)
    return True
def add_promo_to_raw_srt(srt_text: str, promo: str):
    promo_block = f"1\n00:00:00,000 --> 00:00:02,000\n{promo}\n\n"
    
    # إعادة ترقيم الكتل الأصلية بدءًا من 2
    blocks = srt_text.strip().split('\n\n')
    renumbered_blocks = []
    for i, block in enumerate(blocks, start=2):
        lines = block.strip().split('\n')
        if len(lines) >= 2:
            lines[0] = str(i)
        renumbered_blocks.append('\n'.join(lines))
    
    return promo_block + '\n\n'.join(renumbered_blocks)

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


# ✅ أمر /start
@bot.message_handler(commands=['subtitle'])
def handle_start(message):
    if message.from_user.id == ALLOWED_USER_ID:
        bot.reply_to(message, "👋 أرسل فيديو وسأقوم بتحويله إلى ملف ترجمة.")
    else:
        bot.reply_to(message, "❌ هذا البوت مخصص فقط للأدمن.")

# ✅ استقبال فيديو من الأدمن فقط
@bot.message_handler(content_types=['video'])
def handle_video(message):
    if message.from_user.id != ALLOWED_USER_ID:
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
    if message.from_user.id != ALLOWED_USER_ID:
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

@bot.message_handler(commands=['index'])
def handle_video_index(message):
    try:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("""
                SELECT lesson_number, title, link 
                FROM lessons 
                WHERE type = 'video' AND title IS NOT NULL AND link IS NOT NULL
                ORDER BY lesson_number ASC
                LIMIT 20
            """)
            lessons = c.fetchall()

        if not lessons:
            bot.send_message(message.chat.id, "📭 لا توجد فيديوهات محفوظة حتى الآن.")
            return

        text = "🎬 *فهرس فيديوهات القناة:*\n\n"
        for num, title, link in lessons:
            text += f"🔹 *Lesson {num}:* [{title}]({link})\n"

        bot.send_message(message.chat.id, text, parse_mode="Markdown", disable_web_page_preview=True)

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ خطأ أثناء عرض الفهرس:\n{e}")

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
    

