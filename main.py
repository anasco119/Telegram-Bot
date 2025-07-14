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
from telebot import types
import uuid
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



lesson_id = str(uuid.uuid4())

temp_data = {}
user_states = {}
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
            
            # إنشاء جدول الدروس
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

            # تعديل الجدول لإضافة عمود prompt_message_id إن لم يكن موجودًا
            
            # تعديل الجدول لإضافة الأعمدة الجديدة إن لم تكن موجودة
            try:
                c.execute("ALTER TABLE lessons ADD COLUMN prompt_message_id INTEGER")
            except sqlite3.OperationalError:
                pass  # العمود موجود بالفعل

            try:
                c.execute("ALTER TABLE lessons ADD COLUMN tag TEXT")
            except sqlite3.OperationalError:
                pass

            try:
                c.execute("ALTER TABLE lessons ADD COLUMN tag_reason TEXT")
            except sqlite3.OperationalError:
                pass

            # إنشاء جدول البطاقات
            c.execute('''CREATE TABLE IF NOT EXISTS flashcards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lesson_id TEXT,
                video_id TEXT,
                prompt_message_id INTEGER,
                line TEXT,
                explanation TEXT,
                vocab_notes TEXT
            )''')
            c.execute("""
            CREATE TABLE IF NOT EXISTS quizzes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lesson_id TEXT,
                quiz_number INTEGER,
                question TEXT,
                options TEXT,
                answer TEXT
            )
            """)
            c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                level_tag TEXT
            )
            """)
            conn.commit()


            
            logging.info(f"Database created or updated at: {os.path.abspath(DB_FILE)}")
    except Exception as e:
        logging.error(f"Database initialization error: {e}")



def insert_old_lessons_from_json(json_path):
    if not os.path.exists(json_path):
        print(f"❌ الملف غير موجود: {json_path}")
        return

    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()

        # اختياري: تأكد من عدم التكرار
        c.execute("SELECT COUNT(*) FROM lessons WHERE lesson_number IS NOT NULL")
        count = c.fetchone()[0]
        if count > 0:
            print("ℹ️ الدروس تم استيرادها مسبقًا. تم الإلغاء.")
            return

        with open(json_path, "r", encoding="utf-8") as f:
            lessons = json.load(f)

        for i, lesson in enumerate(lessons, start=1):
            lesson_id = f"old_lesson_{i}"
            content = f"{lesson.get('title', '')}\n{lesson.get('link', '')}"

            c.execute("""
                INSERT INTO lessons (
                    id, content, video_id, srt_content, summary,
                    lesson_number, title, link, type, tag, tag_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                lesson_id,
                content,
                None,  # video_id
                lesson.get("srt_content"),   # ✅ مضاف حديثًا
                lesson.get("summary"),       # ✅ مضاف حديثًا
                i,
                lesson.get("title"),
                lesson.get("link"),
                lesson.get("type", "video"),
                lesson.get("tag"),
                lesson.get("tag_reason")
            ))

        conn.commit()
        print(f"✅ تم استيراد {len(lessons)} درس من ملف JSON.")



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

            # حفظ الدرس مباشرة في قاعدة البيانات الرئيسية
            with sqlite3.connect(DB_FILE) as conn:
                c = conn.cursor()
                c.execute("""
                    REPLACE INTO lessons (id, content) 
                    VALUES (?, ?)
                """, (lesson_id, lesson_text))
                conn.commit()

            # عرض رسالة التأكيد
            bot.send_message(
                message.chat.id,
                f"⚠️ هل تريد حقًا إرسال هذا الدرس إلى القناة؟\n\n"
                f"معرف الدرس: {lesson_id}\n"
                f"النص: {lesson_text[:300]}...",  # عرض جزء من النص للمعاينة
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ تأكيد الإرسال", callback_data=f"confirm_post:{lesson_id}"),
                        InlineKeyboardButton("❌ إلغاء", callback_data="cancel_post")
                    ]
                ])
            )

        else:
            bot.send_message(message.chat.id, "هذا الأمر متاح فقط للمسؤول.")
    except Exception as e:
        logging.error(f"خطأ في post_lesson: {e}")
        bot.send_message(USER_ID, f"حدث خطأ: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_post:'))
def confirm_post(call):
    try:
        lesson_id = call.data.split(':')[1]
        
        # استرجاع النص من قاعدة البيانات
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT content FROM lessons WHERE id = ?", (lesson_id,))
            result = c.fetchone()
            
            if not result:
                bot.answer_callback_query(call.id, "❌ لم يتم العثور على بيانات الدرس", show_alert=True)
                return
                
            lesson_text = result[0]

        # إرسال الدرس إلى القناة
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("📖 قراءة تفاعلية", url=f"{WEBHOOK_URL}/reader?text_id={lesson_id}")
        ]])
        
        bot.send_message(CHANNEL_ID, lesson_text, reply_markup=keyboard)
        bot.edit_message_text(
            "✅ تم نشر الدرس بنجاح في القناة.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )
        
    except Exception as e:
        logging.error(f"خطأ في confirm_post: {e}")
        bot.answer_callback_query(call.id, f"حدث خطأ: {e}", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == 'cancel_post')
def cancel_post(call):
    try:
        bot.edit_message_text(
            "❌ تم إلغاء نشر الدرس (البيانات محفوظة في قاعدة البيانات).",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )
    except Exception as e:
        logging.error(f"خطأ في cancel_post: {e}")
        bot.answer_callback_query(call.id, f"حدث خطأ أثناء الإلغاء: {e}", show_alert=True)

            

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


    #  1️⃣ Cohere
    if cohere_client:
        try:
            logging.info("Attempting request with: 5. Cohere...")
            response = cohere_client.chat(model='command-r', message=prompt)
            logging.info("✅ Success with Cohere.")
            return response.text
        except Exception as e:
            logging.warning(f"❌ Cohere failed: {e}")



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



def extract_json_from_string(text: str) -> str:
    """
    تحاول استخراج محتوى JSON من النص، سواء داخل ```json أو ضمن الأقواس مباشرة.
    تتحقق من صحة JSON وتعيده إذا كان صالحًا.
    """
    # 1. حاول استخراج من ```json ... ```
    match = re.search(r'```json\s*([\s\S]+?)\s*```', text)
    if match:
        candidate = match.group(1).strip()
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            print("⚠️ JSON داخل الكتلة غير صالح.")
    
    # 2. إذا لم يكن هناك كتلة json صالحة، حاول استخراج من أول [ أو { إلى آخر ] أو }
    start = min(
        (i for i in [text.find('['), text.find('{')] if i != -1),
        default=-1
    )
    end = max(
        (i for i in [text.rfind(']'), text.rfind('}')] if i != -1),
        default=-1
    )

    if start != -1 and end != -1 and end > start:
        candidate = text[start:end+1].strip()
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            print("⚠️ JSON داخل الأقواس غير صالح.")

    # 3. لا يوجد JSON صالح
    print("❌ لم يتم العثور على JSON صالح في الرد.")
    return "[]"

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


def generate_flashcards_for_lesson(lesson_id, video_id, srt_content, summary):
    try:
        prompt = f"""
أنت مساعد تعليمي ذكي، مهمتك هي إنشاء بطاقات تعليمية تفاعلية بناءً على محتوى فيديو تعليمي.

📝 لديك ما يلي:
1. تفريغ لحوار الفيديو (srt_content) — يحتوي على الجمل المنطوقة.
2. ملخص سياقي للفيديو (summary) — يوضح السياق العام والمغزى.

🎯 المطلوب:
إنشاء قائمة من البطاقات التعليمية (بين 5 إلى 15 بطاقة)، كل بطاقة تحتوي على المعلومات التالية:

- "line": جملة من الحوار.
- "explanation": شرح مبسط وممتع لهذه الجملة في ضوء سياق الفيديو.
- "vocab_notes": ملاحظات لغوية أو مفردات مفيدة من الجملة.

📌 الشروط المهمة:
- ✅ يجب أن تكون النتيجة النهائية **قائمة JSON صالحة 100%** فقط.
- ❌ لا تضف أي تعليقات أو مقدمات أو شرح خارج JSON.
- ⚠️ يجب أن تبدأ النتيجة بـ `[` وتنتهي بـ `]`.

🔽 البيانات التي تعتمد عليها:

🔹 تفريغ الحوار:
```srt
{srt_content}
🔹ملخص سياقي
{summary}
        
لا تكرر الشرح كثيرًا، واجعله مشوقًا ومفيدًا
مثال على شكل التنسيق :
[
  {{
    "line": "I can't believe she said that.",
    "explanation": "قال البطل هذا عندما تفاجأ بتصرف غير متوقع من البطلة.",
    "vocab_notes": "- can't believe = لا أصدق\\n- said that = قالت ذلك"
  }},
  {{
    "line": "We should try again tomorrow.",
    "explanation": "الجملة تدل على الإصرار بعد فشل أولي، وهو ما شجع الفريق على المحاولة مجددًا.",
    "vocab_notes": "- try again = نحاول مجددًا\\n- tomorrow = غدًا"
  }}
]

"""

        ai_response = generate_gemini_response(prompt)
        print("📤 رد الذكاء الاصطناعي:\n", ai_response)

        raw_json = extract_json_from_string(ai_response)
        print("📦 النص المستخرج كـ JSON:\n", raw_json)

        flashcards = json.loads(raw_json)
        print("🔢 عدد العناصر المستخرجة:", len(flashcards))

        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            for card in flashcards:
                c.execute('''
                    INSERT INTO flashcards (lesson_id, line, explanation, vocab_notes)
                    VALUES (?, ?, ?, ?)
                ''', (
                    lesson_id,
                    card["line"],
                    card["explanation"],
                    card["vocab_notes"]
                ))
            conn.commit()

        return len(flashcards)

    except Exception as e:
        print(f"❌ خطأ في توليد أو حفظ البطاقات:\n{e}")
        return 0




def generate_quizzes_for_lesson(lesson_id):
    

    # استخراج البطاقات من قاعدة البيانات
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT line, explanation, vocab_notes FROM flashcards WHERE lesson_id = ?", (lesson_id,))
        flashcards = [{"line": row[0], "explanation": row[1], "vocab_notes": row[2]} for row in c.fetchall()]

    if not flashcards:
        print("❌ لا توجد بطاقات تعليمية.")
        return 0

    # توليد البرومبت مع تصحيح تنسيق JSON
    prompt = f"""
أنت مساعد تعليمي ذكي. مهمتك توليد 3 اختبارات قصيرة (Quiz) بناءً على هذه البطاقات التعليمية.

كل اختبار يحتوي على 3 إلى 5 أسئلة اختيار من متعدد. كل سؤال يتضمن:
- "question": صيغة السؤال بالعربية (مثلاً: ما معنى "I can't believe this"?)
- "options": قائمة من 4 خيارات
- "answer": الخيار الصحيح

📘 البيانات:
{json.dumps(flashcards, ensure_ascii=False, indent=2)}

📌 المطلوب: أرسل فقط قائمة تحتوي على 3 مجموعات من الأسئلة، كل مجموعة عبارة عن قائمة أسئلتها الخاصة. ⚠️ لا تدمج كل الأسئلة في قائمة واحدة، بل اجعل الشكل النهائي هكذا:

[
  [
    {{
      "question": "ما معنى I can't believe this?",
      "options": ["لا أصدق ذلك", "أريد ذلك", "هل تظن ذلك؟", "لن يحدث"],
      "answer": "لا أصدق ذلك"
    }},
    // المزيد من الأسئلة...
  ],
  // اختبار ثاني...
]"""

    # توليد الرد
    ai_response = generate_gemini_response(prompt)
    raw_json = extract_json_from_string(ai_response)

    try:
        quizzes = json.loads(raw_json)
        if not isinstance(quizzes, list) or not all(isinstance(q, list) for q in quizzes):
            print("❌ تنسيق JSON غير صالح (يجب أن يكون قائمة من القوائم).")
            return 0
    except Exception as e:
        print(f"❌ فشل في قراءة JSON:\n{e}")
        return 0

    # تخزين الأسئلة
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        for quiz_number, quiz in enumerate(quizzes, start=1):
            for q in quiz:
                if not isinstance(q, dict):
                    print(f"⚠️ عنصر غير صالح (ليس dict): {q}")
                    continue
                try:
                    c.execute("""
                        INSERT INTO quizzes (lesson_id, quiz_number, question, options, answer)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        lesson_id,
                        quiz_number,
                        q["question"],
                        json.dumps(q["options"], ensure_ascii=False),
                        q["answer"]
                    ))
                except Exception as insert_err:
                    print(f"❌ خطأ أثناء حفظ سؤال:\n{insert_err}")
        conn.commit()

    return sum(len(qz) for qz in quizzes)
# -------------------------------------------------------------------------------------- message handler -------------
#-----------------------------------------

# ✅ أمر /start
@bot.message_handler(commands=['subtitle'])
def handle_start(message):
    if not message.from_user or message.chat.type != "private":
        return
    if message.from_user.id == ALLOWED_USER_ID:
        bot.reply_to(message, "👋 أرسل فيديو وسأقوم بتحويله إلى ملف ترجمة.")
    else:
        bot.reply_to(message, "❌ هذا البوت مخصص فقط للأدمن.")




# ✅ استقبال فيديو من الأدمن فقط
@bot.message_handler(content_types=['video'])
def handle_video(message):
    if not message.from_user or message.chat.type != "private":
        return
    if message.from_user.id != ALLOWED_USER_ID:
        bot.reply_to(message, "❌ هذا الأمر متاح فقط للأدمن.")
        return

    bot.reply_to(message, "📥 تم استلام الفيديو. جاري المعالجة...")

    try:
        file_info = bot.get_file(message.video.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        with open(VIDEO_PATH, 'wb') as f:
            f.write(downloaded_file)

        temp_data['video_id'] = message.video.file_id

        success = process_video_to_srt()

        if success:
            with open(SRT_PATH, 'r', encoding='utf-8') as srt_file:
                srt_content = srt_file.read()

            bot.send_document(message.chat.id, open(SRT_PATH, 'rb'), caption="✅ ملف الترجمة جاهز.")

            # توليد رقم الدرس تلقائيًا
            with sqlite3.connect(DB_FILE) as conn:
                c = conn.cursor()
                c.execute("SELECT MAX(lesson_number) FROM lessons")
                result = c.fetchone()
                last_number = result[0] if result and result[0] else 0
                new_number = last_number + 1

            # تخزين مؤقت
            temp_data['lesson_number'] = new_number
            temp_data['lesson_id'] = str(uuid.uuid4())
            temp_data['srt_content'] = srt_content

            # حفظ بعض البيانات المؤقتة
            
            temp_data['video_file_id'] = message.video.file_id


            # أزرار لنشر الفيديو
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("✅ نعم", callback_data="publish_video_yes"),
                types.InlineKeyboardButton("❌ لا", callback_data="publish_video_no")
            )
            bot.send_message(message.chat.id, "📤 هل تريد نشر الفيديو في القناة الآن؟", reply_markup=markup)
            
    except Exception as e:
        bot.reply_to(message, f"❌ خطأ أثناء التنزيل أو المعالجة:\n{e}")


@bot.callback_query_handler(func=lambda call: call.data == "publish_video_yes")
def handle_publish_yes(call):
    bot.answer_callback_query(call.id)
    user_states[call.from_user.id] = "awaiting_caption"
    bot.send_message(call.message.chat.id, "📝 أرسل الآن الكابشن الذي سيتم نشره مع الفيديو في القناة.")


@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id) == "awaiting_caption")
def handle_caption(msg):
    caption = msg.text.strip()
    user_id = msg.from_user.id

    try:
        # نشر الفيديو في القناة
        post = bot.send_video(
            chat_id='@ans09031',
            video=temp_data['video_file_id'],
            caption=caption
        )

        # توليد رقم الدرس تلقائيًا
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT MAX(lesson_number) FROM lessons")
            result = c.fetchone()
            last_number = result[0] if result and result[0] else 0
            new_number = last_number + 1

        temp_data['lesson_number'] = new_number
        
        temp_data['published_message_id'] = post.message_id
        temp_data['link'] = f"https://t.me/EnglishConvs/{post.message_id}"

        bot.send_message(msg.chat.id, "📌 تم نشر الفيديو بنجاح في القناة.\n📝 الآن أرسل عنوان الدرس.")
        user_states[user_id] = "awaiting_title"
    except Exception as e:
        bot.send_message(msg.chat.id, f"❌ فشل في نشر الفيديو:\n{e}")
        user_states.pop(user_id, None)
        temp_data.clear()





@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id) == "awaiting_title")
def handle_title(msg):
    temp_data['title'] = msg.text.strip()
    user_states[msg.from_user.id] = "awaiting_summary"
    bot.send_message(msg.chat.id, "✍️ أرسل الآن ملخص الدرس (summary).")


@bot.callback_query_handler(func=lambda call: call.data == "publish_video_no")
def handle_save_lesson_no(call):
    bot.answer_callback_query(call.id, "🚫 تم تجاهل حفظ الدرس.")
    temp_data.clear()
    user_states.pop(call.from_user.id, None)



@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id) == "awaiting_summary")
def handle_summary(msg):
    summary = msg.text.strip()

    # توليد الرابط التلقائي من معرف القناة + message_id
    channel_base = "https://t.me/EnglishConvs"
    video_link = temp_data.get('link', 'رابط غير متوفر')
    lesson_number = temp_data['lesson_number']
    lesson_id = temp_data['lesson_id']
    title = temp_data.get('title', f"Lesson {lesson_number}")

    try:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO lessons (id, content, lesson_number, video_id, srt_content, summary, title, link, type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                lesson_id,
                "video",
                lesson_number,
                temp_data['video_file_id'],
                temp_data['srt_content'],
                summary,
                title,
                video_link,
                "video"
            ))
            conn.commit()

        bot.send_message(msg.chat.id, f"✅ تم حفظ الدرس: {title} (رقم {lesson_number}) بنجاح.")
        
            # ✅ بعد الحفظ الناجح: عرض أزرار توليد البطاقات
        markup = types.InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("✅ نعم، أنشئ البطاقات", callback_data=f"generate_flashcards_{lesson_id}"),
            types.InlineKeyboardButton("❌ لا، شكراً", callback_data="cancel_flashcards")
    )
        prompt = bot.send_message(
            msg.chat.id,
            "🎓 هل ترغب في توليد بطاقات تعليمية من هذا الدرس؟",
            reply_markup=markup
    )

        # حفظ معرف رسالة التأكيد في قاعدة البيانات إذا أردت
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("UPDATE lessons SET prompt_message_id = ? WHERE video_id = ?", (prompt.message_id, temp_data['video_file_id']))
            conn.commit()
    except Exception as e:
        bot.send_message(msg.chat.id, f"❌ حدث خطأ أثناء حفظ البيانات:\n{e}")

# -------------------------
# ------ Notifying users --------
# --------------------------------


@bot.message_handler(commands=['start_level'])
def ask_user_level(message):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🟢 مبتدئ مريح", callback_data="set_level_مبتدئ مريح"),
        InlineKeyboardButton("🔵 سهل", callback_data="set_level_سهل")
    )
    markup.row(
        InlineKeyboardButton("🟠 متوسط", callback_data="set_level_متوسط"),
        InlineKeyboardButton("🔴 سريع ومكثف", callback_data="set_level_سريع ومكثف")
    )
    bot.send_message(
        message.chat.id,
        "👋 حدد مستواك لتبدأ بتلقي الدروس المناسبة لك:",
        reply_markup=markup
    )



@bot.callback_query_handler(func=lambda call: call.data.startswith("set_level_"))
def handle_set_level(call):
    tag = call.data.replace("set_level_", "")
    user_id = call.from_user.id

    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO users (user_id, level_tag) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET level_tag=excluded.level_tag
        """, (user_id, tag))
        conn.commit()

    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, f"✅ تم تعيين مستواك: {tag}\n📬 ستصلك الدروس المناسبة لهذا التصنيف.")


