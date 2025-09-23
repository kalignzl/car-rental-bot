import os, re, logging
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv
from telegram import (
    Update, ReplyKeyboardMarkup, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto,
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ConversationHandler,
    ContextTypes, CallbackQueryHandler, filters
)

# ---------------- Setup & Logging ----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("rental-bot")
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "0") or "0")

# ---------------- Data model ----------------
@dataclass
class Listing:
    name: str = ""
    category: str = ""
    price_per_day: float = 0.0
    photo1_id: Optional[str] = None
    photo2_id: Optional[str] = None

CATEGORIES = ["Exotic", "Economic", "Luxury"]
CAT_KB = ReplyKeyboardMarkup(
    [["Exotic", "Economic", "Luxury"]],
    one_time_keyboard=True,
    resize_keyboard=True
)

# Conversation states
NAME, CATEGORY, PRICE, PHOTO1, PHOTO2, REVIEW, EDIT_NAME, EDIT_PRICE, EDIT_CAT, EDIT_P1, EDIT_P2 = range(11)

# ---------------- Helpers ----------------
def clean_price(text: str) -> Optional[float]:
    cleaned = re.sub(r"[^\d.]", "", text or "")
    if cleaned.count(".") > 1 or cleaned == "":
        return None
    try:
        val = float(cleaned)
        return val if val >= 0 else None
    except Exception:
        return None

def format_preview(lst: Listing) -> str:
    p1 = "✅ set" if lst.photo1_id else "❌ missing"
    p2 = "✅ set" if lst.photo2_id else "❌ missing"
    return (
        "*Car Rental Listing*\n"
        f"*Name:* {lst.name or '—'}\n"
        f"*Category:* {lst.category or '—'}\n"
        f"*Price/Day:* {'$'+format(lst.price_per_day, ',.2f') if lst.price_per_day else '—'}\n"
        f"*Photo #1:* {p1}\n"
        f"*Photo #2:* {p2}\n\n"
        "Use the buttons below to edit or submit."
    )

def review_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Replace Name", callback_data="edit_name"),
         InlineKeyboardButton("🗂 Change Category", callback_data="edit_cat")],
        [InlineKeyboardButton("💲 Change Price", callback_data="edit_price")],
        [InlineKeyboardButton("🖼 Replace Photo 1", callback_data="edit_p1"),
         InlineKeyboardButton("🖼 Replace Photo 2", callback_data="edit_p2")],
        [InlineKeyboardButton("✅ Submit", callback_data="submit"),
         InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ])

async def send_preview(chat_id: int, context: ContextTypes.DEFAULT_TYPE, lst: Listing):
    await context.bot.send_message(
        chat_id=chat_id,
        text=format_preview(lst),
        parse_mode="Markdown",
        reply_markup=review_keyboard()
    )

# ---------------- Flow ----------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["listing"] = Listing()
    await update.message.reply_text(
        "Hi! Let’s add a car rental listing.\n\n"
        "Send the *Vehicle Name* (e.g., 'BMW M4 Competition').",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return NAME

async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lst: Listing = context.user_data["listing"]
    lst.name = (update.message.text or "").strip()
    await update.message.reply_text(
        "Choose a *Category*:",
        parse_mode="Markdown",
        reply_markup=CAT_KB
    )
    return CATEGORY

async def handle_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lst: Listing = context.user_data["listing"]
    choice = (update.message.text or "").strip().title()
    if choice not in CATEGORIES:
        await update.message.reply_text(
            "Please choose: Exotic, Economic, or Luxury.",
            reply_markup=CAT_KB
        )
        return CATEGORY
    lst.category = choice
    await update.message.reply_text(
        "Enter the *Price per day* (e.g., 149.99):",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )
    return PRICE

async def handle_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lst: Listing = context.user_data["listing"]
    price = clean_price(update.message.text or "")
    if price is None:
        await update.message.reply_text("Please send a valid number (e.g., 149.99).")
        return PRICE
    lst.price_per_day = price
    await update.message.reply_text(
        "Send *Photo #1* as a Photo (not as a file).",
        parse_mode="Markdown"
    )
    return PHOTO1

async def handle_photo1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lst: Listing = context.user_data["listing"]
    if not update.message.photo:
        await update.message.reply_text("Please send a *photo* (not a document).", parse_mode="Markdown")
        return PHOTO1
    lst.photo1_id = update.message.photo[-1].file_id
    await update.message.reply_text("Great! Now send *Photo #2*.", parse_mode="Markdown")
    return PHOTO2

async def handle_photo2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lst: Listing = context.user_data["listing"]
    if not update.message.photo:
        await update.message.reply_text("Please send a *photo* (not a document).", parse_mode="Markdown")
        return PHOTO2
    lst.photo2_id = update.message.photo[-1].file_id
    await send_preview(update.effective_chat.id, context, lst)
    return REVIEW

# ---------------- Review actions (edit / submit / cancel) ----------------
async def review_actions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    data = q.data
    lst: Listing = context.user_data.get("listing")

    if not lst:
        await q.edit_message_text("No active listing. Use /start to begin.")
        return ConversationHandler.END

    if data == "edit_name":
        await q.message.reply_text("Send the new *Vehicle Name*:", parse_mode="Markdown")
        return EDIT_NAME

    if data == "edit_cat":
        await q.message.reply_text("Choose the new *Category*:", parse_mode="Markdown", reply_markup=CAT_KB)
        return EDIT_CAT

    if data == "edit_price":
        await q.message.reply_text("Send the new *Price per day* (e.g., 159.99):", parse_mode="Markdown")
        return EDIT_PRICE

    if data == "edit_p1":
        await q.message.reply_text("Send the new *Photo #1*.", parse_mode="Markdown")
        return EDIT_P1

    if data == "edit_p2":
        await q.message.reply_text("Send the new *Photo #2*.", parse_mode="Markdown")
        return EDIT_P2

    if data == "submit":
        # Validate required fields
        if not (lst.name and lst.category and lst.price_per_day and lst.photo1_id and lst.photo2_id):
            await q.message.reply_text("Listing is incomplete. Please fill all fields and set both photos.")
            await send_preview(update.effective_chat.id, context, lst)
            return REVIEW

        # Send to Admin
        header = f"📩 *Submitted by:* @{update.effective_user.username or 'unknown'} (id: {update.effective_user.id})"
        summary = (
            f"*Name:* {lst.name}\n"
            f"*Category:* {lst.category}\n"
            f"*Price/Day:* ${lst.price_per_day:,.2f}"
        )
        try:
            if ADMIN_CHAT_ID == 0:
                await q.message.reply_text("Admin chat not set yet. Send /id to the bot and put that number into ADMIN_CHAT_ID in your .env, then restart.")
                return REVIEW
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=header, parse_mode="Markdown")
            await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=summary, parse_mode="Markdown")
            media = [InputMediaPhoto(lst.photo1_id), InputMediaPhoto(lst.photo2_id)]
            await context.bot.send_media_group(chat_id=ADMIN_CHAT_ID, media=media)
        except Exception as e:
            log.exception("Failed to deliver to admin")
            await q.message.reply_text("Sorry, I couldn’t deliver this to the admin. Try again later.")
            return ConversationHandler.END

        await q.message.reply_text("✅ Submitted! Thanks—your listing was sent to the admin.")
        context.user_data.clear()
        return ConversationHandler.END

    if data == "cancel":
        context.user_data.clear()
        await q.message.reply_text("❌ Cancelled. Use /start to begin again.")
        return ConversationHandler.END

    return REVIEW

