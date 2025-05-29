import os
import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Dictionary to track user modes
user_mode = {}

# /start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Standard Quiz", callback_data='standard')],
        [InlineKeyboardButton("Anonymous Quiz", callback_data='anonymous')],
    ]
    await update.message.reply_text("Choose a quiz mode:", reply_markup=InlineKeyboardMarkup(keyboard))

# Callback query handler for mode selection
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_mode[user_id] = query.data == "anonymous"
    mode_text = "🟢 Anonymous mode ON." if user_mode[user_id] else "🔵 Standard mode ON."
    await query.edit_message_text(f"{mode_text}\nNow send your question(s).")

# Message handler to process quiz submissions
async def handle_quiz_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    is_anonymous = user_mode.get(user_id, False)
    text = update.message.text

    if not text or '✅' not in text or 'Ex:' not in text:
        return

    # Regular expression to extract quiz blocks
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

    # Send each parsed quiz as a separate poll and save to quizzes_log.txt
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

        # Save quiz to quizzes_log.txt
        with open("quizzes_log.txt", "a", encoding="utf-8") as f:
            f.write(f"Q: {quiz['question']}\n")
            for idx, option in enumerate(quiz["options"]):
                prefix = "✅ " if idx == quiz["correct_option_id"] else "   "
                f.write(f"{prefix}{option}\n")
            f.write(f"💡 Explanation: {quiz['explanation']}\n")
            f.write(f"📘 Mode: {'Anonymous' if is_anonymous else 'Standard'}\n")
            f.write(f"👤 User: @{update.message.from_user.username or 'unknown'}\n")
            f.write("-" * 50 + "\n")

# Main function to start the bot
def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise ValueError("BOT_TOKEN environment variable not set")

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_quiz_submission))

    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
import threading
from http.server import SimpleHTTPRequestHandler
from socketserver import TCPServer

def run_dummy_server():
    PORT = 8000
    Handler = SimpleHTTPRequestHandler
    with TCPServer(("", PORT), Handler) as httpd:
        print(f"Dummy server running on port {PORT}")
        httpd.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()
