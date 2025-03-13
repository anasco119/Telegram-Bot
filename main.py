# معرف المستخدم الخاص بك (يمكنك معرفته عبر طباعة message.from_user.id في رسالة تجريبية)
allowed_user_id = 123456789  # ضع معرفك هنا

def run_bot():
    @bot.message_handler(func=lambda message: True)
    def chat_with_gemini(message):
        try:
            chat_id = str(message.chat.id)
            message_text = message.text

            # Private chat handling
            if message.chat.type == "private":
                if message.from_user.id == allowed_user_id:
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
                        if response_text.count('\n') <= 5:
                            bot.send_message(message.chat.id, response_text)
                        else:
                            bot.send_message(message.chat.id, "الإجابة طويلة جدًا، يُرجى توضيح السؤال بشكل أدق.")
                    else:
                        bot.send_message(message.chat.id, "Please mention your question or command after my name.")
                elif any(keyword in message_text.lower() for keyword in keywords):
                    response_text = generate_gemini_response(message_text)
                    if response_text.count('\n') <= 5:
                        bot.send_message(message.chat.id, response_text)
                    else:
                        bot.send_message(message.chat.id, "الإجابة طويلة جدًا، يُرجى توضيح السؤال بشكل أدق.")

        except Exception as e:
            bot.send_message(message.chat.id, f"Error: {str(e)}")
