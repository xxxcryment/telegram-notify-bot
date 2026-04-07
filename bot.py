import os
import asyncio
import logging
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import Response, PlainTextResponse
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Переменные окружения
TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))
PORT = int(os.getenv("PORT", 8000))

# Проверка наличия токена
if not TOKEN:
    logger.error("❌ BOT_TOKEN не установлен в переменных окружения!")
    exit(1)

logger.info(f"✅ Токен загружен: {TOKEN[:10]}...")

# Хранилище подписчиков
subscribers = set()

# === ОБРАБОТЧИКИ КОМАНД ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подписка на уведомления"""
    chat_id = update.effective_chat.id
    subscribers.add(chat_id)
    await update.message.reply_text(
        "✅ Вы подписаны на уведомления об обновлении таблиц!\n\n"
        "Теперь, когда вы обновите Google таблицу и нажмете кнопку, "
        "я пришлю уведомление всем подписчикам."
    )
    logger.info(f"Новый подписчик: {chat_id}")

async def notify_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправка уведомления всем подписчикам (только для админа)"""
    if update.effective_chat.id != ADMIN_ID:
        await update.message.reply_text("⛔ У вас нет прав на эту команду")
        return
    
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text(
            "ℹ️ Использование: /notify Название таблицы | Ссылка | Доп. информация"
        )
        return
    
    success_count = 0
    for chat_id in subscribers:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"📢 <b>Таблица обновлена!</b>\n\n{text}",
                parse_mode="HTML"
            )
            success_count += 1
        except Exception as e:
            logger.error(f"Ошибка отправки {chat_id}: {e}")
    
    await update.message.reply_text(f"✅ Уведомление отправлено {success_count} подписчикам")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика подписчиков"""
    if update.effective_chat.id != ADMIN_ID:
        await update.message.reply_text("⛔ У вас нет прав на эту команду")
        return
    
    await update.message.reply_text(f"📊 Всего подписчиков: {len(subscribers)}")

# === ЗАПУСК ===

async def main():
    # Создаем приложение бота
    app = Application.builder().token(TOKEN).updater(None).build()
    
    # Регистрируем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("notify", notify_all))
    app.add_handler(CommandHandler("stats", stats))
    
    # Получаем URL от Render
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if not render_url:
        logger.error("❌ RENDER_EXTERNAL_URL не установлен!")
        return
    
    webhook_url = f"{render_url}/telegram"
    logger.info(f"🌐 Устанавливаем webhook: {webhook_url}")
    
    # Устанавливаем webhook
    await app.bot.set_webhook(webhook_url)
    
    # Создаем Starlette приложение
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
    
    # Запускаем
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
