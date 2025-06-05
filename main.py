import os
import logging
import re
import threading
from http.server import SimpleHTTPRequestHandler
from socketserver import TCPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

user_mode = {}
user_states = {}
image_cache = {}  # Temporary store for image file_id

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Standard Quiz", callback_data='standard')],
        [InlineKeyboardButton("Anonymous Quiz", callback_data='anonymous')],
        [InlineKeyboardButton("Lengthy Quiz", callback_data='lengthy')]
    ]
    await update.message.reply_text("Choose a quiz mode:", reply_markup=InlineKeyboardMarkup(keyboard))

# Button handler
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    mode = query.data

    if mode == "lengthy":
        user_states[user_id] = {"step": "question", "anonymous": False}
        await query.edit_message_text("📝 Lengthy Quiz mode ON.\nStep 1: Send your quiz question (text or image with caption).")
        return

    user_mode[user_id] = (mode == "anonymous")
    mode_text = "🟢 Anonymous mode ON." if user_mode[user_id] else "🔵 Standard mode ON."
    await query.edit_message_text(f"{mode_text}\nNow send your question(s). Image with caption supported.")

# Message handler
async def handle_quiz_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    # Lengthy mode flow
    if user_id in user_states:
        state = user_states[user_id]

        if state["step"] == "question":
            if update.message.photo:
                photo = update.message.photo[-1].file_id
                caption = update.message.caption or "Untitled Quiz"
                state.update({"image": photo, "question": caption})
            else:
                state.update({"question": update.message.text.strip(), "image": None})
            state["step"] = "options"
            await update.message.reply_text("✅ Question saved.\nStep 2: Send options (✅ for correct one) and explanation in this format:\n\nOption A\nOption B ✅\nOption C\nOption D\nEx: Your explanation here.")
            return

        elif state["step"] == "options":
            lines = [line.strip("️ ").strip() for line in update.message.text.strip().split("\n") if line.strip()]
            explanation_line = next((line for line in lines if line.startswith("Ex:")), None)

            if not explanation_line:
                await update.message.reply_text("❌ Please include explanation starting with 'Ex:' in the last line.")
                return

            explanation = explanation_line[3:].strip()
            options = []
            correct_idx = None

            for idx, line in enumerate(lines):
                if line.startswith("Ex:"):
                    break
                if "✅" in line:
                    correct_idx = idx
                    line = line.replace("✅", "").strip()
                options.append(line)

            if len(options) < 2 or correct_idx is None:
                await update.message.reply_text("❌ At least 2 options required and one must be marked with ✅.")
                return

            if state.get("image"):
                await context.bot.send_photo(chat_id=update.message.chat_id, photo=state["image"], caption=state["question"])
            await context.bot.send_poll(
                chat_id=update.message.chat_id,
                question=state["question"],
                options=options,
                type="quiz",
                correct_option_id=correct_idx,
                explanation=explanation,
                is_anonymous=state["anonymous"]
            )

            user_states.pop(user_id)
            await update.message.reply_text("🎉 Quiz created successfully.")
            return

    # Inline Standard/Anonymous flow
    is_anonymous = user_mode.get(user_id, False)

    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        caption = update.message.caption or "Untitled Quiz"
        image_cache[user_id] = {"file_id": file_id, "caption": caption}
        await update.message.reply_text("📸 Image quiz received. Now send options (✅) and explanation (Ex:) in text.")
        return

    if user_id in image_cache:
        cache = image_cache.pop(user_id)
        image_id = cache["file_id"]
        question = cache["caption"]
        text = update.message.text.strip()

        if '✅' not in text or 'Ex:' not in text:
            await update.message.reply_text("❌ Format error. Must include ✅ and Ex:")
            return

        lines = [line.strip("️ ").strip() for line in text.strip().split("\n") if line.strip()]
        explanation_line = next((line for line in lines if line.startswith("Ex:")), None)
        if not explanation_line:
            await update.message.reply_text("❌ Missing explanation (Ex:).")
            return

        explanation = explanation_line[3:].strip()
        options = []
        correct_idx = None
        for idx, line in enumerate(lines):
            if line.startswith("Ex:"):
                break
            if "✅" in line:
                correct_idx = idx
                line = line.replace("✅", "").strip()
            options.append(line)

        if correct_idx is None or len(options) < 2:
            await update.message.reply_text("❌ Must include at least 2 options with one ✅ marked.")
            return

        await context.bot.send_photo(chat_id=update.message.chat_id, photo=image_id, caption=question)
        await context.bot.send_poll(
            chat_id=update.message.chat_id,
            question=question,
            options=options,
            type="quiz",
            correct_option_id=correct_idx,
            explanation=explanation,
            is_anonymous=is_anonymous
        )
        return

    # Text-based inline quiz parsing (no image)
    text = update.message.text.strip()
    if not text or '✅' not in text or 'Ex:' not in text:
        return

    quiz_blocks = re.findall(
        r"(.*?(?:\n.*?){4,5})\s*Ex:\s*(.+?)(?=\n(?:\n|.*?Ex:)|$)",
        text.strip(),
        re.DOTALL
    )

    parsed_quizzes = []

    for block, explanation in quiz_blocks:
        lines = [line.strip("️ ").strip() for line in block.strip().split("\n") if line.strip()]
        if len(lines) < 5:
            continue
        question = lines[0]
        options = []
        correct_option_id = None
        for idx, option in enumerate(lines[1:]):
            if "✅" in option:
                correct_option_id = idx
                option = option.replace("✅", "").strip()
            options.append(option)
        if correct_option_id is not None:
            parsed_quizzes.append({
                "question": question,
                "options": options,
                "correct_option_id": correct_option_id,
                "explanation": explanation.strip()
            })

    if not parsed_quizzes:
        await update.message.reply_text("❌ Couldn’t parse any valid quiz. Check ✅ and Ex: format.")
        return

    for quiz in parsed_quizzes:
        await context.bot.send_poll(
            chat_id=update.message.chat_id,
            question=quiz["question"],
            options=quiz["options"],
            type="quiz",
            correct_option_id=quiz["correct_option_id"],
            explanation=quiz["explanation"],
            is_anonymous=is_anonymous
        )

# Dummy server to keep Railway or Koyeb alive
def run_dummy_server():
    PORT = 8000
    Handler = SimpleHTTPRequestHandler
    with TCPServer(("", PORT), Handler) as httpd:
        print(f"Dummy server running on port {PORT}")
        httpd.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()

# Bot startup
def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise ValueError("BOT_TOKEN environment variable not set")
    application = ApplicationBuilder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_quiz_submission))
    print("🤖 Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()