def notify_users_by_tag(tag, lesson_title, lesson_id):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE level_tag = ?", (tag,))
        users = c.fetchall()

    for user in users:
        try:
            bot.send_message(
                user[0],
                f"📢 درس جديد مناسب لمستواك ({tag}):\n🎬 {lesson_title}\n📚 استخدم /lesson {lesson_id} لعرضه"
            )
        except Exception as e:
            print(f"⚠️ فشل إرسال الدرس للمستخدم {user[0]}: {e}")




@bot.callback_query_handler(func=lambda call: call.data.startswith("generate_flashcards_"))
def handle_generate_flashcards(call):
    bot.answer_callback_query(call.id)
    lesson_id = call.data.split("_")[-1]

    # جلب البيانات من الدرس
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT srt_content, summary, video_id FROM lessons WHERE id = ?", (lesson_id,))
        row = c.fetchone()

    if not row:
        return bot.send_message(call.message.chat.id, "❌ لم يتم العثور على محتوى هذا الدرس.")

    srt_content, summary, video_id = row
    bot.send_message(call.message.chat.id, "⚙️ جاري توليد البطاقات، يرجى الانتظار...")

    try:
        count = generate_flashcards_for_lesson(lesson_id, video_id, srt_content, summary)
        quiz_count = generate_quizzes_for_lesson(lesson_id)
        noto = notify_users_by_tag(tag, title, lesson_number)
        bot.send_message(call.message.chat.id, f"✅ تم إنشاء {count} بطاقة للدرس.")
    except Exception as e:
        return bot.send_message(call.message.chat.id, f"❌ فشل في توليد البطاقات:\n{e}")

    # ثم زر الإشعار
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("✅ نعم، أنشئ الإشعار", callback_data=f"yes_Noto_{lesson_id}"),
        InlineKeyboardButton("❌ لا، شكراً", callback_data="cancel_Noto")
    )
    bot.send_message(call.message.chat.id, "📣 هل تريد إرسال إشعار إلى القناة؟", reply_markup=markup)


