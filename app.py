import os
import json
import logging
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
import uvicorn

# Importing functions and constants from your existing background.py
# Make sure background.py is in the same directory as this app.py
from background import (
    process_update,
    init_bot,
    run_cache_cleanup_and_ram_monitor,
    MAIN_BOT_USERNAME,
    process_cashfree_success # <--- Ise add kiya gaya
)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("App")

# This is an industry-grade practice. 
# Python's garbage collector can destroy asyncio background tasks if they are not referenced.
# This set keeps a strong reference to running tasks until they complete safely.
active_background_tasks = set()

def fire_and_forget(coro):
    """
    Safely executes an async function in the background.
    Instantly returns control so the API can send a 200 OK to Telegram.
    """
    task = asyncio.create_task(coro)
    active_background_tasks.add(task)
    task.add_done_callback(active_background_tasks.discard)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles startup and shutdown events for the FastAPI application.
    """
    logger.info("Starting up server... Initializing Bot logic...")
    try:
        # Initialize databases, pools, and schedulers from background.py
        await init_bot()
        
        # Start the RAM monitor and Cache cleaner in the background continuously
        fire_and_forget(run_cache_cleanup_and_ram_monitor())
        
        logger.info("✅ Bot initialized and Background monitors started successfully.")
    except Exception as e:
        logger.critical(f"❌ Failed to initialize bot on startup: {e}", exc_info=True)
    
    yield  # Server is running here
    
    logger.info("Shutting down server... Cleaning up resources...")
    # Add any specific shutdown cleanup here if needed in the future

app = FastAPI(lifespan=lifespan, title="Echelon File Store App")

@app.get("/")
@app.get("/health")
async def health_check():
    """
    Simple health check endpoint. 
    Render pings this to check if the server is alive.
    """
    return JSONResponse(content={"status": "ok", "message": "Server is running smoothly."})

async def background_update_processor(bot_username: str, body_bytes: bytes, received_time: datetime, header_parsed_time: datetime):
    """
    This function actually parses the JSON and sends it to background.py.
    It runs strictly in the background after the 200 OK is sent.
    """
    try:
        data = json.loads(body_bytes)
        json_parsed_time = datetime.utcnow()
        before_process_update_time = datetime.utcnow()
        
        # Pass data to your highly-optimized BotLogic via process_update
        await process_update(
            bot_username=bot_username,
            data=data,
            received_time=received_time,
            header_parsed_time=header_parsed_time,
            json_parsed_time=json_parsed_time,
            before_process_update_time=before_process_update_time
        )
    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode JSON from Telegram for @{bot_username}: {e}")
    except Exception as e:
        logger.error(f"Error in background update processing for @{bot_username}: {e}", exc_info=True)

@app.post("/tora")
async def main_bot_webhook(request: Request):
    """
    Webhook endpoint for the MAIN Bot.
    Instantly returns 200 OK and delegates work to the background.
    """
    received_time = datetime.utcnow()
    
    try:
        body_bytes = await request.body()
        header_parsed_time = datetime.utcnow()
        
        # Instantly push to background queue
        fire_and_forget(
            background_update_processor(
                bot_username=MAIN_BOT_USERNAME,
                body_bytes=body_bytes,
                received_time=received_time,
                header_parsed_time=header_parsed_time
            )
        )
    except Exception as e:
        logger.error(f"Error reading main bot webhook request: {e}")
    
    # Send immediate 200 OK back to Telegram (Stops 1-minute timeout resends)
    return Response(status_code=200, content="ok")

@app.post("/normal")
async def clone_bot_webhook(request: Request):
    """
    Webhook endpoint for CLONED Bots.
    Extracts the bot username from the secret token, returns 200 OK, and processes in background.
    """
    received_time = datetime.utcnow()
    
    try:
        # background.py passes the clone's username in the secret_token when setting the webhook
        secret_token = request.headers.get("x-telegram-bot-api-secret-token")
        header_parsed_time = datetime.utcnow()
        
        if not secret_token:
            logger.warning("Received /normal webhook without a secret token.")
            return Response(status_code=200, content="ignored") # Return 200 anyway to stop retries
            
        bot_username = secret_token
        body_bytes = await request.body()
        
        # Instantly push to background queue
        fire_and_forget(
            background_update_processor(
                bot_username=bot_username,
                body_bytes=body_bytes,
                received_time=received_time,
                header_parsed_time=header_parsed_time
            )
        )
    except Exception as e:
        logger.error(f"Error reading clone bot webhook request: {e}")
    
    # Send immediate 200 OK back to Telegram
    return Response(status_code=200, content="ok")

@app.post("/cash")
async def cashfree_webhook(request: Request):
    """
    Cashfree se aane wale Async Payment Notifications ko catch karega.
    """
    try:
        body = await request.json()
        
        # Order ID nikalne ka tareeka (API docs ke hisaab se)
        order_id = body.get('data', {}).get('order', {}).get('order_id', '')
        if not order_id and 'orderId' in body:
            order_id = body['orderId'] # Backup in case structure varies
        
        # Humne order_id 'txn_12345' format me banaya hai
        if order_id and order_id.startswith("txn_"):
            transaction_id = int(order_id.split("_")[1])
            logger.info(f"Received Cashfree Webhook for Transaction: {transaction_id}")
            # Isko background me daal do taaki Cashfree ko turant 200 OK mil jaye
            fire_and_forget(process_cashfree_success(transaction_id))
            
    except Exception as e:
        logger.error(f"CF webhook processing error: {e}")
        
    return Response(status_code=200, content="ok")

if __name__ == "__main__":
    # Get port from environment variables (Render automatically provides 'PORT')
    # If not provided (like running locally), default to 8443 or 8000
    port = int(os.environ.get("PORT", 8443))
    
    logger.info(f"Starting server on 0.0.0.0:{port}")
    
    # Run the server using Uvicorn
    uvicorn.run(
        "app:app", 
        host="0.0.0.0", 
        port=port, 
        loop="asyncio",
        log_level="info",
        access_log=False # Disabled access logs for maximum performance
    )
