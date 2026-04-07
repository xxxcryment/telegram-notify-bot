import os
import asyncio
import logging
import httpx
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import Response, PlainTextResponse
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))
PORT = int(os.getenv("PORT", 8000))

if not TOKEN:
    logger.error("❌ BOT_TOKEN не установлен")
    exit(1)

# Webhook URL вашего Google Apps Script (нужно будет создать)
# Об этом чуть позже
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подписка на уведомления"""
    chat_id = update.effective_chat.id
    username = update.effective_user.username or ""
    
    # Отправляем данные в Google Sheets через вебхук
    if WEBHOOK_URL:
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    WEBHOOK_URL,
                    json={
                        "action": "add_subscriber",
                        "chat_id": chat_id,
                        "username": username
                    },
                    timeout=5.0
                )
            logger.info(f"Подписчик {chat_id} добавлен в таблицу")
            await update.message.reply_text(
                "✅ Вы подписаны на уведомления!\n\n"
                "Теперь при обновлении таблицы вы будете получать уведомления."
            )
        except Exception as e:
            logger.error(f"Ошибка сохранения подписчика: {e}")
            await update.message.reply_text(
                "⚠️ Произошла ошибка, но мы уже работаем над этим.\n"
                "Попробуйте позже или напишите администратору."
            )
    else:
        await update.message.reply_text("⚠️ Сервис временно недоступен. Попробуйте позже.")

async def main():
    app = Application.builder().token(TOKEN).updater(None).build()
    app.add_handler(CommandHandler("start", start))
    
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if not render_url:
        logger.error("❌ RENDER_EXTERNAL_URL не установлен")
        return
    
    webhook_url = f"{render_url}/telegram"
    await app.bot.set_webhook(webhook_url)
    logger.info(f"Webhook установлен: {webhook_url}")
    
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
