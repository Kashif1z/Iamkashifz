import logging
import requests
import json
import os
import asyncio
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
)
from telegram.constants import ChatAction
from telegram.error import TelegramError, Forbidden
from google.generativeai.types import HarmCategory, HarmBlockThreshold, FunctionDeclaration, Tool

# --- CONFIGURATION ---
TELEGRAM_BOT_TOKEN = "7742103556:AAGxLjtj-jtZiU1yf-4rhNNmAAKmmVyDygQ"
SMM_PANEL_API_URL = "https://iggrowbot.in/api/v2"
SMM_PANEL_API_KEY = "72571d0fe03a603fe7264ec0baa188d4"
ADMIN_CHAT_ID = "7890197592" # Make sure this is a string
YOUR_UPI_ID = "BHARATPE.8N0C0Z8L1V31797@fbpe"
GEMINI_API_KEY = "AIzaSyAlN_487xIOSTT1v0IWrFBnJAawRzpKxM8"

# --- DATABASE FILE ---
USERS_DB_FILE = "users_database.json"

# --- SERVICES (Updated with Professional Button Names) ---
CATEGORIZED_SERVICES = {
    "❤️ Insta Likes": [
        {"label": "Instagram Likes", "price": "₹3.4", "rate": 3.4, "service_id": "367"},
        {"label": "High Quality Likes", "price": "₹5.9", "rate": 5.9, "service_id": "942"},
    ],
    "✅ Regular Followers": [
        {"label": "Instagram Followers (R365D)", "price": "₹117", "rate": 117.0, "service_id": "364"},
    ],
    "⚡ Fast Followers": [
        {"label": "Real 🇮🇳+🇺🇸 Followers (R60D)", "price": "₹160", "rate": 160.0, "service_id": "970"},
        {"label": "Real 🇮🇳+🇺🇸 Followers (R365D)", "price": "₹170", "rate": 170.0, "service_id": "971"},
    ],
    "👀 Insta Views": [
        {"label": "High Quality 🇮🇳 Views", "price": "₹0.9", "rate": 0.9, "service_id": "983"},
    ],
    "💬 Insta Comments": [
        {"label": "Instagram 🇮🇳 Comments", "price": "₹82", "rate": 82.0, "service_id": "383"},
    ],
}

# --- CONVERSATION STATES ---
(
    SELECT_CATEGORY, SELECT_SERVICE, GET_LINK, GET_QUANTITY,
    GET_ORDER_ID_STATUS,
    GET_FUND_AMOUNT, GET_FUND_UTR,
    AI_SUPPORT_CHAT,
    GET_REFILL_ORDER_ID,
    GET_CUSTOM_MESSAGE,
    # Admin Panel States
    ADMIN_PANEL, ADMIN_GET_USER_ID_FOR_FUND, ADMIN_GET_AMOUNT_FOR_FUND,
    ADMIN_GET_BROADCAST_MESSAGE,
) = range(14)


# --- LOGGING ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)


# --- API HELPER & AI TOOLS ---
def api_request(params):
    payload = {"key": SMM_PANEL_API_KEY, **params}
    try:
        response = requests.post(SMM_PANEL_API_URL, data=payload)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logging.error(f"SMM Panel API Request Failed: {e}")
        return {"error": f"API request failed"}

get_order_status_func = FunctionDeclaration(
    name="get_order_status",
    description="Get the real-time status of a specific order from the SMM panel using its Order ID.",
    parameters={
        "type": "OBJECT",
        "properties": {"order_id": {"type": "STRING", "description": "The unique ID of the order"}},
        "required": ["order_id"]
    },
)

# --- GEMINI AI SETUP ---
GEMINI_ENABLED = False
gemini_model = None
if GEMINI_API_KEY and GEMINI_API_KEY != "PASTE_YOUR_GEMINI_API_KEY_HERE":
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        gemini_model = genai.GenerativeModel(
            model_name='gemini-1.5-flash',
            tools=Tool(function_declarations=[get_order_status_func]),
            system_instruction=(
                "You are a friendly AI support agent for a company named 'InstaFuleBot'. Your name is InstaFuleAI. "
                "You must always reply in Hinglish. Keep your answers very short (1-2 sentences). "
                "If a user asks for an order status, you must use the 'get_order_status' function. "
                "Do not make up information."
            )
        )
        GEMINI_ENABLED = True
        logging.info("Gemini AI successfully initialized.")
    except Exception as e:
        logging.error(f"Gemini AI initialization failed: {e}")
