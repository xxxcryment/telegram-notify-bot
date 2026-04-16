import os
import asyncio
import logging
import httpx
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import Response, PlainTextResponse
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))
PORT = int(os.getenv("PORT", 8000))
CENTRAL_WEBHOOK_URL = os.environ.get("CENTRAL_WEBHOOK_URL")

if not TOKEN:
    logger.error("❌ BOT_TOKEN не установлен")
    exit(1)

if not CENTRAL_WEBHOOK_URL:
    logger.warning("⚠️ CENTRAL_WEBHOOK_URL не установлен")

# ==================== ПОСТОЯННАЯ КЛАВИАТУРА ВНИЗУ ====================
def get_main_keyboard():
    """Создает постоянную клавиатуру внизу экрана"""
    keyboard = [
        [KeyboardButton("📊 Ежедневный ABC"), KeyboardButton("📈 Еженедельный ABC")],
        [KeyboardButton("💰 Предложения цен"), KeyboardButton("📋 Все файлы")],
        [KeyboardButton("❓ Помощь"), KeyboardButton("📊 Статистика")],
        [KeyboardButton("ℹ️ О боте")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ==================== КОМАНДЫ И ОБРАБОТЧИКИ ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подписка на уведомления"""
    chat_id = update.effective_chat.id
    username = update.effective_user.username or "без username"
    
    # Добавляем подписчика через центральный вебхук
    if CENTRAL_WEBHOOK_URL:
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
                response = await client.post(
                    CENTRAL_WEBHOOK_URL,
                    json={
                        "action": "add_subscriber",
                        "chat_id": chat_id,
                        "username": username
                    }
                )
                result = response.json()
                if result.get("status") == "ok":
                    logger.info(f"✅ Новый подписчик: {chat_id} (@{username})")
        except Exception as e:
            logger.error(f"Ошибка: {e}")
    
    await update.message.reply_text(
        "✅ <b>Вы подписаны на уведомления!</b>\n\n"
        "Я буду присылать уведомления, когда обновляются таблицы.\n\n"
        "👇 <b>Кнопки внизу для быстрого доступа к файлам:</b>",
        parse_mode="HTML",
        reply_markup=get_main_keyboard()
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий на кнопки постоянной клавиатуры"""
    text = update.message.text
    chat_id = update.effective_chat.id
    
    if text == "📊 Ежедневный ABC":
        await get_files_by_type(update, "abc_daily", "📊 Ежедневный ABC-анализ")
    
    elif text == "📈 Еженедельный ABC":
        await get_files_by_type(update, "abc_weekly", "📈 Еженедельный ABC-анализ")
    
    elif text == "💰 Предложения цен":
        await get_files_by_type(update, "price_offers", "💰 Предложения цен")
    
    elif text == "📋 Все файлы":
        await get_files_by_type(update, "all", "📋 Все последние файлы")
    
    elif text == "❓ Помощь":
        await show_help(update)
    
    elif text == "📊 Статистика":
        await show_stats(update)
    
    elif text == "ℹ️ О боте":
        await show_about(update)
    
    else:
        await update.message.reply_text(
            "Используйте кнопки внизу для навигации 👇",
            reply_markup=get_main_keyboard()
        )

async def get_files_by_type(update, file_type, type_name):
    """Получение и отправка файлов по типу"""
    # Отправляем сообщение о загрузке
    msg = await update.message.reply_text(f"⏳ Загружаю {type_name}...\n\nПожалуйста, подождите.")
    
    if not CENTRAL_WEBHOOK_URL:
        await msg.edit_text("❌ Центральный вебхук не настроен")
        return
    
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            response = await client.post(
                CENTRAL_WEBHOOK_URL,
                json={
                    "action": "get_last_files",
                    "file_type": file_type
                }
            )
            
            if response.status_code != 200:
                await msg.edit_text(f"❌ Ошибка: HTTP {response.status_code}")
                return
            
            result = response.json()
            
            if result.get("status") == "ok":
                files = result.get("files", [])
                
                if files:
                    if file_type == "all":
                        message = "📁 <b>Последние файлы по категориям:</b>\n\n"
                        current_type = ""
                        for file in files:
                            type_display = {
                                "abc_daily": "📊 Ежедневный ABC:",
                                "abc_weekly": "📈 Еженедельный ABC:",
                                "price_offers": "💰 Предложения цен:"
                            }.get(file.get('type'), f"{file.get('type')}:")
                            
                            if file.get('type') != current_type:
                                current_type = file.get('type')
                                message += f"\n<b>{type_display}</b>\n"
                            message += f"• <a href='{file.get('url')}'>{file.get('name')}</a>\n"
                    else:
                        message = f"📁 <b>{type_name} - последние файлы:</b>\n\n"
                        for i, file in enumerate(files, 1):
                            message += f"{i}. <a href='{file.get('url')}'>{file.get('name')}</a>\n"
                    
                    await msg.edit_text(message, parse_mode="HTML", disable_web_page_preview=True)
                else:
                    await msg.edit_text(f"❌ Нет сохраненных копий для {type_name}")
            else:
                await msg.edit_text(f"❌ Ошибка: {result.get('message', 'Неизвестная ошибка')}")
                
    except httpx.TimeoutException:
        await msg.edit_text("❌ Ошибка: Время ожидания истекло")
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await msg.edit_text(f"❌ Ошибка: {str(e)[:100]}")

async def show_help(update):
    """Показать справку"""
    help_text = (
        "🤖 <b>Помощь по боту</b>\n\n"
        "📌 <b>Доступные кнопки внизу:</b>\n"
        "• Ежедневный ABC - последние 5 копий\n"
        "• Еженедельный ABC - последние 5 копий\n"
        "• Предложения цен - последние 5 копий\n"
        "• Все файлы - все последние копии\n"
        "• Статистика - количество подписчиков\n"
        "• О боте - информация о боте\n\n"
        "📌 <b>Команды:</b>\n"
        "/start - Перезапустить бота\n"
        "/help - Показать эту справку\n\n"
        "🔔 <b>Уведомления:</b>\n"
        "Вы будете получать уведомления при обновлении таблиц"
    )
    await update.message.reply_text(help_text, parse_mode="HTML", reply_markup=get_main_keyboard())

async def show_stats(update):
    """Показать статистику"""
    if not CENTRAL_WEBHOOK_URL:
        await update.message.reply_text("❌ Статистика временно недоступна", reply_markup=get_main_keyboard())
        return
    
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            response = await client.post(
                CENTRAL_WEBHOOK_URL,
                json={"action": "get_stats"}
            )
            result = response.json()
            
            if result.get("status") == "ok":
                stats_text = (
                    "📊 <b>Статистика бота</b>\n\n"
                    f"👥 Подписчиков: {result.get('subscribers_count', 0)}\n"
                    f"📁 Всего копий: {result.get('backups_count', 0)}\n"
                    f"📅 Последнее обновление: {result.get('last_update', 'неизвестно')}"
                )
                await update.message.reply_text(stats_text, parse_mode="HTML", reply_markup=get_main_keyboard())
            else:
                await update.message.reply_text("❌ Ошибка получения статистики", reply_markup=get_main_keyboard())
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:100]}", reply_markup=get_main_keyboard())

async def show_about(update):
    """Информация о боте"""
    about_text = (
        "ℹ️ <b>О боте</b>\n\n"
        "🤖 Бот для уведомлений об обновлении таблиц\n\n"
        "📊 <b>Функции:</b>\n"
        "• Уведомления о новых копиях таблиц\n"
        "• Быстрый доступ к последним файлам\n"
        "• Статистика подписчиков\n\n"
        "📡 <b>Версия:</b> 2.0\n"
        "🕒 <b>Последнее обновление:</b> Апрель 2026"
    )
    await update.message.reply_text(about_text, parse_mode="HTML", reply_markup=get_main_keyboard())

# ==================== ОБРАБОТКА INLINE КНОПОК (если нужны) ====================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка inline кнопок (если используете)"""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    
    if callback_data == "back_to_start":
        await query.edit_message_text(
            "👇 Используйте кнопки внизу для навигации:",
            reply_markup=get_main_keyboard()
        )

# ==================== ЗАПУСК БОТА ====================

async def main():
    app = Application.builder().token(TOKEN).updater(None).build()
    
    # Регистрируем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", show_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
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
