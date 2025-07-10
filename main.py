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
            try:
                c.execute("ALTER TABLE lessons ADD COLUMN prompt_message_id INTEGER")
            except sqlite3.OperationalError:
                pass  # العمود موجود بالفعل

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

            conn.commit()
            logging.info(f"Database created or updated at: {os.path.abspath(DB_FILE)}")
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
                "INSERT INTO lessons (id, content, video_id, srt_content, summary, lesson_number, title, link, type) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (lesson_id, content, None, None, None, i, lesson.get('title'), lesson.get('link'), 'video')
            )
        conn.commit()
        print(f"Imported {len(lessons)} lessons from JSON.")




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


def extract_json_from_string(text: str) -> str:
    """
    Extracts a JSON string from a text that might contain markdown code blocks or other text.
    """
    # البحث عن بلوك JSON داخل ```json ... ```
    match = re.search(r'```json\s*([\s\S]*?)\s*```', text)
    if match:
        return match.group(1).strip()

    # إذا لم يجد بلوك، ابحث عن أول '{' أو '[' وآخر '}' أو ']'
    start = -1
    end = -1
    
    # البحث عن بداية القائمة أو الكائن
    first_brace = text.find('{')
    first_bracket = text.find('[')
    
    if first_brace == -1:
        start = first_bracket
    elif first_bracket == -1:
        start = first_brace
    else:
        start = min(first_brace, first_bracket)

    # إذا لم يتم العثور على بداية، أرجع النص الأصلي
    if start == -1:
        return text

    # البحث عن نهاية القائمة أو الكائن
    last_brace = text.rfind('}')
    last_bracket = text.rfind(']')
    end = max(last_brace, last_bracket)

    # إذا تم العثور على بداية ونهاية، أرجع ما بينهما
    if end > start:
        return text[start:end+1].strip()
        
    # كخيار أخير، أرجع النص كما هو
    return text

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



def generate_flashcards_for_lesson(lesson_id, srt_content, summary):
    try:
        prompt = f"""
أنت مساعد تعليمي ذكي. لديك تفريغ لحوار من مقطع فيديو (srt_content) وملخص عن سياق الفيديو (summary).
مهمتك هي إنشاء بطاقات تعليمية تفاعلية.

لكل سطر أو سطرين في النص، أنشئ بطاقة تحتوي على:
1. "line": الجملة الأصلية
2. "explanation": شرح قصير ممتع يربط الجملة بسياق الفيديو من الملخص
3. "vocab_notes": مفردات مهمة أو ملاحظات نحوية أو لغوية

هذا هو التفريغ الكامل:
{srt_content}

وهذا هو الملخص العام للفيديو:
{summary}

رجاءً أنشئ قائمة JSON لبطاقات تعليمية كما في المثال:

صيغة الإخراج يجب أن تكون JSON list مثل:

[
  {
    "line": "I can't believe she said that.",
    "explanation": "قال البطل هذا عندما تفاجأ بتصرف غير متوقع من البطلة، مما يشير إلى بداية التوتر.",
    "vocab_notes": "- can't believe = لا أصدق\n- said that = قالت ذلك"
  },
  ...
]

لا تكرر الشرح كثيرًا، واجعله مشوقًا ومفيدًا

"""
        # استخدم نموذج AI الخاص بك هنا
        ai_response = generate_gemini_response(prompt)  # استبدلها بما يناسبك
        raw_json = extract_json_from_string(ai_response)
        flashcards = json.loads(raw_json)

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
        print(f"✅ تم إنشاء {len(flashcards)} بطاقة للدرس {lesson_id}")
    except Exception as e:
        print(f"❌ خطأ في توليد البطاقات:\n{e}")
        
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
        temp_data['lesson_id'] = datetime.now().strftime("%Y%m%d%H%M%S")
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
            types.InlineKeyboardButton("🧠 نعم، أنشئ البطاقات", callback_data=f"generate_flashcards_{temp_data['lesson_id']}"),
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

@bot.callback_query_handler(func=lambda call: call.data.startswith("generate_flashcards_"))
def handle_generate_flashcards(call):
    bot.answer_callback_query(call.id)

    lesson_id = call.data.split("_")[-1]

    try:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            # استخرج srt_content و summary و video_id من قاعدة البيانات
            c.execute("SELECT srt_content, summary, video_id FROM lessons WHERE id = ?", (lesson_id,))
            result = c.fetchone()

        if not result:
            bot.send_message(call.message.chat.id, "❌ لم يتم العثور على محتوى هذا الدرس.")
            return

        srt_content, summary, video_id = result  # ✅ الآن video_id موجود
        bot.send_message(call.message.chat.id, "⚙️ جاري توليد البطاقات، يرجى الانتظار...")

        generate_flashcards_for_lesson(video_id, srt_content, summary)

        bot.send_message(call.message.chat.id, "✅ تم إنشاء بطاقات الدرس بنجاح.")
        # ✅ رسالة تأكيد إرسال الإشعار إلى القناة
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("✅ نعم", callback_data="yes_Noto"),
            InlineKeyboardButton("❌ لا، شكراً", callback_data="cancel_Noto")
        )

        bot.send_message(
            call.message.chat.id,
            "📣 هل تريد إرسال إشعار إلى القناة؟",
            reply_markup=markup
        )
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ فشل في توليد البطاقات:\n{e}")

    finally:
        user_states.pop(call.from_user.id, None)
        temp_data.clear()
        try:
            if os.path.exists(SRT_PATH):
                os.remove(SRT_PATH)
            if os.path.exists(VIDEO_PATH):
                os.remove(VIDEO_PATH)
        except Exception as cleanup_error:
            print(f"⚠️ خطأ أثناء حذف الملفات المؤقتة: {cleanup_error}")
            


