from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Command: /menu
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("Option 1", callback_data='1'), InlineKeyboardButton("Option 2", callback_data='2')],
        [InlineKeyboardButton("Option 3", callback_data='3'), InlineKeyboardButton("Option 4", callback_data='4')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Please choose an option:",
        reply_markup=reply_markup
    )

# Handle callback queries
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text=f"Selected option: {query.data}")

# Set bot commands
async def set_commands(application: Application) -> None:
    commands = [
        BotCommand("menu", "Start the bot and show the menu"),
        BotCommand("help", "Get help with using the bot"),
    ]
    await application.bot.set_my_commands(commands)

def main() -> None:
    # Replace 'YOUR_TOKEN' with your bot's token
    application = Application.builder().token("7636016028:AAG2ASaWKAjp3bNyyTF1EUpMDpTxVpMzghw").build()

    # Register command handlers
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(CallbackQueryHandler(button))

    # Set custom commands
    application.run_polling()

if __name__ == '__main__':
    main()