bot_username = "AIChatGeniebot"

@bot.callback_query_handler(func=lambda call: call.data.startswith("yes_Noto_"))
def handle_send_notification(call):
    try:
        bot.answer_callback_query(call.id)

        lesson_id = call.data.split("_")[-1]  # ✅ بدل temp_data
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT title, prompt_message_id FROM lessons WHERE id = ?", (lesson_id,))
            row = c.fetchone()

        if not row:
            bot.send_message(call.message.chat.id, "❌ لم يتم العثور على بيانات هذا الدرس.")
            return

        title, published_message_id = row
        message_text = f"🆕 درس إنجليزي جديد وممتع بانتظارك: *{title}*\n\n🎯 اختر أحد الأنشطة لتبدأ:"

        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("🧠 ابدأ الشرح", url=f"https://t.me/{bot_username}?start=lesson_{lesson_id}"),
            InlineKeyboardButton("📝 اختبر نفسك", url=f"https://t.me/{bot_username}?start=quiz_{lesson_id}")
        )

        prompt = bot.send_message(
            chat_id='@ans09031',
            text=message_text,
            # reply_to_message_id=published_message_id,  ← علق هذا السطر مؤقتًا
            reply_markup=markup,
            parse_mode="Markdown"
        )
        

        # تحديث معرف الرسالة الجديدة
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("UPDATE lessons SET prompt_message_id = ? WHERE id = ?", (prompt.message_id, lesson_id))
            conn.commit()

        bot.send_message(call.message.chat.id, "📣 تم إرسال الأنشطة إلى القناة بنجاح.")
    
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ حدث خطأ أثناء إرسال الإشعار:\n{e}")
    finally:
        user_states.pop(call.from_user.id, None)
        temp_data.clear()