bot_username = "AIChatGeniebot"

@bot.callback_query_handler(func=lambda call: call.data == "yes_Noto")
def handle_send_notification(call):
    try:
        bot.answer_callback_query(call.id)

        lesson_id = temp_data.get("lesson_id")
        published_message_id = temp_data.get("published_message_id")
        

        if not lesson_id or not published_message_id:
            bot.send_message(call.message.chat.id, "❌ لا يمكن متابعة الإشعار لعدم وجود بيانات الدرس.")
            return

        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT title FROM lessons WHERE id = ?", (lesson_id,))
            row = c.fetchone()

        title = row[0] if row else "درس جديد"
        message_text = f"🆕 درس إنجليزي جديد وممتع بانتظارك: *{title}*\n\n🎯 اختر أحد الأنشطة لتبدأ:"

        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("🧠 ابدأ الشرح", url=f"https://t.me/{bot_username}?start=lesson_{lesson_id}"),
            InlineKeyboardButton("📝 اختبر نفسك", url=f"https://t.me/{bot_username}?start=quiz_{lesson_id}")
        )

        prompt = bot.send_message(
            chat_id='@ans09031',
            text=message_text,
            reply_to_message_id=published_message_id,
            reply_markup=markup,
            parse_mode="Markdown"
        )

        # تحديث الجدول
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("UPDATE lessons SET prompt_message_id = ? WHERE id = ?", (prompt.message_id, lesson_id))
            conn.commit()

        bot.send_message(call.message.chat.id, "📣 تم إرسال الأنشطة إلى القناة بنجاح.")
    
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ حدث خطأ أثناء إرسال الإشعار:\n{e}")


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
        c.execute("SELECT id, line, explanation FROM flashcards WHERE lesson_id = ? ORDER BY id LIMIT 1", (lesson_id,))
        card = c.fetchone()
        c.execute("SELECT COUNT(*) FROM flashcards WHERE lesson_id = ?", (lesson_id,))
        total = c.fetchone()[0]

    if card:
        card_id, line, explanation = card
        text = f"📚 بطاقة 1 من {total}\n\n💬 {line}\n\n🧠 {explanation}"

        markup = InlineKeyboardMarkup()
        if total > 1:
            markup.add(InlineKeyboardButton("➡️ التالي", callback_data=f"flash_next_{lesson_id}_{card_id}"))

        bot.send_message(chat_id, text, reply_markup=markup)
    else:
        bot.send_message(chat_id, "❌ لا توجد بطاقات تعليمية لهذا الدرس بعد.")





@bot.callback_query_handler(func=lambda call: call.data.startswith("flash_"))
def handle_flash_navigation(call):
    bot.answer_callback_query(call.id)

    try:
        parts = call.data.split("_")  # مثال: flash_next_123456_4
        direction = parts[1]          # next أو prev
        lesson_id = parts[2]
        current_card_id = int(parts[3])

        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()

            # إجمالي عدد البطاقات
            c.execute("SELECT srt_content, summary FROM lessons WHERE lesson_id = ?", (lesson_id,))
            total = c.fetchone()[0]

            # جميع البطاقات المرتبة بالـ ID
            c.execute("SELECT id, line, explanation FROM flashcards WHERE lesson_id = ? ORDER BY id", (lesson_id,))
            all_ids = [row[0] for row in c.fetchall()]

        # معرفة رقم البطاقة الحالية داخل القائمة
        if current_card_id in all_ids:
            index = all_ids.index(current_card_id)
            if direction == "next" and index < len(all_ids) - 1:
                index += 1
            elif direction == "prev" and index > 0:
                index -= 1
        else:
            index = 0  # fallback في حال لم يجد id

        next_card_id = all_ids[index]

        # جلب بيانات البطاقة الجديدة
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT line, explanation FROM flashcards WHERE id = ?", (next_card_id,))
            row = c.fetchone()

        if row:
            line, explanation = row
            text = f"📚 بطاقة {index + 1} من {total}\n\n💬 {line}\n\n🧠 {explanation}"

            # بناء الأزرار
            markup = InlineKeyboardMarkup()
            if index > 0:
                markup.add(InlineKeyboardButton("⬅️ السابق", callback_data=f"flash_prev_{lesson_id}_{next_card_id}"))
            if index < total - 1:
                markup.add(InlineKeyboardButton("➡️ التالي", callback_data=f"flash_next_{lesson_id}_{next_card_id}"))

            # تعديل نفس الرسالة
            bot.edit_message_text(
                text,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=markup
            )
        else:
            bot.send_message(call.message.chat.id, "❌ لم يتم العثور على هذه البطاقة.")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ حدث خطأ:\n{e}")



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
        
@bot.message_handler(commands=['start'])
def handle_start(message):
    
    args = message.text.split()
    if len(args) > 1:
        param = args[1]
        if param == "index":
            # استدعاء دالة فهرس الفيديو مباشرة
            handle_video_index(message)
            
        if payload.startswith("lesson_"):
            lesson_id = payload.replace("lesson_", "")
            show_flashcards(message.chat.id, lesson_id)
        elif payload.startswith("quiz_"):
            lesson_id = payload.replace("quiz_", "")
            start_quiz(message.chat.id, lesson_id)


        else:
            bot.send_message(message.chat.id, f"مرحبًا بك! لم يتم التعرف على الأمر: {param}")
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
    port = int(os.environ.get('PORT', 10000))  # Render يستخدم 10000
    app.run(host='0.0.0.0', port=port)
