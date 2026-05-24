import asyncio
import logging
from telebot.async_telebot import AsyncTeleBot
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn
import httpx
from config import BOT_TOKEN, OWNER_ID, API_URL
from database import db
from user import register_user_handlers
from admin import register_admin_handlers
from utils import is_rate_limited

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize bot
bot = AsyncTeleBot(BOT_TOKEN, parse_mode="HTML")

# FastAPI app
app = FastAPI(title="LITHOVEX AI", version="1.0")

# Register all handlers
register_user_handlers(bot)
register_admin_handlers(bot)

# API endpoint that proxies requests to the external API
@app.post("/api/chat/completions")
async def chat_completions(request: Request):
    try:
        data = await request.json()
    except:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    # Validate basic structure
    if "messages" not in data or "model" not in data:
        return JSONResponse({"error": "Missing 'model' or 'messages'"}, status_code=400)

    # Forward to the real API (or you can implement your own model switching)
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            headers = {"Content-Type": "application/json"}
            # If streaming is requested, we need to handle it properly.
            # For simplicity, we return the same response as the upstream.
            if data.get("stream", False):
                # Streaming not fully implemented in proxy; return error for now
                return JSONResponse({"error": "Streaming not supported in proxy"}, status_code=400)
            resp = await client.post(API_URL, json=data, headers=headers)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"API proxy error: {e}")
            return JSONResponse({"error": "Upstream API failure"}, status_code=502)

@app.on_event("startup")
async def startup():
    await db.init()
    logger.info("Database initialized")

@app.on_event("shutdown")
async def shutdown():
    await db.close()

async def run_bot():
    logger.info("Starting bot polling...")
    await bot.polling(non_stop=True)

async def main():
    # Start bot polling as a background task
    bot_task = asyncio.create_task(run_bot())
    # Configure uvicorn
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()
    bot_task.cancel()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")