@bot.callback_query_handler(func=lambda call: call.data == "cancel_Noto")
def handle_cancel_noto(call):
    try:
        bot.answer_callback_query(call.id, "🚫 تم إلغاء إرسال إشعار الدرس.")
        bot.send_message(call.message.chat.id, "👍 لن يتم إرسال إشعار إلى القناة.")
    finally:
        user_states.pop(call.from_user.id, None)
        temp_data.clear()

        # حذف الملفات المؤقتة
        try:
            if os.path.exists(SRT_PATH):
                os.remove(SRT_PATH)
            if os.path.exists(VIDEO_PATH):
                os.remove(VIDEO_PATH)
        except Exception as cleanup_error:
            print(f"⚠️ خطأ أثناء حذف الملفات المؤقتة: {cleanup_error}")

# ----------------------------------------
# ------------  start Cards ---------------------
#---------------------------------------

def show_flashcards(chat_id, lesson_id):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT title FROM lessons WHERE id = ?", (lesson_id,))
        lesson = c.fetchone()
        c.execute("SELECT COUNT(*) FROM flashcards WHERE lesson_id = ?", (lesson_id,))
        total = c.fetchone()[0]

    if not lesson or total == 0:
        return bot.send_message(chat_id, "❌ لا توجد بطاقات تعليمية لهذا الدرس بعد.")

    lesson_title = lesson[0]

    text = f"""📘 *بطاقات تعليمية للدرس: {lesson_title}*

📽️ *عنوان الفيديو:* {lesson_title}

🎯 *الهدف:* تحسين مهارات الفهم والمفردات من خلال بطاقات مبنية على الحوار.

✔️ *نصيحة:* شغّل الفيديو في الوضع المصغّر أثناء استعراض البطاقات لتستفيد أكثر.

📝 *عدد البطاقات:* {total}


اضغط على "ابدأ" للانتقال إلى البطاقات التعليمية 👇
"""

    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🚀 ابدأ", callback_data=f"flash_start_{lesson_id}")
    )

    bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("flash_"))