else:
    logging.warning("Gemini API key is not set.")

# --- KEYBOARDS ---
main_menu_keyboard = [
    ["➕ Place Order", "💰 Add Fund"],
    ["💵 My Balance", "🔄 Check Status", "🔄️ Refill"],
    ["🤖 AI Support", "❓ Help"],
    ["❌ Cancel"],
]
main_menu_markup = ReplyKeyboardMarkup(main_menu_keyboard, resize_keyboard=True)

ai_support_keyboard = [["⬅️ Back to Main Menu"]]
ai_support_markup = ReplyKeyboardMarkup(ai_support_keyboard, resize_keyboard=True)

# --- ADMIN PANEL KEYBOARD (NEW) ---
admin_keyboard = [
    ["📊 Total Users", "💸 Add/Remove Fund"],
    ["📢 Broadcast Message"],
    ["⬅️ Exit Admin Panel"]
]
admin_markup = ReplyKeyboardMarkup(admin_keyboard, resize_keyboard=True)


# --- USER DATABASE FUNCTIONS ---
def load_users():
    if not os.path.exists(USERS_DB_FILE): return {}
    with open(USERS_DB_FILE, 'r') as f: return json.load(f)
def save_users(users_data):
    with open(USERS_DB_FILE, 'w') as f: json.dump(users_data, f, indent=4)
def get_user_balance(user_id):
    return load_users().get(str(user_id), {}).get("balance", 0.0)

