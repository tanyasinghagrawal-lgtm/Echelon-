import os
import json
import logging
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, Header
from fastapi.responses import JSONResponse, FileResponse
import uvicorn
import hmac
import hashlib
from urllib.parse import parse_qsl

# Importing functions and constants from your existing background.py
from background import (
    process_update,
    init_bot,
    run_cache_cleanup_and_ram_monitor,
    MAIN_BOT_USERNAME,
    MAIN_BOT_TOKEN,
    process_cashfree_success,
    metrics_aggregator_worker,
    get_web_app_dashboard_data,
    DBManager,
    ALL_BOTS_DB
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
        # Start the RAM monitor and Cache cleaner in the background continuously
        fire_and_forget(run_cache_cleanup_and_ram_monitor())
        
        # Start the 5-Minute In-Memory Latency & Load Aggregator Worker
        fire_and_forget(metrics_aggregator_worker())
        
        logger.info("✅ Bot initialized, Background monitors & Metrics Aggregator started successfully.")    
    except Exception as e:
        logger.critical(f"❌ Failed to initialize bot on startup: {e}", exc_info=True)
    
    yield  # Server is running here
    
    logger.info("Shutting down server... Cleaning up resources...")
    # Add any specific shutdown cleanup here if needed in the future

app = FastAPI(lifespan=lifespan, title="Echelon File Store App")

@app.get("/")
@app.get("/health")
async def health_check():
    return JSONResponse(content={"status": "ok", "message": "Server is running smoothly."})

# --- TELEGRAM MINI APP SECURITY & AUTHENTICATION ---
def verify_telegram_init_data(init_data: str) -> dict:
    """
    Cryptographically verifies Telegram WebApp initData using MAIN_BOT_TOKEN.
    Returns user dict if valid, else raises ValueError.
    """
    if not init_data:
        raise ValueError("Missing initData.")

    parsed_data = dict(parse_qsl(init_data, keep_blank_values=True))
    if "hash" not in parsed_data:
        raise ValueError("Hash missing from initData.")

    received_hash = parsed_data.pop("hash")
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))

    secret_key = hmac.new(b"WebAppData", MAIN_BOT_TOKEN.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(received_hash, expected_hash):
        raise ValueError("Security verification failed: Hash mismatch.")

    user_info = json.loads(parsed_data.get("user", "{}"))
    if not user_info or "id" not in user_info:
        raise ValueError("Invalid user payload.")

    return user_info

# --- MINI APP HOSTING ENDPOINT ---
@app.get("/app")
async def serve_mini_app():
    """
    Serves the any.html file located in the root/home folder.
    """
    html_path = os.path.join(os.path.dirname(__file__), "any.html")
    if os.path.exists(html_path):
        return FileResponse(html_path, media_type="text/html")
    
    # Fallback agar user ne current working directory me rakhi ho
    if os.path.exists("any.html"):
        return FileResponse("any.html", media_type="text/html")
        
    return JSONResponse(status_code=404, content={"error": "any.html file not found in home folder."})

# --- MINI APP API ENDPOINTS ---
@app.post("/api/auth")
async def api_authenticate_user(request: Request):
    """
    Validates Telegram initData and returns user's bots list and role.
    """
    try:
        body = await request.json()
        init_data = body.get("initData", "")
        user = verify_telegram_init_data(init_data)
        user_id = user["id"]

        is_super_admin = (user_id == 6796088344)
        if is_super_admin:
            # Super admin ko server ke saare active clone bots ka access milega
            all_server_bots = await DBManager.execute_sqlite_query(
                ALL_BOTS_DB, 
                "SELECT username FROM bots WHERE username NOT LIKE '%#revoked%'", 
                fetch='all'
            )
            bots = [b[0].split('#')[0] for b in all_server_bots] if all_server_bots else []
        else:
            creator_bots = await DBManager.execute_sqlite_query(
                ALL_BOTS_DB, 
                "SELECT username FROM bots WHERE creator_id=? AND username NOT LIKE '%#revoked%'", 
                (user_id,), 
                fetch='all'
            )
            bots = [b[0].split('#')[0] for b in creator_bots] if creator_bots else []
        return JSONResponse(content={
            "success": True,
            "user_id": user_id,
            "first_name": user.get("first_name", "User"),
            "is_super_admin": is_super_admin,
            "bots": bots
        })
    except ValueError as ve:
        return JSONResponse(status_code=401, content={"success": False, "error": str(ve)})
    except Exception as e:
        logger.error(f"Auth error: {e}")
        return JSONResponse(status_code=500, content={"success": False, "error": "Internal server error."})


@app.post("/api/dashboard-data")
async def api_dashboard_data(request: Request):
    """
    Returns deep analytics, conversion funnel, revenue breakdown, pagination for transactions,
    pending bills, and in-memory latency stats.
    """
    try:
        body = await request.json()
        init_data = body.get("initData", "")
        bot_username = body.get("bot_username")
        time_filter = body.get("time_filter", "24h")  # "1h", "6h", "24h", "7d"
        page = int(body.get("page", 1))
        limit = int(body.get("limit", 20))

        user = verify_telegram_init_data(init_data)
        user_id = user["id"]
        is_super_admin = (user_id == 6796088344)

        # Non-super admins cannot access network-wide 'all' query
        # Non-super admins cannot access network-wide 'all' query
        if not is_super_admin:
            if not bot_username or bot_username == "all":
                creator_bots = await DBManager.execute_sqlite_query(
                    ALL_BOTS_DB, "SELECT username FROM bots WHERE creator_id=? AND username NOT LIKE '%#revoked%'", (user_id,), fetch='all'
                )
                bot_username = creator_bots[0][0].split('#')[0] if creator_bots else None

        # Guard: Agar user ke paas koi active bot nahi hai, toh crash hone se bachayein
        if not is_super_admin and not bot_username:
            return JSONResponse(status_code=200, content={
                "success": True,
                "stats": {},
                "latency_graph": [],
                "bot_settings": {},
                "pending_bills": {},
                "latest_transactions": [],
                "pagination": {"page": 1, "has_more": False}
            })

        data, status_code = await get_web_app_dashboard_data(
            user_id=user_id, 
            bot_username=bot_username, 
            time_filter=time_filter,
            page=page,
            limit=limit
        )
        return JSONResponse(status_code=status_code, content=data)
    except ValueError as ve:
        return JSONResponse(status_code=401, content={"success": False, "error": str(ve)})
    except Exception as e:
        logger.error(f"Dashboard data API error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"success": False, "error": "Failed to fetch dashboard data."})
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
    Cashfree se aane wale Async Payment Notifications ko catch karega aur
    webhook data ko background processor tak bhejega.
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
            
            # --- YAHAN UPDATE HUA HAI ---
            # Ab hum 'body' (jo ki poora webhook JSON hai) ko 'webhook_data' parameter me bhej rahe hain
            fire_and_forget(process_cashfree_success(transaction_id, webhook_data=body))
            
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