def handle_flash_navigation(call):
    bot.answer_callback_query(call.id)
    try:
        parts = call.data.split("_")
        action = parts[1]  # start / next / prev / restart / end
        lesson_id = parts[2]
        current_card_id = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else None

        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            # جميع البطاقات المرتبة
            c.execute("SELECT id, line, explanation, vocab_notes FROM flashcards WHERE lesson_id = ? ORDER BY id", (lesson_id,))
            all_cards = c.fetchall()
            total = len(all_cards)

        if total == 0:
            return bot.send_message(call.message.chat.id, "❌ لا توجد بطاقات لهذا الدرس.")

        if action == "start":
            index = 0
        elif action in ("next", "prev"):
            ids = [card[0] for card in all_cards]
            index = ids.index(current_card_id)
            if action == "next" and index < total - 1:
                index += 1
            elif action == "prev" and index > 0:
                index -= 1
        elif action == "restart":
            index = 0
        elif action == "end":
            index = total  # بطاقة النهاية
        else:
            return

        if index == total:
            # 🎯 بطاقة النهاية
            text = f"""🏁 *انتهيت من مراجعة البطاقات!*



🧠 *ملخص الدرس:* (تمت مراجعته)



🎯 استعد لاختبار نفسك أو راجع البطاقات مجددًا.

— @EnglishConvs"""

            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton("🔁 إعادة", callback_data=f"flash_restart_{lesson_id}"),
                InlineKeyboardButton("📝 اختبار نفسك", url=f"https://t.me/{bot_username}?start=quiz_{lesson_id}")
            )

            return bot.edit_message_text(
                text,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                parse_mode="Markdown",
                reply_markup=markup
            )

        # بطاقة عادية
        card_id, line, explanation, vocab_notes = all_cards[index]
        card_number = index + 1
        text = f"""📚 بطاقة {card_number} من {total}

💬 {line}



🧠 {explanation}


📌 {vocab_notes}

— @EnglishConvs"""

        # أزرار التنقل
        markup = InlineKeyboardMarkup()
        buttons = []
        if index > 0:
            buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"flash_prev_{lesson_id}_{card_id}"))
        if index < total - 1:
            buttons.append(InlineKeyboardButton("➡️ التالي", callback_data=f"flash_next_{lesson_id}_{card_id}"))
        else:
            buttons.append(InlineKeyboardButton("🏁 إنهاء", callback_data=f"flash_end_{lesson_id}"))

        markup.row(*buttons)  # سطر واحد بدل سطرين

        bot.edit_message_text(
            text,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )

    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ حدث خطأ:\n{e}")