# ---------------- Edit handlers (return to REVIEW) ----------------
async def edit_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lst: Listing = context.user_data["listing"]
    lst.name = (update.message.text or "").strip()
    await send_preview(update.effective_chat.id, context, lst)
    return REVIEW

async def edit_cat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lst: Listing = context.user_data["listing"]
    choice = (update.message.text or "").strip().title()
    if choice not in CATEGORIES:
        await update.message.reply_text("Please choose: Exotic, Economic, or Luxury.", reply_markup=CAT_KB)
        return EDIT_CAT
    lst.category = choice
    await send_preview(update.effective_chat.id, context, lst)
    return REVIEW

async def edit_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lst: Listing = context.user_data["listing"]
    price = clean_price(update.message.text or "")
    if price is None:
        await update.message.reply_text("Please send a valid number (e.g., 149.99).")
        return EDIT_PRICE
    lst.price_per_day = price
    await send_preview(update.effective_chat.id, context, lst)
    return REVIEW

async def edit_p1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lst: Listing = context.user_data["listing"]
    if not update.message.photo:
        await update.message.reply_text("Please send a *photo*.", parse_mode="Markdown")
        return EDIT_P1
    lst.photo1_id = update.message.photo[-1].file_id
    await send_preview(update.effective_chat.id, context, lst)
    return REVIEW

async def edit_p2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lst: Listing = context.user_data["listing"]
    if not update.message.photo:
        await update.message.reply_text("Please send a *photo*.", parse_mode="Markdown")
        return EDIT_P2
    lst.photo2_id = update.message.photo[-1].file_id
    await send_preview(update.effective_chat.id, context, lst)
    return REVIEW

# ---------------- Utility commands ----------------
async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelled. Use /start to begin again.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Your chat ID is: `{update.effective_chat.id}`", parse_mode="Markdown")

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Commands:\n"
        "/start – begin a new listing\n"
        "/cancel – cancel the process\n"
        "/id – show your chat id\n"
        "/help – this message"
    )

# ---------------- Main ----------------
def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing. Set it in .env")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            NAME:     [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name)],
            CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_category)],
            PRICE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_price)],
            PHOTO1:   [MessageHandler(filters.PHOTO, handle_photo1)],
            PHOTO2:   [MessageHandler(filters.PHOTO, handle_photo2)],
            REVIEW:   [CallbackQueryHandler(review_actions)],
            EDIT_NAME:[MessageHandler(filters.TEXT & ~filters.COMMAND, edit_name)],
            EDIT_CAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_cat)],
            EDIT_PRICE:[MessageHandler(filters.TEXT & ~filters.COMMAND, edit_price)],
            EDIT_P1:  [MessageHandler(filters.PHOTO, edit_p1)],
            EDIT_P2:  [MessageHandler(filters.PHOTO, edit_p2)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("id", cmd_id))
    app.add_handler(CommandHandler("help", cmd_help))

    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
