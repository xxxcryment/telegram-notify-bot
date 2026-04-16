import os
import asyncio
import logging
import httpx
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import Response, PlainTextResponse
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))
PORT = int(os.getenv("PORT", 8000))
CENTRAL_WEBHOOK_URL = os.environ.get("CENTRAL_WEBHOOK_URL")  # НОВАЯ ПЕРЕМЕННАЯ

if not TOKEN:
    logger.error("❌ BOT_TOKEN не установлен")
    exit(1)

if not CENTRAL_WEBHOOK_URL:
    logger.warning("⚠️ CENTRAL_WEBHOOK_URL не установлен")

# Хранилище подписчиков в памяти (как кэш)
subscribers = set()

# ==================== КОМАНДЫ ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подписка на уведомления"""
    chat_id = update.effective_chat.id
    username = update.effective_user.username or "без username"
    
    # Добавляем подписчика через центральный вебхук
    if CENTRAL_WEBHOOK_URL:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    CENTRAL_WEBHOOK_URL,
                    json={
                        "action": "add_subscriber",
                        "chat_id": chat_id,
                        "username": username
                    },
                    timeout=10.0
                )
                result = response.json()
                if result.get("status") == "ok":
                    subscribers.add(chat_id)
                    logger.info(f"✅ Новый подписчик: {chat_id} (@{username})")
                else:
                    logger.error(f"Ошибка добавления: {result}")
        except Exception as e:
            logger.error(f"Ошибка: {e}")
    else:
        subscribers.add(chat_id)
    
    # Клавиатура
    keyboard = [
        [InlineKeyboardButton("📊 Ежедневный ABC-анализ", callback_data="abc_daily")],
        [InlineKeyboardButton("📈 Еженедельный ABC-анализ", callback_data="abc_weekly")],
        [InlineKeyboardButton("💰 Предложения цен", callback_data="price_offers")],
        [InlineKeyboardButton("📋 Все последние файлы", callback_data="all_backups")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "✅ Вы подписаны на уведомления!\n\n"
        "📋 Я буду присылать уведомления, когда обновляются таблицы.\n\n"
        "👇 Ниже кнопки для быстрого доступа к последним файлам:",
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Помощь"""
    help_text = (
        "🤖 <b>Помощь по боту</b>\n\n"
        "📌 <b>Доступные команды:</b>\n"
        "/start - Подписаться на уведомления\n"
        "/help - Показать эту справку\n"
        "/last - Показать кнопки с последними файлами\n\n"
        "📊 <b>Кнопки с файлами:</b>\n"
        "• Ежедневный ABC-анализ - последние 5 копий\n"
        "• Еженедельный ABC-анализ - последние 5 копий\n"
        "• Предложения цен - последние 5 копий\n"
        "• Все последние файлы - все копии из разных папок\n\n"
        "🔔 <b>Уведомления:</b>\n"
        "Вы будете получать уведомления при обновлении таблиц"
    )
    
    keyboard = [
        [InlineKeyboardButton("📊 Ежедневный ABC", callback_data="abc_daily")],
        [InlineKeyboardButton("📈 Еженедельный ABC", callback_data="abc_weekly")],
        [InlineKeyboardButton("💰 Предложения цен", callback_data="price_offers")],
        [InlineKeyboardButton("📋 Все файлы", callback_data="all_backups")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(help_text, parse_mode="HTML", reply_markup=reply_markup)

async def last_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать кнопки с последними файлами"""
    keyboard = [
        [InlineKeyboardButton("📊 Ежедневный ABC", callback_data="abc_daily")],
        [InlineKeyboardButton("📈 Еженедельный ABC", callback_data="abc_weekly")],
        [InlineKeyboardButton("💰 Предложения цен", callback_data="price_offers")],
        [InlineKeyboardButton("📋 Все файлы", callback_data="all_backups")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "👇 Выберите тип файлов для просмотра последних копий:",
        reply_markup=reply_markup
    )

# ==================== ОБРАБОТКА КНОПОК ====================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    
    if callback_data == "help":
        help_text = (
            "🤖 <b>Помощь по боту</b>\n\n"
            "📌 <b>Доступные команды:</b>\n"
            "/start - Подписаться на уведомления\n"
            "/help - Показать эту справку\n"
            "/last - Показать кнопки с последними файлами"
        )
        await query.edit_message_text(help_text, parse_mode="HTML")
        return
    
    # Показываем сообщение о загрузке
    type_names = {
        "abc_daily": "📊 Ежедневный ABC-анализ",
        "abc_weekly": "📈 Еженедельный ABC-анализ",
        "price_offers": "💰 Предложения цен",
        "all_backups": "📋 Все последние файлы"
    }
    
    type_name = type_names.get(callback_data, "Файлы")
    
    await query.edit_message_text(
        f"⏳ Загружаю {type_name}...\n\nПожалуйста, подождите..."
    )
    
    # Отправляем запрос в центральный вебхук
    if CENTRAL_WEBHOOK_URL:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    CENTRAL_WEBHOOK_URL,
                    json={
                        "action": "get_backups",
                        "file_type": callback_data
                    },
                    timeout=15.0
                )
                result = response.json()
                
                if result.get("status") == "ok":
                    backups = result.get("backups", [])
                    
                    if backups:
                        if callback_data == "all_backups":
                            # Группируем по типам
                            message = "📁 <b>Последние файлы по категориям:</b>\n\n"
                            current_type = ""
                            for backup in backups:
                                if backup['type'] != current_type:
                                    current_type = backup['type']
                                    type_display = {
                                        "abc_daily": "📊 Ежедневный ABC:",
                                        "abc_weekly": "📈 Еженедельный ABC:",
                                        "price_offers": "💰 Предложения цен:"
                                    }.get(current_type, f"{current_type}:")
                                    message += f"\n<b>{type_display}</b>\n"
                                message += f"• <a href='{backup['url']}'>{backup['name']}</a>\n"
                        else:
                            message = f"📁 <b>{type_name} - последние файлы:</b>\n\n"
                            for i, backup in enumerate(backups, 1):
                                message += f"{i}. <a href='{backup['url']}'>{backup['name']}</a>\n"
                        
                        await query.edit_message_text(message, parse_mode="HTML")
                    else:
                        await query.edit_message_text(f"❌ Нет сохраненных копий для {type_name}")
                else:
                    await query.edit_message_text(f"❌ Ошибка получения списка файлов: {result.get('message', '')}")
                    
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            await query.edit_message_text(f"❌ Ошибка: {str(e)[:100]}")
    else:
        await query.edit_message_text("❌ Центральный вебхук не настроен")

# ==================== ЗАПУСК БОТА ====================

async def main():
    app = Application.builder().token(TOKEN).updater(None).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("last", last_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if not render_url:
        logger.error("❌ RENDER_EXTERNAL_URL не установлен")
        return
    
    webhook_url = f"{render_url}/telegram"
    await app.bot.set_webhook(webhook_url)
    logger.info(f"✅ Webhook установлен: {webhook_url}")
    logger.info(f"📡 Центральный вебхук: {CENTRAL_WEBHOOK_URL}")
    
    async def telegram_webhook(request: Request) -> Response:
        data = await request.json()
        update = Update.de_json(data, app.bot)
        await app.update_queue.put(update)
        return Response()
    
    async def healthcheck(request: Request) -> PlainTextResponse:
        return PlainTextResponse("OK")
    
    starlette_app = Starlette(routes=[
        Route("/telegram", telegram_webhook, methods=["POST"]),
        Route("/healthcheck", healthcheck, methods=["GET"]),
        Route("/", healthcheck, methods=["GET"]),
    ])
    
    import uvicorn
    config = uvicorn.Config(
        app=starlette_app,
        host="0.0.0.0",
        port=PORT,
        log_level="info"
    )
    server = uvicorn.Server(config)
    
    async with app:
        await app.start()
        logger.info(f"🚀 Бот запущен на порту {PORT}")
        await server.serve()
        await app.stop()

if __name__ == "__main__":
    asyncio.run(main())
