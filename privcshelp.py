import logging, json, html, traceback, os, asyncpg
from telegram import (
    ReplyKeyboardRemove,
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ChatMember,
)

from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    Defaults,
)
from ptbcontrib.postgres_persistence import PostgresPersistence

from telegram.constants import ParseMode, ChatAction

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

PROJECT, ORDER = range(2)


groups = []
for i in os.getenv("GROUPS").split(", "):
    groups.append(int(i))

sudo = []
if ", " in os.getenv("SUDO"):
    for i in os.getenv("SUDO").split(", "):
        sudo.append(int(i))
else:
    sudo.append(os.getenv("SUDO"))
logs = -1001520759423
TOKEN = str(os.getenv("TOKEN"))

groups = frozenset(groups)
sudo = frozenset(sudo)


async def custom_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cur = await asyncpg.connect(os.getenv("DATABASE_URL"))
    command = context.args[0]
    if command in ["start", "help", "end", "invite", "personal"]:
        return await update.message.reply_text(
            f"'<code>{command}</code>' can't be used as a custom command because it is one of the internal commands of bot"
        )

    reply = " ".join(context.args[1:])
    result = await cur.fetchrow(
        f"SELECT EXISTS(SELECT 1 FROM adminu WHERE command='{command}' AND chat_id={update.effective_chat.id})"
    )
    if result["exists"] == False:
        await cur.execute(
            f"INSERT INTO adminu(command, reply, chat_id) VALUES ('{command}', '{reply}', {update.effective_chat.id})"
        )
    else:
        await cur.execute(f"UPDATE adminu SET reply='{reply}'")
    await cur.close()
    return await update.message.reply_text("Command set successfully!")


async def checkf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cur = await asyncpg.connect(os.getenv("DATABASE_URL"))
    cmd = update.message.text.split(" ")[0].strip("/")
    result = await cur.fetchrow(
        f"SELECT reply FROM adminu WHERE command='{cmd}' AND chat_id={update.effective_chat.id}"
    )
    if result != None:
        await update.message.reply_text(result["reply"])
    return await cur.close()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_chat_action(ChatAction.TYPING)
    try:
        if context.user_data["status"] == "true":
            return await update.message.reply_text(
                "Hi, you are already discussing a project. At the end of the discussion of the project you can add a new project."
            )
    except:
        return await context.bot.send_message(
            update.effective_chat.id,
            f"Hey {update.effective_user.mention_html()}, Welcome to the official Set it Up bot , to discuss a purchase or enquiry about our services kindly add your project :",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("➕Add project", callback_data="add")]]
            ),
        )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_chat_action(ChatAction.TYPING)

    if update.message.text == "/skip":
        context.user_data["email"] = None
    else:
        context.user_data["email"] = update.message.text
    await update.message.reply_text(
        "Enter the name of your project for which you require the services :",
    )
    return PROJECT


async def project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_chat_action(ChatAction.TYPING)
    context.user_data["project"] = update.message.text
    await update.message.reply_text(
        "And finally If you have already made a purchase on our website , kindly enter your order number, If not you can skip this step by clicking on /skip",
    )
    return ORDER


async def order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_chat_action(ChatAction.TYPING)
    bot = context.bot
    if update.message.text == "/skip":
        context.user_data["order"] = None
    else:
        context.user_data["order"] = update.message.text
    context.user_data["status"] = "true"
    for chat in groups:
        title = (await bot.get_chat(chat)).title
        if "Empty" in title:
            invite_link = (await bot.get_chat(chat)).invite_link
            if invite_link == None:
                invite_link = await bot.create_chat_invite_link(chat, member_limit=1)
            context.bot_data[chat] = update.effective_user.id
            break

    message_to_send = f"Name - {update.effective_user.mention_html()}"
    if context.user_data["project"] != None:
        message_to_send = message_to_send + f"\nProject: {context.user_data['project']}"
    if context.user_data["order"] != None:
        message_to_send = (
            message_to_send + f"\nOrder number: {context.user_data['order']}"
        )
    await context.bot.send_chat_action(chat, ChatAction.TYPING)
    await context.bot.send_message(chat, message_to_send)
    await update.message.reply_text(
        "Project saved!", reply_markup=ReplyKeyboardRemove()
    )
    await update.message.reply_text(
        "Please join this group to discuss the project 👇🏻",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Join the group", url=str(invite_link))]]
        ),
    )
    await context.bot.set_chat_title(chat, f"SetitUp - {context.user_data['project']}")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_chat_action(ChatAction.TYPING)
    await update.message.reply_text(
        "☑️ Operation canceled.\n\n👉🏻 To add a new project press /start",
        reply_markup=ReplyKeyboardRemove(),
    )
    if context.user_data != {}:
        del context.user_data
    return ConversationHandler.END