# --- GENERAL HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user; user_id = str(user.id)
    users = load_users()
    if user_id not in users:
        users[user_id] = {"username": user.username or user.first_name, "balance": 0.0}
        save_users(users)
        logging.info(f"New user {user.first_name} ({user_id}) registered.")
    await update.message.reply_text(f"👋 **Welcome, {user.first_name}!**", parse_mode="Markdown", reply_markup=main_menu_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "**Help & Support**\n\n"
        "• **➕ Place Order:** Choose a category, then a service to place an order.\n"
        "• **💰 Add Fund:** Add funds to your wallet.\n"
        "• **💵 My Balance:** Check your current balance.\n"
        "• **🔄 Check Status:** Get real-time status of your order.\n"
        "• **🔄️ Refill:** Request a refill for a previous order.\n"
        "• **🤖 AI Support:** Get instant help from our AI assistant.\n"
        "• **❌ Cancel:** To stop any ongoing process."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown", reply_markup=main_menu_markup)
async def my_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    balance = get_user_balance(update.effective_user.id)
    await update.message.reply_text(f"💵 Your current wallet balance is: **₹{balance:.2f}**", parse_mode="Markdown")
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("Process has been cancelled.", reply_markup=main_menu_markup)
    return ConversationHandler.END

# --- ADMIN PANEL FLOW (NEW) ---
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the admin panel flow, restricted to ADMIN_CHAT_ID."""
    if str(update.effective_user.id) != ADMIN_CHAT_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        return ConversationHandler.END
    await update.message.reply_text("Welcome to the Admin Panel.", reply_markup=admin_markup)
    return ADMIN_PANEL

async def admin_total_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Displays the total number of users."""
    users = load_users()
    await update.message.reply_text(f"📊 Total registered users: {len(users)}")
    return ADMIN_PANEL

async def admin_ask_user_id_for_fund(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Asks for the user ID to add/remove funds."""
    await update.message.reply_text("Please enter the User's Telegram ID.", reply_markup=ReplyKeyboardRemove())
    return ADMIN_GET_USER_ID_FOR_FUND

async def admin_get_user_id_and_ask_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores user ID and asks for the amount."""
    user_id = update.message.text
    if not user_id.isdigit():
        await update.message.reply_text("Invalid User ID. Please enter a numeric ID.", reply_markup=admin_markup)
        return ADMIN_PANEL
    context.user_data['fund_target_user_id'] = user_id
    await update.message.reply_text("Enter the amount to add or remove.\n(Use a negative sign for removal, e.g., -50)")
    return ADMIN_GET_AMOUNT_FOR_FUND

async def admin_update_user_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Updates the user's balance."""
    try:
        amount = float(update.message.text)
    except ValueError:
        await update.message.reply_text("Invalid amount. Please enter a number.", reply_markup=admin_markup)
        return ADMIN_PANEL

    user_id = context.user_data.get('fund_target_user_id')
    users = load_users()

    if user_id not in users:
        await update.message.reply_text(f"User with ID {user_id} not found in the database.", reply_markup=admin_markup)
        return ADMIN_PANEL

    users[user_id]["balance"] += amount
    save_users(users)
    
    action = "added" if amount >= 0 else "removed"
    notification_message = f"An amount of ₹{abs(amount):.2f} has been {action} to your wallet by the admin."

    try:
        await context.bot.send_message(chat_id=user_id, text=notification_message)
        await update.message.reply_text(f"✅ Success! ₹{amount:.2f} processed for user {user_id}. They have been notified.", reply_markup=admin_markup)
    except Forbidden:
        await update.message.reply_text(f"✅ Success! ₹{amount:.2f} processed for user {user_id}, but could not notify them (they may have blocked the bot).", reply_markup=admin_markup)
    except Exception as e:
        logging.error(f"Failed to notify user {user_id} about fund update: {e}")
        await update.message.reply_text(f"✅ Balance updated for user {user_id}, but failed to send notification.", reply_markup=admin_markup)
        
    context.user_data.clear()
    return ADMIN_PANEL

async def admin_ask_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Asks for the broadcast message."""
    await update.message.reply_text("Please enter the message you want to broadcast to all users.", reply_markup=ReplyKeyboardRemove())
    return ADMIN_GET_BROADCAST_MESSAGE

async def admin_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Sends a message to all registered users."""
    message_text = update.message.text
    users = load_users()
    await update.message.reply_text(f"Starting broadcast to {len(users)} users. This may take a while...", reply_markup=admin_markup)

    success_count = 0
    failed_count = 0

    for user_id in users:
        try:
            await context.bot.send_message(chat_id=user_id, text=message_text, parse_mode="Markdown")
            success_count += 1
        except Forbidden:
            logging.warning(f"Broadcast failed for user {user_id}: Bot is blocked.")
            failed_count += 1
        except Exception as e:
            logging.error(f"Broadcast failed for user {user_id}: {e}")
            failed_count += 1
        await asyncio.sleep(0.1) # Avoid hitting API rate limits

    await update.message.reply_text(
        f"📢 **Broadcast Complete!**\n\n"
        f"✅ Sent successfully: {success_count}\n"
        f"❌ Failed (e.g., blocked bot): {failed_count}",
        parse_mode="Markdown"
    )
    return ADMIN_PANEL


async def exit_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Exits the admin panel and returns to the main menu."""
    await update.message.reply_text("Exiting Admin Panel...", reply_markup=main_menu_markup)
    return ConversationHandler.END


# --- ORDER FLOW ---
async def order_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    categories = list(CATEGORIZED_SERVICES.keys())
    keyboard = [categories[i:i + 2] for i in range(0, len(categories), 2)]
    keyboard.append(["⬅️ Back to Main Menu"])
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("Please select a category from the buttons below:", reply_markup=reply_markup)
    return SELECT_CATEGORY

async def select_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    category_name = update.message.text
    if category_name not in CATEGORIZED_SERVICES:
        await update.message.reply_text("Invalid category. Please use the buttons.", reply_markup=main_menu_markup)
        return ConversationHandler.END
    context.user_data['selected_category'] = category_name
    services = CATEGORIZED_SERVICES[category_name]
    keyboard = []
    for service in services:
        button_text = f"{service['label']} ({service['price']})"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"svc_{service['service_id']}")])
    keyboard.append([InlineKeyboardButton("⬅️ Back to Categories", callback_data="back_to_cat")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text=f"You selected: **{category_name}**\n\nPlease choose a service:", reply_markup=reply_markup, parse_mode="Markdown")
    return SELECT_SERVICE

async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Returning to the main menu...", reply_markup=main_menu_markup)
    context.user_data.clear()
    return ConversationHandler.END

async def select_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    if query.data == "back_to_cat":
        categories = list(CATEGORIZED_SERVICES.keys())
        keyboard = [categories[i:i + 2] for i in range(0, len(categories), 2)]
        keyboard.append(["⬅️ Back to Main Menu"])
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Please select a category again:", reply_markup=reply_markup)
        await query.message.delete()
        return SELECT_CATEGORY
    service_id = query.data.split('svc_')[1]
    category_name = context.user_data.get('selected_category')
    if not category_name:
        await query.edit_message_text("An error occurred. Please start over.", reply_markup=main_menu_markup)
        return ConversationHandler.END
    service_details = next((s for s in CATEGORIZED_SERVICES[category_name] if s['service_id'] == service_id), None)
    if not service_details:
        await query.edit_message_text("Error: Service not found.", reply_markup=main_menu_markup)
        return ConversationHandler.END
    context.user_data.update({'service_id': service_id, 'rate': service_details['rate'], 'label': service_details['label']})
    await query.edit_message_text(f"You've selected: **{service_details['label']}**\n\nPlease enter the **Link** for your order.", parse_mode="Markdown")
    return GET_LINK

async def get_link_and_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["link"] = update.message.text
    await update.message.reply_text("Great! Now, please enter the **Quantity**.", parse_mode="Markdown")
    return GET_QUANTITY

async def place_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try: quantity = int(update.message.text)
    except ValueError:
        await update.message.reply_text("Invalid quantity. Please enter a number.")
        return GET_QUANTITY
    user_id_str = str(update.effective_user.id)
    cost = (context.user_data['rate'] / 1000) * quantity
    if get_user_balance(user_id_str) < cost:
        await update.message.reply_text(f"Insufficient Balance! Order requires ₹{cost:.2f}, but you have ₹{get_user_balance(user_id_str):.2f}.", reply_markup=main_menu_markup)
        return ConversationHandler.END
    await update.message.reply_text("Processing your order...")
    order_params = {"action": "add", "service": context.user_data['service_id'], "link": context.user_data['link'], "quantity": quantity}
    response_data = api_request(order_params)
    if response_data and "order" in response_data:
        users = load_users(); users[user_id_str]["balance"] -= cost; save_users(users)
        await update.message.reply_text(f"✅ **Order Placed!**\nOrder ID: `{response_data['order']}`\n₹{cost:.2f} deducted.", parse_mode="Markdown", reply_markup=main_menu_markup)
    else:
        await update.message.reply_text(f"❌ **Order Failed!**\nReason: {response_data.get('error', 'Unknown error')}", reply_markup=main_menu_markup)
    context.user_data.clear()
    return ConversationHandler.END

# --- REFILL FLOW ---
async def refill_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Please enter the **Order ID** you want to request a refill for.", parse_mode="Markdown")
    return GET_REFILL_ORDER_ID

async def get_refill_order_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    order_id = update.message.text
    if not order_id.isdigit():
        await update.message.reply_text("Invalid Order ID. Please enter only numbers.")
        return GET_REFILL_ORDER_ID

    user = update.effective_user
    text_to_admin = (
        f"**🔄️ New Refill Request**\n\n"
        f"**User:** {user.first_name} (@{user.username or 'N/A'})\n"
        f"**User ID:** `{user.id}`\n"
        f"**Order ID for Refill:** `{order_id}`"
    )
    keyboard = [
        [InlineKeyboardButton("✅ Added for Refill", callback_data=f"refill_added_{user.id}_{order_id}")],
        [InlineKeyboardButton("❌ Refill Failed", callback_data=f"refill_failed_{user.id}_{order_id}")],
        [InlineKeyboardButton("✍️ Send Custom Message", callback_data=f"refill_custom_{user.id}_{order_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=text_to_admin, parse_mode="Markdown", reply_markup=reply_markup)
        await update.message.reply_text("✅ Your refill request has been sent to the admin for review.", reply_markup=main_menu_markup)
    except Exception as e:
        logging.error(f"Failed to send refill request to admin: {e}")
        await update.message.reply_text("❌ Sorry, could not process your request. Please try again later.", reply_markup=main_menu_markup)

    return ConversationHandler.END

async def handle_refill_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    data = query.data.split("_")
    action_type = data[1]
    user_id = data[2]
    order_id = data[3]
    
    original_text = query.message.text
    
    if action_type == "added":
        message_to_user = f"✅ Good news! Your refill request for Order ID `{order_id}` has been accepted. It will be processed within 24 hours."
        try:
            await context.bot.send_message(chat_id=user_id, text=message_to_user, parse_mode="Markdown")
            await query.edit_message_text(text=f"{original_text}\n\n---\n**Action Taken: Refill Added ✅**\nUser has been notified.")
        except Exception as e:
            logging.error(f"Failed to send 'refill_added' message to user {user_id}: {e}")
            await query.edit_message_text(text=f"{original_text}\n\n---\n**Action Failed:** Could not send message to user.")

    elif action_type == "failed":
        message_to_user = f"❌ Unfortunately, your refill request for Order ID `{order_id}` has failed. Please contact support for more details."
        try:
            await context.bot.send_message(chat_id=user_id, text=message_to_user, parse_mode="Markdown")
            await query.edit_message_text(text=f"{original_text}\n\n---\n**Action Taken: Refill Failed ❌**\nUser has been notified.")
        except Exception as e:
            logging.error(f"Failed to send 'refill_failed' message to user {user_id}: {e}")
            await query.edit_message_text(text=f"{original_text}\n\n---\n**Action Failed:** Could not send message to user.")
            
async def ask_for_custom_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    data = query.data.split("_")
    user_id = data[2]
    order_id = data[3]
    
    context.user_data['custom_msg_user_id'] = user_id
    context.user_data['custom_msg_order_id'] = order_id
    
    await query.message.reply_text(f"✍️ Please send the message you want to forward to user `{user_id}` regarding order `{order_id}`.")
    return GET_CUSTOM_MESSAGE

async def send_custom_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    admin_message = update.message.text
    user_id = context.user_data.get('custom_msg_user_id')
    
    if not user_id:
        await update.message.reply_text("Error: Could not find user to send the message to. Please start again.")
        return ConversationHandler.END
        
    try:
        await context.bot.send_message(chat_id=user_id, text=f"**Message from Admin:**\n\n{admin_message}", parse_mode="Markdown")
        await update.message.reply_text("✅ Message sent successfully to the user.")
    except Exception as e:
        logging.error(f"Failed to send custom message to user {user_id}: {e}")
        await update.message.reply_text("❌ Failed to send message. The user might have blocked the bot.")

    context.user_data.clear()
    return ConversationHandler.END

# --- ADD FUND & OTHER FLOWS ---
async def add_fund_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("✨ **Enter the amount you wish to add.**", parse_mode="Markdown")
    return GET_FUND_AMOUNT
async def get_fund_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        amount = float(update.message.text)
        if amount <= 1: raise ValueError
        context.user_data['fund_amount'] = amount
        caption = (f"To add **₹{amount:.2f}**, pay to UPI ID below.\n\n`{YOUR_UPI_ID}`\n\n"
                   "After payment, enter the **Transaction ID (UTR)** here.")
        await update.message.reply_text(text=caption, parse_mode="Markdown")
        return GET_FUND_UTR
    except ValueError:
        await update.message.reply_text("Invalid amount. Please enter a number > 1.")
        return GET_FUND_AMOUNT
async def get_fund_utr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    utr = update.message.text
    if not (utr.isdigit() and 10 <= len(utr) <= 18):
        await update.message.reply_text("Invalid UTR. Please enter a valid 10-18 digit Transaction ID.")
        return GET_FUND_UTR
    amount = context.user_data['fund_amount']; user = update.effective_user
    text_to_admin = (f"**✨ New Fund Request**\n**User:** {user.first_name} (@{user.username})\n"
                     f"**User ID:** `{user.id}`\n**Amount:** `₹{amount:.2f}`\n**UTR:** `{utr}`")
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user.id}_{amount}"),
                                     InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user.id}_{amount}") ]])
    await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=text_to_admin, reply_markup=keyboard, parse_mode="Markdown")
    await update.message.reply_text("✅ **Thank you!** Your request is sent for verification.", reply_markup=main_menu_markup)
    context.user_data.clear(); return ConversationHandler.END
async def handle_fund_approval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query; await query.answer()
    data = query.data.split('_'); action, user_id, amount = data[0], data[1], float(data[2])
    users = load_users()
    if user_id in users:
        if action == "approve":
            users[user_id]["balance"] += amount; save_users(users)
            await query.edit_message_text(f"✅ Approved! ₹{amount:.2f} added to User {user_id}.")
            await context.bot.send_message(chat_id=user_id, text=f"🎉 Your fund request of ₹{amount:.2f} has been approved.")
        else:
            await query.edit_message_text(f"❌ Rejected request for user {user_id}.")
            await context.bot.send_message(chat_id=user_id, text=f"😔 Sorry, your fund request of ₹{amount:.2f} has been rejected.")
    else:
        await query.edit_message_text(f"Error: User {user_id} not found in database.")

async def status_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Please enter the **Order ID**.", parse_mode="Markdown")
    return GET_ORDER_ID_STATUS
async def get_order_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message.text.isdigit():
        await update.message.reply_text("Invalid Order ID format.")
        return GET_ORDER_ID_STATUS
    order_id = update.message.text
    await update.message.reply_text(f"Fetching status for Order ID {order_id}...")
    response_data = api_request({"action": "status", "order": order_id})
    if response_data and "status" in response_data:
        await update.message.reply_text(f"Status for `{order_id}`: **{response_data.get('status')}**", parse_mode="Markdown", reply_markup=main_menu_markup)
    else:
        await update.message.reply_text(f"Could not find status for Order ID: `{order_id}`.", reply_markup=main_menu_markup, parse_mode="Markdown")
    return ConversationHandler.END
    
async def ai_support_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not GEMINI_ENABLED:
        await update.message.reply_text("Maaf kijiye, AI Support abhi uplabdh nahi hai.", reply_markup=main_menu_markup)
        return ConversationHandler.END
    context.user_data['chat'] = gemini_model.start_chat()
    await update.message.reply_text("🤖 **AI Support mein aapka swagat hai!**", reply_markup=ai_support_markup)
    return AI_SUPPORT_CHAT
async def handle_ai_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    user_message = update.message.text
    chat = context.user_data.get('chat')
    if not chat: chat = gemini_model.start_chat(); context.user_data['chat'] = chat
    try:
        response = chat.send_message(user_message)
        model_response_part = response.candidates[0].content.parts[0]
        if hasattr(model_response_part, 'function_call') and model_response_part.function_call.name:
            function_call = model_response_part.function_call
            if function_call.name == "get_order_status":
                order_id = function_call.args.get("order_id")
                logging.info(f"AI requested 'get_order_status' for ID: {order_id}")
                status_data = api_request({"action": "status", "order": order_id})
                response_to_ai = chat.send_message([{"function_response": {"name": "get_order_status", "response": status_data}}])
                await update.message.reply_text(response_to_ai.text, reply_markup=ai_support_markup)
        else:
            await update.message.reply_text(response.text, reply_markup=ai_support_markup)
    except Exception as e:
        print(f"🔴🔴🔴 AI CHAT ERROR: {e} 🔴🔴🔴")
        logging.error(f"AI Chat failed: {e}")
        await update.message.reply_text("Maaf kijiye, kuch takniki samasya aa gayi hai.", reply_markup=ai_support_markup)
    return AI_SUPPORT_CHAT
async def ai_support_end(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("Mukhya menu par wapas ja rahe hain...", reply_markup=main_menu_markup)
    return ConversationHandler.END

# --- MAIN APP SETUP ---
def main() -> None:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    input_filter = filters.TEXT & ~filters.COMMAND & ~filters.Regex("^❌ Cancel$") & ~filters.Regex("^⬅️ Back to Main Menu$")
    universal_fallbacks = [
        CommandHandler("cancel", cancel), 
        MessageHandler(filters.Regex("^❌ Cancel$"), cancel)
    ]

    order_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ Place Order$"), order_start)],
        states={
            SELECT_CATEGORY: [MessageHandler(filters.TEXT & ~filters.Regex("^⬅️ Back to Main Menu$"), select_category)],
            SELECT_SERVICE: [CallbackQueryHandler(select_service)],
            GET_LINK: [MessageHandler(input_filter, get_link_and_quantity)],
            GET_QUANTITY: [MessageHandler(input_filter, place_order)],
        }, 
        fallbacks=[MessageHandler(filters.Regex("^⬅️ Back to Main Menu$"), back_to_main_menu)] + universal_fallbacks,
        map_to_parent={ ConversationHandler.END: ConversationHandler.END }
    )
    fund_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^💰 Add Fund$"), add_fund_start)],
        states={
            GET_FUND_AMOUNT: [MessageHandler(input_filter, get_fund_amount)],
            GET_FUND_UTR: [MessageHandler(input_filter, get_fund_utr)],
        }, fallbacks=universal_fallbacks
    )
    status_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔄 Check Status$"), status_start)],
        states={GET_ORDER_ID_STATUS: [MessageHandler(input_filter, get_order_status)]},
        fallbacks=universal_fallbacks
    )
    ai_support_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🤖 AI Support$"), ai_support_start)],
        states={
            AI_SUPPORT_CHAT: [MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex("^⬅️ Back to Main Menu$"), handle_ai_chat)],
        },
        fallbacks=[MessageHandler(filters.Regex("^⬅️ Back to Main Menu$"), ai_support_end)] + universal_fallbacks
    )
    refill_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^🔄️ Refill$"), refill_start)],
        states={
            GET_REFILL_ORDER_ID: [MessageHandler(input_filter, get_refill_order_id)],
        },
        fallbacks=universal_fallbacks
    )
    admin_custom_msg_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(ask_for_custom_message, pattern="^refill_custom_")],
        states={
            GET_CUSTOM_MESSAGE: [MessageHandler(input_filter, send_custom_message)]
        },
        fallbacks=universal_fallbacks
    )
    
    # --- ADMIN CONVERSATION HANDLER (NEW) ---
    admin_conv = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_command)],
        states={
            ADMIN_PANEL: [
                MessageHandler(filters.Regex("^📊 Total Users$"), admin_total_users),
                MessageHandler(filters.Regex("^💸 Add/Remove Fund$"), admin_ask_user_id_for_fund),
                MessageHandler(filters.Regex("^📢 Broadcast Message$"), admin_ask_broadcast_message),
                MessageHandler(filters.Regex("^⬅️ Exit Admin Panel$"), exit_admin_panel),
            ],
            ADMIN_GET_USER_ID_FOR_FUND: [MessageHandler(input_filter, admin_get_user_id_and_ask_amount)],
            ADMIN_GET_AMOUNT_FOR_FUND: [MessageHandler(input_filter, admin_update_user_balance)],
            ADMIN_GET_BROADCAST_MESSAGE: [MessageHandler(input_filter, admin_broadcast_message)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Add all handlers to the application
    application.add_handler(admin_conv) # Add admin handler first
    application.add_handler(order_conv)
    application.add_handler(fund_conv)
    application.add_handler(status_conv)
    application.add_handler(ai_support_conv)
    application.add_handler(refill_conv)
    application.add_handler(admin_custom_msg_conv)
    
    # Regular command and message handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Regex("^❓ Help$"), help_command))
    application.add_handler(MessageHandler(filters.Regex("^💵 My Balance$"), my_balance))
    
    # Callback query handlers for approvals
    application.add_handler(CallbackQueryHandler(handle_fund_approval, pattern="^(approve_|reject_)"))
    application.add_handler(CallbackQueryHandler(handle_refill_action, pattern="^(refill_added_|refill_failed_)"))


    print("Bot with Interactive Admin Panel is running...")
    application.run_polling()

if __name__ == "__main__":
    main()