# تخزين حالة الاختبار لكل مستخدم
user_quiz_state = {}

def start_quiz(chat_id, lesson_id, bot):
    """بدء اختبار معين وإرسال أول سؤال"""
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT quiz_number, question, options, answer 
            FROM quizzes 
            WHERE lesson_id = ? 
            ORDER BY quiz_number
        """, (lesson_id,))
        quizzes = c.fetchall()

    if not quizzes:
        bot.send_message(chat_id, "❌ لا توجد اختبارات محفوظة لهذا الدرس بعد.")
        return

    # تحويل النتائج إلى هيكل مناسب
    quiz_data = []
    current_quiz = []
    current_quiz_number = None

    for quiz in quizzes:
        quiz_number, question, options, answer = quiz
        options = json.loads(options)
        
        if current_quiz_number != quiz_number:
            if current_quiz:
                quiz_data.append(current_quiz)
            current_quiz = []
            current_quiz_number = quiz_number
        
        current_quiz.append({
            "question": question,
            "options": options,
            "answer": answer
        })
    
    if current_quiz:
        quiz_data.append(current_quiz)

    # حفظ حالة الاختبار للمستخدم
    user_quiz_state[chat_id] = {
        'lesson_id': lesson_id,
        'quizzes': quiz_data,
        'current_quiz': 0,
        'current_question': 0,
        'score': 0
    }

    # إرسال أول سؤال
    send_next_question(chat_id, bot)

def send_next_question(chat_id, bot):
    """إرسال السؤال التالي في الاختبار"""
    if chat_id not in user_quiz_state:
        return

    state = user_quiz_state[chat_id]
    quizzes = state['quizzes']
    quiz_idx = state['current_quiz']
    question_idx = state['current_question']

    if quiz_idx >= len(quizzes):
        # انتهاء جميع الاختبارات
        bot.send_message(
            chat_id,
            f"🏁 انتهت جميع الاختبارات! النتيجة النهائية: {state['score']}/{sum(len(q) for q in quizzes)}"
        )
        del user_quiz_state[chat_id]
        return

    current_quiz = quizzes[quiz_idx]
    
    if question_idx >= len(current_quiz):
        # الانتقال إلى الاختبار التالي
        state['current_quiz'] += 1
        state['current_question'] = 0
        send_next_question(chat_id, bot)
        return

    question_data = current_quiz[question_idx]
    
    # إرسال السؤال الحالي
    poll = bot.send_poll(
        chat_id=chat_id,
        question=question_data["question"],
        options=question_data["options"],
        is_anonymous=False,
        type='quiz',
        correct_option_id=question_data["options"].index(question_data["answer"])
    )

    # حفظ معرف الرسالة لتتبع الإجابة
    state['last_poll_message_id'] = poll.message_id

@bot.poll_answer_handler()
def handle_poll_answer(poll_answer):
    """معالجة إجابة المستخدم على السؤال"""
    chat_id = poll_answer.user.id
    
    if chat_id not in user_quiz_state:
        return

    state = user_quiz_state[chat_id]
    
    # الحصول على تفاصيل السؤال الحالي
    current_quiz = state['quizzes'][state['current_quiz']]
    current_question = current_quiz[state['current_question']]
    
    # التحقق من الإجابة
    correct_option = current_question["options"].index(current_question["answer"])
    if poll_answer.option_ids and poll_answer.option_ids[0] == correct_option:
        state['score'] += 1
        feedback = "✅ إجابة صحيحة!"
    else:
        feedback = f"❌ إجابة خاطئة! الإجابة الصحيحة هي: {current_question['answer']}"
    
    # إرسال التغذية الراجعة
    bot.send_message(chat_id, feedback)
    
    # الانتقال إلى السؤال التالي
    state['current_question'] += 1
    send_next_question(chat_id, bot)


def generate_all_content_on_startup():
    print("🚀 بدء توليد المحتوى التعليمي لجميع الدروس...\n")

    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT id, video_id, srt_content, summary FROM lessons WHERE srt_content IS NOT NULL AND summary IS NOT NULL")
        lessons = c.fetchall()

    for lesson_id, video_id, srt_content, summary in lessons:
        # التحقق من وجود البطاقات
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM flashcards WHERE lesson_id = ?", (lesson_id,))
            flashcard_count = c.fetchone()[0]

        if flashcard_count == 0:
            try:
                print(f"📘 توليد البطاقات للدرس {lesson_id}...")
                generate_flashcards_for_lesson(lesson_id, video_id, srt_content, summary)
                print(f"✅ تم توليد البطاقات للدرس {lesson_id}")
            except Exception as e:
                print(f"❌ فشل في توليد البطاقات للدرس {lesson_id}:\n{e}")
                continue
        else:
            print(f"✔️ البطاقات موجودة مسبقًا للدرس {lesson_id}")

        # التحقق من وجود اختبارات
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM quizzes WHERE lesson_id = ?", (lesson_id,))
            quiz_count = c.fetchone()[0]

        if quiz_count == 0:
            try:
                print(f"📝 توليد اختبارات للدرس {lesson_id}...")
                total_questions = generate_quizzes_for_lesson(lesson_id)
                print(f"✅ تم توليد {total_questions} سؤالًا للدرس {lesson_id}")
            except Exception as e:
                print(f"❌ فشل في توليد اختبارات للدرس {lesson_id}:\n{e}")
        else:
            print(f"✔️ الاختبارات موجودة مسبقًا للدرس {lesson_id}")

    print("\n🎉 اكتملت عملية توليد المحتوى لجميع الدروس.")

# ----------------------------------------
# ------- old code -------------------------
# --------------------------------

@bot.message_handler(commands=['import_old_lessons'])
def import_lessons_command(message):
    if not message.from_user or message.chat.type != "private":
        return
    if message.from_user.id != ALLOWED_USER_ID:
        bot.reply_to(message, "❌ هذا الأمر مخصص فقط للأدمن.")
        return

    try:
        insert_old_lessons_from_json("videos_list.json")
        bot.reply_to(message, "✅ تم استيراد الدروس القديمة بنجاح.")
    except Exception as e:
        bot.reply_to(message, f"❌ حدث خطأ أثناء الاستيراد:\n{e}")

        
@bot.message_handler(commands=['index'])
def handle_video_index(message):
    if not message.from_user or message.chat.type != "private":
        return
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
        



def send_flashcards(bot, chat_id, lesson_id, mode='private'):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT line, explanation, vocab_notes 
            FROM flashcards 
            WHERE lesson_id = ?
        """, (lesson_id,))
        cards = c.fetchall()

    if not cards:
        bot.send_message(chat_id, "❌ لا توجد بطاقات تعليمية لهذا الدرس.")
        return

    for idx, (line, explanation, vocab) in enumerate(cards, start=1):
        text = f"""📘 *البطاقة {idx}*
✉️ *الجملة:* `{line}`

📖 *الشرح:* {explanation}

📌 *ملاحظات:* {vocab}"""
        bot.send_message(chat_id, text, parse_mode='Markdown')

    if mode == "channel":
        bot.send_message(chat_id, f"✅ تم نشر بطاقات الدرس: {lesson_id}")