async def end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_chat_action(ChatAction.TYPING)
    bot = context.bot
    chat = update.effective_chat
    user_chat = context.bot_data[update.effective_chat.id]
    await bot.send_chat_action(chat.id, ChatAction.TYPING)
    if "Empty" in (await bot.get_chat(chat.id)).title:
        return await bot.send_message(chat.id, "The chat is already empty")

    try:
        await bot.unban_chat_member(chat.id, user_chat)
    except:
        pass
    await bot.set_chat_title(chat.id, "SetitUp - Empty")
    try:
        await bot.revoke_chat_invite_link(
            chat.id, (await bot.get_chat(chat.id)).invite_link
        )
    except:
        pass
    await context.bot.send_chat_action(user_chat, ChatAction.TYPING)
    await bot.send_message(
        user_chat,
        "✅ Discussion of the project concluded.\n\n👉🏻 Press /start to add a new project.",
    )
    context.application.user_data[user_chat].clear()
    return await bot.send_message(chat.id, "Project closed.")


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_chat_action(ChatAction.TYPING)
    return await update.message.reply_text("Command not found. Type /start")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    # Log the error before we do anything else, so we can see it even if something breaks.
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

    # traceback.format_exception returns the usual python message about an exception, but as a
    # list of strings rather than a single string, so we have to join them together.
    tb_list = traceback.format_exception(
        None, context.error, context.error.__traceback__
    )
    tb_string = "".join(tb_list)

    # Build the message with some markup and additional information about what happened.
    # You might need to add some logic to deal with messages longer than the 4096 character limit.
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message = (
        f"An exception was raised while handling an update\n"
        f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}"
        "</pre>\n\n"
        f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n"
        f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )

    # Finally, send the message
    await context.bot.send_message(chat_id=logs, text=message)


async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update.message.reply_chat_action(ChatAction.TYPING)
    bot = context.bot
    valid = [ChatMember.ADMINISTRATOR, ChatMember.OWNER]
    if (
        await bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
    ).status in valid:
        try:
            invite_link = (await bot.get_chat(update.effective_user.id)).invite_link
            await bot.revoke_chat_invite_link(update.effective_chat.id, invite_link)
        except:
            new = await bot.create_chat_invite_link(
                update.effective_chat.id, member_limit=1
            )
        await update.message.reply_text(
            f"To invite your partner / associate to the group forward this message with the invite link to them\n{new.invite_link}"
        )

    else:
        await update.message.reply_text("This command is for admins")


def main():
    defaults = Defaults(block=False, parse_mode=ParseMode.HTML)
    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .defaults(defaults)
        .persistence(PostgresPersistence(url=str(os.getenv("DB_URI"))))
        .build()
    )
    start_handler = CommandHandler(["start", "help"], start, filters.ChatType.PRIVATE)
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button)],
        states={
            PROJECT: [
                MessageHandler(filters.TEXT & ~filters.Regex("^❌Cancel"), project)
            ],
            ORDER: [MessageHandler(filters.TEXT & ~filters.Regex("^❌Cancel"), order)],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌Cancel"), cancel)],
        name="my_conversation",
        persistent=True,
    )
    end_handler = CommandHandler("end", end, filters.User(sudo) & filters.Chat(groups))
    unknown_handler = MessageHandler(
        filters.COMMAND
        & ~filters.Command(["start", "help"])
        & filters.ChatType.PRIVATE,
        unknown,
    )
    invite_handler = CommandHandler("invite", invite, filters.Chat(groups))
    newcmd_handler = CommandHandler("personal", custom_command)
    reply_handler = MessageHandler(filters.COMMAND, checkf)

    app.add_handlers(
        [
            start_handler,
            conv_handler,
            end_handler,
            unknown_handler,
            invite_handler,
            newcmd_handler,
            reply_handler,
        ]
    )
    app.add_error_handler(error_handler)
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 8443)),
        url_path=TOKEN,
        webhook_url=f"https://{str(os.getenv('APP'))}.herokuapp.com/" + TOKEN,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