def send_quiz(bot, chat_id, lesson_id, mode='private'):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT quiz_number, question, options, answer 
            FROM quizzes 
            WHERE lesson_id = ?
            ORDER BY quiz_number
        """, (lesson_id,))
        quizzes = c.fetchall()

    if not quizzes:
        bot.send_message(chat_id, "❌ لا توجد اختبارات محفوظة لهذا الدرس.")
        return

    quiz_data = {}
    for quiz_number, question, options, answer in quizzes:
        options = json.loads(options)
        correct_idx = options.index(answer)
        if quiz_number not in quiz_data:
            quiz_data[quiz_number] = []
        quiz_data[quiz_number].append((question, options, correct_idx))

    for quiz_number, questions in quiz_data.items():
        for question, options, correct_idx in questions:
            bot.send_poll(
                chat_id,
                question=question,
                options=options,
                type='quiz',
                correct_option_id=correct_idx,
                is_anonymous=False
        )


@bot.message_handler(commands=['lesson'])
def handle_lesson_command(message):
    parts = message.text.split()
    if len(parts) < 2:
        return bot.reply_to(message, "❗ استخدم الأمر بهذا الشكل:\n/lesson 3")

    try:
        lesson_number = int(parts[1])
    except ValueError:
        return bot.reply_to(message, "❗ رقم الدرس غير صالح. استخدم رقمًا مثل:\n/lesson 2")

    # جلب بيانات الدرس من قاعدة البيانات
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT id, title, tag FROM lessons WHERE lesson_number = ?", (lesson_number,))
        result = c.fetchone()

    if not result:
        return bot.send_message(message.chat.id, "❌ لم يتم العثور على هذا الدرس.")

    lesson_id, title, tag = result

    # إعداد الأزرار
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🎓 عرض البطاقات", callback_data=f"view_flashcards_{lesson_id}"),
        InlineKeyboardButton("📝 اختبر نفسك", callback_data=f"quiz_{lesson_id}")
    )

    tag_text = f"\n🏷️ التصنيف: *{tag}*" if tag else ""
    bot.send_message(
        message.chat.id,
        f"🎬 *{title}* (درس رقم {lesson_number}){tag_text}\nاختر الإجراء:",
        parse_mode="Markdown",
        reply_markup=markup
        )
    



@bot.callback_query_handler(func=lambda call: call.data.startswith("quiz_"))
def handle_quiz_start(call):
    lesson_id = call.data.replace("quiz_", "")
    send_quiz(bot, call.message.chat.id, lesson_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("view_flashcards_"))
def handle_view_flashcards(call):
    lesson_id = call.data.replace("view_flashcards_", "")
    send_flashcards(bot, call.message.chat.id, lesson_id)

@bot.message_handler(commands=['index_by_tag'])
def handle_index_by_tag(message):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT lesson_number, title, tag FROM lessons 
            WHERE lesson_number IS NOT NULL 
            ORDER BY 
                CASE 
                    WHEN tag = 'مبتدئ مريح' THEN 1
                    WHEN tag = 'سهل' THEN 2
                    WHEN tag = 'متوسط' THEN 3
                    WHEN tag = 'سريع ومكثف' THEN 4
                    ELSE 5
                END, lesson_number
        """)
        rows = c.fetchall()

    if not rows:
        return bot.send_message(message.chat.id, "❌ لا توجد دروس متاحة بعد.")

    # تجميع الدروس حسب التصنيف
    tag_groups = {}
    for num, title, tag in rows:
        tag = tag or "غير مصنف"
        tag_groups.setdefault(tag, []).append((num, title))

    # إعداد الرد
    tag_emojis = {
        "مبتدئ مريح": "🟢",
        "سهل": "🔵",
        "متوسط": "🟠",
        "سريع ومكثف": "🔴",
        "غير مصنف": "⚪️"
    }

    reply = "📚 *فهرس الدروس حسب المستوى:*\n\n"
    for tag, lessons in tag_groups.items():
        emoji = tag_emojis.get(tag, "🗂️")
        reply += f"{emoji} *{tag}:*\n"
        for num, title in lessons:
            reply += f"{num}. {title} — /lesson {num}\n"
        reply += "\n"

    bot.send_message(message.chat.id, reply, parse_mode="Markdown")




@bot.message_handler(commands=['start'])
def handle_start(message):
    args = message.text.split()

    if len(args) > 1:
        payload = args[1]  # استخدم اسم موحّد بدلاً من param

        if payload == "index":
            handle_video_index(message)

        elif payload.startswith("lesson_"):
            lesson_id = payload.replace("lesson_", "")
            show_flashcards(message.chat.id, lesson_id)

        elif payload.startswith("quiz_"):
            lesson_id = payload.replace("quiz_", "")
            start_quiz(message.chat.id, lesson_id, bot)  # مرر bot هنا

        else:
            bot.send_message(message.chat.id, f"مرحبًا بك! لم يتم التعرف على الأمر: {payload}")

    else:
        bot.send_message(message.chat.id, "👋 مرحبًا بك في البوت!")

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
    generate_all_content_on_startup()
    port = int(os.environ.get('PORT', 10000))  # Render يستخدم 10000
    app.run(host='0.0.0.0', port=port)
