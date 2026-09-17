import io
import qrcode
from PIL import Image
import os
from telegram.request import HTTPXRequest
import json
import apscheduler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import asyncio
from asyncio import get_event_loop
from datetime import datetime, timedelta
from collections import OrderedDict
import httpx
import base64
from zoneinfo import ZoneInfo
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot, InputMediaPhoto, InputMediaVideo, InputMediaDocument, InputMediaAudio, ChatJoinRequest
from telegram.constants import ParseMode, ChatAction
from telegram.error import TelegramError
import uuid
import logging
import re
import random
from urllib.parse import urlparse
import multiprocessing
# 'from multiprocessing import Manager' ko hata diya gaya hai

# Naye imports
import pickle
import redis.asyncio as aioredis

# --- VALKEY CONNECTION (Aiven.io) ---
VALKEY_URL = "rediss://default:AVNS_a0NYthGi8jkT6AJ3sVz@valkey-362b0d18-mritunjaykumarbrb5-7df3.f.aivencloud.com:17686"
valkey_client = aioredis.from_url(
    VALKEY_URL, 
    decode_responses=False,
    max_connections=500,
    socket_timeout=10.0
)
CUSTOM_SHORTENERS = {
"vplink.in": "https://vplink.in/api?api=94a14c12df6aee29ce8996550feafb3ef7106777&url=",
"arolinks.com": "https://arolinks.com/api?api=40cc76b3ab04e717960295cbe52f3f9cb09402db&url=",
"example.com": "https://example.com/api?key=yourkey&url="
}
logging.basicConfig(level=logging.ERROR, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
# --- YEH NAYI LINES ADD KAREIN ---
# Default Channel Check ke liye Constants
DEFAULT_CHANNELS = [
    {
        "id": -1003251476624, # Dusra Channel (Aapka naya wala)
        "link": "https://t.me/echelonsuper"
    }
    # Future me aur channels add karne ke liye, neeche diye format me add karein:
    # ,{ "id": -100..., "link": "https://t.me/..." }
]

# --- NAYA ON/OFF SWITCH ---
# True = Channel check ON rahega
# False = Channel check OFF ho jayega (Bot fast chalega)
IS_DEFAULT_CHANNEL_CHECK_ON = False
# --- NAYI LINES YAHAN KHATAM HOTI HAIN ---
# Baaki ka code (MAIN_BOT_TOKEN, etc.) waise hi rahega
EC2_PUBLIC_IP_OR_DOMAIN = "https://echelon-b5kp.onrender.com"
MAIN_BOT_TOKEN = "7932461290:AAHeVsa-iadPNOdnPlNSokmfKo88PCyvlYE"
MAIN_BOT_USERNAME = "Echelon_File_Store_Bot"
WEB_SERVER_HOST = "0.0.0.0"
WEB_SERVER_PORT = 8443
WEBHOOK_URL = EC2_PUBLIC_IP_OR_DOMAIN
DB_DIR = "databases"
os.makedirs(DB_DIR, exist_ok=True)
ALL_BOTS_DB = os.path.join(DB_DIR, "all_bots_list.db")
EXTERNAL_VIDEOS = []


async def fetch_external_videos():
    global EXTERNAL_VIDEOS
    last_json_file = os.path.join(DB_DIR, "last_videos.json")
    
    # 1. Agar RAM khali hai aur local backup file exist karti hai, toh turant local se pehle hi load kar lo
    if not EXTERNAL_VIDEOS and os.path.exists(last_json_file):
        try:
            with open(last_json_file, 'r', encoding='utf-8') as f:
                EXTERNAL_VIDEOS = json.load(f)
            logger.info(f"Initial Fallback: Local JSON se {len(EXTERNAL_VIDEOS)} videos load kiye gaye.")
        except Exception as read_e:
            logger.error(f"Local JSON read error: {read_e}")

    # 2. Server se latest video list download karne ki koshish karo
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("https://videopl.onrender.com/videos.json", timeout=20)
            resp.raise_for_status()
            new_videos = resp.json()
            if isinstance(new_videos, list) and len(new_videos) > 0:
                EXTERNAL_VIDEOS = new_videos
                logger.info(f"Safaltapoorvak {len(EXTERNAL_VIDEOS)} external videos load ho gaye RAM me.")
                with open(last_json_file, 'w', encoding='utf-8') as f:
                    json.dump(EXTERNAL_VIDEOS, f)
                return True
    except Exception as e:
        logger.error(f"External videos URL fetch error: {e}")
        # Agar URL fail hui aur RAM abhi bhi khali hai, toh dubara local JSON check karo
        if not EXTERNAL_VIDEOS and os.path.exists(last_json_file):
            try:
                with open(last_json_file, 'r', encoding='utf-8') as f:
                    EXTERNAL_VIDEOS = json.load(f)
                logger.info(f"Fallback after network fail: {len(EXTERNAL_VIDEOS)} videos loaded from local JSON.")
            except Exception as read_e:
                logger.error(f"Local fallback read error: {read_e}")

    return len(EXTERNAL_VIDEOS) > 0


async def ensure_external_videos_worker():
    """
    Background worker: Agar EXTERNAL_VIDEOS RAM me load nahi hai,
    toh har 5 minute me auto-retry karega jab tak load na ho jaye.
    Load hone ke baad baar-baar bekar network calls nahi karega.
    """
    while True:
        try:
            if not EXTERNAL_VIDEOS:
                logger.warning("EXTERNAL_VIDEOS RAM me load nahi hai. Har 5 min me retry kar raha hoon...")
                success = await fetch_external_videos()
                if success:
                    logger.info("EXTERNAL_VIDEOS successfully auto-loaded in background worker.")
            
            # Agar load ho chuka hai toh 1 ghanta rest karega, agar load nahi hua toh 5 min (300 sec) baad retry karega
            sleep_time = 3600 if EXTERNAL_VIDEOS else 300
            await asyncio.sleep(sleep_time)
        except Exception as e:
            logger.error(f"External videos retry worker error: {e}")
            await asyncio.sleep(300)

# --- YEH SAHI CODE PASTE KAREIN ---

# background.py me is class ko poora replace karein

import asyncio
from datetime import datetime
import re
# --- NAYA POSTGRESQL CODE SHURU ---
import asyncpg
from asyncpg.exceptions import UndefinedTableError

# User ke diye gaye DB Parameters
# User ke diye gaye DB Parameters
# Aiven Database URL
DATABASE_URL = "postgres://avnadmin:AVNS_VzxykM_0WsHdgr-IIyM@pg-344d515a-mritunjaysinghagrawal-209d.g.aivencloud.com:22418/defaultdb?sslmode=require"


# Global variable connection pool ke liye
pg_pool = None

async def init_postgresql_pool():
    """PostgreSQL connection pool ko initialize karta hai (Smart Connection Management ke sath)."""
    global pg_pool
    max_retries = 5  # Agar fail hota hai toh kul 5 baar koshish karega
    retry_delay = 2  # Har koshish ke beech 2 second ka gap rakhega

    for attempt in range(max_retries):
        try:
            # Aiven URL (DSN) ka use karke connection pool banayein
            pg_pool = await asyncpg.create_pool(
                dsn=DATABASE_URL, 
                min_size=1, 
                max_size=19,  # Max 19 connections
                max_inactive_connection_lifetime=60.0, # 1 minute idle rehte hi drop karega
                command_timeout=30.0
                # Yahan se invalid 'max_connection_lifetime' hata diya gaya hai!
            )

            if attempt > 0:
                logger.info(f"✅ SUCCESS: PostgreSQL se connection attempt #{attempt + 1} me safaltapoorvak jud gaya.")
            else:
                logger.info("PostgreSQL connection pool safaltapoorvak initialize ho gaya.")
            
            return # Connection safal, function se bahar niklo

        except Exception as e:
            logger.warning(f"PostgreSQL se connect karne ka attempt #{attempt + 1} fail ho gaya. Error: {e}")

            if attempt < max_retries - 1:
                logger.info(f"{retry_delay} seconds baad dobara koshish ki jayegi...")
                await asyncio.sleep(retry_delay)
            else:
                logger.error(f"❌ GIVING UP: Saare {max_retries} attempts fail ho gaye. PostgreSQL se connect nahi ho pa raha hai.")
                # Ab admin ko soochit karo
                try:
                    main_bot = Bot(token=MAIN_BOT_TOKEN)
                    await main_bot.initialize()
                    await main_bot.send_message(
                        ADMIN_NOTIFY_ID,
                        f"🚨 CRITICAL ERROR 🚨\n\nPostgreSQL database se {max_retries} baar koshish karne ke baad bhi connect nahi ho pa raha hai. FSUB Request-Join feature kaam nahi karega.\n\nFinal Error: `{e}`"
                    )
                except Exception as notify_e:
                    logger.error(f"Admin ko DB connection error ki soochana bhejte waqt error: {notify_e}")
class TTLAsyncCache:
    """
    High-performance asynchronous cache engine powered by Aiven Valkey/Redis.
    Automatic key expiration (TTL) and zero memory-lock bottlenecks.
    """
    def __init__(self, prefix: str, ttl_seconds: int):
        self.prefix = prefix
        self.ttl = ttl_seconds

    def _make_key(self, key) -> str:
        return f"{self.prefix}:{key}"

    async def get(self, key):
        try:
            raw_data = await valkey_client.get(self._make_key(key))
            if raw_data is not None:
                return pickle.loads(raw_data)
            return None
        except Exception as e:
            logger.error(f"Valkey cache get error for key '{key}': {e}")
            return None

    async def set(self, key, value):
        try:
            pickled_val = pickle.dumps(value)
            if self.ttl > 0:
                await valkey_client.set(self._make_key(key), pickled_val, ex=self.ttl)
            else:
                await valkey_client.set(self._make_key(key), pickled_val)
        except Exception as e:
            logger.error(f"Valkey cache set error for key '{key}': {e}")

    async def delete(self, key):
        try:
            await valkey_client.delete(self._make_key(key))
        except Exception as e:
            logger.error(f"Valkey cache delete error for key '{key}': {e}")

    async def contains(self, key):
        try:
            return bool(await valkey_client.exists(self._make_key(key)))
        except Exception as e:
            logger.error(f"Valkey cache contains error for key '{key}': {e}")
            return False

# --- ASYNC VALKEY CACHES ---
CACHE_BOT_TOKENS = TTLAsyncCache("tokens", 43200)
CACHE_BOT_SETTINGS = TTLAsyncCache("settings", 43200)
CACHE_FSUB_USER_STATUS = TTLAsyncCache("fsub_status", 1800)
CACHE_AD_VERIFY_LINK = TTLAsyncCache("ad_verify", 600)
CACHE_CONVERSATION = TTLAsyncCache("conversation", 240)
CACHE_FSUB_PENDING = TTLAsyncCache("fsub_pending", 600)
CACHE_USER_MEMBERSHIP = TTLAsyncCache("membership", 600)
CACHE_FILE = TTLAsyncCache("file", 6000)
CACHE_BATCH = TTLAsyncCache("batch", 6000)
CACHE_MEDIA_GROUP = TTLAsyncCache("media_group", 30)
CACHE_UNKNOWN_PAYLOAD = TTLAsyncCache("unknown_payload", 86400)
# 7 Days (7 * 86400 seconds) ke liye manual premium audit cache
CACHE_MANUAL_PREMIUM = TTLAsyncCache("manual_prem", 604800)

CONCURRENCY_SEMAPHORE = asyncio.Semaphore(1260)

# ... 
ADMIN_NOTIFY_ID = -1002537516601

# --- PENDING USERS BATCH BUFFER ---
PENDING_NEW_USERS = {}  # Format: {'bot_username': {user_id1, user_id2, ...}}
PENDING_USERS_LOCK = asyncio.Lock()

# --- HIGH-SPEED IN-MEMORY METRICS & LATENCY TRACKER ---
from collections import deque

CURRENT_ACTIVE_REQUESTS = 0
METRICS_LOCK = asyncio.Lock()

# Har 5 minute ke dauran aane wale requests ka temporary buffer
CURRENT_WINDOW_DATA = {
    'latencies': [],          # All request processing times in ms
    'bot_requests': {},       # {'bot_username': count}
    'peak_concurrency': 0,    # Max simultaneous requests in this 5 min
    'total_requests': 0
}

# Pichle 24 Ghante ka 5-min history (12 points/hr * 24 = 288 points)
# RAM consumption: Less than 1.5 MB
HISTORICAL_5MIN_METRICS = deque(maxlen=288)

def record_live_metric(bot_username: str, latency_ms: float):
    """Safely records request latency and counts in fast RAM without blocking."""
    global CURRENT_WINDOW_DATA
    try:
        CURRENT_WINDOW_DATA['latencies'].append(latency_ms)
        CURRENT_WINDOW_DATA['total_requests'] += 1
        
        clean_name = bot_username.split('#')[0]
        CURRENT_WINDOW_DATA['bot_requests'][clean_name] = CURRENT_WINDOW_DATA['bot_requests'].get(clean_name, 0) + 1
    except Exception:
        pass

async def record_bot_activity(bot_username: str, user_id: int = None, action_type: str = "click"):
    """
    High-Precision Time-Series Analytics Engine powered by Valkey:
    - Hourly bucket (h:YYYY-MM-DD-HH) taaki 1h aur 6h filters exact kaam karein
    - Daily bucket (d:YYYY-MM-DD) taaki 24h aur 7d filters ka exact rolling sum nikle
    - Total Lifetime Counters
    """
    try:
        clean_name = bot_username.split('#')[0]
        now = datetime.utcnow()
        today_str = now.strftime('%Y-%m-%d')
        hour_str = now.strftime('%Y-%m-%d-%H')

        pipe = valkey_client.pipeline()
        if action_type == "click":
            pipe.incr(f"stats:{clean_name}:clicks:total")
            pipe.incr(f"stats:{clean_name}:clicks:{today_str}")
            pipe.incr(f"stats:{clean_name}:clicks:h:{hour_str}")
            pipe.incr(f"stats:{clean_name}:clicks:d:{today_str}")
            pipe.expire(f"stats:{clean_name}:clicks:h:{hour_str}", 172800) # 48 hours TTL
            pipe.expire(f"stats:{clean_name}:clicks:d:{today_str}", 864000) # 10 days TTL
        elif action_type == "view":
            pipe.incr(f"stats:{clean_name}:views:total")
            pipe.incr(f"stats:{clean_name}:views:{today_str}")
            pipe.incr(f"stats:{clean_name}:views:h:{hour_str}")
            pipe.incr(f"stats:{clean_name}:views:d:{today_str}")
            pipe.expire(f"stats:{clean_name}:views:h:{hour_str}", 172800)
            pipe.expire(f"stats:{clean_name}:views:d:{today_str}", 864000)

        if user_id:
            uid_str = str(user_id)
            pipe.sadd(f"stats:{clean_name}:active:{today_str}", uid_str)
            pipe.sadd(f"stats:{clean_name}:active:h:{hour_str}", uid_str)
            pipe.sadd(f"stats:{clean_name}:active:d:{today_str}", uid_str)
            pipe.expire(f"stats:{clean_name}:active:{today_str}", 172800)
            pipe.expire(f"stats:{clean_name}:active:h:{hour_str}", 172800)
            pipe.expire(f"stats:{clean_name}:active:d:{today_str}", 864000)

        await pipe.execute()
    except Exception as e:
        logger.error(f"Error recording bot activity: {e}")
async def metrics_aggregator_worker():
    """
    Valkey-First Metrics Engine:
    1. Server startup par turant Valkey RAM se purana 24h data pull karta hai.
    2. Har 5 min me naya bucket banakar Valkey me commit karta hai (288 rolling points = 24 hours).
    3. Server RAM ke raw latencies snapshot ko turant delete/free kar deta hai.
    """
    global CURRENT_WINDOW_DATA, HISTORICAL_5MIN_METRICS
    logger.info("Metrics Aggregator Worker started.")

    # 1. STARTUP RESTORE: Valkey RAM se existing history turant RAM me restore karo
    try:
        raw_history = await valkey_client.get("server_metrics:history_5min")
        if raw_history:
            if isinstance(raw_history, bytes):
                raw_history = raw_history.decode('utf-8')
            saved_data = json.loads(raw_history)
            if isinstance(saved_data, list):
                HISTORICAL_5MIN_METRICS.clear()
                HISTORICAL_5MIN_METRICS.extend(saved_data[-288:])
                logger.info(f"✅ Valkey RAM se {len(HISTORICAL_5MIN_METRICS)} historical points restore ho gaye.")
    except Exception as init_err:
        logger.error(f"Valkey startup metrics restore error: {init_err}")

    while True:
        try:
            await asyncio.sleep(300) # 5-minute collection window

            # Local Window Snapshot lekar RAM reset karo
            async with METRICS_LOCK:
                snapshot = CURRENT_WINDOW_DATA
                CURRENT_WINDOW_DATA = {
                    'latencies': [],
                    'bot_requests': {},
                    'peak_concurrency': CURRENT_ACTIVE_REQUESTS,
                    'total_requests': 0
                }

            lats = snapshot.get('latencies', [])
            req_count = snapshot.get('total_requests', 0)

            if lats:
                avg_lat = round(sum(lats) / len(lats), 2)
                max_lat = round(max(lats), 2)
                min_lat = round(min(lats), 2)
                sorted_lats = sorted(lats)
                p95_idx = int(len(sorted_lats) * 0.95)
                p95_lat = round(sorted_lats[p95_idx], 2)
            else:
                avg_lat, max_lat, min_lat, p95_lat = 0.0, 0.0, 0.0, 0.0

            timestamp_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:00')

            bucket = {
                'timestamp': timestamp_str,
                'epoch': int(datetime.utcnow().timestamp()),
                'total_requests': req_count,
                'avg_latency_ms': avg_lat,
                'max_latency_ms': max_lat,
                'min_latency_ms': min_lat,
                'p95_latency_ms': p95_lat,
                'peak_concurrency': snapshot.get('peak_concurrency', 0),
                'bot_requests': snapshot.get('bot_requests', {})
            }

            # Server RAM se heavy raw latencies ko turant wipe karo
            del snapshot, lats

            HISTORICAL_5MIN_METRICS.append(bucket)

            # Valkey RAM me update karo (48 hours TTL taaki server band hone par bhi data rahe)
            try:
                metrics_json = json.dumps(list(HISTORICAL_5MIN_METRICS))
                await valkey_client.set("server_metrics:history_5min", metrics_json, ex=172800)
            except Exception as ce:
                logger.error(f"Valkey metrics write error: {ce}")

        except Exception as e:
            logger.error(f"Metrics aggregator worker error: {e}", exc_info=True)
            await asyncio.sleep(60)

async def get_metrics_for_webapp() -> list:
    """
    Web App Dashboard ko direct Valkey RAM se 24-hour metrics serve karta hai.
    Agar Valkey busy ho, tabhi fallback server RAM se lega.
    """
    try:
        raw_data = await valkey_client.get("server_metrics:history_5min")
        if raw_data:
            if isinstance(raw_data, bytes):
                raw_data = raw_data.decode('utf-8')
            return json.loads(raw_data)
    except Exception as e:
        logger.error(f"Error fetching metrics from Valkey for Web App: {e}")

    # Fallback agar Valkey se response na mile
    return list(HISTORICAL_5MIN_METRICS)

def generate_random_string(length):
    return uuid.uuid4().hex[:length]
class DBManager:
    @staticmethod
    def _get_safe_tablename(bot_username, suffix):
        """Table name ke liye bot_username ko safe banata hai."""
        # Username se non-alphanumeric characters ko underscore se replace karein
        safe_username = re.sub(r'[^a-zA-Z0-9_]', '_', bot_username)
        return f"{safe_username}_{suffix}"

    # --- PostgreSQL ke liye Naye Functions ---
    @staticmethod
    async def execute_pg_query(query, params=(), fetch=None):
        if not pg_pool:
            logger.error("PostgreSQL pool available nahi hai.")
            raise Exception("Database connection pool not initialized.")
        try:
            async with pg_pool.acquire() as conn:
                if fetch == 'one':
                    return await conn.fetchrow(query, *params)
                elif fetch == 'all':
                    return await conn.fetch(query, *params)
                else:
                    await conn.execute(query, *params)
                    return None # INSERT/UPDATE ke liye
        except Exception as e:
            logger.error(f"PostgreSQL error: {e} - Query: {query} - Params: {params}")
            raise

    # --- SQLite ke liye Purana Function (Siraf all_bots_list.db ke liye) ---
    # --- "Fake" SQLite Wrapper (Jo ab PostgreSQL use karega) ---
    @staticmethod
    async def execute_sqlite_query(db_path, query, params=(), fetch=None):
        """
        Yeh function ab SQLite use nahi karta. Yeh 'Controller' hai jo
        SQLite query (jo '?' use karti hai) ko PostgreSQL query (jo '$1, $2' use karti hai)
        mein convert karta hai aur main PG connection pool use karta hai.
        """
        if not pg_pool:
            logger.error("PostgreSQL pool available nahi hai (Wrapper call).")
            raise Exception("Database connection pool not initialized.")

        # 1. Convert '?' to '$1', '$2', '$3'...
        # Kyunki SQLite '?' use karta hai aur Postgres '$n'
        if '?' in query:
            parts = query.split('?')
            new_query = ""
            for i, part in enumerate(parts[:-1]):
                new_query += f"{part}${i+1}"
            new_query += parts[-1]
            query = new_query

        # 2. Query Execute karo using existing PG function
        try:
            async with pg_pool.acquire() as conn:
                if fetch == 'one':
                    # Postgres Record object return karta hai, jo tuple jaisa behave karta hai
                    # isliye code change karne ki zaroorat nahi padegi
                    return await conn.fetchrow(query, *params)
                elif fetch == 'all':
                    return await conn.fetch(query, *params)
                else:
                    await conn.execute(query, *params)
                    return None
        except Exception as e:
            logger.error(f"Wrapper converted query error: {e} - Original: {query}")
            raise

    # --- Initial Setup (Updated for PostgreSQL) ---
    # --- Initial Setup (Updated for PostgreSQL) ---
    @staticmethod
    async def setup_initial_dbs():
        # Ab hum 'bots' table ko PostgreSQL me banayenge
        query = """
        CREATE TABLE IF NOT EXISTS bots (
            username TEXT PRIMARY KEY,
            api_key TEXT NOT NULL,
            creator_id BIGINT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS support_messages (
            id SERIAL PRIMARY KEY,
            bot_username TEXT NOT NULL,
            admin_chat_id BIGINT NOT NULL,
            admin_message_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_support_msg_admin ON support_messages (admin_chat_id, admin_message_id, bot_username);
        CREATE INDEX IF NOT EXISTS idx_support_msg_created ON support_messages (created_at);
        """
        # Hum direct PG query function use kar rahe hain table banane ke liye
        await DBManager.execute_pg_query(query)
        logger.info("Table 'bots' and 'support_messages' ensured in PostgreSQL.")    
    
    # --- Clone Bot ke liye Tables banana (PostgreSQL) ---
    @staticmethod
    async def setup_clone_tables(bot_username):
        # Files Table
        files_table = DBManager._get_safe_tablename(bot_username, 'files')
        files_query = f"""
        CREATE TABLE IF NOT EXISTS {files_table} (
            share_id TEXT PRIMARY KEY,
            file_id TEXT,
            file_type TEXT NOT NULL
        );"""
        await DBManager.execute_pg_query(files_query)

        # Captions Table
        captions_table = DBManager._get_safe_tablename(bot_username, 'captions')
        captions_query = f"""
        CREATE TABLE IF NOT EXISTS {captions_table} (
            share_id TEXT PRIMARY KEY,
            caption TEXT NOT NULL
        );"""
        await DBManager.execute_pg_query(captions_query)

        # Multi-files Table
        multi_files_table = DBManager._get_safe_tablename(bot_username, 'multi_files')
        multi_files_query = f"""
        CREATE TABLE IF NOT EXISTS {multi_files_table} (
            multi_share_id TEXT PRIMARY KEY,
            share_ids TEXT NOT NULL
        );"""
        await DBManager.execute_pg_query(multi_files_query)

        # Settings Table
        settings_table = DBManager._get_safe_tablename(bot_username, 'settings')
        settings_query = f"""
        CREATE TABLE IF NOT EXISTS {settings_table} (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );"""
        await DBManager.execute_pg_query(settings_query)
        
        # Default settings daalna
        # Default settings daalna
        # Default settings daalna
        default_settings = [
            ('protected', json.dumps(True)), ('deletion', json.dumps(False)),
            ('deletion_time', json.dumps(7200)), ('admins', json.dumps([])),
            ('fsub_channels', json.dumps([])), ('footer', json.dumps('')),
            ('ad_api_link', json.dumps('')), ('ad_tutorial_link', json.dumps('')),
            ('welcome_message', json.dumps('')), ('custom_button_name', json.dumps('')),
            ('custom_button_url', json.dumps('')), ('paid_messages_enabled', json.dumps(True)),
            ('super_broadcast_enabled', json.dumps(False)),
            ('super_broadcast_msg_id', json.dumps(None)),
            ('super_broadcast_chat_id', json.dumps(None)),
            ('free_limit', json.dumps(0))
        ]        
        for key, value in default_settings:
            await DBManager.execute_pg_query(
                f"INSERT INTO {settings_table} (key, value) VALUES ($1, $2) ON CONFLICT (key) DO NOTHING",
                (key, value)
            )

        # Users Table
        users_table = DBManager._get_safe_tablename(bot_username, 'users')
        users_query = f"""
        CREATE TABLE IF NOT EXISTS {users_table} (
            user_id BIGINT PRIMARY KEY,
            membership_expiry TIMESTAMPTZ
        );"""
        await DBManager.execute_pg_query(users_query)
        
        # Premium Users Table
        premium_table = DBManager._get_safe_tablename(bot_username, 'premium')
        premium_query = f"""
        CREATE TABLE IF NOT EXISTS {premium_table} (
            user_id BIGINT PRIMARY KEY,
            expiry_time TIMESTAMPTZ
        );"""
        await DBManager.execute_pg_query(premium_query)

        # Unknown Payloads Table
        unknown_table = DBManager._get_safe_tablename(bot_username, 'unknown_payloads')
        unknown_query = f"""
        CREATE TABLE IF NOT EXISTS {unknown_table} (
            slug TEXT PRIMARY KEY,
            video_id TEXT NOT NULL
        );"""
        await DBManager.execute_pg_query(unknown_query)

        # Paid Messages Table (15-char payloads)
        # Paid Messages Table (15-char payloads)
        paid_msg_table = DBManager._get_safe_tablename(bot_username, 'paid_messages')
        paid_msg_query = f"""
        CREATE TABLE IF NOT EXISTS {paid_msg_table} (
            payload VARCHAR(15) PRIMARY KEY,
            file_id TEXT,
            file_type TEXT NOT NULL,
            caption TEXT,
            price NUMERIC(10, 2) NOT NULL DEFAULT 0,
            stars_price INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );"""
        await DBManager.execute_pg_query(paid_msg_query)
        try:
            await DBManager.execute_pg_query(f"ALTER TABLE {paid_msg_table} ADD COLUMN IF NOT EXISTS stars_price INTEGER DEFAULT 0;")
        except Exception:
            pass
        # Paid Messages Access Subtable
        # Paid Messages Access Subtable
        paid_access_table = DBManager._get_safe_tablename(bot_username, 'paid_msg_access')
        paid_access_query = f"""
        CREATE TABLE IF NOT EXISTS {paid_access_table} (
            payload VARCHAR(15) NOT NULL,
            user_id BIGINT NOT NULL,
            granted_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (payload, user_id)
        );"""
        await DBManager.execute_pg_query(paid_access_query)

        # Paid Channels Table (16-char payload)
        paid_channels_table = DBManager._get_safe_tablename(bot_username, 'paid_channels')
        paid_channels_query = f"""
        CREATE TABLE IF NOT EXISTS {paid_channels_table} (
            payload VARCHAR(16) PRIMARY KEY,
            channel_ids TEXT NOT NULL,
            price NUMERIC(10, 2) NOT NULL DEFAULT 0,
            stars_price INTEGER DEFAULT 0,
            demo_msg_id BIGINT,
            demo_chat_id BIGINT,
            is_paused BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );"""
        await DBManager.execute_pg_query(paid_channels_query)

        # Paid Channels Access Subtable
        paid_chan_access_table = DBManager._get_safe_tablename(bot_username, 'paid_channel_access')
        paid_chan_access_query = f"""
        CREATE TABLE IF NOT EXISTS {paid_chan_access_table} (
            id SERIAL PRIMARY KEY,
            payload VARCHAR(16) NOT NULL,
            user_id BIGINT NOT NULL,
            invite_links TEXT NOT NULL,
            granted_at TIMESTAMPTZ DEFAULT NOW()
        );"""
        await DBManager.execute_pg_query(paid_chan_access_query)
    # Join Request DB (Yeh pehle se hi PG use kar raha tha, to bas isko update kar rahe hain)    
    # Join Request DB (Yeh pehle se hi PG use kar raha tha, to bas isko update kar rahe hain)
    
    @staticmethod
    async def setup_join_request_db(bot_username, channel_id):
        if not pg_pool:
            logger.error("PG Pool available nahi hai, join request table nahi ban sakti.")
            return
        
        safe_channel_id = abs(channel_id)
        table_name = f"join_requests_{safe_channel_id}"
        
        query = f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            user_id BIGINT PRIMARY KEY
        );
        """
        await DBManager.execute_pg_query(query)
        logger.info(f"Table '{table_name}' for bot @{bot_username} successfully created/ensured in PostgreSQL.")
    @staticmethod
    async def setup_channel_ads_infrastructure():
        """Channel Ads Broadcast feature ke liye universal table banata hai."""
        query = """
        CREATE TABLE IF NOT EXISTS channel_ads_broadcast (
            id SERIAL PRIMARY KEY,
            bot_username TEXT NOT NULL,
            channel_id BIGINT NOT NULL,
            from_chat_id BIGINT NOT NULL,
            message_id BIGINT NOT NULL,
            interval_seconds INTEGER NOT NULL,
            next_run_at TIMESTAMPTZ NOT NULL,
            UNIQUE(bot_username, channel_id)
        );
        """
        await DBManager.execute_pg_query(query)
        logger.info("Table 'channel_ads_broadcast' ensured in PostgreSQL.")
    
    # --- PAYMENT FEATURE KE LIYE NAYE DB FUNCTIONS ---
    @staticmethod
    async def setup_payment_infrastructure():
        """Global tables jo payment system ke liye zaroori hain, unhe banata hai."""
        active_query = """
        CREATE TABLE IF NOT EXISTS active_upi_transactions (
            transaction_id BIGINT PRIMARY KEY,
            bot_username TEXT NOT NULL,
            admin_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            amount NUMERIC(10, 2) NOT NULL,
            plan_duration_days INTEGER NOT NULL,
            transaction_start_time TIMESTAMPTZ NOT NULL,
            upi_id TEXT NOT NULL,
            target_payload TEXT DEFAULT ''
        );
        """
        await DBManager.execute_pg_query(active_query)
        try:
            await DBManager.execute_pg_query("ALTER TABLE active_upi_transactions ADD COLUMN IF NOT EXISTS target_payload TEXT DEFAULT '';")
        except Exception:
            pass        
        # Unique transaction ID ke liye counter
        counter_query = """
        CREATE TABLE IF NOT EXISTS transaction_id_counter (
            singleton_key INT PRIMARY KEY DEFAULT 1,
            last_id BIGINT NOT NULL,
            CONSTRAINT singleton_check CHECK (singleton_key = 1)
        );
        """
        await DBManager.execute_pg_query(counter_query)

        # Universal Scammer List Table (Shared across all clone bots)
        # Universal Scammer List Table (Shared across all clone bots)
        scammer_table_query = """
        CREATE TABLE IF NOT EXISTS scammer_users (
            user_id BIGINT PRIMARY KEY,
            reason TEXT DEFAULT 'AI approved payment reversed by admin',
            bot_username TEXT,
            flagged_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
        await DBManager.execute_pg_query(scammer_table_query)

        # AI-Approved Transactions Tracker Table
        # AI-Approved Transactions Tracker Table
        ai_tx_query = """
        CREATE TABLE IF NOT EXISTS ai_approved_transactions (
            transaction_id BIGINT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            target_payload TEXT DEFAULT '',
            sent_message_id BIGINT,
            approved_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
        await DBManager.execute_pg_query(ai_tx_query)
        try:
            await DBManager.execute_pg_query("ALTER TABLE ai_approved_transactions ADD COLUMN IF NOT EXISTS target_payload TEXT DEFAULT '';")
            await DBManager.execute_pg_query("ALTER TABLE ai_approved_transactions ADD COLUMN IF NOT EXISTS sent_message_id BIGINT;")
            await DBManager.execute_pg_query("ALTER TABLE active_upi_transactions ADD COLUMN IF NOT EXISTS plan_duration_seconds INTEGER DEFAULT 0;")
        except Exception:
            pass

        # Pehli baar counter set karna
        # Pehli baar counter set karna
        # Admin Commission Billing Tables
        admin_bill_query = """
        CREATE TABLE IF NOT EXISTS admin_bills (
            creator_id BIGINT PRIMARY KEY,
            total_sales NUMERIC(12, 2) DEFAULT 0.0,
            total_bill NUMERIC(12, 2) DEFAULT 0.0,
            total_paid NUMERIC(12, 2) DEFAULT 0.0,
            pending_bill NUMERIC(12, 2) DEFAULT 0.0,
            is_locked BOOLEAN DEFAULT FALSE,
            last_checked_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS admin_bill_payments (
            id SERIAL PRIMARY KEY,
            creator_id BIGINT NOT NULL,
            amount NUMERIC(10, 2) NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
        await DBManager.execute_pg_query(admin_bill_query)

        # Pehli baar counter set karna
        await DBManager.execute_pg_query(
            "INSERT INTO transaction_id_counter (last_id) VALUES (1000000000) ON CONFLICT DO NOTHING;"
        )
        logger.info("Payment infrastructure tables (active_transactions, scammer_users, ai_approved_txs, id_counter, admin_bills) safaltapoorvak banaye gaye.")    
    @staticmethod
    async def get_next_transaction_id():
        """Atomically agla unique transaction ID return karta hai."""
        query = "UPDATE transaction_id_counter SET last_id = last_id + 1 RETURNING last_id;"
        result = await DBManager.execute_pg_query(query, fetch='one')
        if result:
            return result['last_id']
        raise Exception("Transaction ID generate nahi ho paya.")

    @staticmethod
    async def setup_bot_payment_tables(bot_username):
        """Har bot ke liye uske successful aur failed transaction tables banata hai."""
        safe_bot_username = DBManager._get_safe_tablename(bot_username, '')

        # Successful transactions
        success_table = f"{safe_bot_username}successful_transactions"
        success_query = f"""
        CREATE TABLE IF NOT EXISTS {success_table} (
            transaction_id BIGINT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            amount NUMERIC(10, 2) NOT NULL,
            plan_duration_days INTEGER NOT NULL,
            completion_time TIMESTAMPTZ NOT NULL,
            target_payload TEXT DEFAULT '',
            sent_message_id BIGINT
        );
        """
        await DBManager.execute_pg_query(success_query)
        try:
            await DBManager.execute_pg_query(f"ALTER TABLE {success_table} ADD COLUMN IF NOT EXISTS target_payload TEXT DEFAULT '';")
            await DBManager.execute_pg_query(f"ALTER TABLE {success_table} ADD COLUMN IF NOT EXISTS sent_message_id BIGINT;")
        except Exception:
            pass

        # Failed transactions
        # Failed transactions
        failed_table = f"{safe_bot_username}failed_transactions"
        failed_query = f"""
        CREATE TABLE IF NOT EXISTS {failed_table} (
            transaction_id BIGINT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            amount NUMERIC(10, 2) NOT NULL,
            plan_duration_days INTEGER NOT NULL,
            failure_time TIMESTAMPTZ NOT NULL,
            target_payload TEXT DEFAULT '',
            sent_message_id BIGINT
        );
        """
        await DBManager.execute_pg_query(failed_query)
        try:
            await DBManager.execute_pg_query(f"ALTER TABLE {success_table} ADD COLUMN IF NOT EXISTS target_payload TEXT DEFAULT '';")
            await DBManager.execute_pg_query(f"ALTER TABLE {success_table} ADD COLUMN IF NOT EXISTS sent_message_id BIGINT;")
            await DBManager.execute_pg_query(f"ALTER TABLE {success_table} ADD COLUMN IF NOT EXISTS plan_duration_seconds INTEGER DEFAULT 0;")
            await DBManager.execute_pg_query(f"ALTER TABLE {success_table} ADD COLUMN IF NOT EXISTS currency TEXT DEFAULT 'INR';")
            await DBManager.execute_pg_query(f"ALTER TABLE {failed_table} ADD COLUMN IF NOT EXISTS target_payload TEXT DEFAULT '';")
            await DBManager.execute_pg_query(f"ALTER TABLE {failed_table} ADD COLUMN IF NOT EXISTS sent_message_id BIGINT;")
            await DBManager.execute_pg_query(f"ALTER TABLE {failed_table} ADD COLUMN IF NOT EXISTS plan_duration_seconds INTEGER DEFAULT 0;")
            await DBManager.execute_pg_query(f"ALTER TABLE {failed_table} ADD COLUMN IF NOT EXISTS currency TEXT DEFAULT 'INR';")
        except Exception:
            pass        
        logger.info(f"Payment tables for @{bot_username} successfully created/ensured.")    
    # --- PAYMENT FEATURE FUNCTIONS KHATAM ---

    # --- NAYA SMART DELETION SCHEDULER INFRASTRUCTURE ---
    @staticmethod
    async def setup_deletion_infrastructure():
        """
        Ek single, smart table banata hai jo deletions ko 'job queue' ki tarah manage karega.
        Sequence ke duplicate hone wale error ko handle karta hai.
        """
        table_query = """
        CREATE TABLE IF NOT EXISTS scheduled_deletions (
            id SERIAL PRIMARY KEY,
            bot_username TEXT NOT NULL,
            chat_id BIGINT NOT NULL,
            message_id BIGINT NOT NULL,
            delete_at TIMESTAMPTZ NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            retry_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT
        );
        """
        index_query = """
        CREATE INDEX IF NOT EXISTS idx_deletions_status_delete_at
        ON scheduled_deletions (status, delete_at)
        WHERE (status = 'pending');
        """
        
        try:
            # Table banane ki koshish karo
            await DBManager.execute_pg_query(table_query)
            logger.info("Table 'scheduled_deletions' created or already exists.")
            
            # Index banane ki koshish karo
            await DBManager.execute_pg_query(index_query)
            logger.info("Index 'idx_deletions_status_delete_at' created or already exists.")
            
        except asyncpg.exceptions.UniqueViolationError as e:
            # Sirf sequence ke duplicate hone wale error ko pakdo aur ignore karo
            if "scheduled_deletions_id_seq" in str(e):
                logger.warning(f"Sequence 'scheduled_deletions_id_seq' pehle se मौजूद hai. Maan rahe hain ki table theek hai. Error: {e}")
            else:
                # Agar koi aur UniqueViolationError hai, toh use raise karo
                logger.error(f"Deletion infrastructure banate waqt unexpected UniqueViolationError: {e}")
                raise e # Re-raise the error if it's not the sequence issue
        except Exception as e:
            # Baaki sabhi errors ko log karo aur raise karo
            logger.error(f"Deletion infrastructure banate waqt error: {e}")
            raise e # Re-raise other errors
            
    # --- NAYA DELETION SCHEDULER INFRASTRUCTURE KHATAM ---

    # --- PAYMENT FEATURE FUNCTIONS KHATAM ---
# YEH NAYA FUNCTION ADD KAREIN
# --- ADD THIS GLOBALLY AFTER DBManager CLASS ---

# --- ADD THIS GLOBALLY AFTER DBManager CLASS ---
async def process_cashfree_success(transaction_id: int, webhook_data: dict = None):
    if not pg_pool: return False
    try:
        async with pg_pool.acquire() as conn:
            tx_data = await conn.fetchrow("SELECT * FROM active_upi_transactions WHERE transaction_id = $1", transaction_id)
            if not tx_data:
                return False
            
            admin_id = tx_data['admin_id']
            bot_username = tx_data['bot_username']
            user_id = tx_data['user_id']
            amount = tx_data['amount']
            days = tx_data['plan_duration_days']
            target_payload = tx_data.get('target_payload') if 'target_payload' in tx_data else ''

            safe_bot_table = DBManager._get_safe_tablename(bot_username, '')
            sent_msg_id = None
            
        bot = await get_bot_instance(bot_username, force_initialize=True)

        # Agar yeh Paid Message transaction hai
        # Agar yeh Paid Message ya Paid Channel transaction hai
        if target_payload:
            logic_obj = BotLogic(bot_username, {})
            logic_obj.bot = bot
            logic_obj.chat_id = user_id
            logic_obj.user_id = user_id

            if len(target_payload) == 16:
                # 📢 16-Char Paid Channel
                await logic_obj.deliver_paid_channel_access(bot_username, user_id, target_payload)
            else:
                # 📩 15-Char Paid Message
                paid_access_table = DBManager._get_safe_tablename(bot_username, 'paid_msg_access')
                await DBManager.execute_pg_query(
                    f"INSERT INTO {paid_access_table} (payload, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                    (target_payload, user_id)
                )
                if bot:
                    await bot.send_message(user_id, "✅ **Payment Verified!**\n\nAapko is paid message ka access mil gaya hai. Neeche aapka message bheja ja raha hai:", parse_mode='Markdown')
                    sent_msg = await logic_obj.send_paid_message_to_user(target_payload)
                    if sent_msg:
                        sent_msg_id = sent_msg.message_id
            
            async with pg_pool.acquire() as conn:
                await conn.execute(f"INSERT INTO {safe_bot_table}successful_transactions (transaction_id, user_id, amount, plan_duration_days, completion_time, target_payload, sent_message_id) VALUES ($1, $2, $3, $4, NOW(), $5, $6)", transaction_id, user_id, amount, days, target_payload or '', sent_msg_id)
                await conn.execute("DELETE FROM active_upi_transactions WHERE transaction_id = $1", transaction_id)        
        
        else:
            async with pg_pool.acquire() as conn:
                await conn.execute(f"INSERT INTO {safe_bot_table}successful_transactions (transaction_id, user_id, amount, plan_duration_days, completion_time, target_payload, sent_message_id) VALUES ($1, $2, $3, $4, NOW(), $5, $6)", transaction_id, user_id, amount, days, target_payload or '', None)
                await conn.execute("DELETE FROM active_upi_transactions WHERE transaction_id = $1", transaction_id)
            
            # Regular Premium Transaction Logic
            # Regular Premium Transaction Logic
            premium_table = DBManager._get_safe_tablename(bot_username, 'premium')
            duration_sec = tx_data.get('plan_duration_seconds', 0) if 'plan_duration_seconds' in tx_data else 0
            interval_str = f"{duration_sec} seconds" if duration_sec and duration_sec > 0 else f"{days} days"
            
            pg_query = f"""
            INSERT INTO {premium_table} (user_id, expiry_time) VALUES ($1, NOW() + INTERVAL '{interval_str}')
            ON CONFLICT (user_id) DO UPDATE SET expiry_time = 
                CASE 
                    WHEN {premium_table}.expiry_time < NOW() THEN NOW() + INTERVAL '{interval_str}'
                    ELSE {premium_table}.expiry_time + INTERVAL '{interval_str}'
                END;
            """
            await DBManager.execute_pg_query(pg_query, (user_id,))            
            # Auto Sync Premium
            creator_res = await DBManager.execute_sqlite_query(ALL_BOTS_DB, "SELECT creator_id FROM bots WHERE username=?", (bot_username,), fetch='one')
            if creator_res:
                creator_id = creator_res[0]
                bots = await DBManager.execute_sqlite_query(ALL_BOTS_DB, "SELECT username FROM bots WHERE creator_id=?", (creator_id,), fetch='all')
                for b in bots:
                    b_uname = b[0]
                    if b_uname == bot_username: continue
                    settings_table = DBManager._get_safe_tablename(b_uname, 'settings')
                    sync_data = await DBManager.execute_pg_query(f"SELECT value FROM {settings_table} WHERE key='premium_sync_enabled'", fetch='one')
                    if sync_data and json.loads(sync_data['value']):
                        prem_t = DBManager._get_safe_tablename(b_uname, 'premium')
                        q = f"""
                        INSERT INTO {prem_t} (user_id, expiry_time) VALUES ($1, NOW() + INTERVAL '{days} days')
                        ON CONFLICT (user_id) DO UPDATE SET expiry_time = 
                            CASE 
                                WHEN {prem_t}.expiry_time < NOW() THEN NOW() + INTERVAL '{days} days'
                                ELSE {prem_t}.expiry_time + INTERVAL '{days} days'
                            END;
                        """
                        await DBManager.execute_pg_query(q, (user_id,))

            dur_sec_notify = tx_data.get('plan_duration_seconds', 0) if 'plan_duration_seconds' in tx_data else 0
            label_notify = f"{dur_sec_notify // 3600} Hours" if dur_sec_notify and dur_sec_notify < 86400 else f"{days} Days"
            if bot:
                await bot.send_message(user_id, f"✅ **Payment Verified!**\n\nAapka payment safaltapoorvak verify ho gaya hai. Aapko {label_notify} ka premium mil gaya hai!", parse_mode='Markdown')
        # --- NAYA: ADMIN NOTIFICATION LOGIC ---
        if bot and admin_id:
            try:
                cf_extra = ""
                # Agar webhook data bheja gaya hai toh use parse karo
                if webhook_data and "data" in webhook_data and "payment" in webhook_data["data"]:
                    pay_info = webhook_data["data"]["payment"]
                    cf_payment_id = pay_info.get("cf_payment_id", "N/A")
                    bank_ref = pay_info.get("bank_reference", "N/A")
                    pay_group = pay_info.get("payment_group", "N/A")
                    
                    cf_extra = (
                        f"\n<b>🏦 Bank Ref:</b> <code>{bank_ref}</code>\n"
                        f"<b>💳 CF Payment ID:</b> <code>{cf_payment_id}</code>\n"
                        f"<b>📱 Method:</b> {str(pay_group).upper()}"
                    )
                    
                    if "customer_details" in webhook_data["data"]:
                        phone = webhook_data["data"]["customer_details"].get("customer_phone")
                        if phone:
                            cf_extra += f"\n<b>📞 Customer Phone:</b> {phone}"

                item_type = f"Paid Message ({target_payload})" if target_payload else f"{label_notify} Premium"                
                
                
                
                admin_msg = (
                    f"💳 <b>New Cashfree Payment Received!</b>\n\n"
                    f"<b>Bot:</b> @{bot_username}\n"
                    f"<b>User ID:</b> <code>{user_id}</code>\n"
                    f"<b>Order ID:</b> <code>txn_{transaction_id}</code>\n"
                    f"<b>Amount:</b> ₹{amount}\n"
                    f"<b>Item:</b> {item_type}{cf_extra}\n\n"
                    f"<i>✅ System ne payment verify karke user ko access de diya hai. Agar ye payment suspicious lagti hai, toh aap neeche diye gaye button se access Cancel kar sakte hain.</i>"
                )
                
                admin_keyboard = [
                    [InlineKeyboardButton("↩️ Cancel Premium (Reverse)", callback_data=f"admin_cancel_premium_{transaction_id}")]
                ]
                
                await bot.send_message(
                    chat_id=admin_id,
                    text=admin_msg,
                    reply_markup=InlineKeyboardMarkup(admin_keyboard),
                    parse_mode=ParseMode.HTML
                )
            except Exception as notify_e:
                logger.error(f"Failed to send Cashfree success notification to admin {admin_id}: {notify_e}")

        return True
    except Exception as e:
        logger.error(f"Process CF success error: {e}")
        return False
async def continuous_smooth_user_sync_worker():
    """
    Valkey-Based Background Worker:
    1. Valkey (Redis) se pending users SPOP (atomic pop) karke nikalta hai.
    2. Bot-by-bot smoothly DB me write karta hai.
    3. DB fail hone par wapas Valkey me daal deta hai taaki data loss na ho.
    """
    logger.info("Valkey Smooth User Sync Worker shuru ho gaya hai.")
    while True:
        try:
            if not pg_pool:
                await asyncio.sleep(10)
                continue

            # Valkey se saare pending_users ke keys dhoondo
            raw_keys = await valkey_client.keys("pending_users:*")
            if not raw_keys:
                await asyncio.sleep(300)
                continue

            for key in raw_keys:
                key_str = key.decode('utf-8') if isinstance(key, bytes) else str(key)
                bot_username = key_str.split(":", 1)[1]

                # Valkey se ek baar me max 10,000 users nikal lo aur Set se hata do (Atomic Read + Delete)
                uids = await valkey_client.spop(key_str, 10000)
                if not uids:
                    continue

                try:
                    users_table = DBManager._get_safe_tablename(bot_username, 'users')
                    query = f"INSERT INTO {users_table} (user_id) VALUES ($1) ON CONFLICT (user_id) DO NOTHING"
                    
                    # Valkey return values bytes/string hoti hain, ishe integer me convert karein
                    uids_int = [int(uid) for uid in uids]
                    
                    # 100-100 ke chunks me DB me write karo
                    chunk_size = 100
                    for i in range(0, len(uids_int), chunk_size):
                        chunk = [(uid,) for uid in uids_int[i:i + chunk_size]]
                        async with pg_pool.acquire() as conn:
                            await conn.executemany(query, chunk)
                        await asyncio.sleep(0.05) # DB ko saans lene ke liye micro-pause

                except Exception as bot_err:
                    logger.error(f"Error syncing users from Valkey for @{bot_username}: {bot_err}")
                    # Agar PostgreSQL fail ho gaya, toh users ko wapas Valkey queue me daal do
                    if uids:
                        await valkey_client.sadd(key_str, *uids)

            # Saara data process hone ke baad agle batch ke liye 5 minute wait
            await asyncio.sleep(300)

        except Exception as e:
            logger.error(f"Valkey User sync worker loop error: {e}", exc_info=True)
            await asyncio.sleep(60)
# -----------------------------------------------
# background.py mein yeh naye imports add karein (file ke shuru mein)
import psutil
from datetime import datetime

# Yeh poora naya function background.py mein add karein
# Yeh poora naya function background.py mein add karein
async def run_cache_cleanup_and_ram_monitor():
    """
    Ek background task jo Valkey/Redis stats ko monitor karke 
    admin ko regular reports bhejta hai, jisme active cached users bhi shamil hain.
    """
    logger.info("Valkey Server Health Monitor service shuru ho gayi hai.")
    
    REPORT_INTERVAL_SECONDS = 3600 # Har 1 ghante me report bhejega
    time_since_last_report = 0

    while True:
        try:
            check_interval = 300
            await asyncio.sleep(check_interval)
            time_since_last_report += check_interval
            
            if time_since_last_report >= REPORT_INTERVAL_SECONDS:
                # Valkey/Redis ki jaankari collect karo
                info = await valkey_client.info()
                
                # Cache me active (membership) users count nikalein
                active_keys = await valkey_client.keys("membership:*")
                active_cached_users = len(active_keys)

                used_memory = info.get('used_memory_human', 'N/A')
                peak_memory = info.get('used_memory_peak_human', 'N/A')
                connected_clients = info.get('connected_clients', 'N/A')
                uptime_days = info.get('uptime_in_days', 'N/A')
                keyspace_hits = info.get('keyspace_hits', 0)
                keyspace_misses = info.get('keyspace_misses', 0)
                
                total_lookups = keyspace_hits + keyspace_misses
                hit_rate = (keyspace_hits / total_lookups * 100) if total_lookups > 0 else 0

                # --- ADVANCED DB TRACKER (WITH QUERY DETAILS) ---
                db_stats_str = "<b>🗄️ DB Connection Details:</b>\n"
                if pg_pool:
                    try:
                        async with pg_pool.acquire() as conn:
                            # Hum connection ka state aur aakhri query ka 45 chars nikal rahe hain
                            q = """
                            SELECT state, 
                                   SUBSTRING(query FROM 1 FOR 45) as short_query, 
                                   COUNT(*) as count 
                            FROM pg_stat_activity 
                            WHERE datname = current_database() AND pid <> pg_backend_pid()
                            GROUP BY state, short_query
                            ORDER BY count DESC
                            LIMIT 15;
                            """
                            db_res = await conn.fetch(q)
                            if db_res:
                                for row in db_res:
                                    st = row['state'] if row['state'] else "unknown"
                                    # Query formatting for Telegram HTML
                                    sq = row['short_query'].replace('\n', ' ').strip() if row['short_query'] else "No Query"
                                    sq = sq.replace('<', '&lt;').replace('>', '&gt;')
                                    db_stats_str += f"   • [{st}] <code>{row['count']}x</code> : <i>{sq}...</i>\n"
                            else:
                                db_stats_str += "   • No active data found.\n"
                    except Exception as db_e:
                        db_stats_str += f"   • Error fetching DB stats: {db_e}\n"
                else:
                    db_stats_str += "   • DB Pool not active.\n"

                report_message = (
                    f"📊 <b>System & Cache Health Report</b> 📊\n\n"
                    f"📅 <b>Timestamp:</b> <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>\n\n"
                    f"👥 <b>Active Users in Cache:</b> <code>{active_cached_users}</code>\n\n"
                    f"{db_stats_str}\n"
                    f"🧠 <b>Valkey Memory Usage:</b>\n"
                    f"   • <b>Used Memory:</b> <code>{used_memory}</code>\n"
                    f"   • <b>Peak Memory:</b> <code>{peak_memory}</code>\n\n"
                    f"📈 <b>Performance Stats:</b>\n"
                    f"   • <b>Connected Clients:</b> <code>{connected_clients}</code>\n"
                    f"   • <b>Cache Hit Rate:</b> <code>{hit_rate:.2f}%</code>\n"
                    f"   • <b>Uptime:</b> <code>{uptime_days} days</code>"
                )                
                await notify_admin(report_message)                
                time_since_last_report = 0

        except Exception as e:
            logger.error(f"Valkey Health Monitor task mein error aaya: {e}", exc_info=True)

# --- NAYA SMART DELETION PROCESSOR FUNCTION ---
# --- ULTRA LIGHT VALKEY DELETION PROCESSOR (0 DB LOAD) ---
async def process_scheduled_deletions():
    """
    Valkey Sorted Set (ZSET) se expired deletion jobs fetch karke process karta hai.
    PostgreSQL database connection pool ko bilkul touch nahi karta.
    """
    try:
        import time
        now = time.time()

        # Jo jobs expire ho chuke hain (score <= now), unhe Valkey se nikalo (Batch limit 50)
        jobs_raw = await valkey_client.zrangebyscore("valkey_scheduled_deletions", 0, now, start=0, num=50)
        if not jobs_raw:
            return

        # Turant Valkey se remove kar do taaki agle cycle me duplicate run na ho
        await valkey_client.zrem("valkey_scheduled_deletions", *jobs_raw)

        for job_str in jobs_raw:
            try:
                # Agar bytes format me aaya ho toh decode karein
                if isinstance(job_str, bytes):
                    job_str = job_str.decode('utf-8')
                job = json.loads(job_str)

                bot_username = job['bot']
                chat_id = job['chat']
                message_id = job['msg']

                bot_instance = await get_bot_instance(bot_username, force_initialize=True)
                if not bot_instance:
                    continue

                await bot_instance.delete_message(chat_id, message_id)

            except TelegramError as te:
                err_str = str(te).lower()
                # Agar flood wait ho, toh Valkey ZSET me dobara daal do retry time ke sath
                if "flood control exceeded" in err_str or "too many requests" in err_str:
                    retry_after = getattr(te, 'retry_after', 60)
                    retry_time = time.time() + retry_after + 5
                    await valkey_client.zadd("valkey_scheduled_deletions", {job_str: retry_time})
                # Baaki cases (message already deleted, etc.) me kuch nahi karna
            except Exception as e:
                logger.error(f"Valkey deletion task execute error: {e}")

    except Exception as e:
        logger.error(f"Error in process_scheduled_deletions (Valkey): {e}")

async def process_channel_ads_broadcast():
    """
    Har 5 minute me chalta hai:
    1. Render URL ko ping karta hai.
    2. DB check karke channel ads broadcast execute karta hai.
    """
    # 1. External Render API Keep-Alive Ping (Response ignore hoga)
    try:
        async with httpx.AsyncClient() as client:
            await client.get("https://videopl.onrender.com/verify?user_id=8471795595", timeout=10)
    except Exception as ping_e:
        logger.warning(f"Keep-alive ping error (safely ignored): {ping_e}")

    # 2. Database & Broadcast Check
    if not pg_pool:
        return
    try:
        query = """
        SELECT id, bot_username, channel_id, from_chat_id, message_id, interval_seconds
        FROM channel_ads_broadcast
        WHERE next_run_at <= NOW()
        """
        due_ads = await DBManager.execute_pg_query(query, fetch='all')
        if not due_ads:
            return

        for ad in due_ads:
            ad_id = ad['id']
            b_uname = ad['bot_username']
            c_id = ad['channel_id']
            f_chat_id = ad['from_chat_id']
            m_id = ad['message_id']
            interval_sec = ad['interval_seconds']

            bot_inst = await get_bot_instance(b_uname, force_initialize=True)
            if not bot_inst:
                continue

            try:
                # Silent Broadcast: disable_notification=True add kiya gaya hai
                await bot_inst.copy_message(
                    chat_id=c_id, 
                    from_chat_id=f_chat_id, 
                    message_id=m_id, 
                    disable_notification=True
                )
                # Next run time update karo
                update_q = f"""
                UPDATE channel_ads_broadcast 
                SET next_run_at = NOW() + INTERVAL '{interval_sec} seconds'
                WHERE id = $1
                """
                await DBManager.execute_pg_query(update_q, (ad_id,))            
            except TelegramError as te:
                err_str = str(te).lower()
                logger.warning(f"Ad broadcast error for @{b_uname} in channel {c_id}: {te}")
                # Agar permission error ya bot kicked error ho
                if any(x in err_str for x in ["forbidden", "not enough rights", "chat not found", "bot was kicked", "have no rights"]):
                    await DBManager.execute_pg_query("DELETE FROM channel_ads_broadcast WHERE id = $1", (ad_id,))
                    creator_data = await DBManager.execute_sqlite_query(ALL_BOTS_DB, "SELECT creator_id FROM bots WHERE username=?", (b_uname,), fetch='one')
                    if creator_data and creator_data[0]:
                        try:
                            await bot_inst.send_message(
                                creator_data[0],
                                f"⚠️ **Channel Ad Broadcast Error**\n\nChannel ID: `{c_id}`\n\nError: `{te}`\n\nBot ko message send karne ki permission na hone ki wajah se is channel ko Ad Broadcast list se hata diya gaya hai."
                            )
                        except Exception:
                            pass
            except Exception as gen_e:
                logger.error(f"General error in channel ad broadcast for @{b_uname}: {gen_e}")

    except Exception as e:
        logger.error(f"Error in process_channel_ads_broadcast: {e}", exc_info=True)


async def process_support_messages_cleanup():
    """Har 24 ghante me 2 month (60 days) se purane message mappings ko delete karta hai."""
    if not pg_pool:
        return
    try:
        query = "DELETE FROM support_messages WHERE created_at < NOW() - INTERVAL '60 days';"
        await DBManager.execute_pg_query(query)
        logger.info("2-month old support message mappings cleaned up successfully.")
    except Exception as e:
        logger.error(f"Error during support messages cleanup: {e}")

async def get_creator_billing_stats(creator_id: int):
    """
    Admin ke sabhi clone bots ki real-time sales, 8% commission aur advance payments calculate karta hai.
    Chahe setting on ho ya off, agar sales hui hain toh accurate bill dikhayega.
    """
    if not pg_pool or not creator_id:
        return {
            'creator_id': creator_id,
            'total_sales': 0.0,
            'total_bill': 0.0,
            'total_paid': 0.0,
            'pending_bill': 0.0,
            'advance_balance': 0.0,
            'is_advance': False,
            'is_locked': False,
            'paid_enabled': False,
            'status_label': 'Clean'
        }

    bots = await DBManager.execute_sqlite_query(ALL_BOTS_DB, "SELECT username FROM bots WHERE creator_id=?", (creator_id,), fetch='all')
    if not bots:
        return {
            'creator_id': creator_id,
            'total_sales': 0.0,
            'total_bill': 0.0,
            'total_paid': 0.0,
            'pending_bill': 0.0,
            'advance_balance': 0.0,
            'is_advance': False,
            'is_locked': False,
            'paid_enabled': False,
            'status_label': 'Clean'
        }

    total_sales = 0.0
    paid_enabled_found = False

    for b in bots:
        b_name = b[0].split('#')[0]
        settings_table = DBManager._get_safe_tablename(b_name, 'settings')
        safe_bot = DBManager._get_safe_tablename(b_name, '')
        success_table = f"{safe_bot}successful_transactions"

        # Check agar paid settings active hain
        try:
            val = await DBManager.execute_pg_query(f"SELECT value FROM {settings_table} WHERE key='paid_enabled'", fetch='one')
            if val:
                try:
                    is_en = json.loads(val['value'])
                except Exception:
                    is_en = bool(val['value'])
                if is_en:
                    paid_enabled_found = True
        except Exception:
            pass

        # Real-time sales calculate karo chahe setting toggle kuch bhi ho
        try:
            sales_row = await DBManager.execute_pg_query(
                f"SELECT COALESCE(SUM(CASE WHEN currency = 'XTR' THEN amount * 1.2 ELSE amount END), 0) as total FROM {success_table}",
                fetch='one'
            )
            if sales_row:
                total_sales += float(sales_row['total'])
        except Exception:
            pass

    total_commission = round(total_sales * 0.08, 2)
    bill_row = await DBManager.execute_pg_query("SELECT total_paid, is_locked FROM admin_bills WHERE creator_id = $1", (creator_id,), fetch='one')
    total_paid = float(bill_row['total_paid']) if bill_row else 0.0
    is_locked = bool(bill_row['is_locked']) if bill_row else False

    # Difference calculate karein
    net_difference = round(total_commission - total_paid, 2)

    is_advance = False
    advance_balance = 0.0
    pending_bill = 0.0

    if net_difference < 0:
        # User ne advance payment kiya hai
        is_advance = True
        advance_balance = abs(net_difference)
        pending_bill = net_difference  # Negative value bhej rahe hain frontend ke liye
        status_label = f"Advance Credit (₹{advance_balance:.2f})"
    elif net_difference > 0:
        pending_bill = net_difference
        status_label = "Payment Due" if pending_bill >= 100.0 else "Clean"
    else:
        status_label = "Clean"

    if is_locked:
        status_label = "Locked"

    return {
        'creator_id': creator_id,
        'total_sales': total_sales,
        'total_bill': total_commission,
        'total_paid': total_paid,
        'pending_bill': pending_bill,
        'advance_balance': advance_balance,
        'is_advance': is_advance,
        'is_locked': is_locked,
        'paid_enabled': paid_enabled_found,
        'status_label': status_label
    }
async def is_creator_purchases_locked(creator_id: int) -> bool:
    """Check karta hai ki creator ke bots pe naye purchases blocked hain ya nahi."""
    if not pg_pool or not creator_id:
        return False
    row = await DBManager.execute_pg_query("SELECT is_locked FROM admin_bills WHERE creator_id = $1", (creator_id,), fetch='one')
    return bool(row['is_locked']) if row else False


async def process_manual_premium_audit():
    """
    Har roz shaam 8:00 PM IST par manual premium grants ko audit karta hai.
    Sabhi violations ko batch karke Super Admin aur Clone Creators ko 
    ek single consolidated summary report bhejta hai taaki chat me spam na ho.
    """
    if not pg_pool:
        return

    logger.info("Running Daily 8:00 PM Manual Premium Audit...")
    try:
        raw_keys = await valkey_client.keys("manual_prem:*")
        if not raw_keys:
            return

        main_bot = await get_bot_instance(MAIN_BOT_USERNAME, force_initialize=True)
        super_admin_id = 6796088344

        # Creator-wise audit data collect karne ke liye dict
        # Format: {creator_id: {'total_added': 0.0, 'bots': set(), 'items': []}}
        creator_reports = {}
        all_flagged_for_super_admin = []

        for raw_k in raw_keys:
            k_str = raw_k.decode('utf-8') if isinstance(raw_k, bytes) else str(raw_k)
            clean_key = k_str.replace("manual_prem:", "", 1)
            grant_data = await CACHE_MANUAL_PREMIUM.get(clean_key)
            if not grant_data:
                continue

            bot_username = grant_data.get('bot_username')
            user_id = grant_data.get('user_id')
            days = grant_data.get('days', 7)
            admin_id = grant_data.get('admin_id')

            if not bot_username or not user_id:
                await CACHE_MANUAL_PREMIUM.delete(clean_key)
                continue

            safe_bot = DBManager._get_safe_tablename(bot_username, '')
            failed_table = f"{safe_bot}failed_transactions"
            success_table = f"{safe_bot}successful_transactions"

            await DBManager.setup_bot_payment_tables(bot_username)

            matched_tx = None
            tx_source = None
            tx_time = None

            # 1. Check active_upi_transactions
            try:
                active_tx = await DBManager.execute_pg_query(
                    "SELECT * FROM active_upi_transactions WHERE user_id = $1 AND bot_username = $2 AND transaction_start_time >= NOW() - INTERVAL '7 days' ORDER BY transaction_start_time DESC LIMIT 1",
                    (user_id, bot_username),
                    fetch='one'
                )
                if active_tx:
                    matched_tx = dict(active_tx)
                    tx_source = 'active'
                    tx_time = matched_tx.get('transaction_start_time')
            except Exception as ae:
                logger.warning(f"Error checking active_upi_transactions: {ae}")

            # 2. Check failed_transactions
            try:
                failed_tx = await DBManager.execute_pg_query(
                    f"SELECT * FROM {failed_table} WHERE user_id = $1 AND failure_time >= NOW() - INTERVAL '7 days' ORDER BY failure_time DESC LIMIT 1",
                    (user_id,),
                    fetch='one'
                )
                if failed_tx:
                    f_time = failed_tx.get('failure_time')
                    if not matched_tx or (f_time and tx_time and f_time > tx_time):
                        matched_tx = dict(failed_tx)
                        tx_source = 'failed'
            except Exception as fe:
                logger.warning(f"Error checking failed_transactions: {fe}")

            if matched_tx:
                # Price calculation
                settings_table = DBManager._get_safe_tablename(bot_username, 'settings')
                paid_settings_row = await DBManager.execute_pg_query(
                    f"SELECT value FROM {settings_table} WHERE key='paid_settings'",
                    fetch='one'
                )
                paid_info = {}
                if paid_settings_row:
                    try:
                        paid_info = json.loads(paid_settings_row['value'])
                    except Exception:
                        pass

                plan_price = 0.0
                if days == 7:
                    plan_price = float(paid_info.get('price_7') or 0.0)
                elif days in [28, 30]:
                    plan_price = float(paid_info.get('price_28') or 0.0)
                elif days == 90:
                    plan_price = float(paid_info.get('price_90') or 0.0)
                else:
                    for cp in paid_info.get('custom_plans', []):
                        if cp.get('seconds') == days * 86400 or str(days) in str(cp.get('label', '')):
                            plan_price = float(cp.get('price') or 0.0)
                            break

                if plan_price <= 0:
                    plan_price = float(matched_tx.get('amount', 0.0) or 0.0)

                # 1. Forceful Entry in Successful Transactions
                audit_txn_id = await DBManager.get_next_transaction_id()
                await DBManager.execute_pg_query(
                    f"""
                    INSERT INTO {success_table} 
                    (transaction_id, user_id, amount, plan_duration_days, completion_time, target_payload, currency)
                    VALUES ($1, $2, $3, $4, NOW(), '', 'INR')
                    ON CONFLICT DO NOTHING
                    """,
                    (audit_txn_id, user_id, plan_price, days)
                )

                # 2. Cleanup source record
                if tx_source == 'active':
                    await DBManager.execute_pg_query(
                        "DELETE FROM active_upi_transactions WHERE transaction_id = $1",
                        (matched_tx['transaction_id'],)
                    )
                elif tx_source == 'failed':
                    await DBManager.execute_pg_query(
                        f"DELETE FROM {failed_table} WHERE transaction_id = $1", 
                        (matched_tx['transaction_id'],)
                    )

                # 3. Find Creator ID & Buffer Data for Batched Report
                creator_res = await DBManager.execute_sqlite_query(
                    ALL_BOTS_DB, 
                    "SELECT creator_id FROM bots WHERE username=?", 
                    (bot_username,), 
                    fetch='one'
                )
                creator_id = creator_res[0] if creator_res else admin_id

                item_info = {
                    'bot': bot_username,
                    'user_id': user_id,
                    'days': days,
                    'price': plan_price,
                    'status': 'Unresolved QR' if tx_source == 'active' else 'Denied Tx'
                }

                if creator_id not in creator_reports:
                    creator_reports[creator_id] = {'total_added': 0.0, 'bots': set(), 'items': []}

                creator_reports[creator_id]['total_added'] += plan_price
                creator_reports[creator_id]['bots'].add(bot_username)
                creator_reports[creator_id]['items'].append(item_info)

                all_flagged_for_super_admin.append({**item_info, 'creator_id': creator_id})

            # Cache key cleanup
            await CACHE_MANUAL_PREMIUM.delete(clean_key)

        # -------------------------------------------------------------
        # BATCH NOTIFICATIONS: Har Creator ko sirf 1 Summary Message jayega
        # -------------------------------------------------------------
        for creator_id, c_data in creator_reports.items():
            # Billing recalculate
            stats = await get_creator_billing_stats(creator_id)
            if stats:
                tot_sales = stats['total_sales']
                tot_comm = stats['total_bill']
                tot_paid = stats['total_paid']
                pending = stats['pending_bill']
                should_lock = pending >= 200.0

                await DBManager.execute_pg_query(
                    """
                    INSERT INTO admin_bills (creator_id, total_sales, total_bill, total_paid, pending_bill, is_locked, last_checked_at)
                    VALUES ($1, $2, $3, $4, $5, $6, NOW())
                    ON CONFLICT (creator_id) DO UPDATE SET
                        total_sales = EXCLUDED.total_sales,
                        total_bill = EXCLUDED.total_bill,
                        total_paid = EXCLUDED.total_paid,
                        pending_bill = EXCLUDED.pending_bill,
                        is_locked = EXCLUDED.is_locked,
                        last_checked_at = NOW()
                    """,
                    (creator_id, tot_sales, tot_comm, tot_paid, pending, should_lock)
                )

            # Summary list text prepare karein
            items_text = ""
            for itm in c_data['items']:
                items_text += f"• User <code>{itm['user_id']}</code> (@{itm['bot']}) — {itm['days']}d — ₹{itm['price']:,.2f} ({itm['status']})\n"

            consolidated_warning = (
                f"⚠️ <b>Important Notice: Service Charge Audit Report</b> ⚠️\n\n"
                f"Our daily 8:00 PM audit detected <b>{len(c_data['items'])} unverified transaction(s)</b> where manual premium was granted.\n\n"
                f"<b>Flagged Accounts:</b>\n{items_text}\n"
                f"<b>Total Added to Sales:</b> ₹{c_data['total_added']:,.2f}\n"
                f"<b>Updated Pending Service Charge:</b> ₹{pending:,.2f}\n\n"
                f"<i>Please use automated verification to avoid service charge penalties or suspension.</i>"
            )

            # Sirf Main Bot se 1 warning message bhejo
            if main_bot:
                try:
                    await main_bot.send_message(creator_id, consolidated_warning, parse_mode=ParseMode.HTML)
                except Exception as e:
                    logger.error(f"Failed to send batched warning to creator {creator_id}: {e}")

        # Super Admin ke liye 1 Single Consolidated Alert
        if all_flagged_for_super_admin and main_bot:
            total_sum = sum(x['price'] for x in all_flagged_for_super_admin)
            admin_items_summary = ""
            for x in all_flagged_for_super_admin:
                admin_items_summary += f"• @{x['bot']} | Creator: <code>{x['creator_id']}</code> | User: <code>{x['user_id']}</code> | ₹{x['price']:,.2f} ({x['status']})\n"

            super_admin_summary = (
                f"🚨 <b>Daily Audit Summary: {len(all_flagged_for_super_admin)} Violations Detected</b> 🚨\n\n"
                f"{admin_items_summary}\n"
                f"<b>Total Forcefully Added:</b> ₹{total_sum:,.2f}\n\n"
                f"<i>All amounts have been added to respective bot sales & service charge bills.</i>"
            )
            try:
                await main_bot.send_message(super_admin_id, super_admin_summary, parse_mode=ParseMode.HTML)
            except Exception as se:
                logger.error(f"Failed to notify super admin summary: {se}")

    except Exception as e:
        logger.error(f"Error in process_manual_premium_audit: {e}", exc_info=True)

async def process_daily_bill_check():
    """Har roz shaam 8:00 PM IST (14:30 UTC) par pending bills evaluate karta hai."""
    if not pg_pool:
        return

    # --- NAYA: 8:00 PM IST par manual premium audit execute karein ---
    await process_manual_premium_audit()
    # -------------------------------------------------------------

    logger.info("Running daily 8:00 PM IST Commission Bill Check...")
    all_creators = await DBManager.execute_sqlite_query(ALL_BOTS_DB, "SELECT DISTINCT creator_id FROM bots", fetch='all')
    if not all_creators:
        return
    main_bot = await get_bot_instance(MAIN_BOT_USERNAME, force_initialize=True)

    for row in all_creators:
        creator_id = row[0]
        stats = await get_creator_billing_stats(creator_id)
        if not stats or not stats['paid_enabled']:
            continue

        pending = stats['pending_bill']
        total_sales = stats['total_sales']
        total_comm = stats['total_bill']
        total_paid = stats['total_paid']
        should_lock = pending >= 200.0

        await DBManager.execute_pg_query(
            """
            INSERT INTO admin_bills (creator_id, total_sales, total_bill, total_paid, pending_bill, is_locked, last_checked_at)
            VALUES ($1, $2, $3, $4, $5, $6, NOW())
            ON CONFLICT (creator_id) DO UPDATE SET
                total_sales = EXCLUDED.total_sales,
                total_bill = EXCLUDED.total_bill,
                total_paid = EXCLUDED.total_paid,
                pending_bill = EXCLUDED.pending_bill,
                is_locked = EXCLUDED.is_locked,
                last_checked_at = NOW()
            """,
            (creator_id, total_sales, total_comm, total_paid, pending, should_lock)
        )
        if pending >= 100.0:
            pay_btn = InlineKeyboardMarkup([[InlineKeyboardButton("💳 Pay Now", url=f"https://t.me/{MAIN_BOT_USERNAME}?start=pay")]])
            
            if should_lock:
                msg_text = (
                    f"🚨 <b>Important Billing Notice: Purchases Suspended</b> 🚨\n\n"
                    f"Your pending service charge bill has reached <b>₹{pending:.2f}</b> (which exceeds the ₹200 threshold).\n\n"
                    f"As per policy, new purchases on all your cloned bots have been temporarily blocked starting today at 8:00 PM IST.\n"
                    f"Existing premium members can still access content normally, but new purchases cannot be made until your bill is cleared.\n\n"
                    f"Please click below to pay your pending bill and restore your services immediately."
                )
            else:
                msg_text = (
                    f"⚠️ <b>Billing Notice: Pending Bill Alert</b> ⚠️\n\n"
                    f"Your pending service charge bill has crossed ₹100 and is currently <b>₹{pending:.2f}</b>.\n\n"
                    f"Please pay your pending bill as soon as possible. If your pending bill crosses <b>₹200</b>, new purchases on your bot will be suspended starting from the next 8:00 PM IST cycle.\n\n"
                    f"Click below to pay now."
                )
            if main_bot:
                try:
                    await main_bot.send_message(creator_id, msg_text, reply_markup=pay_btn, parse_mode=ParseMode.HTML)
                except Exception as e:
                    logger.error(f"Failed to send billing alert from main bot to {creator_id}: {e}")

            bots = await DBManager.execute_sqlite_query(ALL_BOTS_DB, "SELECT username FROM bots WHERE creator_id=?", (creator_id,), fetch='all')
            for b in bots:
                b_uname = b[0].split('#')[0]
                c_bot = await get_bot_instance(b_uname, force_initialize=True)
                if c_bot:
                    try:
                        await c_bot.send_message(creator_id, msg_text, reply_markup=pay_btn, parse_mode=ParseMode.HTML)
                    except Exception as e:
                        logger.error(f"Failed to send billing alert from clone @{b_uname} to {creator_id}: {e}")


async def handle_unauthorized_token(bot_username, creator_id):

    """
    Handles the process when a bot's token is found to be unauthorized.
    Notifies the creator and marks the bot as revoked in the database.
    """
    logger.warning(f"Unauthorized token detected for @{bot_username}. Notifying owner {creator_id}.")
    main_bot = await get_bot_instance(MAIN_BOT_USERNAME)
    if not main_bot:
        logger.error("Could not get main bot instance to notify owner about revoked token.")
        return

    # User ko message bhejo
    try:
        text = (
            f"🚨 **API Token Revoked!** 🚨\n\n"
            f"Hamare system ne detect kiya hai ki aapne apne bot `@{bot_username}` ka API token revoke ya change kar diya hai.\n\n"
            f"Jab tak aap naya token update nahi karte, aapka bot kaam nahi karega.\n\n"
            f"Kripya neeche diye gaye button par click karke naya API token update karein."
        )
        # Callback data me original username bina #revoked ke bhejenge
        clean_bot_username = bot_username.split('#')[0]
        keyboard = [[InlineKeyboardButton("🔄 Change Token", callback_data=f"update_revoked_token_{clean_bot_username}")]]
        await main_bot.send_message(
            chat_id=creator_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except Exception as e:
        logger.error(f"Failed to send revoked token notification to owner {creator_id} for @{bot_username}: {e}")

    # DB me bot ko #revoked mark karo
    # DB me bot ko #revoked mark karo
    clean_uname = bot_username.split('#')[0]
    revoked_username = f"{clean_uname}#revoked"
    await DBManager.execute_sqlite_query(
        ALL_BOTS_DB,
        "UPDATE bots SET username = ? WHERE username = ?",
        (revoked_username, clean_uname)
    )
    # Cache aur Memory dono se bot ko safely shutdown aur clear karo
    await CACHE_BOT_TOKENS.delete(clean_uname)
    await shutdown_bot_instance(clean_uname)
    logger.info(f"Marked @{bot_username} as revoked and closed connection pool.")

# background.py


# --- GLOBAL BOT POOL (Singleton Pattern - Zero RAM & Socket Leak) ---
BOT_INSTANCES = {}
BOT_INSTANCES_LOCK = asyncio.Lock()

async def shutdown_bot_instance(bot_username: str):
    """Ek specific bot instance aur uske HTTPX connection pool ko properly shutdown karta hai."""
    clean_name = bot_username.split('#')[0]
    async with BOT_INSTANCES_LOCK:
        if clean_name in BOT_INSTANCES:
            bot = BOT_INSTANCES.pop(clean_name)
            try:
                await bot.shutdown()
                logger.info(f"Bot @{clean_name} instance properly shutdown and sockets released.")
            except Exception as e:
                logger.error(f"Error shutting down bot @{clean_name}: {e}")

async def get_bot_instance(bot_username, force_initialize=None):
    """
    Bot ka instance singleton pool se fetch ya reuse karta hai, 
    aur initialization fail hone par dangling objects ko clean karta hai.
    """
    if "#revoked" in bot_username:
        logger.warning(f"get_bot_instance skipped for revoked bot: @{bot_username}")
        return None

    clean_name = bot_username.split('#')[0]

    # 1. Pool me check karein
    async with BOT_INSTANCES_LOCK:
        if clean_name in BOT_INSTANCES:
            return BOT_INSTANCES[clean_name]

    # 2. Token fetch karein
    token = await CACHE_BOT_TOKENS.get(clean_name)
    if not token:
        if clean_name == MAIN_BOT_USERNAME:
            token = MAIN_BOT_TOKEN
        else:
            result = await DBManager.execute_sqlite_query(
                ALL_BOTS_DB, "SELECT api_key FROM bots WHERE username=?", (clean_name,), fetch='one'
            )
            token = result[0] if result else None
        if token:
            await CACHE_BOT_TOKENS.set(clean_name, token)
        else:
            logger.error(f"get_bot_instance: @{clean_name} ke liye token nahi mila.")
            return None

    # 3. Connection Pool aur Bot initialize karein with safe cleanup on failure
    request_defaults = HTTPXRequest(
        connection_pool_size=16,
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0
    )
    
    bot = Bot(token=token, request=request_defaults)
    try:
        await bot.initialize()
    except Exception as e:
        logger.error(f"Bot initialize failed for @{clean_name}: {e}")
        try:
            await bot.shutdown() # Failed object ke connections ko safely close karein
        except Exception:
            pass
        return None

    # 4. Global pool me save karein
    async with BOT_INSTANCES_LOCK:
        # Race condition handle karne ke liye dobara check karein
        if clean_name in BOT_INSTANCES:
            try:
                await bot.shutdown() # Agar parallel thread ne pehle hi bana liya ho
            except Exception:
                pass
            return BOT_INSTANCES[clean_name]
            
        BOT_INSTANCES[clean_name] = bot

    return bot

async def notify_admin(message):
    # Yahan hum force_initialize=True bhej rahe hain taaki main_bot theek se kaam kare
    main_bot = await get_bot_instance(MAIN_BOT_USERNAME, force_initialize=True)
    if not main_bot:
        logger.error("Failed to notify admin: Could not get main bot instance.")
        return
    try:
        # Pehle HTML mode me try karega
        await main_bot.send_message(ADMIN_NOTIFY_ID, message, parse_mode=ParseMode.HTML)
    except Exception:
        try:
            # Fallback: Agar special formatting fail ho toh bina parse_mode plain text bhejega
            await main_bot.send_message(ADMIN_NOTIFY_ID, message, parse_mode=None)
        except Exception as e:
            logger.error(f"Failed to notify admin: {e}")

class BotLogic:
    def __init__(self, bot_username, update_data, received_time=None, 
                 header_parsed_time=None, json_parsed_time=None, # <--- Naya parameter
                 before_process_update_time=None, process_update_start_time=None):
        self.bot_username = bot_username
        self.update_data = update_data
        self.bot = None
        self.update = None
        self.user_id = None
        self.chat_id = None
        
        # --- SUPER DETAILED LATENCY TRACKER ---
        self.latency_tracker = []
        if received_time:
            self.latency_tracker.append(("Webhook Received", received_time))
        if header_parsed_time:
            self.latency_tracker.append(("Header Parsed", header_parsed_time)) # <--- Naya step
        if json_parsed_time:
            self.latency_tracker.append(("JSON Parsed", json_parsed_time))
        if before_process_update_time:
            self.latency_tracker.append(("Pre-Process Call", before_process_update_time))
        if process_update_start_time:
            self.latency_tracker.append(("Process Func Start", process_update_start_time)) 
# background.py
# YEH NAYA FUNCTION ADD KAREIN
    def _get_seconds_until_next_5am_ist(self) -> int:
        """Calculate exact seconds remaining until next 5:00 AM IST."""
        tz_ist = ZoneInfo('Asia/Kolkata')
        now_ist = datetime.now(tz_ist)
        target = now_ist.replace(hour=5, minute=0, second=0, microsecond=0)
        if now_ist >= target:
            target += timedelta(days=1)
        ttl = int((target - now_ist).total_seconds())
        return max(ttl, 60)

    async def consume_free_limit(self, max_limit: int) -> bool:
        """
        Atomic Check & Deduct using Valkey Lua Script.
        Prevents race conditions in high traffic so rapid clicks cannot bypass limits.
        """
        if max_limit <= 0:
            return False

        cache_key = f"free_limit:{self.bot_username}:{self.user_id}"
        ttl_seconds = self._get_seconds_until_next_5am_ist()

        # Lua script ensures atomic get, increment, and TTL setting
        lua_script = """
        local key = KEYS[1]
        local ttl = tonumber(ARGV[1])
        local max_limit = tonumber(ARGV[2])

        local current = redis.call('GET', key)
        if not current then
            redis.call('SET', key, 1, 'EX', ttl)
            return 1
        else
            local num = tonumber(current)
            if num < max_limit then
                redis.call('INCR', key)
                return 1
            else
                return 0
            end
        end
        """
        try:
            res = await valkey_client.eval(lua_script, 1, cache_key, ttl_seconds, max_limit)
            return bool(int(res) == 1)
        except Exception as e:
            logger.error(f"Valkey atomic free limit consumption error: {e}")
            return False

    async def is_user_premium(self) -> bool:
        """Checks if current user is admin or an active premium member (Cached)."""
        if await self.is_user_admin():
            return True
        cache_key = f"{self.bot_username}_{self.user_id}_is_prem"
        cached_status = await CACHE_USER_MEMBERSHIP.get(cache_key)
        if cached_status is not None:
            return cached_status

        now = datetime.utcnow().replace(tzinfo=None)
        premium_table = DBManager._get_safe_tablename(self.bot_username, 'premium')
        premium_data = await DBManager.execute_pg_query(
            f"SELECT expiry_time FROM {premium_table} WHERE user_id=$1",
            (self.user_id,),
            fetch='one'
        )
        if premium_data and premium_data['expiry_time'].replace(tzinfo=None) > now:
            await CACHE_USER_MEMBERSHIP.set(cache_key, True)
            return True
        else:
            await CACHE_USER_MEMBERSHIP.set(cache_key, False)
            return False

    def _parse_duration_string(self, text: str):
        """
        Parses inputs like '1 hr', '5 day', '8 month', '1 yr', '16 month', '30 min', '120 sec'.
        Returns (seconds, clean_readable_label) or (None, None).
        """        
        text = text.strip().lower()
        match = re.match(r'^(\d+)\s*([a-zA-Z]+)$', text)
        if not match:
            return None, None
        
        val = int(match.group(1))
        unit = match.group(2)
        if val <= 0:
            return None, None
            
        if unit in ['s', 'sec', 'second', 'seconds']:
            return val, (f"{val} Second" if val == 1 else f"{val} Seconds")
        elif unit in ['m', 'min', 'minute', 'minutes']:
            return val * 60, (f"{val} Minute" if val == 1 else f"{val} Minutes")
        elif unit in ['h', 'hr', 'hrs', 'hour', 'hours']:
            return val * 3600, (f"{val} Hour" if val == 1 else f"{val} Hours")
        elif unit in ['d', 'day', 'days']:
            return val * 86400, (f"{val} Day" if val == 1 else f"{val} Days")
        elif unit in ['w', 'wk', 'week', 'weeks']:
            return val * 7 * 86400, (f"{val} Week" if val == 1 else f"{val} Weeks")
        elif unit in ['mo', 'mon', 'month', 'months']:
            return val * 30 * 86400, (f"{val} Month" if val == 1 else f"{val} Months")
        elif unit in ['y', 'yr', 'year', 'years']:
            return val * 365 * 86400, (f"{val} Year" if val == 1 else f"{val} Years")
        return None, None

    def _escape_markdown(self, text: str) -> str:
        """Telegram ke MARKDOWN_V2 ke liye special characters ko escape karta hai."""
        escape_chars = r'\_*[]()~`>#+-=|{}.!'
        return re.sub(f'([\{re.escape(escape_chars)}])', r'\\\1', text)
    # --- PAYMENT FEATURE KE LIYE NAYA HELPER FUNCTION ---
    def _generate_upi_qr(self, upi_id: str, amount: float, name: str = "Bot Premium") -> bytes:
        """UPI ID aur amount se QR code image generate karta hai."""
        upi_string = f"upi://pay?pa={upi_id}&pn={name.replace(' ', '%20')}&am={amount:.2f}&cu=INR"
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
        qr.add_data(upi_string)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Image ko memory me save karke bytes return karo
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        return buf.getvalue()
    
    
    # --- NAYA HELPER FUNCTION KHATAM ---
    
    # --- IS NAYE CODE KO `_generate_upi_qr` KE NEECHE PASTE KAREIN ---
    def _get_fake_phone(self, user_id: int) -> str:
        uid_str = str(user_id)
        if len(uid_str) == 9:
            uid_str += "8"
        elif len(uid_str) >= 11:
            uid_str = uid_str[:10]
        else:
            uid_str = uid_str.ljust(10, '0')
        
        first_digit = int(uid_str[0])
        if 0 <= first_digit <= 3:
            uid_str = "8" + uid_str[1:]
        elif 4 <= first_digit <= 7:
            uid_str = "9" + uid_str[1:]
        return uid_str

    async def _create_cashfree_order(self, transaction_id: int, amount: float, phone: str, cf_app_id: str, cf_secret: str):
        order_id = f"txn_{transaction_id}"
        return_url = f"https://t.me/{self.bot_username}?start=success_txn_{transaction_id}"
        notify_url = f"{WEBHOOK_URL}/cash"
        
        url = "https://api.cashfree.com/pg/orders"
        headers = {
            'Content-Type': 'application/json',
            'x-client-id': cf_app_id,
            'x-client-secret': cf_secret,
            'x-api-version': '2021-05-21'
        }
        payload = {
            "order_id": order_id,
            "order_amount": float(amount),
            "order_currency": "INR",
            "customer_details": {
                "customer_id": f"cust_{self.user_id}",
                "customer_phone": str(phone)
            },
            "order_meta": {
                "return_url": return_url,
                "notify_url": notify_url
            }
        }
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=headers, timeout=10)
                data = response.json()
                if "payment_link" in data:
                    return order_id, data["payment_link"]
                else:
                    logger.error(f"CF Error: {data}")
                    return None, None
        except Exception as e:
            logger.error(f"CF Request Error: {e}")
            return None, None

    async def _check_cashfree_direct(self, order_id: str, cf_app_id: str, cf_secret: str) -> bool:
        url = f"https://api.cashfree.com/pg/orders/{order_id}"
        headers = {
            'x-client-id': cf_app_id,
            'x-client-secret': cf_secret,
            'x-api-version': '2021-05-21'
        }
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, timeout=10)
                data = response.json()
                if data.get("order_status") == "PAID":
                    return True
                return False
        except Exception as e:
            logger.error(f"CF Check Error: {e}")
            return False
    # -------------------------------------------------------------

    async def initialize(self):
        # Step 1: Bot ka object banao (API call ke bina, performance ke liye)
        self.bot = await get_bot_instance(self.bot_username, force_initialize=False) # <-- Yahan False add karna zaroori hai
        if not self.bot:
            return False
        
        if self.latency_tracker:
            self.latency_tracker.append(("Bot Object Created", datetime.utcnow()))

        # Step 2: Telegram ke message ko parse karo
        self.update = Update.de_json(self.update_data, self.bot)
        
        # NAYA LATENCY POINT: Message parse hone ka time alag se record karenge
        if self.latency_tracker:
            self.latency_tracker.append(("Update Parsed", datetime.utcnow()))

        if self.update.effective_user:
            self.user_id = self.update.effective_user.id
        if self.update.effective_chat:
            self.chat_id = self.update.effective_chat.id
        
        return True
    async def process(self):
        global CURRENT_ACTIVE_REQUESTS, CURRENT_WINDOW_DATA
        CURRENT_ACTIVE_REQUESTS += 1
        if CURRENT_ACTIVE_REQUESTS > CURRENT_WINDOW_DATA['peak_concurrency']:
            CURRENT_WINDOW_DATA['peak_concurrency'] = CURRENT_ACTIVE_REQUESTS

        try:
            async with CONCURRENCY_SEMAPHORE:
                if not await self.initialize():
                    return
                if self.update.effective_chat.type in ['group', 'supergroup']:
                    try:
                        if self.bot_username == MAIN_BOT_USERNAME:
                            message_to_send = "I am the main bot and I do not work in groups. I will leave now."
                        else:
                            message_to_send = "I am a file store bot and I am not designed to work in groups. I will leave now. Please use me in a private chat."
                        await self.bot.send_message(self.chat_id, message_to_send)
                        await self.bot.leave_chat(self.chat_id)
                        logger.info(f"Bot @{self.bot_username} left group {self.chat_id}.")
                    except Exception as e:
                        logger.error(f"Error leaving group {self.chat_id} for bot @{self.bot_username}: {e}")
                    return            
            conv_state = await CACHE_CONVERSATION.get(f"{self.bot_username}_{self.user_id}")
            if conv_state and self.update.message:
        # ...
                handler_name = f"handle_conv_{conv_state['command']}"
                if hasattr(self, handler_name):
                    await getattr(self, handler_name)(conv_state)
                    return
            if self.update.callback_query:
                await self.handle_callback_query()
            elif self.update.chat_join_request:
                await self.handle_chat_join_request()
            elif self.update.chat_member:
                await self.handle_chat_member_update()
            elif self.update.pre_checkout_query:
                await self.handle_pre_checkout_query()
            
            elif self.update.message:
                # Telegram Stars Successful Payment Check
                if self.update.message.successful_payment:
                    await self.handle_successful_stars_payment()
                    return

                # 1. Admin reply check sabse pehle hoga
                if await self.handle_admin_reply():
                    return
                if self.update.message.text and self.update.message.text.startswith('/start'):
                    await self.handle_start_command()
                    return
                elif not await self.run_pre_checks():
                    return
                if self.update.message.text:
                    if self.update.message.text.startswith('/'):
                        await self.handle_command()
                    else:
                        await self.handle_text_message()
                elif self.update.message.effective_attachment:
                    await self.handle_file_message()
        finally:
            CURRENT_ACTIVE_REQUESTS = max(0, CURRENT_ACTIVE_REQUESTS - 1)
            # Latency calculate karke metric record karo
            try:
                start_dt = self.latency_tracker[0][1] if self.latency_tracker else None
                if start_dt:
                    total_dur_ms = (datetime.utcnow() - start_dt).total_seconds() * 1000
                    record_live_metric(self.bot_username, total_dur_ms)
            except Exception:
                pass
    
    
    async def send_admin_policy_warning(self):
        """Admin ko link generate hone ke baad content policy warning message bhejta hai."""
        settings = await self.get_bot_settings()
        # Agar admin ne pehle hi band kar diya hai, toh function yahi ruk jayega
        if settings.get('policy_warning_disabled', False):
            return

        policy_text = (
            "⚠️ Before sharing this link, please make sure that your content does not violate our "
            "⚠️ <b>BOT USAGE & CONTENT POLICY</b>."
        )
        policy_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Content Policy", url="https://t.me/echelon_notification/156")],
            [InlineKeyboardButton("🔕 I Understand (Turn Off)", callback_data=f"disable_policy_warning_{self.bot_username}")]
        ])
        await self.bot.send_message(
            self.chat_id,
            policy_text,
            reply_markup=policy_keyboard,
            parse_mode=ParseMode.HTML
        )

    async def handle_pre_checkout_query(self):
        """Telegram dwara pre-checkout query ko turant approve karta hai."""
        query = self.update.pre_checkout_query
        try:
            await query.answer(ok=True)
        except Exception as e:
            logger.error(f"Error answering pre_checkout_query: {e}")

    async def send_paid_message_stars_invoice(self, transaction_id: int, payload: str, stars_amount: int, message=None):
        """Paid message ke liye direct Telegram Stars ka invoice bhejta hai."""
        if message:
            try:
                await message.delete()
            except Exception:
                pass

        prices = [telegram.LabeledPrice(label="Unlock Paid Message", amount=stars_amount)]
        try:
            await self.bot.send_invoice(
                chat_id=self.chat_id,
                title="🔓 Unlock Paid Content",
                description=f"Access private message/media on @{self.bot_username}",
                payload=f"stars_txn_{transaction_id}",
                provider_token="",
                currency="XTR",
                prices=prices
            )
        except Exception as e:
            logger.error(f"Error sending Stars invoice for paid message: {e}")
            await self.bot.send_message(self.chat_id, "❌ Error creating Telegram Stars invoice. Please try with UPI.")
    
    async def handle_successful_stars_payment(self):
        """Telegram Stars payment ko verify karke instant premium grant karta hai."""
        sp = self.update.message.successful_payment
        payload = sp.invoice_payload
        total_stars = sp.total_amount

        if not payload or not payload.startswith("stars_txn_"):
            return

        try:
            transaction_id = int(payload.split("_")[2])
        except (IndexError, ValueError):
            return

        tx_data = await DBManager.execute_pg_query(
            "SELECT * FROM active_upi_transactions WHERE transaction_id = $1", 
            (transaction_id,), fetch='one'
        )
        if not tx_data:
            await self.bot.send_message(self.chat_id, "✅ Aapka payment pehle hi verify ho chuka hai!")
            return

        admin_id = tx_data['admin_id']
        bot_username = tx_data['bot_username']
        user_id = tx_data['user_id']
        days = tx_data['plan_duration_days']
        target_payload = tx_data.get('target_payload') if 'target_payload' in tx_data else ''

        safe_bot_table = DBManager._get_safe_tablename(bot_username, '')
        premium_table = DBManager._get_safe_tablename(bot_username, 'premium')

        # Successful table me record daalo
        # Successful table me record daalo (Currency XTR tag ke sath)
        await DBManager.execute_pg_query(
            f"INSERT INTO {safe_bot_table}successful_transactions (transaction_id, user_id, amount, plan_duration_days, completion_time, target_payload, sent_message_id, currency) VALUES ($1, $2, $3, $4, NOW(), $5, $6, 'XTR')",
            transaction_id, user_id, float(total_stars), days, target_payload or '', None
        )        
        await DBManager.execute_pg_query("DELETE FROM active_upi_transactions WHERE transaction_id = $1", (transaction_id,))

        # Premium table update
        # Premium table update
        sent_msg_id = None
        if target_payload:
            if len(target_payload) == 16:
                await self.deliver_paid_channel_access(bot_username, user_id, target_payload)
            else:
                paid_access_table = DBManager._get_safe_tablename(bot_username, 'paid_msg_access')
                await DBManager.execute_pg_query(
                    f"INSERT INTO {paid_access_table} (payload, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                    (target_payload, user_id)
                )
                await self.bot.send_message(
                    self.chat_id,
                    f"🌟 <b>Payment Verified via Telegram Stars ({total_stars} ⭐)!</b>\n\nAapka paid message neeche send kiya ja raha hai:",
                    parse_mode=ParseMode.HTML
                )
                sent_msg = await self.send_paid_message_to_user(target_payload)
                if sent_msg:
                    sent_msg_id = sent_msg.message_id
                    await DBManager.execute_pg_query(
                        f"UPDATE {safe_bot_table}successful_transactions SET sent_message_id = $1 WHERE transaction_id = $2",
                        sent_msg_id, transaction_id
                    )        
        else:
            # Regular Subscription Plan
            dur_sec = tx_data.get('plan_duration_seconds', 0) if 'plan_duration_seconds' in tx_data else 0
            interval_str = f"{dur_sec} seconds" if dur_sec and dur_sec > 0 else f"{days} days"

            pg_query = f"""
            INSERT INTO {premium_table} (user_id, expiry_time) VALUES ($1, NOW() + INTERVAL '{interval_str}')
            ON CONFLICT (user_id) DO UPDATE SET expiry_time = 
                CASE 
                    WHEN {premium_table}.expiry_time < NOW() THEN NOW() + INTERVAL '{interval_str}'
                    ELSE {premium_table}.expiry_time + INTERVAL '{interval_str}'
                END;
            """
            await DBManager.execute_pg_query(pg_query, (user_id,))
            await self.auto_add_premium_to_synced_bots(bot_username, user_id, days)

            await self.bot.send_message(
                self.chat_id,
                f"🌟 <b>Payment Verified via Telegram Stars!</b>\n\n"
                f"Aapka payment safaltapoorvak receive ho gaya hai (<b>{total_stars} ⭐</b>).\n"
                f"Aapko <b>{days} Days</b> ka Premium Access mil gaya hai. Enjoy!",
                parse_mode=ParseMode.HTML
            )
        # Admin Notification
        if admin_id:
            try:
                admin_msg = (
                    f"⭐ <b>New Telegram Stars Payment Received!</b>\n\n"
                    f"<b>Bot:</b> @{bot_username}\n"
                    f"<b>User ID:</b> <code>{user_id}</code>\n"
                    f"<b>Order ID:</b> <code>{payload}</code>\n"
                    f"<b>Stars Received:</b> {total_stars} ⭐\n"
                    f"<b>Plan:</b> {days} Days Premium\n"
                    f"<b>Telegram Charge ID:</b> <code>{sp.telegram_payment_charge_id}</code>\n\n"
                    f"<i>✅ Telegram dwara payment 100% genuine verify ho chuka hai aur membership activate ho chuki hai.</i>"
                )
                await self.bot.send_message(admin_id, admin_msg, parse_mode=ParseMode.HTML)
            except Exception as ne:
                logger.error(f"Stars admin notification error: {ne}")
    
    async def disable_policy_warning(self, message, bot_username):
        """Admin jab I Understand click karega toh ye setting save karke msg delete kar dega."""
        settings_table = DBManager._get_safe_tablename(bot_username, 'settings')
        query = f"INSERT INTO {settings_table} (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = $2"
        await DBManager.execute_pg_query(query, ('policy_warning_disabled', json.dumps(True)))

        if await CACHE_BOT_SETTINGS.contains(bot_username):
            await CACHE_BOT_SETTINGS.delete(bot_username)
            
        try:
            await message.delete()
            await self.bot.send_message(self.chat_id, "✅ Policy warning has been permanently disabled for this bot.")
        except Exception:
            pass    
    
    async def initiate_paid_channel_purchase(self, payload: str):
        """User ko demo message dikhata hai aur Paid Channel ke payment options deta hai."""
        chan_table = DBManager._get_safe_tablename(self.bot_username, 'paid_channels')
        chan_pkg = await DBManager.execute_pg_query(f"SELECT * FROM {chan_table} WHERE payload=$1", (payload,), fetch='one')
        if not chan_pkg:
            await self.bot.send_message(self.chat_id, "❌ Channel package not found or expired.")
            return

        settings = await self.get_bot_settings()
        creator_id = settings.get('creator_id')
        if await is_creator_purchases_locked(creator_id):
            await self.bot.send_message(self.chat_id, "⚠️ New purchases are temporarily suspended on this bot. Please try again later.")
            return

        # 1. Show Demo message if available
        demo_msg_id = chan_pkg['demo_msg_id']
        demo_chat_id = chan_pkg['demo_chat_id']
        if demo_msg_id and demo_chat_id:
            try:
                await self.bot.copy_message(chat_id=self.chat_id, from_chat_id=demo_chat_id, message_id=demo_msg_id)
            except Exception as demo_err:
                logger.warning(f"Could not deliver demo message: {demo_err}")

        # 2. Payment details
        price = float(chan_pkg['price'] or 0.0)
        stars_price = int(chan_pkg['stars_price'] or 0)
        paid_info = settings.get('paid_settings', {})
        admin_id = settings.get('creator_id')
        upi_id = paid_info.get('upi_id')
        cf_enabled = paid_info.get('cf_enabled', False)
        upi_enabled = paid_info.get('upi_enabled', True)
        stars_enabled = paid_info.get('stars_enabled', False)

        has_fiat = bool(price > 0 and (upi_id or cf_enabled) and upi_enabled)
        has_stars = bool(stars_enabled and stars_price > 0)

        if not has_fiat and not has_stars:
            await self.bot.send_message(self.chat_id, "Admin has not configured a payment method for this package. Please contact support.")
            return

        transaction_id = await DBManager.get_next_transaction_id()
        query = """
        INSERT INTO active_upi_transactions 
        (transaction_id, bot_username, admin_id, user_id, amount, plan_duration_days, transaction_start_time, upi_id, target_payload)
        VALUES ($1, $2, $3, $4, $5, 0, NOW(), $6, $7)
        """
        await DBManager.execute_pg_query(query, (
            transaction_id, self.bot_username, admin_id, self.user_id, float(price or stars_price), upi_id or "", payload
        ))

        channels_count = len(json.loads(chan_pkg['channel_ids']))
        if has_fiat and has_stars:
            method_text = (
                f"📢 <b>Unlock Paid Channels ({channels_count} Channels)</b>\n\n"
                f"Select your preferred payment method to join:"
            )
            method_keyboard = [
                [InlineKeyboardButton(f"💳 Pay with UPI / Online (₹{price:.2f})", callback_data=f"pay_method_fiat_{transaction_id}")],
                [InlineKeyboardButton(f"⭐ Pay with Telegram Stars ({stars_price} ⭐)", callback_data=f"pay_paidchan_stars_{transaction_id}_{payload}_{stars_price}")]
            ]
            await self.bot.send_message(self.chat_id, method_text, reply_markup=InlineKeyboardMarkup(method_keyboard), parse_mode=ParseMode.HTML)
        elif has_stars:
            await self.send_paid_channel_stars_invoice(transaction_id, payload, stars_price)
        else:
            if cf_enabled:
                await self.handle_switch_payment(self.update.message, transaction_id, "cf", new_message=True)
            else:
                await self.handle_switch_payment(self.update.message, transaction_id, "upi", new_message=True)

    async def send_paid_channel_stars_invoice(self, transaction_id: int, payload: str, stars_amount: int, message=None):
        """Paid Channel ke liye Telegram Stars ka invoice bhejta hai."""
        if message:
            try: await message.delete()
            except Exception: pass

        prices = [telegram.LabeledPrice(label="Join Paid Channel", amount=stars_amount)]
        try:
            await self.bot.send_invoice(
                chat_id=self.chat_id,
                title="📢 Join Paid Channel",
                description=f"Get instant 30-day single-use invite link for private channel(s).",
                payload=f"stars_txn_{transaction_id}",
                provider_token="",
                currency="XTR",
                prices=prices
            )
        except Exception as e:
            logger.error(f"Stars invoice error for paid channel: {e}")
            await self.bot.send_message(self.chat_id, "❌ Error creating Telegram Stars invoice. Please try paying with UPI.")
    
    async def forward_to_admin(self):
        """User ke normal message ko cloned bot ke creator ke yaha forward karta hai aur map karta hai."""
        if self.bot_username == MAIN_BOT_USERNAME:
            return
        settings = await self.get_bot_settings()
        creator_id = settings.get('creator_id')
        if not creator_id or creator_id == self.user_id:
            return

        try:
            # 1. User ke original message par 🥱 react karein
            try:
                await self.bot.set_message_reaction(
                    chat_id=self.chat_id,
                    message_id=self.update.message.message_id,
                    reaction="🥱"
                )
            except Exception as react_err:
                logger.warning(f"Reaction add karne me error: {react_err}")

            # 2. Admin ke paas message forward karein
            fwd_msg = await self.bot.forward_message(
                chat_id=creator_id,
                from_chat_id=self.chat_id,
                message_id=self.update.message.message_id
            )
            if fwd_msg:
                # 3. Database me mapping save karein
                query = """
                INSERT INTO support_messages (bot_username, admin_chat_id, admin_message_id, user_id)
                VALUES ($1, $2, $3, $4)
                """
                await DBManager.execute_pg_query(
                    query,
                    (self.bot_username, creator_id, fwd_msg.message_id, self.user_id)
                )
        except Exception as e:
            logger.error(f"Error forwarding message to admin for @{self.bot_username}: {e}")    
    
    async def handle_admin_reply(self):
        """Admin dwara kisi forwarded message ke reply ko user tak deliver karta hai."""
        if self.bot_username == MAIN_BOT_USERNAME:
            return False
        if not self.update.message or not self.update.message.reply_to_message:
            return False

        reply_to_id = self.update.message.reply_to_message.message_id
        query = """
        SELECT user_id FROM support_messages 
        WHERE admin_chat_id = $1 AND admin_message_id = $2 AND bot_username = $3
        """
        record = await DBManager.execute_pg_query(query, (self.chat_id, reply_to_id, self.bot_username), fetch='one')
        if not record:
            return False

        target_user_id = record['user_id']
        try:
            await self.bot.copy_message(
                chat_id=target_user_id,
                from_chat_id=self.chat_id,
                message_id=self.update.message.message_id
            )
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=f"✅ Send to <code>{target_user_id}</code>",
                reply_to_message_id=self.update.message.message_id,
                parse_mode=ParseMode.HTML
            )
            return True
        except Exception as e:
            logger.error(f"Error delivering admin reply to user {target_user_id}: {e}")
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=f"❌ Message deliver nahi ho paya: {e}",
                reply_to_message_id=self.update.message.message_id
            )
            return True    
    async def handle_chat_join_request(self):
        if not self.update.chat_join_request:
            return
        join_request = self.update.chat_join_request
        user_id = join_request.from_user.id
        channel_id = join_request.chat.id

        settings = await self.get_bot_settings()
        fsub_channels = settings.get('fsub_channels', [])
        target_channel = next((ch for ch in fsub_channels if ch['id'] == channel_id), None)

        if not target_channel:
            return

        # Link verification helper
        def clean_link(link_str):
            if not link_str: return ""
            return re.sub(r'^(https?:\/\/)?(www\.)?(t\.me|telegram\.me)\/', '', str(link_str).strip()).rstrip('/')

        req_link = join_request.invite_link.invite_link if join_request.invite_link else None
        expected_link = target_channel.get('link', '')

        # Check: Agar link match nahi hua toh join count nahi hoga
        if not req_link or clean_link(req_link) != clean_link(expected_link):
            logger.info(f"Join request ignored for count in channel {channel_id}: link mismatch (Used: {req_link}, Expected: {expected_link})")
            return

        await DBManager.setup_join_request_db(self.bot_username, channel_id)
        
        if not pg_pool:
            logger.error(f"PG Pool not available. Cannot process join request for user {user_id} in channel {channel_id}.")
            return

        safe_channel_id = abs(channel_id)
        table_name = f"join_requests_{safe_channel_id}"

        try:
            async with pg_pool.acquire() as conn:
                count_res = await conn.fetchval(f"SELECT COUNT(*) FROM {table_name}")
                if count_res and count_res >= 1000:
                    await conn.execute(f"DELETE FROM {table_name} WHERE user_id IN (SELECT user_id FROM {table_name} ORDER BY random() LIMIT 1)")
                await conn.execute(f"INSERT INTO {table_name} (user_id) VALUES ($1) ON CONFLICT (user_id) DO NOTHING", user_id)
        except Exception as e:
            logger.error(f"PostgreSQL me join request handle karte waqt error ({table_name}): {e}")
        
        await CACHE_FSUB_USER_STATUS.set(f"{self.bot_username}_{user_id}_{channel_id}", True)

        main_admin_id = settings.get('creator_id')
        current_joins = int(target_channel.get('current', 0)) + 1
        target_channel['current'] = current_joins
        target_joins = int(target_channel.get('target', 0))

        channels_to_remove = []
        if target_joins > 0 and current_joins >= target_joins:
            channels_to_remove.append(channel_id)
            if main_admin_id:
                try:
                    await self.bot.send_message(
                        main_admin_id, 
                        f"🎉 Target Achieved! 🎉\n\nChannel {channel_id} has reached its target of {target_joins} joins and has been removed from the FSUB list."
                    )
                except Exception:
                    pass

        if channels_to_remove:
            fsub_channels = [ch for ch in fsub_channels if ch['id'] not in channels_to_remove]
        
        settings_table = DBManager._get_safe_tablename(self.bot_username, 'settings')
        query = f"INSERT INTO {settings_table} (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = $2"
        await DBManager.execute_pg_query(query, ('fsub_channels', json.dumps(fsub_channels)))

        if await CACHE_BOT_SETTINGS.contains(self.bot_username):
            await CACHE_BOT_SETTINGS.delete(self.bot_username)    
    
    async def handle_chat_member_update(self):
        """Direct channel joins ko bot ke invite link se verify karke count karta hai."""
        if not self.update.chat_member:
            return
        chat_member = self.update.chat_member
        channel_id = chat_member.chat.id
        user_id = chat_member.new_chat_member.user.id

        # Check: User channel me naya add/join hua hona chahiye
        old_status = chat_member.old_chat_member.status
        new_status = chat_member.new_chat_member.status
        if old_status in ['member', 'administrator', 'creator'] or new_status not in ['member', 'administrator', 'creator']:
            return

        joined_link = chat_member.invite_link.invite_link if chat_member.invite_link else None
        if not joined_link:
            return

        settings = await self.get_bot_settings()
        fsub_channels = settings.get('fsub_channels', [])
        target_channel = next((ch for ch in fsub_channels if ch['id'] == channel_id and ch.get('mode', 'normal') == 'normal'), None)
        if not target_channel:
            return

        def clean_link(link_str):
            if not link_str: return ""
            return re.sub(r'^(https?:\/\/)?(www\.)?(t\.me|telegram\.me)\/', '', str(link_str).strip()).rstrip('/')

        expected_link = target_channel.get('link', '')

        # Link mismatch check
        if clean_link(joined_link) != clean_link(expected_link):
            logger.info(f"Direct join ignored for channel {channel_id}: link mismatch (Used: {joined_link}, Expected: {expected_link})")
            return

        # User ka status cache me true mark karein
        await CACHE_FSUB_USER_STATUS.set(f"{self.bot_username}_{user_id}_{channel_id}", True)

        main_admin_id = settings.get('creator_id')
        current_joins = int(target_channel.get('current', 0)) + 1
        target_channel['current'] = current_joins
        target_joins = int(target_channel.get('target', 0))

        channels_to_remove = []
        if target_joins > 0 and current_joins >= target_joins:
            channels_to_remove.append(channel_id)
            if main_admin_id:
                try:
                    await self.bot.send_message(
                        main_admin_id,
                        f"🎉 Target Achieved! 🎉\n\nChannel {channel_id} has reached its target of {target_joins} joins and has been removed from the FSUB list."
                    )
                except Exception:
                    pass

        if channels_to_remove:
            fsub_channels = [ch for ch in fsub_channels if ch['id'] not in channels_to_remove]

        settings_table = DBManager._get_safe_tablename(self.bot_username, 'settings')
        query = f"INSERT INTO {settings_table} (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = $2"
        await DBManager.execute_pg_query(query, ('fsub_channels', json.dumps(fsub_channels)))

        if await CACHE_BOT_SETTINGS.contains(self.bot_username):
            await CACHE_BOT_SETTINGS.delete(self.bot_username)
    
    async def show_channel_ads_menu(self, message, bot_username):
        """Channel Ads feature ka admin menu dikhata hai."""
        count_res = await DBManager.execute_pg_query(
            "SELECT COUNT(*) as total FROM channel_ads_broadcast WHERE bot_username=$1", 
            (bot_username,), 
            fetch='one'
        )
        total_channels = count_res['total'] if count_res else 0
        
        status_text = f"✅ Active ({total_channels} Channels added)" if total_channels > 0 else "❌ Not Configured"

        text = (
            f"📢 <b>Channel Ads Broadcast Manager for @{bot_username}</b>\n\n"
            f"<b>Status:</b> {status_text}\n\n"
            f"Is feature se aapka bot apne target channels me automatically set time gap pe aapka ad message broadcast karta rahega."
        )

        keyboard = [
            [InlineKeyboardButton("✏️ Set or Update Ad Message", callback_data=f"channel_ads_set_{bot_username}")],
            [InlineKeyboardButton("🗑️ Delete this Feature", callback_data=f"channel_ads_delete_{bot_username}")],
            [InlineKeyboardButton("⬅️ Back", callback_data=f"bot_settings_{bot_username}")]
        ]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

    async def delete_channel_ads_feature(self, message, bot_username):
        """Channel Ads schedule ko database se delete karta hai."""
        await DBManager.execute_pg_query("DELETE FROM channel_ads_broadcast WHERE bot_username=$1", (bot_username,))
        await message.edit_text(
            f"🗑️ Channel Ads feature aur saare scheduled channel broadcasts @{bot_username} ke liye delete kar diye gaye hain.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=f"channel_ads_menu_{bot_username}")]])
        )

    async def handle_conv_channel_ad_msg(self, state):
        """Ad message ko capture karta hai aur interval select karne ko bolta hai."""
        bot_username = state.get('bot_username', self.bot_username)
        msg = self.update.message

        if not msg:
            await self.bot.send_message(self.chat_id, "Invalid message. Operation canceled.")
            key = f"{self.bot_username}_{self.user_id}"
            await CACHE_CONVERSATION.delete(key)
            return

        state['ad_msg_id'] = msg.message_id
        state['ad_from_chat_id'] = self.chat_id
        
        key = f"{self.bot_username}_{self.user_id}"
        await CACHE_CONVERSATION.set(key, state)

        keyboard = [
            [
                InlineKeyboardButton("1 Hr", callback_data=f"channel_ads_interval_{bot_username}_3600"),
                InlineKeyboardButton("2 Hr", callback_data=f"channel_ads_interval_{bot_username}_7200")
            ],
            [
                InlineKeyboardButton("6 Hr", callback_data=f"channel_ads_interval_{bot_username}_21600"),
                InlineKeyboardButton("12 Hr", callback_data=f"channel_ads_interval_{bot_username}_43200")
            ],
            [
                InlineKeyboardButton("24 Hr", callback_data=f"channel_ads_interval_{bot_username}_86400")
            ]
        ]
        await self.bot.send_message(
            self.chat_id,
            "✅ Message receive ho gaya!\n\nAb choose karein ki har kitne time interval pe yeh ad channels me broadcast hona chahiye:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def set_channel_ad_interval(self, message, bot_username, interval_seconds):
        """Interval save karta hai aur channels forward karne ko kehta hai."""
        key = f"{self.bot_username}_{self.user_id}"
        state = await CACHE_CONVERSATION.get(key)
        if not state:
            state = {'bot_username': bot_username}

        state['command'] = 'channel_ad_add_channel'
        state['interval_seconds'] = interval_seconds
        state['bot_username'] = bot_username
        await CACHE_CONVERSATION.set(key, state)

        hours = interval_seconds // 3600
        text = (
            f"⏱️ <b>Interval Set: Har {hours} Ghante</b>\n\n"
            f"Ab jis-jis channel me ad message send karna hai, <b>un-un channels se koi bhi message yahan FORWARD karein.</b>\n\n"
            f"<i>(Note: Dhyan rahe ki bot us channel me admin hona chahiye aur uske paas Send/Post Message permission honi chahiye.)</i>"
        )
        keyboard = [[InlineKeyboardButton("✅ Forwarding Done / Finish", callback_data=f"channel_ads_done_{bot_username}")]]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

    async def handle_conv_channel_ad_add_channel(self, state):
        """Forwarded post se channel ID nikal kar test send karke verify karta hai."""
        message = self.update.message
        bot_username = state.get('bot_username', self.bot_username)
        ad_msg_id = state.get('ad_msg_id')
        ad_from_chat_id = state.get('ad_from_chat_id')
        interval_seconds = state.get('interval_seconds', 7200)

        channel_id = None
        if hasattr(message, 'forward_origin') and message.forward_origin and message.forward_origin.type == 'channel':
            channel_id = message.forward_origin.chat.id
        elif hasattr(message, 'forward_from_chat') and message.forward_from_chat:
            channel_id = message.forward_from_chat.id

        if not channel_id:
            await self.bot.send_message(self.chat_id, "❌ Kripya channel se seedha post forward karein.")
            return

        clone_bot = await get_bot_instance(bot_username, force_initialize=True)
        if not clone_bot:
            await self.bot.send_message(self.chat_id, "Bot instance load nahi ho paya.")
            return

        # Test sending message to verify permission
        # Test sending message to verify permission (Silent)
        try:
            test_msg = await clone_bot.send_message(channel_id, "🔔 Checking ad broadcast permission...", disable_notification=True)
            await clone_bot.delete_message(channel_id, test_msg.message_id)
        except Exception:
            await self.bot.send_message(
                self.chat_id,
                f"❌ <b>I don't have send message permission on that channel</b> (`{channel_id}`).\n\nKripya bot ko channel me Admin banayein aur 'Post Messages' permission on karke dobara post forward karein.",
                parse_mode=ParseMode.HTML
            )
            return

        # Permission verified -> DB me insert/update karo (First run immediately with NOW())
        insert_query = f"""
        INSERT INTO channel_ads_broadcast (bot_username, channel_id, from_chat_id, message_id, interval_seconds, next_run_at)
        VALUES ($1, $2, $3, $4, $5, NOW())
        ON CONFLICT (bot_username, channel_id) DO UPDATE SET 
            from_chat_id = EXCLUDED.from_chat_id,
            message_id = EXCLUDED.message_id,
            interval_seconds = EXCLUDED.interval_seconds,
            next_run_at = NOW();
        """        
        await DBManager.execute_pg_query(insert_query, (bot_username, channel_id, ad_from_chat_id, ad_msg_id, interval_seconds))

        keyboard = [[InlineKeyboardButton("✅ Forwarding Done / Finish", callback_data=f"channel_ads_done_{bot_username}")]]
        await self.bot.send_message(
            self.chat_id,
            f"✅ Channel (`{channel_id}`) safaltapoorvak add ho gaya!\n\nAap agle channel se message forward kar sakte hain ya niche diye gaye <b>Finish</b> button par click karein.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )

    async def handle_channel_ads_done(self, message, bot_username):
        """Channel forwarding state complete hone par finish karta hai."""
        key = f"{self.bot_username}_{self.user_id}"
        await CACHE_CONVERSATION.delete(key)
        
        count_res = await DBManager.execute_pg_query(
            "SELECT COUNT(*) as total FROM channel_ads_broadcast WHERE bot_username=$1", 
            (bot_username,), 
            fetch='one'
        )
        total = count_res['total'] if count_res else 0

        await message.edit_text(
            f"🎉 <b>Channel Ads Configuration Complete!</b>\n\n"
            f"Kul <b>{total}</b> channels me ad schedule ho gaya hai. Bot set time intervals pe auto broadcast karta rahega.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ Back to Bot Settings", callback_data=f"bot_settings_{bot_username}")]])
            , parse_mode=ParseMode.HTML
        )
    
    async def run_pre_checks(self):
        if self.bot_username == MAIN_BOT_USERNAME:
            return True
        if self.update.message and self.update.message.text and self.update.message.text.startswith('/start'):
            return True
        if not await self.check_fsub():
            return False
        # check_membership yahan se hata diya gaya hai taaki non-premium user ka support message block na ho
        return True
    
    async def handle_start_command(self):
        if self.bot_username == MAIN_BOT_USERNAME:
            await self.handle_main_bot_start()
            try:
                await self.bot.delete_message(self.chat_id, self.update.message.message_id)
            except Exception:
                pass
        else:
            await self.handle_clone_bot_start()

    async def handle_main_bot_start(self):
        args = self.update.message.text.split()[1:] if len(self.update.message.text.split()) > 1 else []
        payload = args[0] if args else None

        if payload == "pay":
            stats = await get_creator_billing_stats(self.user_id)
            if not stats:
                await self.bot.send_message(self.chat_id, "❌ You have not created any cloned bots yet.")
                return

            p_bill = stats['pending_bill']
            tot_sales = stats['total_sales']
            tot_comm = stats['total_bill']
            tot_paid = stats['total_paid']
            lock_str = "🔴 Locked (New purchases disabled)" if stats['is_locked'] else "🟢 Active"

            bill_msg = (
                f"💳 <b>Bill Payment </b>\n\n"
                f"• <b>Total Sales (Across your bots):</b> ₹{tot_sales:,.2f}\n"
                f"• <b>Total Bill:</b> ₹{tot_comm:,.2f}\n"
                f"• <b>Total Paid So Far:</b> ₹{tot_paid:,.2f}\n"
                f"• <b>Current Pending Bill:</b> ₹{p_bill:,.2f}\n"
                f"• <b>Bot Status:</b> {lock_str}\n\n"
                f"Please enter the amount you want to pay (Minimum: ₹100).\n\n"
                f"💡 <i>Tip: You can pay in advance so that your bot's purchase system is never interrupted.</i>"
            )
            await self.initiate_conversation('admin_bill_amount', bill_msg, parse_mode=ParseMode.HTML)
            return
        user_name = self.update.effective_user.first_name
        text = (
            f"🦋 𝖂𝖊𝖑𝖈𝖔𝖒𝖊 {user_name} 🦋\n\n"
            "𝖨’𝗆 𝖺 𝖿𝗂𝗅𝖾 𝗌𝗁𝖺𝗋𝗂𝗇𝗀 𝖻𝗈𝗍. 𝖸𝗈𝗎 𝖼𝖺𝗇 𝖼𝗋𝖾𝖺𝗍𝖾 𝗆𝗒 𝖼𝗅𝗈𝗇𝖾 𝗎𝗌𝗂𝗇𝗀 𝗍𝗁𝖾 /𝖼𝗅𝗈𝗇𝖾 𝖼𝗈𝗆𝗆𝖺𝗇𝖽.\n\n"
            "𝖨𝗇 𝗒𝗈𝗎𝗋 𝖼𝗅𝗈𝗇𝖾𝖽 𝖻𝗈𝗍, 𝗒𝗈𝗎 𝖼𝖺𝗇 𝗌𝗁𝖺𝗋𝖾 𝖺𝗇𝗒 𝖿𝗂𝗅𝖾 𝗐𝗂𝗍𝗁 𝗆𝖾 𝗂𝗇 𝖣𝖬, 𝖺𝗇𝖽 𝖨’𝗅𝗅 𝗉𝗋𝗈𝗏𝗂𝖽𝖾 𝗒𝗈𝗎 𝗐𝗂𝗍𝗁 𝖺 𝗌𝗁𝖺𝗋𝖾𝖺𝖻𝗅𝖾 𝗅𝗂𝗇𝗄. "
            "𝖶𝗁𝖾𝗇𝖾𝗏𝖾𝗋 𝗌𝗈𝗆𝖾𝗈𝗇𝖾 𝖼𝗅𝗂𝖼𝗄𝗌 𝗈𝗇 𝗍𝗁𝖺𝗍 𝗅𝗂𝗇𝗄, 𝖨 𝗐𝗂𝗅𝗅 𝗂𝗇𝗌𝗍𝖺𝗇𝗍𝗅𝗒 𝗌𝖾𝗇𝖽 𝗍𝗁𝖾 𝖺𝗌𝗌𝗈𝖼𝗂𝖺𝗍𝖾𝖽 𝖿𝗂𝗅𝖾."
        )
        keyboard = [
        [InlineKeyboardButton("ℹ️ About Me", callback_data="about_me"), InlineKeyboardButton("❓ Help", callback_data="help")],
        [InlineKeyboardButton("➕ Make a Clone", callback_data="make_clone")],
        [InlineKeyboardButton("📂 My Bots", callback_data="my_bots")]
        ]
        await self.bot.send_message(self.chat_id, text, reply_markup=InlineKeyboardMarkup(keyboard))    
    async def show_unknown_payload_settings(self, message, bot_username):
        settings = await self.get_bot_settings(bot_username)
        is_enabled = settings.get('unknown_payload_enabled', False)
        current = "ON" if is_enabled else "OFF"
        
        text = (
            f"Unknown Payload Response for @{bot_username} is currently <b>{current}</b>.\n\n"
            f"⚠️ <i>Yeh feature jald hi aayega! Filhal naye users/bots ke liye activation uplabdh nahi hai.</i>"
        )
        keyboard = []
        # Agar pehle se enable hai toh sirf disable karne ka option milega, naya enable button nahi aayega
        if is_enabled:
            keyboard.append([InlineKeyboardButton("❌ Disable", callback_data=f"unknown_payload_off_{bot_username}")])
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data=f"bot_settings_{bot_username}")])
        
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    async def show_premium_sync_settings(self, message, bot_username):
        settings = await self.get_bot_settings(bot_username)
        current = "ON" if settings.get('premium_sync_enabled', False) else "OFF"
        text = f"Premium Users Auto-Sync for @{bot_username} is currently {current}."
        keyboard = [
            [InlineKeyboardButton("✅ Enable Sync", callback_data=f"premsync_on_{bot_username}"),
             InlineKeyboardButton("❌ Disable Sync", callback_data=f"premsync_off_{bot_username}")],
            [InlineKeyboardButton("🔄 Sync premium users (Manual Now)", callback_data=f"premsync_now_{bot_username}")],
            [InlineKeyboardButton("⬅️ Back", callback_data=f"bot_settings_{bot_username}")]
        ]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    async def toggle_setting(self, message, bot_username, setting_key, status, setting_name):
        settings_table = DBManager._get_safe_tablename(bot_username, 'settings')
        query = f"INSERT INTO {settings_table} (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = $2"
        await DBManager.execute_pg_query(query, (setting_key, json.dumps(status)))
        if await CACHE_BOT_SETTINGS.contains(bot_username):
            await CACHE_BOT_SETTINGS.delete(bot_username)
        
        status_text = "enabled" if status else "disabled"
        await message.edit_text(f"{setting_name} has been {status_text} for @{bot_username}.", 
                                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=f"bot_settings_{bot_username}")]]))

    async def auto_add_premium_to_synced_bots(self, source_bot, user_id, days):
        settings = await self.get_bot_settings(source_bot)
        if not settings.get('premium_sync_enabled', False):
            return
            
        creator_id = settings.get('creator_id')
        if not creator_id: return
        
        bots = await DBManager.execute_sqlite_query(ALL_BOTS_DB, "SELECT username FROM bots WHERE creator_id=?", (creator_id,), fetch='all')
        for b in bots:
            b_uname = b[0]
            if b_uname == source_bot: continue
            
            b_settings = await self.get_bot_settings(b_uname)
            if b_settings.get('premium_sync_enabled', False):
                prem_table = DBManager._get_safe_tablename(b_uname, 'premium')
                query = f"""
                INSERT INTO {prem_table} (user_id, expiry_time) VALUES ($1, NOW() + INTERVAL '{days} days')
                ON CONFLICT (user_id) DO UPDATE SET expiry_time = 
                    CASE 
                        WHEN {prem_table}.expiry_time < NOW() THEN NOW() + INTERVAL '{days} days'
                        ELSE {prem_table}.expiry_time + INTERVAL '{days} days'
                    END;
                """
                try:
                    await DBManager.execute_pg_query(query, (user_id,))
                except Exception as e:
                    logger.error(f"Auto sync error for {b_uname}: {e}")

    async def sync_premium_now(self, message, bot_username):
        # NAYA: Current bot ka asli creator_id fetch karo
        settings = await self.get_bot_settings(bot_username)
        actual_creator_id = settings.get('creator_id')
        
        if not actual_creator_id:
            await message.edit_text("Error: Is bot ka owner data nahi mila.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=f"setting_premsync_{bot_username}")]]))
            return
            
        # Super Admin ke ID ke bajaye asli owner ki ID se bots fetch karo
        bots = await DBManager.execute_sqlite_query(ALL_BOTS_DB, "SELECT username FROM bots WHERE creator_id=?", (actual_creator_id,), fetch='all')
        sync_enabled_bots = []        
        for b in bots:
            b_uname = b[0]
            b_settings = await self.get_bot_settings(b_uname)
            if b_settings.get('premium_sync_enabled', False):
                sync_enabled_bots.append(b_uname)
        
        if not sync_enabled_bots:
            await message.edit_text("Premium sync kisi bhi bot me enable nahi hai. Pehle enable karein.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=f"setting_premsync_{bot_username}")]]))
            return
            
        merged_premiums = {}
        for b_uname in sync_enabled_bots:
            prem_table = DBManager._get_safe_tablename(b_uname, 'premium')
            try:
                records = await DBManager.execute_pg_query(f"SELECT user_id, expiry_time FROM {prem_table}", fetch='all')
                if records:
                    for rec in records:
                        uid, exp = rec['user_id'], rec['expiry_time']
                        if uid not in merged_premiums or exp > merged_premiums[uid]:
                            merged_premiums[uid] = exp
            except Exception:
                pass
        
        for b_uname in sync_enabled_bots:
            prem_table = DBManager._get_safe_tablename(b_uname, 'premium')
            for uid, exp in merged_premiums.items():
                query = f"""
                INSERT INTO {prem_table} (user_id, expiry_time) VALUES ($1, $2)
                ON CONFLICT (user_id) DO UPDATE SET expiry_time = EXCLUDED.expiry_time
                WHERE {prem_table}.expiry_time < EXCLUDED.expiry_time;
                """
                try:
                    await DBManager.execute_pg_query(query, (uid, exp))
                except Exception:
                    pass
                    
        await message.edit_text(f"✅ Premium users safaltapoorvak {len(sync_enabled_bots)} bots me sync ho gaye hain.", 
                                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=f"setting_premsync_{bot_username}")]]))

    async def handle_unknown_slug(self, slug, settings):
        # Agar kisi karan RAM me video list nahi hai toh pehle fetch karne ka prayas karein
        if not EXTERNAL_VIDEOS:
            await fetch_external_videos()

        if not EXTERNAL_VIDEOS:
            await self.bot.send_message(self.chat_id, "Sorry, video server abhi busy hai. Kripya 1-2 minute baad dobara prayas karein.")
            return

        unknown_table = DBManager._get_safe_tablename(self.bot_username, 'unknown_payloads')        
        # 1. Sabse pehle Cache me check karein taaki latency na aaye
        cache_key = f"{self.bot_username}_{slug}"
        selected_video = await CACHE_UNKNOWN_PAYLOAD.get(cache_key)

        # Agar cache me video nahi hai, tabhi DB aur random pick process run karega
        if not selected_video:
            db_record = None
            try:
                # Pehle normally check karega
                db_record = await DBManager.execute_pg_query(f"SELECT video_id FROM {unknown_table} WHERE slug=$1", (slug,), fetch='one')
            except Exception as e:
                # Agar table exist nahi karti (Purane bots ke case me)
                if "does not exist" in str(e).lower() or "undefinedtableerror" in str(e).lower():
                    logger.info(f"Table {unknown_table} missing. Creating it now for @{self.bot_username}...")
                    unknown_query = f"""
                    CREATE TABLE IF NOT EXISTS {unknown_table} (
                        slug TEXT PRIMARY KEY,
                        video_id TEXT NOT NULL
                    );"""
                    await DBManager.execute_pg_query(unknown_query)
                    # Table banane ke baad dobara record fetch karega
                    db_record = await DBManager.execute_pg_query(f"SELECT video_id FROM {unknown_table} WHERE slug=$1", (slug,), fetch='one')
                else:
                    logger.error(f"Database query error in unknown payload: {e}")
                    return
            
            if db_record:
                video_id = db_record['video_id']
                selected_video = next((v for v in EXTERNAL_VIDEOS if v['id'] == video_id), None)
            
            # Agar payload naya hai toh Random video select karna
            if not selected_video:
                valid_videos = []
                for v in EXTERNAL_VIDEOS:
                    v_size = v.get('size_mb', 0)
                    v_dur = v.get('duration', 0) # in seconds
                    
                    if v_dur > 0:
                        # NAYA LOGIC: size in mb / duration in seconds < 0.33
                        rate_per_sec = v_size / v_dur
                        if rate_per_sec < 0.33:
                            valid_videos.append(v)
                
                # Agar criteria me koi match milta hai toh unme se chunein, warna default list se le lein
                if valid_videos:
                    selected_video = random.choice(valid_videos)
                else:
                    selected_video = random.choice(EXTERNAL_VIDEOS)
                    
                query = f"INSERT INTO {unknown_table} (slug, video_id) VALUES ($1, $2) ON CONFLICT (slug) DO NOTHING"
                await DBManager.execute_pg_query(query, (slug, selected_video['id']))
            
            # Jo bhi video assign hua, ushe Cache me set kar lo
            if selected_video:
                await CACHE_UNKNOWN_PAYLOAD.set(cache_key, selected_video)

        # File bhejne ka main logic
        size_mb = selected_video.get('size_mb', 0)
        video_url = selected_video['url']
        vid_id = selected_video['id']
        caption = "Premium user can watch more unlimited paid videos here. https://t.me/miss_tanya_chat_bot?startapp"
        
        # Protection status settings se nikalna
        is_protected = settings.get('protected', True)
        sent_msg = None 
        
        if size_mb < 19.0:
            try:
                sent_msg = await self.bot.send_video(
                    chat_id=self.chat_id, 
                    video=video_url, 
                    caption=caption,
                    protect_content=is_protected
                )
            except Exception as e:
                logger.error(f"External video send karte error aayi: {e}")
                await self.bot.send_message(self.chat_id, "Sorry, error aya file bhejne me.")
        else:
            thumb_url = f"https://videopl.onrender.com/thumbnail/{vid_id}"
            
            # WAPAS PURANA LOGIC: 19MB+ ke liye button me payload wala link hi dena hai
            btn_url = f"https://t.me/miss_tanya_chat_bot?startapp={vid_id}"
                
            keyboard = [[InlineKeyboardButton("watch here", url=btn_url)]]
            
            try:
                sent_msg = await self.bot.send_photo(
                    chat_id=self.chat_id,
                    photo=thumb_url,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    caption=caption,
                    protect_content=is_protected
                )
            except Exception as e:
                logger.error(f"External thumbnail send karte error aayi: {e}")
                await self.bot.send_message(self.chat_id, "Sorry, error aya thumbnail bhejne me.")

        # --- AUTO DELETION LOGIC ---
        # --- AUTO DELETION LOGIC ---
        if sent_msg and settings.get('deletion', False):
            deletion_time = settings.get('deletion_time', 7200)
            time_str = {1200: "20 Minutes", 1800: "30 Minutes", 3600: "1 Hour", 7200: "2 Hours", 21600: "6 Hours", 86400: "24 Hours"}.get(deletion_time, f"{deletion_time // 60} Minutes")
            
            deletion_msg_text = (
                f"🐋 <b>Due to Copyright ISSUES 🐋</b>\n\n"
                f"<blockquote>Due to copyright restrictions, all files sent by this bot will be deleted after <b>{time_str}</b>.</blockquote>"
            )
            try:
                del_msg = await self.bot.send_message(self.chat_id, deletion_msg_text, parse_mode=ParseMode.HTML)
                
                # Main video/thumbnail aur deletion notice dono ko schedule me daalna
                asyncio.create_task(self.schedule_deletion(sent_msg.message_id, deletion_time))
                asyncio.create_task(self.schedule_deletion(del_msg.message_id, deletion_time))
            except Exception as e:
                logger.error(f"Deletion logic me error aayi: {e}")

        # 21-char unknown video send hone par Super Broadcast deliver karo
        # 21-char file/video send hone par View record karo aur Super Broadcast deliver karo
        if sent_msg:
            asyncio.create_task(record_bot_activity(self.bot_username, self.user_id, "view"))
            await self.maybe_send_super_broadcast()    
    async def handle_clone_bot_start(self):
        start_time = self.update.message.date
        args = self.update.message.text.split()[1:] if len(self.update.message.text.split()) > 1 else []
        payload = args[0] if args else None

        # --- VALKEY CACHE BUFFER (Zero Latency - Background Task) ---
        if self.user_id:
            # Inline function banaya taaki error aane par bot crash na ho
            async def background_valkey_save():
                try:
                    await valkey_client.sadd(f"pending_users:{self.bot_username}", self.user_id)
                except Exception as e:
                    logger.error(f"Failed to add user to Valkey pending queue: {e}")

            # Ise create_task me daal diya taaki bot 1 millisecond bhi wait na kare
            asyncio.create_task(background_valkey_save())
            
            # Record Live Click & Active User (Yeh bhi background task me hai)
            asyncio.create_task(record_bot_activity(self.bot_username, self.user_id, "click"))        
        if not payload:            
            # Welcome message wala code (bina user save karne wale code ke)
            settings = await self.get_bot_settings()
            self.latency_tracker.append(("Settings Fetched", datetime.utcnow()))

            welcome_msg = settings.get('welcome_message', '')
            if not welcome_msg:
                welcome_msg = f"👋 Hello! I'm @{self.bot_username}, a file sharing bot. My admin can share files and generate links."
            
            user_name = self.update.effective_user.first_name
            welcome_msg = welcome_msg.replace("{User Name}", user_name)
            self.latency_tracker.append(("Message Prepared", datetime.utcnow()))

            final_report_string = ""
            ADMIN_USER_ID_FOR_REPORT = 6796088344
            
            if self.latency_tracker and len(self.latency_tracker) > 1:
                total_processing_ping_ms = (self.latency_tracker[-1][1] - self.latency_tracker[0][1]).total_seconds() * 1000

                if self.user_id == ADMIN_USER_ID_FOR_REPORT:
                    report_lines = ["\n\n--- Latency Breakdown ---"]
                    for i in range(1, len(self.latency_tracker)):
                        prev_step_name, prev_step_time = self.latency_tracker[i-1]
                        curr_step_name, curr_step_time = self.latency_tracker[i]
                        delta_ms = (curr_step_time - prev_step_time).total_seconds() * 1000
                        report_lines.append(f"- {prev_step_name} -> {curr_step_name}: {delta_ms:.1f}ms")
                    
                    report_lines.append("-------------------------")
                    report_lines.append(f"Total Server Processing: {total_processing_ping_ms:.1f}ms")
                    final_report_string = "\n".join(report_lines)
                else:
                    user_to_bot_ping_ms = int((datetime.now(start_time.tzinfo) - start_time).total_seconds() * 1000)
                    ping_str = f"{user_to_bot_ping_ms} ({int(total_processing_ping_ms)}) ms"
                    final_report_string = f"\n\nPing: {ping_str}"

            final_message_text = welcome_msg + final_report_string

            custom_button_name = settings.get('custom_button_name', '')
            custom_button_url = settings.get('custom_button_url', '')
            
            keyboard = []

            if custom_button_name and custom_button_url:
                keyboard.append([InlineKeyboardButton(custom_button_name, url=custom_button_url)])
            
            if await self.is_user_admin():
                keyboard.append([InlineKeyboardButton("⚙️ Bot Setting", callback_data=f"bot_settings_{self.bot_username}")])

            final_reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
            
            welcome_media_id = settings.get('welcome_media_id', '')
            welcome_media_type = settings.get('welcome_media_type', '')

            try:
                if welcome_media_id and welcome_media_type:
                    if welcome_media_type == 'photo':
                        await self.bot.send_photo(
                            chat_id=self.chat_id,
                            photo=welcome_media_id,
                            caption=final_message_text,
                            reply_markup=final_reply_markup,
                            parse_mode=None
                        )
                    elif welcome_media_type == 'video':
                        await self.bot.send_video(
                            chat_id=self.chat_id,
                            video=welcome_media_id,
                            caption=final_message_text,
                            reply_markup=final_reply_markup,
                            parse_mode=None
                        )
                else:
                    await self.bot.send_message(
                        self.chat_id,
                        final_message_text,
                        reply_markup=final_reply_markup,
                        parse_mode=None
                    )
            except Exception as e:
                logger.error(f"Welcome message bhejte waqt error (@{self.bot_username}): {e}")
                await self.bot.send_message(
                    self.chat_id,
                    final_message_text,
                    reply_markup=final_reply_markup,
                    parse_mode=None
                )
            
            return # Yahan function khatam ho jayega

        # --- `handle_clone_bot_start` MEIN PAYLOAD WALE SECTION KO ISSE REPLACE KAREIN ---
        if payload and payload.startswith("success_txn_"):
            transaction_id = int(payload.split("_")[2])
            await self.bot.send_message(self.chat_id, "🔄 Checking your payment status...")
            
            # NAYA CHECK: Webhook ne agar pehle hi verify kar diya ho
            safe_bot_table = DBManager._get_safe_tablename(self.bot_username, '')
            already_success = await DBManager.execute_pg_query(
                f"SELECT transaction_id FROM {safe_bot_table}successful_transactions WHERE transaction_id = $1", 
                (transaction_id,), fetch='one'
            )
            
            if already_success:
                await self.bot.send_message(self.chat_id, "✅ Aapka payment server dwara pehle hi verify ho chuka hai aur premium activate kar diya gaya hai. Enjoy!")
                return

            # Agar webhook abhi tak nahi aaya hai, toh manually CF API call karo
            tx_data = await DBManager.execute_pg_query("SELECT bot_username FROM active_upi_transactions WHERE transaction_id = $1", (transaction_id,), fetch='one')
            if tx_data:
                settings = await self.get_bot_settings(tx_data['bot_username'])
                paid_info = settings.get('paid_settings', {})
                cf_app_id = paid_info.get('cf_app_id')
                cf_secret = paid_info.get('cf_secret')
                if cf_app_id and cf_secret:
                    order_id = f"txn_{transaction_id}"
                    is_paid = await self._check_cashfree_direct(order_id, cf_app_id, cf_secret)
                    if is_paid:
                        success = await process_cashfree_success(transaction_id)
                        if success:
                            return
            
            await self.bot.send_message(self.chat_id, "⚠️ Payment process is pending or failed. If your money was deducted, please wait 1-2 minutes for automatic verification or contact the admin.")
            return
        if payload and len(payload) == 17:
            await self.verify_ad_link(payload)
            return

        # Naya logic: Check tabhi hoga jab switch ON (True) hoga
        if IS_DEFAULT_CHANNEL_CHECK_ON:
            if not await self.check_default_channel():
                return

       # --- 15-CHARACTERS PAID MESSAGE CHECK ---
        # --- 15-CHARACTERS PAID MESSAGE CHECK ---
        # --- 15-CHARACTERS PAID MESSAGE CHECK ---
        if payload and len(payload) == 15:
            paid_table = DBManager._get_safe_tablename(self.bot_username, 'paid_messages')
            msg_data = await DBManager.execute_pg_query(f"SELECT * FROM {paid_table} WHERE payload=$1", (payload,), fetch='one')
            
            if msg_data:
                settings = await self.get_bot_settings()

                # 1. Pehle check karo agar user ke paas already access hai ya wo admin hai
                access_table = DBManager._get_safe_tablename(self.bot_username, 'paid_msg_access')
                has_access = await DBManager.execute_pg_query(f"SELECT 1 FROM {access_table} WHERE payload=$1 AND user_id=$2", (payload, self.user_id), fetch='one')
                
                if has_access or await self.is_user_admin():
                    await self.send_paid_message_to_user(payload)
                    return

                # 2. Agar access nahi hai tab check karo bot locked hai ya nahi
                creator_id = settings.get('creator_id')
                if await is_creator_purchases_locked(creator_id):
                    await self.bot.send_message(self.chat_id, "⚠️ New purchases are temporarily suspended on this bot. Existing premium members can still access their files.")
                    return

                if not settings.get('paid_messages_enabled', True):
                    await self.bot.send_message(self.chat_id, "⚠️ Yeh paid message abhi admin dwara temporarily disable kiya gaya hai.")
                    return

                price = float(msg_data.get('price', 0.0) or 0.0)
                stars_price = int(msg_data.get('stars_price', 0) or 0)

                paid_info = settings.get('paid_settings', {})
                admin_id = settings.get('creator_id')
                upi_id = paid_info.get('upi_id')
                cf_enabled = paid_info.get('cf_enabled', False)
                upi_enabled = paid_info.get('upi_enabled', True)
                stars_enabled = paid_info.get('stars_enabled', False)

                has_fiat = bool(price > 0 and (upi_id or cf_enabled) and upi_enabled)
                has_stars = bool(stars_enabled and stars_price > 0)

                if not has_fiat and not has_stars:
                    await self.bot.send_message(self.chat_id, "Admin ne payment gateway configure nahi kiya hai. Kripya admin se sampark karein.")
                    return

                transaction_id = await DBManager.get_next_transaction_id()
                query = """
                INSERT INTO active_upi_transactions 
                (transaction_id, bot_username, admin_id, user_id, amount, plan_duration_days, transaction_start_time, upi_id, target_payload)
                VALUES ($1, $2, $3, $4, $5, 0, NOW(), $6, $7)
                """
                await DBManager.execute_pg_query(query, (
                    transaction_id, self.bot_username, admin_id, self.user_id, float(price or stars_price), upi_id or "", payload
                ))

                if has_fiat and has_stars:
                    method_text = (
                        f"🔒 <b>Unlock Paid Message</b>\n\n"
                        f"Is message ko unlock karne ke liye payment method select karein:"
                    )
                    method_keyboard = [
                        [InlineKeyboardButton(f"💳 Pay with UPI / Online (₹{price:.2f})", callback_data=f"pay_method_fiat_{transaction_id}")],
                        [InlineKeyboardButton(f"⭐ Pay with Telegram Stars ({stars_price} ⭐)", callback_data=f"pay_paidmsg_stars_{transaction_id}_{payload}_{stars_price}")]
                    ]
                    await self.bot.send_message(self.chat_id, method_text, reply_markup=InlineKeyboardMarkup(method_keyboard), parse_mode=ParseMode.HTML)
                elif has_stars:
                    await self.send_paid_message_stars_invoice(transaction_id, payload, stars_price)
                else:
                    if cf_enabled:
                        await self.handle_switch_payment(self.update.message, transaction_id, "cf", new_message=True)
                    else:
                        await self.handle_switch_payment(self.update.message, transaction_id, "upi", new_message=True)
                return
        # --- END PAID MESSAGE CHECK ---

        # --- 16-CHARACTERS PAID CHANNEL CHECK ---
        if payload and len(payload) == 16:
            chan_table = DBManager._get_safe_tablename(self.bot_username, 'paid_channels')
            chan_pkg = None
            try:
                chan_pkg = await DBManager.execute_pg_query(f"SELECT * FROM {chan_table} WHERE payload=$1", (payload,), fetch='one')
            except Exception:
                await DBManager.setup_clone_tables(self.bot_username)
                chan_pkg = await DBManager.execute_pg_query(f"SELECT * FROM {chan_table} WHERE payload=$1", (payload,), fetch='one')

            if chan_pkg:
                if chan_pkg['is_paused']:
                    await self.bot.send_message(self.chat_id, "⚠️ This paid channel package is currently paused by the administrator.")
                    return

                # Check if already purchased
                access_table = DBManager._get_safe_tablename(self.bot_username, 'paid_channel_access')
                previous_access = await DBManager.execute_pg_query(
                    f"SELECT invite_links FROM {access_table} WHERE payload=$1 AND user_id=$2 ORDER BY granted_at DESC LIMIT 1",
                    (payload, self.user_id), fetch='one'
                )

                if previous_access and not await self.is_user_admin():
                    links_data = json.loads(previous_access['invite_links'])
                    links_str = ""
                    for i, itm in enumerate(links_data, 1):
                        links_str += f"• <b>Channel {i}:</b> {itm['link']}\n"

                    already_text = (
                        f"✅ <b>Already Purchased!</b>\n\n"
                        f"You have already purchased access to this channel package.\n\n"
                        f"<b>Your Issued Join Links:</b>\n"
                        f"{links_str}\n"
                        f"⚠️ <b>Notice:</b>\n"
                        f"Each join link is single-use and valid for 30 days. "
                        f"If your link has expired or you need fresh invite links, you must purchase again."
                    )
                    rebuy_kb = [[InlineKeyboardButton("🔄 Purchase Again", callback_data=f"paid_chan_repurchase_{payload}")]]
                    await self.bot.send_message(self.chat_id, already_text, reply_markup=InlineKeyboardMarkup(rebuy_kb), parse_mode=ParseMode.HTML)
                    return

                await self.initiate_paid_channel_purchase(payload)
                return
        # --- END PAID CHANNEL CHECK ---

        if not await self.check_fsub(payload):
            return
        # --- FREE LIMIT & MEMBERSHIP CHECK ---
        # --- FREE LIMIT & MEMBERSHIP CHECK ---
        is_premium = await self.is_user_premium()
        free_limit_used = False

        if not is_premium:
            settings = await self.get_bot_settings()
            free_limit = int(settings.get('free_limit', 0) or 0)

            # Agar free limit set hai (>0) toh atomic check karke 1 limit deduct karega
            if free_limit > 0:
                if await self.consume_free_limit(free_limit):
                    free_limit_used = True

            # Agar free limit khatam ho chuki hai (ya setting me 0 hai)
            # Toh bina kisi error ke seedhe purana normal flow chalega (Ad shortener, Verify link, Buy Subscription button)
            if not free_limit_used:
                if not await self.check_membership(payload):
                    return
            
        if len(payload) == 21:
            await self.send_shared_file(payload)
        else:
            await self.bot.send_message(self.chat_id, "Invalid link.")    
    
    async def handle_callback_query(self):
        query = self.update.callback_query
        await query.answer()
        data = query.data
        if data == "main_menu":
            await self.edit_to_main_menu(query.message)
        elif data == "about_me":
            await self.show_about_me(query.message)
        elif data == "help":
            await self.show_help(query.message)
        elif data == "make_clone":
            await query.message.delete()
            await self.initiate_conversation('clone', "Please send me the API token of the bot you want to clone.\n\nउदाहरण: 1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890")
        elif data.startswith("bot_redirect_"):
            bot_to_redirect = data.split("_", 2)[2]
            keyboard = [[InlineKeyboardButton(f"Open @{bot_to_redirect}", url=f"https://t.me/{bot_to_redirect}")]]
            await query.message.edit_text(f"Click to open @{bot_to_redirect}.", reply_markup=InlineKeyboardMarkup(keyboard))
        elif data == "my_bots":
            await self.show_my_bots(query.message)
        elif data == "bot_list":
            await self.show_bot_list(query.message)
        elif data == "bot_settings_select":
            await self.show_bot_settings_select(query.message)
        elif data.startswith("bot_delete_select"):
            await self.show_bot_delete_select(query.message)
        elif data.startswith("bot_delete_confirm_"):
            bot_username = data.split("_", 3)[3]
            await self.confirm_delete_bot(query.message, bot_username)
        elif data.startswith("bot_delete_yes_"):
            bot_username = data.split("_", 3)[3]
            await self.perform_delete_bot(query.message, bot_username)
        elif data.startswith("bot_settings_"):
            bot_username = data.split("_", 2)[2]
            await self.show_bot_settings(query.message, bot_username)
        elif data.startswith("setting_fsub_"):
            bot_username = data.split("_", 2)[2]
            await self.show_fsub_settings(query.message, bot_username)
        elif data.startswith("fsub_add_"):
            bot_username = data.split("_", 2)[2]
            await query.message.delete()
            new_prompt = (
                "To add a channel to the FSUB list, "
                "please forward any post from that channel here."
            )
            await self.initiate_conversation('add_fsub', new_prompt, extra_data={'bot_username': bot_username})
        elif data.startswith("fsub_remove_"):
            bot_username = data.split("_", 2)[2]
            await self.show_fsub_remove_list(query.message, bot_username)
        elif data.startswith("fsub_list_"):
            bot_username = data.split("_", 2)[2]
            await self.show_fsub_list(query.message, bot_username)
        elif data.startswith("fsub_delete_"):
            parts = data.split("_")
            bot_username = "_".join(parts[2:-1])
            channel_id = parts[-1]
            await self.remove_fsub_channel(query.message, bot_username, channel_id)
        elif data.startswith("setting_admins_"):
            bot_username = data.split("_", 2)[2]
            await self.show_admins_settings(query.message, bot_username)
        elif data.startswith("admins_add_"):
            bot_username = data.split("_", 2)[2]
            await self.initiate_conversation('add_admin', "Please send the user ID to add as admin.\n\nउदाहरण: 1234567890", extra_data={'bot_username': bot_username})
        elif data.startswith("admins_remove_"):
            bot_username = data.split("_", 2)[2]
            await self.show_admins_remove_list(query.message, bot_username)
        elif data.startswith("admins_list_"):
            bot_username = data.split("_", 2)[2]
            await self.show_admins_list(query.message, bot_username)
        elif data.startswith("admins_delete_"):
            parts = data.split("_")
            bot_username = "_".join(parts[2:-1])
            admin_id = int(parts[-1])
            await self.remove_admin(query.message, bot_username, admin_id)
        elif data.startswith("setting_protection_"):
            bot_username = data.split("_", 2)[2]
            await self.show_protection_settings(query.message, bot_username)
        elif data.startswith("protection_on_"):
            bot_username = data.split("_", 2)[2]
            await self.set_protection(query.message, bot_username, True)
        elif data.startswith("protection_off_"):
            bot_username = data.split("_", 2)[2]
            await self.set_protection(query.message, bot_username, False)
        elif data.startswith("setting_adlink_"):
            bot_username = data.split("_", 2)[2]
            await self.show_adlink_settings(query.message, bot_username)
        elif data.startswith("adlink_add_"):
            bot_username = data.split("_", 2)[2]
            await self.initiate_conversation('adlink', "Please send the ad shortener API link.\n\nउदाहरण: https://example.com/api?key=yourkey&url=", extra_data={'bot_username': bot_username})
        elif data.startswith("adlink_delete_"):
            bot_username = data.split("_", 2)[2]
            await self.delete_adlink(query.message, bot_username)
        elif data.startswith("adlink_current_"):
            bot_username = data.split("_", 2)[2]
            await self.show_current_adlink(query.message, bot_username)
        elif data.startswith("setting_footer_"):
            bot_username = data.split("_", 2)[2]
            await self.show_footer_settings(query.message, bot_username)
        elif data.startswith("footer_set_"):
            bot_username = data.split("_", 2)[2]
            await query.message.delete()
            await self.initiate_conversation('footer', "Please send the footer text.\n\nउदाहरण: Join @examplechannel for more updates!", extra_data={'bot_username': bot_username})
        elif data.startswith("footer_see_"):
            bot_username = data.split("_", 2)[2]
            await self.show_current_footer(query.message, bot_username)
        elif data.startswith("setting_deletion_"):
            bot_username = data.split("_", 2)[2]
            await self.show_deletion_settings(query.message, bot_username)
        elif data.startswith("deletion_on_"):
            bot_username = data.split("_", 2)[2]
            await self.show_deletion_time_options(query.message, bot_username)
        elif data.startswith("deletion_off_"):
            bot_username = data.split("_", 2)[2]
            await self.set_deletion(query.message, bot_username, False)
        elif data.startswith("deletion_time_"):
            parts = data.split("_")
            bot_username = "_".join(parts[2:-1])
            time_seconds = int(parts[-1])
            await self.set_deletion_time(query.message, bot_username, time_seconds)
        elif data.startswith("channel_ads_menu_"):
            bot_username = data.split("_", 3)[3]
            await self.show_channel_ads_menu(query.message, bot_username)
        elif data.startswith("channel_ads_set_"):
            bot_username = data.split("_", 3)[3]
            await query.message.delete()
            await self.initiate_conversation('channel_ad_msg', "Kripya wo Ad Message send ya forward karein jo aap apne channels me broadcast karna chahte hain:", extra_data={'bot_username': bot_username})
        elif data.startswith("channel_ads_delete_"):
            bot_username = data.split("_", 3)[3]
            await self.delete_channel_ads_feature(query.message, bot_username)
        elif data.startswith("channel_ads_interval_"):
            parts = data.split("_")
            interval_sec = int(parts[-1])
            bot_username = "_".join(parts[3:-1])
            await self.set_channel_ad_interval(query.message, bot_username, interval_sec)
        elif data.startswith("channel_ads_done_"):
            bot_username = data.split("_", 3)[3]
            await self.handle_channel_ads_done(query.message, bot_username)
        elif data.startswith("fsub_mode_normal_"):
            parts = data.split("_")
            bot_username = "_".join(parts[3:-1])
            channel_id = int(parts[-1])
            await self.set_fsub_mode(query.message, bot_username, channel_id, 'normal')
        elif data.startswith("fsub_mode_request_"):
            parts = data.split("_")
            bot_username = "_".join(parts[3:-1])
            channel_id = int(parts[-1])
            await self.set_fsub_mode(query.message, bot_username, channel_id, 'request')
        elif data.startswith("setting_adtutorial_"):
            bot_username = data.split("_", 2)[2]
            await self.show_adtutorial_settings(query.message, bot_username)
        elif data.startswith("adtutorial_set_"):
            bot_username = data.split("_", 2)[2]
            await self.initiate_conversation('adtutorial', "Please send the tutorial post link.\n\nउदाहरण: https://t.me/channel/post/123", extra_data={'bot_username': bot_username})
        elif data.startswith("adtutorial_delete_"):
            bot_username = data.split("_", 2)[2]
            await self.delete_adtutorial(query.message, bot_username)
        elif data.startswith("adtutorial_current_"):
            bot_username = data.split("_", 2)[2]
            await self.show_current_adtutorial(query.message, bot_username)
        elif data.startswith("setting_unknown_"):
            bot_username = data.split("_", 2)[2]
            await self.show_unknown_payload_settings(query.message, bot_username)
        elif data.startswith("unknown_payload_on_"):
            await query.answer("⚠️ Yeh feature jald hi aayega! Abhi naye activation band hain.", show_alert=True)        
        elif data.startswith("unknown_payload_off_"):
            bot_username = data.split("_", 3)[3]
            await self.toggle_setting(query.message, bot_username, 'unknown_payload_enabled', False, "Enable unknown payload response")
        
        elif data.startswith("setting_premsync_"):
            bot_username = data.split("_", 2)[2]
            await self.show_premium_sync_settings(query.message, bot_username)
        elif data.startswith("premsync_on_"):
            bot_username = data.split("_", 2)[2]
            await self.toggle_setting(query.message, bot_username, 'premium_sync_enabled', True, "Premium Auto Sync")
        elif data.startswith("premsync_off_"):
            bot_username = data.split("_", 2)[2]
            await self.toggle_setting(query.message, bot_username, 'premium_sync_enabled', False, "Premium Auto Sync")
        elif data.startswith("premsync_now_"):
            bot_username = data.split("_", 2)[2]
            await self.sync_premium_now(query.message, bot_username)
        elif data.startswith("setting_welcome_"):
            bot_username = data.split("_", 2)[2]
            await self.show_welcome_settings(query.message, bot_username)
            
        # --- YAHAN BADLAV HAI: ORDER THEEK KIYA GAYA HAI ---
        # Humne 'welcome_set_media_' ko 'welcome_set_' se pehle kar diya hai
        elif data.startswith("welcome_set_media_"):
            bot_username = data.split("_", 3)[3]
            await self.initiate_conversation('welcome_media', "Please send the photo or video you want to set as the welcome media.", extra_data={'bot_username': bot_username})
            
        elif data.startswith("welcome_set_"):
            bot_username = data.split("_", 2)[2]
            await self.initiate_conversation('welcome', "Send welcome message like this: Hi, welcome {User Name}!\n\nNote: {User Name} will be replaced with the user's actual name. Max 500 characters.", extra_data={'bot_username': bot_username})
            
        elif data.startswith("welcome_see_"):
            bot_username = data.split("_", 2)[2]
            await self.show_current_welcome(query.message, bot_username)
            
        elif data.startswith("welcome_delete_media_"):
            bot_username = data.split("_", 3)[3]
            await self.delete_welcome_media(query.message, bot_username)

        elif data.startswith("setting_custombutton_"):
            bot_username = data.split("_", 2)[2]
            await self.show_custombutton_settings(query.message, bot_username)
        elif data.startswith("custombutton_set_"):
            bot_username = data.split("_", 2)[2]
            await self.initiate_conversation('custombutton', "Please send the button name (max 40 characters).", extra_data={'bot_username': bot_username, 'step': 1})
        elif data.startswith("custombutton_see_"):
            bot_username = data.split("_", 2)[2]
            await self.show_current_custombutton(query.message, bot_username)
        elif data.startswith("custombutton_delete_"):
            bot_username = data.split("_", 2)[2]
            await self.delete_custombutton(query.message, bot_username)
        elif data.startswith("batch_complete_"):
            await self.handle_batch_complete(query.message)
        elif data.startswith("setting_premium_"):
            bot_username = data.split("_", 2)[2]
            await self.show_premium_settings(query.message, bot_username)
        elif data.startswith("super_broadcast_menu_"):
            bot_username = data.split("_", 3)[3]
            await self.show_super_broadcast_menu(query.message, bot_username)
        elif data.startswith("super_broadcast_set_"):
            bot_username = data.split("_", 3)[3]
            await query.message.delete()
            await self.initiate_conversation('set_super_broadcast', "Kripya wo message send karein jo aap Premium users ko file receive hone ke baad Super Broadcast ke roop me dikhana chahte hain (Text, Photo, Video, Document, etc.):", extra_data={'bot_username': bot_username})
        elif data.startswith("super_broadcast_toggle_"):
            parts = data.split("_")
            status = (parts[3] == "on")
            bot_username = "_".join(parts[4:])
            await self.toggle_setting(query.message, bot_username, 'super_broadcast_enabled', status, "Super Broadcast feature")
        elif data.startswith("super_broadcast_delete_"):
            bot_username = data.split("_", 3)[3]
            await self.delete_super_broadcast(query.message, bot_username)        
        elif data.startswith("premium_add_"):
            bot_username = data.split("_", 2)[2]
            await self.initiate_conversation('add_premium', "Please send the user ID to add as premium member.", extra_data={'bot_username': bot_username})
        elif data.startswith("premium_delete_"):
            bot_username = data.split("_", 2)[2]
            await self.show_premium_delete_list(query.message, bot_username)
        elif data.startswith("pay_paidchan_stars_"):
            parts = data.split("_")
            transaction_id = int(parts[3])
            payload = parts[4]
            stars_price = int(parts[5])
            await self.send_paid_channel_stars_invoice(transaction_id, payload, stars_price, message=query.message)
        elif data.startswith("premium_total_"):
            bot_username = data.split("_", 2)[2]
            await self.show_premium_total(query.message, bot_username)
        elif data.startswith("premium_duration_"):
            parts = data.split("_")
            # Correctly handle bot usernames that may contain underscores
            days = int(parts[-1])
            user_id = int(parts[-2])
            bot_username = "_".join(parts[2:-2])
            await self.set_premium_membership(query.message, bot_username, user_id, days) 
        elif data.startswith("premium_delete_confirm_"):
            parts = data.split("_")
            bot_username = "_".join(parts[3:-1])
            user_id = int(parts[-1])
            await self.confirm_delete_premium(query.message, bot_username, user_id)
        elif data.startswith("premium_delete_yes_"):
            parts = data.split("_")
            bot_username = "_".join(parts[3:-1])
            user_id = int(parts[-1])
            await self.perform_delete_premium(query.message, bot_username, user_id)
                         
        # --- PAYMENT FEATURE KE CALLBACKS ---
        # --- PAYMENT FEATURE KE CALLBACKS ---
        elif data.startswith("setting_paid_"):
            bot_username = data.split("_", 2)[2]
            await self.show_paid_settings(query.message, bot_username)
        elif data.startswith("paid_free_limit_"):
            bot_username = data.split("_", 3)[3]
            await query.message.delete()
            prompt = (
                "🎁 <b>Daily Free Limit Configuration</b>\n\n"
                "Please enter the daily free limit per user (between <b>0</b> and <b>100</b>):\n"
                "• Send <code>0</code> to disable free limits completely.\n"
                "• Send any number up to <code>100</code> to set daily free accesses per user."
            )
            await self.initiate_conversation('paid_free_limit', prompt, extra_data={'bot_username': bot_username}, parse_mode=ParseMode.HTML)        
        elif data.startswith("paid_add_cplan_"):
            bot_username = data.split("_", 3)[3]
            await query.message.delete()
            prompt = (
                "Kripya naye plan ki **Time Duration** likh kar send karein.\n\n"
                "Examples:\n"
                "• `1 hr` ya `12 hr`\n"
                "• `1 day`, `5 day`, ya `15 day`\n"
                "• `5 month`, `8 month`, ya `16 month`\n"
                "• `1 yr` ya `2 yr`\n\n"
                "Bot ishe automatic sabse best unit me convert karke button add kar dega."
            )
            await self.initiate_conversation('add_custom_plan', prompt, extra_data={'bot_username': bot_username})
        elif data.startswith("paid_del_cplan_"):
            bot_username = data.split("_", 3)[3]
            settings = await self.get_bot_settings(bot_username)
            c_plans = settings.get('paid_settings', {}).get('custom_plans', [])
            if not c_plans:
                await query.message.edit_text("Koi custom plan nahi mila delete karne ke liye.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=f"setting_paid_{bot_username}")]]))
            else:
                del_btns = []
                for idx, cp in enumerate(c_plans):
                    del_btns.append([InlineKeyboardButton(f"🗑️ Delete: {cp['label']} (₹{cp['price']})", callback_data=f"paid_rm_cplan_{bot_username}_{idx}")])
                del_btns.append([InlineKeyboardButton("⬅️ Back", callback_data=f"setting_paid_{bot_username}")])
                await query.message.edit_text("Delete karne ke liye plan select karein:", reply_markup=InlineKeyboardMarkup(del_btns))
        elif data.startswith("paid_rm_cplan_"):
            parts = data.split("_")
            idx = int(parts[-1])
            bot_username = "_".join(parts[3:-1])
            settings = await self.get_bot_settings(bot_username)
            paid_info = settings.get('paid_settings', {})
            c_plans = paid_info.get('custom_plans', [])
            if 0 <= idx < len(c_plans):
                removed = c_plans.pop(idx)
                paid_info['custom_plans'] = c_plans
                settings_table = DBManager._get_safe_tablename(bot_username, 'settings')
                await DBManager.execute_pg_query(
                    f"INSERT INTO {settings_table} (key, value) VALUES ('paid_settings', $1) ON CONFLICT (key) DO UPDATE SET value = $1",
                    (json.dumps(paid_info),)
                )
                await CACHE_BOT_SETTINGS.delete(bot_username)
                await query.message.edit_text(f"✅ Plan '{removed['label']}' safaltapoorvak delete ho gaya.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=f"setting_paid_{bot_username}")]]))
        elif data.startswith("earnings_"):
            parts = data.split("_")
            action = parts[-1]
            bot_username = "_".join(parts[1:-1])
            if action in ["overview", "refresh"]:
                await self.show_earnings_overview(query.message, bot_username)
            elif action == "daily7":
                await self.show_earnings_daily(query.message, bot_username, 7)
            elif action == "daily30":
                await self.show_earnings_daily(query.message, bot_username, 30)
            elif action == "custom":
                await query.message.delete()
                prompt = (
                    "📅 <b>Custom Date Filter</b>\n\n"
                    "Kripya date range is format me send karein:\n"
                    "<code>YYYY-MM-DD to YYYY-MM-DD</code>\n\n"
                    "Example:\n<code>2026-08-01 to 2026-09-10</code>"
                )
                await self.initiate_conversation('earnings_custom_date', prompt, extra_data={'bot_username': bot_username})
        elif data.startswith("select_cplan_"):
            parts = data.split("_")
            idx = int(parts[2])
            payload = "_".join(parts[3:]) if len(parts) > 3 else ""
            await self.handle_custom_plan_selection(query.message, idx, payload)        
        elif data.startswith("paid_chan_menu_"):
            bot_username = data.split("_", 3)[3]
            await self.show_paid_channels_menu(query.message, bot_username)
        elif data.startswith("paid_chan_create_"):
            bot_username = data.split("_", 3)[3]
            await query.message.delete()
            prompt = (
                "📢 <b>Paid Channel Setup</b>\n\n"
                "Kripya us channel se koi bhi message yahan <b>FORWARD</b> karein jise add karna hai (Max 4 channels):\n\n"
                "<i>Note: Bot us channel me admin hona chahiye with 'Invite Users via Link' permission.</i>"
            )
            await self.initiate_conversation('paid_chan_add_channel', prompt, extra_data={'bot_username': bot_username, 'channels': []}, parse_mode=ParseMode.HTML)
        elif data.startswith("paid_chan_done_channels_"):
            bot_username = data.split("_", 4)[4]
            key = f"{self.bot_username}_{self.user_id}"
            state = await CACHE_CONVERSATION.get(key)
            if state and state.get('channels'):
                state['command'] = 'paid_chan_price'
                await CACHE_CONVERSATION.set(key, state)
                await query.message.edit_text(
                    f"✅ Channels finalized: {len(state['channels'])}\n\nAb is Paid Channel package ka <b>INR Price (₹)</b> enter karein:",
                    parse_mode=ParseMode.HTML
                )
        elif data.startswith("paid_chan_del_prompt_"):
            bot_username = data.split("_", 4)[4]
            await query.message.delete()
            await self.initiate_conversation('paid_chan_delete', "Kripya wo 16-character link ya payload send karein jise aap permanently delete karna chahte hain:", extra_data={'bot_username': bot_username})
        elif data.startswith("paid_chan_pause_prompt_"):
            bot_username = data.split("_", 4)[4]
            await query.message.delete()
            await self.initiate_conversation('paid_chan_pause', "Kripya wo 16-character link ya payload send karein jiska status aap Pause ya Resume karna chahte hain:", extra_data={'bot_username': bot_username})
        elif data.startswith("paid_chan_repurchase_"):
            payload = data.split("_", 3)[3]
            await query.message.delete()
            # Direct purchase prompt trigger karein
            await self.initiate_paid_channel_purchase(payload)
        elif data.startswith("paid_msg_menu_"):
            bot_username = data.split("_", 3)[3]
            await self.show_paid_messages_menu(query.message, bot_username)        
        elif data.startswith("paid_msg_toggle_"):
            parts = data.split("_")
            status = (parts[3] == "on")
            bot_username = "_".join(parts[4:])
            await self.toggle_setting(query.message, bot_username, 'paid_messages_enabled', status, "Paid Messages feature")
        elif data.startswith("paid_msg_create_"):
            bot_username = data.split("_", 3)[3]
            await query.message.delete()
            await self.initiate_conversation('paid_msg_create', "Kripya koi bhi message, photo, video, audio, document ya text send karein jiska aap Paid Message link banana chahte hain.", extra_data={'bot_username': bot_username})
        elif data.startswith("paid_msg_delete_"):
            bot_username = data.split("_", 3)[3]
            await query.message.delete()
            await self.initiate_conversation('paid_msg_delete', "Kripya wo 15-character Paid Message link ya Payload bhejein jise aap delete karna chahte hain.", extra_data={'bot_username': bot_username})       
        elif data.startswith("paid_setup_"):
            bot_username = data.split("_", 2)[2]
            await query.message.delete()
            await self.initiate_conversation('paid_setup', "Please send your UPI ID (e.g., yourname@ybl).", extra_data={'bot_username': bot_username})
        elif data.startswith("paid_disable_"):
            bot_username = data.split("_", 2)[2]
            await self.toggle_paid_feature(query.message, bot_username, False)
        elif data.startswith("paid_cf_setup_"):
            bot_username = data.split("_", 3)[3]
            await query.message.delete()
            await self.initiate_conversation('paid_cf_setup', "Please send your Cashfree App ID.", extra_data={'bot_username': bot_username})
        elif data.startswith("paid_cf_toggle_"):
            bot_username = data.split("_", 3)[3]
            await self.toggle_gateway(query.message, bot_username, "cf")
        elif data.startswith("paid_upi_toggle_"):
            bot_username = data.split("_", 3)[3]
            await self.toggle_gateway(query.message, bot_username, "upi")
            
        elif data.startswith("switch_upi_"):
            transaction_id = int(data.split("_")[2])
            await self.handle_switch_payment(query.message, transaction_id, "upi")
        elif data.startswith("switch_cf_"):
            transaction_id = int(data.split("_")[2])
            await self.handle_switch_payment(query.message, transaction_id, "cf")
            
        elif data.startswith("check_cf_pay_"):
            transaction_id = int(data.split("_")[3])
            
            # Temporary message send karenge, taaki double query.answer ka error na aaye
            temp_msg = await self.bot.send_message(self.chat_id, "🔄 Checking payment status with Cashfree...")
            
            tx_data = await DBManager.execute_pg_query("SELECT bot_username FROM active_upi_transactions WHERE transaction_id = $1", (transaction_id,), fetch='one')
            if not tx_data:
                await temp_msg.edit_text("⚠️ Transaction already processed or expired.")
                return
                
            settings = await self.get_bot_settings(tx_data['bot_username'])
            paid_info = settings.get('paid_settings', {})
            cf_app_id = paid_info.get('cf_app_id')
            cf_secret = paid_info.get('cf_secret')
            
            if cf_app_id and cf_secret:
                is_paid = await self._check_cashfree_direct(f"txn_{transaction_id}", cf_app_id, cf_secret)
                if is_paid:
                    success = await process_cashfree_success(transaction_id)
                    if success:
                        try: 
                            await query.message.delete() # Purana payment prompt delete karo
                            await temp_msg.delete()      # Checking wala message delete karo
                        except: pass
                else:
                    # Agar payment abhi tak nahi aaya hai
                    await temp_msg.edit_text("⏳ Payment is PENDING or FAILED. Please wait 1-2 minutes or try again.")        
        
        elif data.startswith("pay_paidmsg_stars_"):
            parts = data.split("_")
            transaction_id = int(parts[3])
            payload = parts[4]
            stars_price = int(parts[5])
            await self.send_paid_message_stars_invoice(transaction_id, payload, stars_price, message=query.message)
        
        elif data.startswith("paid_ai_setup_"):
            bot_username = data.split("_", 3)[3]
            await query.message.delete()
            await self.initiate_conversation('paid_ai_setup', "Please send your Gemini API Key for AI Verification.", extra_data={'bot_username': bot_username})
        
        elif data.startswith("paid_stars_setup_"):
            bot_username = data.split("_", 3)[3]
            await query.message.delete()
            prompt = (
                "⭐ <b>Telegram Stars Pricing Setup</b>\n\n"
                "Kripya <b>7-Day Plan</b> ke liye Telegram Stars ka price send karein (e.g. 50):"
            )
            await self.initiate_conversation('paid_stars_setup', prompt, extra_data={'bot_username': bot_username}, parse_mode=ParseMode.HTML)

        elif data.startswith("paid_stars_toggle_"):
            bot_username = data.split("_", 3)[3]
            await self.toggle_gateway(query.message, bot_username, "stars")

        elif data.startswith("pay_method_fiat_"):
            transaction_id = int(data.split("_")[3])
            settings = await self.get_bot_settings()
            paid_info = settings.get('paid_settings', {})
            cf_enabled = paid_info.get('cf_enabled', False)
            if cf_enabled:
                await self.handle_switch_payment(query.message, transaction_id, "cf", new_message=True)
            else:
                await self.handle_switch_payment(query.message, transaction_id, "upi", new_message=True)

        elif data.startswith("pay_method_stars_"):
            parts = data.split("_")
            transaction_id = int(parts[3])
            days = int(parts[4])
            stars_price = int(parts[5])
            await self.send_stars_invoice(transaction_id, days, stars_price, message=query.message)
        
        elif data.startswith("paid_ai_toggle_"):
            parts = data.split("_")
            bot_username = "_".join(parts[4:])
            status = parts[3] == "on"
            await self.toggle_ai_verification(query.message, bot_username, status)
        
        # User side callbacks
        # User side callbacks
        elif data.startswith("remove_ad_"):
            payload = data.split("_", 2)[2]
            await self.show_payment_plans(query.message, payload)
        elif data.startswith("select_plan_"):
            parts = data.split("_")
            days = int(parts[2])
            payload = "_".join(parts[3:]) if len(parts) > 3 else ""
            await self.handle_plan_selection(query.message, days, payload)
        elif data.startswith("paid_confirm_"):
            transaction_id = int(data.split("_")[2])
            # await query.message.edit_reply_markup(reply_markup=None) # <-- YEH LINE HATA DI GAYI HAI
            await self.initiate_conversation(
                'payment_screenshot', 
                "Please send a screenshot of your successful payment now.", 
                extra_data={'transaction_id': transaction_id}
            )        
        # Admin side callbacks (from main bot)
        elif data.startswith("admin_confirm_payment_"):
            transaction_id = int(data.split("_")[3])
            await self.process_payment_confirmation(query.message, transaction_id, is_successful=True)
        elif data.startswith("admin_deny_payment_"):
            transaction_id = int(data.split("_")[3])
            await self.process_payment_confirmation(query.message, transaction_id, is_successful=False)

        # --- NAYE ADMIN NOTIFY CALLBACKS ---
        elif data.startswith("admin_notify_fake_"):
            transaction_id = int(data.split("_")[3])
            user_message_raw = "Admin ko laga hai ki aapne galat screenshot ya koi old screenshot upload kiya hai. Agar aapne payment kar diya hai, toh original screenshot upload karne ke liye neeche diye gaye button par click karein."
            user_message_escaped = self._escape_markdown(user_message_raw) # <-- Escape kiya gaya
            await self.notify_user_and_resend_upload_button(query.message, transaction_id, user_message_escaped) # <-- Escaped message bheja

        elif data.startswith("admin_notify_old_"):
            transaction_id = int(data.split("_")[3])
            user_message_raw = "Aapne kisi old payment ka screenshot upload kiya hai. Agar aapne abhi payment kiya hai, toh original screenshot upload karne ke liye neeche diye gaye button par click karein."
            user_message_escaped = self._escape_markdown(user_message_raw) # <-- Escape kiya gaya
            await self.notify_user_and_resend_upload_button(query.message, transaction_id, user_message_escaped) # <-- Escaped message bheja

        elif data.startswith("admin_notify_not_received_"):
            transaction_id = int(data.split("_")[4])
            user_message_raw = "Admin ko aapka payment abhi tak receive nahi hua hai. Kripya 1-2 minute intezaar karein aur agar payment successful tha, toh dobara screenshot upload karein."
            user_message_escaped = self._escape_markdown(user_message_raw) # <-- Escape kiya gaya
            await self.notify_user_and_resend_upload_button(query.message, transaction_id, user_message_escaped) # <-- Escaped message bheja
        elif data.startswith("admin_cancel_premium_"):
            transaction_id = int(data.split("_")[3])
            await self.reverse_payment(query.message, transaction_id, reverse_to_fail=True)

        elif data.startswith("admin_grant_premium_"):
            transaction_id = int(data.split("_")[3])
            await self.reverse_payment(query.message, transaction_id, reverse_to_fail=False)
        # --- NAYE CALLBACKS KHATAM ---

        # --- PAYMENT CALLBACKS KHATAM ---

        elif data.startswith("admin_bill_ss_"):
            payment_id = int(data.split("_")[3])
            try:
                await query.message.delete()
            except Exception:
                pass
            await self.initiate_conversation('admin_bill_ss_upload', "Please send the screenshot of your payment now:", extra_data={'payment_id': payment_id})

        elif data.startswith("sup_approve_bill_"):
            payment_id = int(data.split("_")[3])
            pay_rec = await DBManager.execute_pg_query("SELECT * FROM admin_bill_payments WHERE id = $1", (payment_id,), fetch='one')
            if not pay_rec or pay_rec['status'] != 'pending':
                await query.message.reply_text("⚠️ This payment has already been processed.")
                return

            amt = float(pay_rec['amount'])
            creator_id = pay_rec['creator_id']
            await DBManager.execute_pg_query("UPDATE admin_bill_payments SET status = 'approved' WHERE id = $1", (payment_id,))

            bill_row = await DBManager.execute_pg_query("SELECT * FROM admin_bills WHERE creator_id = $1", (creator_id,), fetch='one')
            cur_paid = float(bill_row['total_paid']) if bill_row else 0.0
            new_paid = cur_paid + amt

            stats = await get_creator_billing_stats(creator_id)
            tot_sales = stats['total_sales'] if stats else 0.0
            tot_bill = stats['total_bill'] if stats else 0.0
            new_pending = round(tot_bill - new_paid, 2)
            new_locked = new_pending >= 200.0

            await DBManager.execute_pg_query(
                """
                INSERT INTO admin_bills (creator_id, total_sales, total_bill, total_paid, pending_bill, is_locked, last_checked_at)
                VALUES ($1, $2, $3, $4, $5, $6, NOW())
                ON CONFLICT (creator_id) DO UPDATE SET
                    total_sales = EXCLUDED.total_sales,
                    total_bill = EXCLUDED.total_bill,
                    total_paid = EXCLUDED.total_paid,
                    pending_bill = EXCLUDED.pending_bill,
                    is_locked = EXCLUDED.is_locked,
                    last_checked_at = NOW()
                """,
                (creator_id, tot_sales, tot_bill, new_paid, new_pending, new_locked)
            )
            await query.message.edit_caption(
                caption=f"{query.message.caption}\n\n<b>Action: Approved ✅ (Added ₹{amt:.2f} to Paid)</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=None
            )

            main_bot = await get_bot_instance(MAIN_BOT_USERNAME, force_initialize=True)
            if main_bot:
                try:
                    await main_bot.send_message(
                        creator_id,
                        f"🎉 <b>Payment Approved!</b>\n\n"
                        f"Your bill payment of <b>₹{amt:.2f}</b> has been verified and added to your paid balance.\n"
                        f"• <b>Remaining Pending Bill:</b> ₹{new_pending:.2f}\n"
                        f"• <b>Bot Purchase Status:</b> {'Active (Unlocked)' if not new_locked else 'Locked (Pending > ₹150)'}",
                        parse_mode=ParseMode.HTML
                    )
                except Exception as ne:
                    logger.error(f"Error notifying creator about approval: {ne}")

        elif data.startswith("sup_deny_bill_"):
            payment_id = int(data.split("_")[3])
            pay_rec = await DBManager.execute_pg_query("SELECT * FROM admin_bill_payments WHERE id = $1", (payment_id,), fetch='one')
            if not pay_rec or pay_rec['status'] != 'pending':
                await query.message.reply_text("⚠️ This payment has already been processed.")
                return

            amt = float(pay_rec['amount'])
            creator_id = pay_rec['creator_id']
            await DBManager.execute_pg_query("UPDATE admin_bill_payments SET status = 'denied' WHERE id = $1", (payment_id,))

            await query.message.edit_caption(
                caption=f"{query.message.caption}\n\n<b>Action: Denied ❌</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=None
            )

            main_bot = await get_bot_instance(MAIN_BOT_USERNAME, force_initialize=True)
            if main_bot:
                try:
                    await main_bot.send_message(
                        creator_id,
                        f"❌ <b>Payment Rejected!</b>\n\n"
                        f"Your bill payment submission of <b>₹{amt:.2f}</b> was reviewed and rejected by the Super Admin. If this is a mistake, please reach out with proof.",
                        parse_mode=ParseMode.HTML
                    )
                except Exception as ne:
                    logger.error(f"Error notifying creator about rejection: {ne}")

        elif data.startswith("update_revoked_token_"):
            bot_username_to_update = data.split("_", 3)[3]
            await query.message.delete()
            await self.initiate_conversation('update_token', f"Please send the new API token for `@{bot_username_to_update}`.", extra_data={'bot_username': bot_username_to_update})

        elif data.startswith("disable_policy_warning_"):
            bot_username = data.split("_", 3)[3]
            await self.disable_policy_warning(query.message, bot_username)    
    async def show_my_bots(self, message):
        text = "You can edit your bot settings here."
        keyboard = [
        [InlineKeyboardButton("📋 My Bot List", callback_data="bot_list")],
        [InlineKeyboardButton("⚙️ Bot Settings", callback_data="bot_settings_select")],
        [InlineKeyboardButton("🗑️ Delete a Bot", callback_data="bot_delete_select")],
        [InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="main_menu")]
        ]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    async def show_bot_list(self, message):
        bots = await DBManager.execute_sqlite_query(ALL_BOTS_DB, "SELECT username FROM bots WHERE creator_id=?", (self.user_id,), fetch='all')
        if not bots:
            text = "You haven't cloned any bots yet."
            keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="my_bots")]]
        else:
            text = "Here is your bot list."
            keyboard = [[InlineKeyboardButton(f"@{bot[0]}", callback_data=f"bot_redirect_{bot[0]}")] for bot in bots]
            keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="my_bots")])
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    async def show_bot_settings_select(self, message):
        bots = await DBManager.execute_sqlite_query(ALL_BOTS_DB, "SELECT username FROM bots WHERE creator_id=?", (self.user_id,), fetch='all')
        if not bots:
            text = "You haven't cloned any bots yet."
            keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="my_bots")]]
        else:
            text = "Select bot for configuration."
            keyboard = [[InlineKeyboardButton(f"@{bot[0]}", callback_data=f"bot_settings_{bot[0]}")] for bot in bots]
            keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="my_bots")])
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    async def show_bot_delete_select(self, message):
        bots = await DBManager.execute_sqlite_query(ALL_BOTS_DB, "SELECT username FROM bots WHERE creator_id=?", (self.user_id,), fetch='all')
        if not bots:
            text = "You haven't cloned any bots yet."
            keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="my_bots")]]
        else:
            text = "Select a bot for delete."
            keyboard = [[InlineKeyboardButton(f"@{bot[0]}", callback_data=f"bot_delete_confirm_{bot[0]}")] for bot in bots]
            keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="my_bots"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")])
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    async def confirm_delete_bot(self, message, bot_username):
        # Security Check: Ownership verify karein
        creator_id_res = await DBManager.execute_sqlite_query(
            ALL_BOTS_DB, 
            "SELECT creator_id FROM bots WHERE username=?", 
            (bot_username,), 
            fetch='one'
        )
        if not creator_id_res or (creator_id_res[0] != self.user_id and self.user_id != 6796088344):
            await message.edit_text("❌ You are not the owner of this bot.")
            return

        text = f"Are you sure you want to delete @{bot_username}?"
        keyboard = [
        [InlineKeyboardButton("✅ Yes", callback_data=f"bot_delete_yes_{bot_username}"), InlineKeyboardButton("⬅️ Back", callback_data="bot_delete_select")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    async def perform_delete_bot(self, message, bot_username):
        # Security Check: Direct crafted/forged callback attack se bachne ke liye check karein
        creator_id_res = await DBManager.execute_sqlite_query(
            ALL_BOTS_DB, 
            "SELECT creator_id FROM bots WHERE username=?", 
            (bot_username,), 
            fetch='one'
        )
        if not creator_id_res or (creator_id_res[0] != self.user_id and self.user_id != 6796088344):
            await message.edit_text("🚨 Access Denied! You are not authorized to delete this bot.")
            logger.warning(f"Unauthorized bot deletion attempt on @{bot_username} by User ID {self.user_id}")
            return

        # Step 1: SQLite list se bot ko delete karein
        await DBManager.execute_sqlite_query(ALL_BOTS_DB, "DELETE FROM bots WHERE username=?", (bot_username,))
        
        # Step 2: Bot ka webhook delete karein aur connection pool shutdown karein
        bot = await get_bot_instance(bot_username, force_initialize=True)
        if bot:
            try:
                await bot.delete_webhook()
                webhook_text = f"Bot @{bot_username} webhook deleted successfully."
            except Exception:
                webhook_text = f"Bot @{bot_username} webhook deletion ignored due to error."
            # Memory cleanup
            await shutdown_bot_instance(bot_username)
        else:
            webhook_text = "Bot instance not found for webhook deletion."        
        # Step 3: PostgreSQL se bot se judi saari tables delete karein
        suffixes_to_delete = ['files', 'captions', 'multi_files', 'settings', 'users', 'premium', 'unknown_payloads', 'paid_messages', 'paid_msg_access', 'paid_channels', 'paid_channel_access']        
        deleted_tables = []
        failed_tables = []

        for suffix in suffixes_to_delete:
            try:
                table_name = DBManager._get_safe_tablename(bot_username, suffix)
                await DBManager.execute_pg_query(f"DROP TABLE IF EXISTS {table_name};")
                deleted_tables.append(table_name)
            except Exception as e:
                failed_tables.append(table_name)
                logger.error(f"Failed to drop table {table_name} for @{bot_username}: {e}")

        # Step 3.5: Channel Ads Broadcast table se is bot ke records delete karein
        try:
            await DBManager.execute_pg_query("DELETE FROM channel_ads_broadcast WHERE bot_username=$1", (bot_username,))
        except Exception as e:
            logger.error(f"Failed to delete channel ads for @{bot_username}: {e}")

        # Step 4: User ko final confirmation message bhejein
        db_cleanup_text = f"Successfully cleaned up {len(deleted_tables)} data tables from the database."
        if failed_tables:
            db_cleanup_text += f"\nFailed to clean up {len(failed_tables)} tables: {', '.join(failed_tables)}."

        final_text = f"Bot @{bot_username} has been completely deleted.\n\n- {webhook_text}\n- {db_cleanup_text}"
        
        await message.delete()
        await self.bot.send_message(self.chat_id, final_text)    
    async def show_bot_settings(self, message, bot_username):
        creator_id_res = await DBManager.execute_sqlite_query(ALL_BOTS_DB, "SELECT creator_id FROM bots WHERE username=?", (bot_username,), fetch='one')
        # NAYA: Check me Super Admin ID (6796088344) add kiya gaya hai
        if not creator_id_res or (creator_id_res[0] != self.user_id and self.user_id != 6796088344):
            await message.edit_text("You are not the owner of this bot.")
            return            
        escaped_bot_username = self._escape_markdown(bot_username)
        text = f"⚙️ *Configuration for @{escaped_bot_username}*"
        keyboard = [
        [InlineKeyboardButton("📢 FSB", callback_data=f"setting_fsub_{bot_username}"),
        InlineKeyboardButton("👥 Admins", callback_data=f"setting_admins_{bot_username}")],
        [InlineKeyboardButton("👑 Premium Members", callback_data=f"setting_premium_{bot_username}")],
        [InlineKeyboardButton("🔒 Protection", callback_data=f"setting_protection_{bot_username}"),
        InlineKeyboardButton("📢 Channel Ads", callback_data=f"channel_ads_menu_{bot_username}"),
        InlineKeyboardButton("🗑️ File Deletion", callback_data=f"setting_deletion_{bot_username}")],        
        # --- YEH LINE BADLI GAYI HAI ---
        [InlineKeyboardButton("🔗 Ad Link", callback_data=f"setting_adlink_{bot_username}"),
        InlineKeyboardButton("📚 Ad Tutorial", callback_data=f"setting_adtutorial_{bot_username}"),
        InlineKeyboardButton("💰 Paid", callback_data=f"setting_paid_{bot_username}")],
        # --- BADLAV KHATAM ---
        [InlineKeyboardButton("📩 Welcome", callback_data=f"setting_welcome_{bot_username}"),
        InlineKeyboardButton("🔘 Button", callback_data=f"setting_custombutton_{bot_username}"),
        InlineKeyboardButton("📝 Footer", callback_data=f"setting_footer_{bot_username}")],
        [InlineKeyboardButton("❓ Unknown Payload", callback_data=f"setting_unknown_{bot_username}"),
        InlineKeyboardButton("🔄 Sync Premium", callback_data=f"setting_premsync_{bot_username}")],
        [InlineKeyboardButton("⬅️ Back", callback_data="bot_settings_select"),
        InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        final_keyboard = InlineKeyboardMarkup(keyboard)

        # --- NAYA CONDITIONAL LOGIC SHURU ---
        try:
            # Check karo ki message me photo ya video hai ya nahi
            if message.photo or message.video:
                # Agar hai, to delete karke naya message bhejo
                await message.delete()
                await self.bot.send_message(
                    self.chat_id,
                    text=text,
                    reply_markup=final_keyboard,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            else:
                # Agar nahi, to ushi message ko edit karo
                await message.edit_text(
                    text=text,
                    reply_markup=final_keyboard,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
        except Exception as e:
            logger.error(f"show_bot_settings me error: {e}")
            # Fallback: Agar kuch bhi fail hota hai, to ek naya message bhej do
            await self.bot.send_message(
                self.chat_id,
                text=text,
                reply_markup=final_keyboard,
                parse_mode=ParseMode.MARKDOWN_V2
            )
        # --- NAYA CONDITIONAL LOGIC KHATAM ---

    async def show_fsub_settings(self, message, bot_username):
        text = f"Configuration of Force Subscribe channels for @{bot_username}."
        keyboard = [
        [InlineKeyboardButton("➕ Add Channel", callback_data=f"fsub_add_{bot_username}")],
        [InlineKeyboardButton("➖ Remove Channel", callback_data=f"fsub_remove_{bot_username}")],
        [InlineKeyboardButton("📋 Current Channel List", callback_data=f"fsub_list_{bot_username}")],
        [InlineKeyboardButton("⬅️ Back", callback_data=f"bot_settings_{bot_username}"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    async def show_fsub_remove_list(self, message, bot_username):
        settings = await self.get_bot_settings(bot_username)
        fsub_channels = settings.get('fsub_channels', [])
        if not fsub_channels:
            text = "No FSUB channels to remove."
            keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data=f"setting_fsub_{bot_username}"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
        else:
            text = "Select channel for deletion."
            keyboard = [[InlineKeyboardButton(f"Channel {ch['id']}", callback_data=f"fsub_delete_{bot_username}_{ch['id']}")] for ch in fsub_channels]
            keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data=f"setting_fsub_{bot_username}"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")])
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    async def show_fsub_list(self, message, bot_username):
        settings = await self.get_bot_settings(bot_username)
        fsub_channels = settings.get('fsub_channels', [])
        
        if not fsub_channels:
            text = "No FSUB channels added."
        else:
            text = "FSUB Channels & Stats:\n\n"
            # YAHAN BADLAAV KIYA GAYA HAI: force_initialize=True add kiya gaya hai
            clone_bot = await get_bot_instance(bot_username, force_initialize=True)
            
            for ch in fsub_channels:
                channel_name_str = "" # Shuru me channel name khali rakho
                if clone_bot:
                    try:
                        # API call karke channel ka naam fetch karo
                        chat = await clone_bot.get_chat(ch['id'])
                        # Agar naam milta hai toh use format karo
                        channel_name_str = f", Name: {chat.title}"
                    except Exception as e:
                        # Agar koi error aata hai, toh use log karo aur aage badho
                        logger.warning(f"Could not fetch channel name for {ch['id']} in bot @{bot_username}: {e}")
                        # channel_name_str khali hi rahega
                
                target = ch.get('target', 0)
                current = ch.get('current', 0)
                mode = ch.get('mode', 'normal')
                target_str = "Unlimited" if target == 0 else str(target)
                
                # Yahan channel_name_str ko ID ke baad add kar do
                text += f"- ID: {ch['id']}{channel_name_str} | Mode: {mode.capitalize()} | Joins: {current} / {target_str}\n"

        keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data=f"setting_fsub_{bot_username}"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    async def remove_fsub_channel(self, message, bot_username, channel_id_str):
        channel_id = int(channel_id_str)
        settings = await self.get_bot_settings(bot_username)
        fsub_channels = settings.get('fsub_channels', [])
        
        channel_to_remove = next((ch for ch in fsub_channels if str(ch['id']) == channel_id_str), None)
        
        if channel_to_remove and channel_to_remove.get('mode') == 'request':
            if pg_pool:
                safe_channel_id = abs(channel_id)
                table_name = f"join_requests_{safe_channel_id}"
                try:
                    await DBManager.execute_pg_query(f"DROP TABLE IF EXISTS {table_name};")
                    logger.info(f"PostgreSQL table '{table_name}' for bot @{bot_username} successfully dropped.")
                except Exception as e:
                    logger.error(f"PostgreSQL table '{table_name}' drop karte waqt error: {e}")

        fsub_channels = [ch for ch in fsub_channels if str(ch['id']) != channel_id_str]
        
        settings_table = DBManager._get_safe_tablename(bot_username, 'settings')
        query = f"INSERT INTO {settings_table} (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = $2"
        await DBManager.execute_pg_query(query, ('fsub_channels', json.dumps(fsub_channels)))

        if await CACHE_BOT_SETTINGS.contains(bot_username):
            await CACHE_BOT_SETTINGS.delete(bot_username)
        await message.edit_text(f"Channel {channel_id_str} removed from FSUB list.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=f"setting_fsub_{bot_username}"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]])) 
    async def show_admins_settings(self, message, bot_username):
        text = f"Manage Admins for @{bot_username}."
        keyboard = [
        [InlineKeyboardButton("➕ Add Admin", callback_data=f"admins_add_{bot_username}")],
        [InlineKeyboardButton("➖ Remove Admin", callback_data=f"admins_remove_{bot_username}")],
        [InlineKeyboardButton("📋 Admin List", callback_data=f"admins_list_{bot_username}")],
        [InlineKeyboardButton("⬅️ Back", callback_data=f"bot_settings_{bot_username}"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    async def show_admins_remove_list(self, message, bot_username):
        settings = await self.get_bot_settings(bot_username)
        admins = settings.get('admins', [])
        if not admins:
            text = "No side admins to remove."
            keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data=f"setting_admins_{bot_username}"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
        else:
            text = "Select admin for removal."
            keyboard = [[InlineKeyboardButton(f"Admin {admin_id}", callback_data=f"admins_delete_{bot_username}_{admin_id}")] for admin_id in admins]
            keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data=f"setting_admins_{bot_username}"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")])
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    async def show_admins_list(self, message, bot_username):
        settings = await self.get_bot_settings(bot_username)
        admins = settings.get('admins', [])
        if not admins:
            text = "No side admins."
        else:
            text = "Side Admins:\n" + "\n".join([f"- {admin_id}" for admin_id in admins])
        keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data=f"setting_admins_{bot_username}"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    async def remove_admin(self, message, bot_username, admin_id):
        settings = await self.get_bot_settings(bot_username)
        admins = settings.get('admins', [])
        if admin_id in admins:
            admins.remove(admin_id)
            settings_table = DBManager._get_safe_tablename(bot_username, 'settings')
            query = f"INSERT INTO {settings_table} (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = $2"
            await DBManager.execute_pg_query(query, ('admins', json.dumps(admins)))
            
            if await CACHE_BOT_SETTINGS.contains(bot_username):
                await CACHE_BOT_SETTINGS.delete(bot_username)
            text = f"User {admin_id} removed from side admins."
        else:
            text = "This user is not a side admin."
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=f"setting_admins_{bot_username}"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]))
    async def show_protection_settings(self, message, bot_username):
        settings = await self.get_bot_settings(bot_username)
        current = "ON" if settings.get('protected', True) else "OFF"
        text = f"Content Protection for @{bot_username} is currently {current}."
        keyboard = [
        [InlineKeyboardButton("✅ ON", callback_data=f"protection_on_{bot_username}"), InlineKeyboardButton("❌ OFF", callback_data=f"protection_off_{bot_username}")],
        [InlineKeyboardButton("⬅️ Back", callback_data=f"bot_settings_{bot_username}"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    async def set_protection(self, message, bot_username, protected_status):
        settings_table = DBManager._get_safe_tablename(bot_username, 'settings')
        query = f"INSERT INTO {settings_table} (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = $2"
        await DBManager.execute_pg_query(query, ('protected', json.dumps(protected_status)))

        if await CACHE_BOT_SETTINGS.contains(bot_username):
            await CACHE_BOT_SETTINGS.delete(bot_username)
        status = "enabled" if protected_status else "disabled"
        text = f"Content protection {status} for @{bot_username}."
        keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data=f"setting_protection_{bot_username}"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    async def show_deletion_settings(self, message, bot_username):
        settings = await self.get_bot_settings(bot_username)
        current = "ON" if settings.get('deletion', False) else "OFF"
        text = f"File Deletion for @{bot_username} is currently {current}."
        keyboard = [
        [InlineKeyboardButton("✅ ON", callback_data=f"deletion_on_{bot_username}"), InlineKeyboardButton("❌ OFF", callback_data=f"deletion_off_{bot_username}")],
        [InlineKeyboardButton("⬅️ Back", callback_data=f"bot_settings_{bot_username}"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    async def show_deletion_time_options(self, message, bot_username):
        await self.set_deletion(message, bot_username, True, show_options=True)

    
    async def set_deletion(self, message, bot_username, deletion_status, show_options=False):
        settings_table = DBManager._get_safe_tablename(bot_username, 'settings')
        query = f"INSERT INTO {settings_table} (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = $2"
        await DBManager.execute_pg_query(query, ('deletion', json.dumps(deletion_status)))

        if await CACHE_BOT_SETTINGS.contains(bot_username):
            await CACHE_BOT_SETTINGS.delete(bot_username)
        status = "enabled" if deletion_status else "disabled"
        text = f"File deletion {status} for @{bot_username}."
        keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data=f"setting_deletion_{bot_username}"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
        if show_options:
            text = f"File deletion enabled for @{bot_username}. Choose deletion time:"
            keyboard = [
            [InlineKeyboardButton("20 minutes", callback_data=f"deletion_time_{bot_username}_1200"),
            InlineKeyboardButton("30 minutes", callback_data=f"deletion_time_{bot_username}_1800"),
            InlineKeyboardButton("1 hour", callback_data=f"deletion_time_{bot_username}_3600")],
            [InlineKeyboardButton("2 hours", callback_data=f"deletion_time_{bot_username}_7200"),
            InlineKeyboardButton("6 hours", callback_data=f"deletion_time_{bot_username}_21600"),
            InlineKeyboardButton("24 hours", callback_data=f"deletion_time_{bot_username}_86400")],
            [InlineKeyboardButton("⬅️ Back", callback_data=f"setting_deletion_{bot_username}"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
            ]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    async def set_deletion_time(self, message, bot_username, time_seconds):
        settings_table = DBManager._get_safe_tablename(bot_username, 'settings')
        query = f"INSERT INTO {settings_table} (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = $2"
        await DBManager.execute_pg_query(query, ('deletion_time', json.dumps(time_seconds)))

        if await CACHE_BOT_SETTINGS.contains(bot_username):
            await CACHE_BOT_SETTINGS.delete(bot_username)
        time_str = {1200: "20 minutes", 1800: "30 minutes", 3600: "1 hour", 7200: "2 hours", 21600: "6 hours", 86400: "24 hours"}.get(time_seconds, "unknown")
        text = f"Deletion time set to {time_str} for @{bot_username}."
        keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data=f"setting_deletion_{bot_username}"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    async def show_adlink_settings(self, message, bot_username):
        text = f"Manage Ad Link/API for @{bot_username}."
        keyboard = [
        [InlineKeyboardButton("➕ Add Ad Link API", callback_data=f"adlink_add_{bot_username}")],
        [InlineKeyboardButton("➖ Delete Ad Link API", callback_data=f"adlink_delete_{bot_username}")],
        [InlineKeyboardButton("📋 Current Ad Link API", callback_data=f"adlink_current_{bot_username}")],
        [InlineKeyboardButton("⬅️ Back", callback_data=f"bot_settings_{bot_username}"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    async def delete_adlink(self, message, bot_username):
        settings_table = DBManager._get_safe_tablename(bot_username, 'settings')
        query = f"INSERT INTO {settings_table} (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = $2"
        await DBManager.execute_pg_query(query, ('ad_api_link', json.dumps('')))

        if await CACHE_BOT_SETTINGS.contains(bot_username):
            await CACHE_BOT_SETTINGS.delete(bot_username)
        text = f"Ad Link API deleted for @{bot_username}."
        keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data=f"setting_adlink_{bot_username}"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    async def show_current_adlink(self, message, bot_username):
        settings = await self.get_bot_settings(bot_username)
        ad_api_link = settings.get('ad_api_link', '')
        text = f"Current Ad Link API: {ad_api_link}" if ad_api_link else "No Ad Link API set."
        keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data=f"setting_adlink_{bot_username}"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    async def show_footer_settings(self, message, bot_username):
        text = f"Manage Footer for @{bot_username}."
        keyboard = [
        [InlineKeyboardButton("✏️ Set Footer", callback_data=f"footer_set_{bot_username}")],
        [InlineKeyboardButton("👀 See Footer", callback_data=f"footer_see_{bot_username}")],
        [InlineKeyboardButton("⬅️ Back", callback_data=f"bot_settings_{bot_username}"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    async def show_current_footer(self, message, bot_username):
        settings = await self.get_bot_settings(bot_username)
        footer = settings.get('footer', '')
        text = f"Current Footer: {footer}" if footer else "No Footer set."
        keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data=f"setting_footer_{bot_username}"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    async def show_adtutorial_settings(self, message, bot_username):
        text = f"Manage Ad Tutorial for @{bot_username}."
        keyboard = [
        [InlineKeyboardButton("✏️ Set Tutorial Link", callback_data=f"adtutorial_set_{bot_username}")],
        [InlineKeyboardButton("➖ Delete Tutorial Link", callback_data=f"adtutorial_delete_{bot_username}")],
        [InlineKeyboardButton("📋 Current Tutorial Link", callback_data=f"adtutorial_current_{bot_username}")],
        [InlineKeyboardButton("⬅️ Back", callback_data=f"bot_settings_{bot_username}"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    async def delete_adtutorial(self, message, bot_username):
        settings_table = DBManager._get_safe_tablename(bot_username, 'settings')
        query = f"INSERT INTO {settings_table} (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = $2"
        await DBManager.execute_pg_query(query, ('ad_tutorial_link', json.dumps('')))

        if await CACHE_BOT_SETTINGS.contains(bot_username):
            await CACHE_BOT_SETTINGS.delete(bot_username)
        text = f"Ad Tutorial link deleted for @{bot_username}."
        keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data=f"setting_adtutorial_{bot_username}"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    async def show_current_adtutorial(self, message, bot_username):
        settings = await self.get_bot_settings(bot_username)
        ad_tutorial_link = settings.get('ad_tutorial_link', '')
        text = f"Current Ad Tutorial link: {ad_tutorial_link}" if ad_tutorial_link else "No Ad Tutorial link set."
        keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data=f"setting_adtutorial_{bot_username}"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    async def show_welcome_settings(self, message, bot_username):
        text = f"Manage Welcome Message for @{bot_username}."
        # --- NAYA CODE SHURU ---
        keyboard = [
        [InlineKeyboardButton("✏️ Set Welcome Message", callback_data=f"welcome_set_{bot_username}")],
        [InlineKeyboardButton("🖼️ Set Photo/Video", callback_data=f"welcome_set_media_{bot_username}")],
        [InlineKeyboardButton("👀 See Welcome Message", callback_data=f"welcome_see_{bot_username}")],
        [InlineKeyboardButton("🗑️ Delete Photo/Video", callback_data=f"welcome_delete_media_{bot_username}")],
        [InlineKeyboardButton("⬅️ Back", callback_data=f"bot_settings_{bot_username}"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        # --- NAYA CODE KHATAM ---
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard)) 
    async def show_current_welcome(self, message, bot_username):
        settings = await self.get_bot_settings(bot_username)
        welcome = settings.get('welcome_message', '')
        text = f"Current Welcome Message: {welcome}" if welcome else "No custom welcome message set. Using default."
        keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data=f"setting_welcome_{bot_username}"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    async def show_custombutton_settings(self, message, bot_username):
        text = f"Manage Custom Button for @{bot_username}."
        keyboard = [
        [InlineKeyboardButton("✏️ Set Custom Button", callback_data=f"custombutton_set_{bot_username}")],
        [InlineKeyboardButton("👀 See Custom Button", callback_data=f"custombutton_see_{bot_username}")],
        [InlineKeyboardButton("➖ Delete Custom Button", callback_data=f"custombutton_delete_{bot_username}")],
        [InlineKeyboardButton("⬅️ Back", callback_data=f"bot_settings_{bot_username}"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    async def show_current_custombutton(self, message, bot_username):
        settings = await self.get_bot_settings(bot_username)
        name = settings.get('custom_button_name', '')
        url = settings.get('custom_button_url', '')
        text = f"Current Custom Button: {name} -> {url}" if name and url else "No Custom Button set."
        keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data=f"setting_custombutton_{bot_username}"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    async def delete_custombutton(self, message, bot_username):
        settings_table = DBManager._get_safe_tablename(bot_username, 'settings')
        name_query = f"INSERT INTO {settings_table} (key, value) VALUES ('custom_button_name', $1) ON CONFLICT (key) DO UPDATE SET value = $1"
        url_query = f"INSERT INTO {settings_table} (key, value) VALUES ('custom_button_url', $1) ON CONFLICT (key) DO UPDATE SET value = $1"
        
        await DBManager.execute_pg_query(name_query, (json.dumps(''),))
        await DBManager.execute_pg_query(url_query, (json.dumps(''),))

        if await CACHE_BOT_SETTINGS.contains(bot_username):
            await CACHE_BOT_SETTINGS.delete(bot_username)
        text = f"Custom Button deleted for @{bot_username}."
        keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data=f"setting_custombutton_{bot_username}"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    async def show_premium_settings(self, message, bot_username):
        text = f"Manage Premium Members for @{bot_username}."
        keyboard = [
        [InlineKeyboardButton("➕ Add Premium Member", callback_data=f"premium_add_{bot_username}")],
        [InlineKeyboardButton("➖ Delete Premium Member", callback_data=f"premium_delete_{bot_username}")],
        [InlineKeyboardButton("📊 Total Premium Members", callback_data=f"premium_total_{bot_username}")],
        [InlineKeyboardButton("📢 Super Broadcast", callback_data=f"super_broadcast_menu_{bot_username}")],
        [InlineKeyboardButton("⬅️ Back", callback_data=f"bot_settings_{bot_username}"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    async def show_premium_delete_list(self, message, bot_username):
        premium_table = DBManager._get_safe_tablename(bot_username, 'premium')
        premium_users_records = await DBManager.execute_pg_query(f"SELECT user_id FROM {premium_table}", fetch='all')

        if not premium_users_records:
            text = "No premium members to delete."
            keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data=f"setting_premium_{bot_username}"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
        else:
            text = "Select premium member to delete."
            keyboard = [[InlineKeyboardButton(f"User {rec['user_id']}", callback_data=f"premium_delete_confirm_{bot_username}_{rec['user_id']}")] for rec in premium_users_records]
            keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data=f"setting_premium_{bot_username}"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")])
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    async def show_premium_total(self, message, bot_username):
        premium_table = DBManager._get_safe_tablename(bot_username, 'premium')
        count_result = await DBManager.execute_pg_query(f"SELECT COUNT(user_id) as total FROM {premium_table}", fetch='one')
        
        total_users = count_result['total'] if count_result else 0
        if total_users == 0:
            text = "Aapke bot mein koi premium member nahi hai."
        else:
            text = f"Aapke bot mein kul {total_users} premium members hain."
        keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data=f"setting_premium_{bot_username}"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    async def confirm_delete_premium(self, message, bot_username, user_id):
        text = f"Are you sure you want to delete premium membership for user {user_id}?"
        keyboard = [
        [InlineKeyboardButton("✅ Yes", callback_data=f"premium_delete_yes_{bot_username}_{user_id}"), InlineKeyboardButton("⬅️ Back", callback_data=f"premium_delete_{bot_username}")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    async def perform_delete_premium(self, message, bot_username, user_id):
        premium_table = DBManager._get_safe_tablename(bot_username, 'premium')
        query = f"DELETE FROM {premium_table} WHERE user_id=$1"
        await DBManager.execute_pg_query(query, (user_id,))
        text = f"Premium membership deleted for user {user_id}."
        keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data=f"setting_premium_{bot_username}"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    async def show_super_broadcast_menu(self, message, bot_username):
        """Super Broadcast feature ka admin menu dikhata hai."""
        settings = await self.get_bot_settings(bot_username)
        is_enabled = settings.get('super_broadcast_enabled', False)
        sb_msg_id = settings.get('super_broadcast_msg_id')
        
        status_str = "✅ Enabled" if is_enabled else "❌ Disabled"
        msg_status = "✅ Message Set Hai" if sb_msg_id else "❌ Message Set Nahi Hai"

        text = (
            f"📢 <b>Super Broadcast Manager for @{bot_username}</b>\n\n"
            f"<b>Feature Status:</b> {status_str}\n"
            f"<b>Message Status:</b> {msg_status}\n\n"
            f"<i>Yeh message ek ad ki tarah kaam karega jo sirf Premium users ko har file receive hone ke baad aakhri me send kiya jayega.</i>"
        )

        toggle_btn = (
            InlineKeyboardButton("❌ Disable Feature", callback_data=f"super_broadcast_toggle_off_{bot_username}")
            if is_enabled else
            InlineKeyboardButton("✅ Enable Feature", callback_data=f"super_broadcast_toggle_on_{bot_username}")
        )

        keyboard = [
            [InlineKeyboardButton("✏️ Set / Update Message", callback_data=f"super_broadcast_set_{bot_username}")],
            [toggle_btn],
            [InlineKeyboardButton("🗑️ Delete Feature / Message", callback_data=f"super_broadcast_delete_{bot_username}")],
            [InlineKeyboardButton("⬅️ Back", callback_data=f"setting_premium_{bot_username}")]
        ]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

    async def handle_conv_set_super_broadcast(self, state):
        """Admin dwara send kiye gaye Super Broadcast message ko save karta hai."""
        key = f"{self.bot_username}_{self.user_id}"
        await CACHE_CONVERSATION.delete(key)
        
        bot_username = state.get('bot_username', self.bot_username)
        msg_id = self.update.message.message_id
        chat_id = self.chat_id
        
        settings_table = DBManager._get_safe_tablename(bot_username, 'settings')
        
        # Save msg_id, chat_id, aur feature ko enable karo
        await DBManager.execute_pg_query(
            f"INSERT INTO {settings_table} (key, value) VALUES ('super_broadcast_msg_id', $1) ON CONFLICT (key) DO UPDATE SET value = $1",
            (json.dumps(msg_id),)
        )
        await DBManager.execute_pg_query(
            f"INSERT INTO {settings_table} (key, value) VALUES ('super_broadcast_chat_id', $1) ON CONFLICT (key) DO UPDATE SET value = $1",
            (json.dumps(chat_id),)
        )
        await DBManager.execute_pg_query(
            f"INSERT INTO {settings_table} (key, value) VALUES ('super_broadcast_enabled', $1) ON CONFLICT (key) DO UPDATE SET value = $1",
            (json.dumps(True),)
        )
        
        # RAM Cache refresh karo
        if await CACHE_BOT_SETTINGS.contains(bot_username):
            await CACHE_BOT_SETTINGS.delete(bot_username)
            
        await self.bot.send_message(
            self.chat_id, 
            f"✅ **Super Broadcast message successfully set and enabled for @{bot_username}!**\n\nAb premium users ko koi bhi file milne ke baad yeh message automatic bhej diya jayega.", 
            parse_mode=ParseMode.MARKDOWN
        )

    async def delete_super_broadcast(self, message, bot_username):
        """Super Broadcast message ko reset aur delete karta hai."""
        settings_table = DBManager._get_safe_tablename(bot_username, 'settings')
        
        await DBManager.execute_pg_query(
            f"INSERT INTO {settings_table} (key, value) VALUES ('super_broadcast_msg_id', $1) ON CONFLICT (key) DO UPDATE SET value = $1",
            (json.dumps(None),)
        )
        await DBManager.execute_pg_query(
            f"INSERT INTO {settings_table} (key, value) VALUES ('super_broadcast_chat_id', $1) ON CONFLICT (key) DO UPDATE SET value = $1",
            (json.dumps(None),)
        )
        await DBManager.execute_pg_query(
            f"INSERT INTO {settings_table} (key, value) VALUES ('super_broadcast_enabled', $1) ON CONFLICT (key) DO UPDATE SET value = $1",
            (json.dumps(False),)
        )
        
        if await CACHE_BOT_SETTINGS.contains(bot_username):
            await CACHE_BOT_SETTINGS.delete(bot_username)
            
        await message.edit_text(
            f"🗑️ Super Broadcast message delete aur feature disable kar diya gaya hai for @{bot_username}.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=f"super_broadcast_menu_{bot_username}")]])
        )

    async def maybe_send_super_broadcast(self):
        """Check karta hai agar user Premium ya Admin hai toh 21-char file delivery ke baad super broadcast send karta hai."""
        settings = await self.get_bot_settings()
        if not settings.get('super_broadcast_enabled', False):
            return
            
        sb_msg_id = settings.get('super_broadcast_msg_id')
        sb_chat_id = settings.get('super_broadcast_chat_id')
        if not sb_msg_id or not sb_chat_id:
            return

        # 1. Admin/Owner check
        is_premium = await self.is_user_admin()

        # 2. Premium table check (Optimized with Cache)
        if not is_premium:
            now = datetime.utcnow().replace(tzinfo=None)
            cache_key = f"{self.bot_username}_{self.user_id}_is_prem"
            
            cached_status = await CACHE_USER_MEMBERSHIP.get(cache_key)
            if cached_status is not None:
                is_premium = cached_status
            else:
                premium_table = DBManager._get_safe_tablename(self.bot_username, 'premium')
                premium_data = await DBManager.execute_pg_query(
                    f"SELECT expiry_time FROM {premium_table} WHERE user_id=$1", 
                    (self.user_id,), 
                    fetch='one'
                )
                if premium_data and premium_data['expiry_time'].replace(tzinfo=None) > now:
                    is_premium = True
                    await CACHE_USER_MEMBERSHIP.set(cache_key, True)
                else:
                    await CACHE_USER_MEMBERSHIP.set(cache_key, False)

        # Agar user Premium/Admin hai toh 21-char link par broadcast deliver karo
        # Agar user Premium/Admin hai toh 21-char link par broadcast deliver karo
        if is_premium:
            try:
                sb_sent = await self.bot.copy_message(
                    chat_id=self.chat_id,
                    from_chat_id=sb_chat_id,
                    message_id=sb_msg_id
                )
                if sb_sent and settings.get('deletion', False):
                    deletion_time = settings.get('deletion_time', 7200)
                    asyncio.create_task(self.schedule_deletion(sb_sent.message_id, deletion_time))
            except Exception as e:
                logger.error(f"Super broadcast deliver karne me error: {e}")    
    
    async def set_premium_membership(self, message, bot_username, user_id, days):
        premium_table = DBManager._get_safe_tablename(bot_username, 'premium')
        query = f"""
        INSERT INTO {premium_table} (user_id, expiry_time) VALUES ($1, NOW() + INTERVAL '{days} days')
        ON CONFLICT (user_id) DO UPDATE SET expiry_time = NOW() + INTERVAL '{days} days';
        """
        await DBManager.execute_pg_query(query, (user_id,))
        
        duration_str = {7: "1 Week", 30: "1 Month", 90: "3 Months"}.get(days, f"{days} days")
        text = f"Premium membership set for user {user_id} for {duration_str}."
        
        # Auto sync feature call yahan hoga
        await self.auto_add_premium_to_synced_bots(bot_username, user_id, days)

        # --- NAYA: 7 DINO KE LIYE MANUAL PREMIUM CACHE ME SAVE KAREIN ---
        try:
            import time
            cache_audit_key = f"{bot_username}_{user_id}_{int(time.time())}"
            manual_audit_data = {
                "bot_username": bot_username,
                "user_id": user_id,
                "days": days,
                "admin_id": self.user_id,
                "timestamp": int(time.time())
            }
            await CACHE_MANUAL_PREMIUM.set(cache_audit_key, manual_audit_data)
        except Exception as cache_err:
            logger.error(f"Failed to cache manual premium log: {cache_err}")
        # -------------------------------------------------------------

        keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data=f"setting_premium_{bot_username}"), InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        try:
            clone_bot = await get_bot_instance(bot_username)
            if clone_bot:
                await clone_bot.send_message(user_id, f"Aapko @{bot_username} ke liye {duration_str} ki Premium sadasyata mil gayi hai.")
            else:
                logger.error(f"Could not get instance for @{bot_username} to send premium notification.")
        except Exception as e:
            logger.error(f"Failed to send premium notification from @{bot_username} to {user_id}: {e}")    
    
    async def edit_to_main_menu(self, message):
        user_name = self.update.effective_user.first_name
        text = (
            f"🦋 𝖂𝖊𝖑𝖈𝖔𝖒𝖊 {user_name} 🦋\n\n"
            "𝖨’𝗆 𝖺 𝖿𝗂𝗅𝖾 𝗌𝗁𝖺𝗋𝗂𝗇𝗀 𝖻𝗈𝗍. 𝖸𝗈𝗎 𝖼𝖺𝗇 𝖼𝗋𝖾𝖺𝗍𝖾 𝗆𝗒 𝖼𝗅𝗈𝗇𝖾 𝗎𝗌𝗂𝗇𝗀 𝗍𝗁𝖾 /𝖼𝗅𝗈𝗇𝖾 𝖼𝗈𝗆𝗆𝖺𝗇𝖽.\n\n"
            "𝖨𝗇 𝗒𝗈𝗎𝗋 𝖼𝗅𝗈𝗇𝖾𝖽 𝖻𝗈𝗍, 𝗒𝗈𝗎 𝖼𝖺𝗇 𝗌𝗁𝖺𝗋𝖾 𝖺𝗇𝗒 𝖿𝗂𝗅𝖾 𝗐𝗂𝗍𝗁 𝗆𝖾 𝗂𝗇 𝖣𝖬, 𝖺𝗇𝖽 𝖨’𝗅𝗅 𝗉𝗋𝗈𝗏𝗂𝖽𝖾 𝗒𝗈𝗎 𝗐𝗂𝗍𝗁 𝖺 𝗌𝗁𝖺𝗋𝖾𝖺𝖻𝗅𝖾 𝗅𝗂𝗇𝗄. "
            "𝖶𝗁𝖾𝗇𝖾𝗏𝖾𝗋 𝗌𝗈𝗆𝖾𝗈𝗇𝖾 𝖼𝗅𝗂𝖼𝗄𝗌 𝗈𝗇 𝗍𝗁𝖺𝗍 𝗅𝗂𝗇𝗄, 𝖨 𝗐𝗂𝗅𝗅 𝗂𝗇𝗌𝗍𝖺𝗇𝗍𝗅𝗒 𝗌𝖾𝗇𝖽 𝗍𝗁𝖾 𝖺𝗌𝗌𝗈𝖼𝗂𝖺𝗍𝖾𝖽 𝖿𝗂𝗅𝖾."
        )
        keyboard = [
        [InlineKeyboardButton("ℹ️ About Me", callback_data="about_me"), InlineKeyboardButton("❓ Help", callback_data="help")],
        [InlineKeyboardButton("➕ Make a Clone", callback_data="make_clone")],
        [InlineKeyboardButton("📂 My Bots", callback_data="my_bots")]
        ]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    async def show_about_me(self, message):
        text = (
            "✨ 𝓐𝓫𝓸𝓾𝓽 𝓜𝓮 ✨\n\n"
            "𝗢𝘄𝗻𝗲𝗿: @echelonbotcommunity\n"
            "𝗨𝗽𝗱𝗮𝘁𝗲 𝗖𝗵𝗮𝗻𝗻𝗲𝗹: @echelon_notification\n"
            "𝗩𝗲𝗿𝘀𝗶𝗼𝗻: v4.5.8 (Stable and Free)"
        )
        keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="main_menu")]]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    async def show_help(self, message):
        text = (
            "✨ 𝙃𝙤𝙬 𝙏𝙤 𝙐𝙨𝙚 𝙈𝙚 ✨\n\n"
            "𝘏𝘦𝘭𝘭𝘰! 𝘐'𝘮 𝘺𝘰𝘶𝘳 𝘧𝘳𝘪𝘦𝘯𝘥𝘭𝘺 𝘧𝘪𝘭𝘦 𝘴𝘩𝘢𝘳𝘪𝘯𝘨 𝘢𝘴𝘴𝘪𝘴𝘵𝘢𝘯𝘵. 𝘛𝘩𝘪𝘴 𝘨𝘶𝘪𝘥𝘦 𝘤𝘰𝘷𝘦𝘳𝘴 𝘦𝘷𝘦𝘳𝘺𝘵𝘩𝘪𝘯𝘨 𝘺𝘰𝘶 𝘯𝘦𝘦𝘥 𝘵𝘰 𝘬𝘯𝘰𝘸! 💖\n\n"
            "•*¨*•.¸¸☆*･ﾟﾟ･*☆¸¸.•*¨*•\n\n"
            "┌─── ･ ｡ﾟ☆: *.☽ .* :☆ﾟ. ───┐\n"
            "      🤖  𝗠𝗮𝗶𝗻 𝗕𝗼𝘁 𝗚𝘂𝗶𝗱𝗲\n"
            "└─── ･ ｡ﾟ☆: *.☽ .* :☆ﾟ. ───┘\n"
            "» /start - 𝘛𝘰 𝘴𝘦𝘦 𝘵𝘩𝘦 𝘮𝘢𝘪𝘯 𝘮𝘦𝘯𝘶.\n"
            "» /clone - 𝘛𝘰 𝘤𝘳𝘦𝘢𝘵𝘦 𝘺𝘰𝘶𝘳 𝘷𝘦𝘳𝘺 𝘰𝘸𝘯 𝘤𝘰𝘱𝘺 𝘰𝘧 𝘮𝘦!\n"
            "» 📂 My Bots Button - 𝘛𝘩𝘪𝘴 𝘪𝘴 𝘺𝘰𝘶𝘳 𝘊𝘰𝘯𝘵𝘳𝘰𝘭 𝘗𝘢𝘯𝘦𝘭! 𝘜𝘴𝘦 𝘪𝘵 𝘵𝘰 𝘮𝘢𝘯𝘢𝘨𝘦, 𝘤𝘰𝘯𝘧𝘪𝘨𝘶𝘳𝘦, 𝘢𝘯𝘥 𝘥𝘦𝘭𝘦𝘵𝘦 𝘺𝘰𝘶𝘳 𝘤𝘭𝘰𝘯𝘦𝘥 𝘣𝘰𝘵𝘴.\n\n"
            "•*¨*•.¸¸☆*･ﾟﾟ･*☆¸¸.•*¨*•\n\n"
            "┌─── ･ ｡ﾟ☆: *.☽ .* :☆ﾟ. ───┐\n"
            "  🪄 𝗬𝗼𝘂𝗿 𝗖𝗹𝗼𝗻𝗲𝗱 𝗕𝗼𝘁'𝘀 𝗠𝗮𝗴𝗶𝗰\n"
            "└─── ･ ｡ﾟ☆: *.☽ .* :☆ﾟ. ───┘\n\n"
            "  ╭── ⋅ ⋅ ── ✩ ── ⋅ ⋅ ──╮\n"
            "      🔗 𝙂𝙚𝙣𝙚𝙧𝙖𝙩𝙞𝙣𝙜 𝙇𝙞𝙣𝙠𝙨 🔗\n"
            "  ╰── ⋅ ⋅ ── ✩ ── ⋅ ⋅ ──╯\n"
            "  » 𝗦𝗶𝗻𝗴𝗹𝗲 𝗙𝗶𝗹𝗲: 𝘑𝘶𝘴𝘵 𝘴𝘦𝘯𝘥 𝘢𝘯𝘺 𝘧𝘪𝘭𝘦 (photo, video, document) 𝘥𝘪𝘳𝘦𝘤𝘵𝘭𝘺 𝘵𝘰 𝘺𝘰𝘶𝘳 𝘣𝘰𝘵, 𝘢𝘯𝘥 𝘐'𝘭𝘭 𝘨𝘪𝘷𝘦 𝘺𝘰𝘶 𝘢 𝘴𝘱𝘦𝘤𝘪𝘢𝘭 𝘭𝘪𝘯𝘬! 📄\n"
            "  » 𝗔𝗹𝗯𝘂𝗺/𝗠𝗲𝗱𝗶𝗮 𝗚𝗿𝗼𝘂𝗽: 𝘚𝘦𝘯𝘥 𝘮𝘶𝘭𝘵𝘪𝘱𝘭𝘦 𝘱𝘩𝘰𝘵𝘰𝘴 𝘰𝘳 𝘷𝘪𝘥𝘦𝘰𝘴 𝘵𝘰𝘨𝘦𝘵𝘩𝘦𝘳 𝘢𝘴 𝘢𝘯 𝘢𝘭𝘣𝘶𝘮, 𝘢𝘯𝘥 𝘐'𝘭𝘭 𝘤𝘳𝘦𝘢𝘵𝘦 𝘰𝘯𝘦 𝘭𝘪𝘯𝘬 𝘧𝘰𝘳 𝘵𝘩𝘦 𝘦𝘯𝘵𝘪𝘳𝘦 𝘤𝘰𝘭𝘭𝘦𝘤𝘵𝘪𝘰𝘯! 🖼️\n\n"
            "  ╭── ⋅ ⋅ ── ✩ ── ⋅ ⋅ ──╮\n"
            "    👑 𝘼𝙙𝙢𝙞𝙣 𝘾𝙤𝙢𝙢𝙖𝙣𝙙𝙨 👑\n"
            "  ╰── ⋅ ⋅ ── ✩ ── ⋅ ⋅ ──╯\n"
            "  » /batch_link: 𝘜𝘴𝘦 𝘵𝘩𝘪𝘴 𝘵𝘰 𝘣𝘶𝘯𝘥𝘭𝘦 𝘮𝘢𝘯𝘺 𝘴𝘦𝘱𝘢𝘳𝘢𝘵𝘦 𝘧𝘪𝘭𝘦𝘴. 𝘐'𝘭𝘭 𝘸𝘢𝘪𝘵 𝘧𝘰𝘳 2 𝘮𝘪𝘯𝘶𝘵𝘦𝘴 𝘧𝘰𝘳 𝘺𝘰𝘶 𝘵𝘰 𝘴𝘦𝘯𝘥 𝘢𝘭𝘭 𝘺𝘰UR 𝘧𝘪𝘭𝘦𝘴, 𝘵𝘩𝘦𝘯 𝘐'𝘭𝘭 𝘨𝘪𝘷𝘦 𝘺𝘰𝘶 𝘰𝘯𝘦 𝘮𝘢𝘴𝘵𝘦𝘳 𝘭𝘪𝘯𝘬! ⏱️\n"
            "  » /broadcast: 𝘚𝘦𝘯𝘥 𝘢 𝘮𝘦𝘴𝘴𝘢𝘨𝘦 𝘵𝘰 ALL 𝘶𝘴𝘦𝘳𝘴 𝘰𝘧 𝘺𝘰𝘶𝘳 𝘣𝘰𝘵.\n"
            "  » /premium_broadcast: 𝘚𝘦𝘯𝘥 𝘢 𝘴𝘱𝘦𝘤𝘪𝘢𝘭 𝘮𝘦𝘴𝘴𝘢𝘨𝘦 𝘰𝘯𝘭𝘺 𝘵𝘰 𝘺𝘰𝘶𝘳 𝘱𝘳𝘦𝘮𝘪𝘶𝘮 𝘮𝘦𝘮𝘣𝘦𝘳𝘴. ✨\n"
            "  » /short_link: 𝘐𝘧 𝘺𝘰𝘶 𝘩𝘢𝘷𝘦 𝘢𝘯 𝘈𝘥 𝘈𝘗𝘐 𝘴𝘦𝘵 𝘶𝘱, 𝘶𝘴𝘦 𝘵𝘩𝘪𝘴 𝘵𝘰 𝘴𝘩𝘰𝘳𝘵𝘦𝘯 𝘢𝘯𝘺 𝘜𝘙𝘓.\n\n"
            "•*¨*•.¸¸☆*･ﾟﾟ･*☆¸¸.•*¨*•\n\n"
            "┌─── ･ ｡ﾟ☆: *.☽ .* :☆ﾟ. ───┐\n"
            "  ⚙️ 𝗦𝘂𝗽𝗲𝗿𝗰𝗵𝗮𝗿𝗴𝗲 𝗬𝗼𝘂𝗿 𝗖𝗹𝗼𝗻𝗲 (Settings)\n"
            "└─── ･ ｡ﾟ☆: *.☽ .* :☆ﾟ. ───┘\n"
            "𝘎𝘰 𝘵𝘰 𝘵𝘩𝘦 𝗠𝗮𝗶𝗻 𝗕𝗼𝘁 → \"📂 𝘔𝘺 𝘉𝘰𝘵𝘴\" → \"⚙️ 𝘉𝘰𝘵 𝘚𝘦𝘵𝘵𝘪𝘯𝘨𝘴\" 𝘵𝘰 𝘤𝘶𝘴𝘵𝘰𝘮𝘪𝘻𝘦 𝘦𝘷𝘦𝘳𝘺𝘵𝘩𝘪𝘯𝘨:\n"
            "  » 📢 𝗙𝗦𝗨𝗕: 𝘍𝘰𝘳𝘤𝘦 𝘶𝘴𝘦𝘳𝘴 𝘵𝘰 𝘫𝘰𝘪𝘯 𝘤𝘩𝘢𝘯𝘯𝘦𝘭𝘴.\n"
            "  » 👥 𝗔𝗱𝗺𝗶𝗻𝘀: 𝘈𝘥𝘥 𝘩𝘦𝘭𝘱𝘦𝘳𝘴 𝘵𝘰 𝘮𝘢𝘯𝘢𝘨𝘦 𝘺𝘰𝘶𝘳 𝘣𝘰𝘵.\n"
            "  » 👑 𝗣𝗿𝗲𝗺𝗶𝘂𝗺 𝗠𝗲𝗺𝗯𝗲𝗿𝘀: 𝘎𝘳𝘢𝘯𝘵 𝘢𝘥-𝘧𝘳𝘦𝘦 𝘢𝘤𝘤𝘦𝘴𝘴.\n"
            "  » 🔒 𝗣𝗿𝗼𝘁𝗲𝗰𝘁𝗶𝗼𝗻: 𝘚𝘵𝘰𝘱 𝘧𝘰𝘳𝘸𝘢𝘳𝘥𝘪𝘯𝘨/𝘴𝘢𝘷𝘪𝘯𝘨 𝘧𝘪𝘭𝘦𝘴.\n"
            "  » 🗑️ 𝗙𝗶𝗹𝗲 𝗗𝗲𝗹𝗲𝘁𝗶𝗼𝗻: 𝘈𝘶𝘵𝘰-𝘥𝘦𝘭𝘦𝘵𝘦 𝘧𝘪𝘭𝘦𝘴 𝘢𝘧𝘵𝘦𝘳 𝘢 𝘴𝘦𝘵 𝘵𝘪𝘮𝘦.\n"
            "  » 🔗 𝗔𝗱 𝗟𝗶𝗻𝗸/𝗔𝗣𝗜: 𝘔𝘰𝘯𝘦𝘵𝘪𝘻𝘦 𝘸𝘪𝘵𝘩 𝘢 𝘴𝘩𝘰𝘳𝘵𝘦𝘯𝘦𝘳.\n"
            "  » 📚 𝗔𝗱 𝗧𝘂𝘁𝗼𝗿𝗶𝗮𝗹: 𝘚𝘦𝘵 𝘢 𝘩𝘦𝘭𝘱 𝘭𝘪𝘯𝘬 𝘧𝘰𝘳 𝘺𝘰𝘶𝘳 𝘢𝘥𝘴.\n"
            "  » 📩 𝗪𝗲𝗹𝗰𝗼𝗺𝗲: 𝘊𝘳𝘦𝘢𝘵𝘦 𝘢 𝘤𝘶𝘴𝘵𝘰𝘮 𝘸𝘦𝘭𝘤𝘰𝘮𝘦 𝘮𝘦𝘴𝘴𝘢𝘨𝘦.\n"
            "  » 🔘 𝗕𝘂𝘁𝘁𝗼𝗻: 𝘈𝘥𝘥 𝘢 𝘜𝘙𝘓 𝘣𝘶𝘵𝘵𝘰𝘯 𝘵𝘰 𝘺𝘰𝘶𝘳 𝘸𝘦𝘭𝘤𝘰𝘮𝘦.\n"
            "  » 📝 𝗙𝗼𝗼𝘁𝗲𝗿: 𝘈𝘥𝘥 𝘢 𝘤𝘶𝘴𝘵𝘰𝘮 𝘤𝘢𝘱𝘵𝘪𝘰𝘯 𝘵𝘰 𝘢𝘭𝘭 𝘧𝘪𝘭𝘦𝘴.\n\n"
            "•*¨*•.¸¸☆*･ﾟﾟ･*☆¸¸.•*¨*•\n\n"
            "┌─── ･ ｡ﾟ☆: *.☽ .* :☆ﾟ. ───┐\n"
            "  🧠 𝗦𝗺𝗮𝗿𝘁 𝗙𝗲𝗮𝘁𝘂𝗿𝗲𝘀 (Automatic Helpers)\n"
            "└─── ･ ｡ﾟ☆: *.☽ .* :☆ﾟ. ───┘\n"
            "𝘐'𝘮 𝘴𝘮𝘢𝘳𝘵! 𝘐 𝘩𝘢𝘯𝘥𝘭𝘦 𝘱𝘳𝘰𝘣𝘭𝘦𝘮𝘴 𝘢𝘶𝘵𝘰𝘮𝘢𝘵𝘪𝘤𝘢𝘭𝘭𝘺 𝘴𝘰 𝘺𝘰𝘶 𝘥𝘰𝘯'𝘵 𝘩𝘢𝘷𝘦 𝘵𝘰 𝘸𝘰𝘳𝘳𝘺. 🤓\n"
            "  » 𝗔𝘂𝘁𝗼 𝗙𝗦𝗨𝗕 𝗙𝗶𝘅: 𝘐𝘧 𝘺𝘰𝘶𝘳 𝘣𝘰𝘵 𝘪𝘴 𝘳𝘦𝘮𝘰𝘷𝘦𝘥 𝘧𝘳𝘰𝘮 𝘢𝘯 𝘍𝘚𝘜𝘉 𝘤𝘩𝘢𝘯𝘯𝘦𝘭, 𝘐'𝘭𝘭 𝘢𝘶𝘵𝘰𝘮𝘢𝘵𝘪𝘤𝘢𝘭𝘭𝘺 𝘳𝘦𝘮𝘰𝘷𝘦 𝘵𝘩𝘢𝘵 𝘤𝘩𝘢𝘯𝘯𝘦𝘭 𝘧𝘳𝘰𝘮 𝘺𝘰𝘶𝘳 𝘴𝘦𝘵𝘵𝘪𝘯𝘨𝘴 & 𝘯𝘰𝘵𝘪𝘧𝘺 𝘺𝘰𝘶. 𝘛𝘩𝘪𝘴 𝘱𝘳𝘦𝘷𝘦𝘯𝘵𝘴 𝘶𝘴𝘦𝘳𝘴 𝘧𝘳𝘰𝘮 𝘨𝘦𝘵𝘵𝘪𝘯𝘨 𝘴𝘵𝘶𝘤𝘬!\n"
            "  » 𝗔𝘂𝘁𝗼 𝗔𝗱-𝗟𝗶𝗻𝗸 𝗙𝗶𝘅: 𝘐𝘧 𝘺𝘰𝘶𝘳 𝘢𝘥 𝘴𝘩𝘰𝘳𝘵𝘦𝘯𝘦𝘳 𝘈𝘗𝘐 𝘴𝘵𝘰𝘱𝘴 𝘸𝘰𝘳𝘬𝘪𝘯𝘨, 𝘐'𝘭𝘭 𝘥𝘦𝘵𝘦𝘤𝘵 𝘵𝘩𝘦 𝘦𝘳𝘳𝘰𝘳𝘴, 𝘢𝘶𝘵𝘰𝘮𝘢𝘵𝘪𝘤𝘢𝘭𝘭𝘺 𝘳𝘦𝘮𝘰𝘷𝘦 𝘵𝘩𝘦 𝘧𝘢𝘶𝘭𝘵𝘺 𝘭𝘪𝘯𝘬, 𝘢𝘯𝘥 𝘭𝘦𝘵 𝘺𝘰𝘶 𝘬𝘯𝘰𝘸.\n"
            "  » 𝗔𝘂𝘁𝗼 𝗣𝗿𝗲𝗺𝗶𝘂𝗺 𝗘𝘅𝗽𝗶𝗿𝘆: 𝘞𝘩𝘦𝘯 𝘢 𝘱𝘳𝘦𝘮𝘪𝘶𝘮 𝘶𝘴𝘦𝘳'𝘴 𝘴𝘶𝘣𝘴𝘤𝘳𝘪𝘱𝘵𝘪𝘰𝘯 𝘦𝘯𝘥𝘴, 𝘐 𝘢𝘶𝘵𝘰𝘮𝘢𝘵𝘪𝘤𝘢𝘭𝘭𝘺 𝘮𝘢𝘯𝘢𝘨𝘦 𝘪𝘵 𝘢𝘯𝘥 𝘯𝘰𝘵𝘪𝘧𝘺 𝘵𝘩𝘦𝘮. 𝘕𝘰 𝘮𝘢𝘯𝘶𝘢𝘭 𝘵𝘳𝘢𝘤𝘬𝘪𝘯𝘨 𝘯𝘦𝘦𝘥𝘦𝘥!\n"
            "  » 𝗔𝘂𝘁𝗼 𝗧𝗼𝗸𝗲𝗻 𝗣𝗿𝗼𝘁𝗲𝗰𝘁𝗶𝗼𝗻: 𝘐𝘧 𝘺𝘰𝘶 𝘢𝘤𝘤𝘪𝘥𝘦𝘯𝘵𝘢𝘭𝘭𝘺 𝘤𝘩𝘢𝘯𝘨𝘦 𝘺𝘰𝘶𝘳 𝘣𝘰𝘵'𝘴 𝘵𝘰𝘬𝘦𝘯, 𝘐 𝘸𝘪𝘭𝘭 𝘥𝘦𝘵𝘦𝘤𝘵 𝘪𝘵, 𝘱𝘢𝘶𝘴𝘦 𝘵𝘩𝘦 𝘣𝘰𝘵, 𝘢𝘯𝘥 𝘴𝘦𝘯𝘥 𝘺𝘰𝘶 𝘢 𝘮𝘦𝘴𝘴𝘢𝘨𝘦 𝘸𝘪𝘵𝘩 𝘢 𝘣𝘶𝘵𝘵𝘰𝘯 𝘵𝘰 𝘶𝘱𝘥𝘢𝘵𝘦 𝘪𝘵 𝘦𝘢𝘴𝘪𝘭𝘺.\n"
            "  » 𝗚𝗿𝗼𝘂𝗽 𝗣𝗿𝗼𝘁𝗲𝗰𝘁𝗼𝗿: 𝘐 𝘢𝘮 𝘥𝘦𝘴𝘪𝘨𝘯𝘦𝘥 𝘧𝘰𝘳 𝘱𝘳𝘪𝘷𝘢𝘵𝘦 𝘤𝘩𝘢𝘵𝘴. 𝘐𝘧 𝘴𝘰𝘮𝘦𝘰𝘯𝘦 𝘢𝘥𝘥𝘴 𝘮𝘦 𝘵𝘰 𝘢 𝘨𝘳𝘰𝘶𝘱, 𝘐 𝘸𝘪𝘭𝘭 𝘱𝘰𝘭𝘪𝘵𝘦𝘭𝘺 𝘦𝘹𝘱𝘭𝘢𝘪𝘯 𝘵𝘩𝘪𝘴 𝘢𝘯𝘥 𝘭𝘦𝘢𝘷𝘦 𝘢𝘶𝘵𝘰𝘮𝘢𝘵𝘪𝘤𝘢𝘭𝘭𝘺.\n\n"
            "•*¨*•.¸¸☆*･ﾟﾟ･*☆¸¸.•*¨*•\n\n"
            "┌─── ･ ｡ﾟ☆: *.☽ .* :☆ﾟ. ───┐\n"
            "    💎 𝗛𝗶𝗱𝗱𝗲𝗻 𝗚𝗲𝗺𝘀 & 𝗣𝗿𝗼 𝗧𝗶𝗽𝘀\n"
            "└─── ･ ｡ﾟ☆: *.☽ .* :☆ﾟ. ───┘\n"
            "𝘋𝘪𝘥 𝘺𝘰𝘶 𝘬𝘯𝘰𝘸 𝘺𝘰𝘶 𝘤𝘰𝘶𝘭𝘥 𝘥𝘰 𝘵𝘩𝘦𝘴𝘦 𝘤𝘰𝘰𝘭 𝘵𝘩𝘪𝘯𝘨𝘴? 😉\n"
            "  » 𝗟𝗶𝗻𝗸 𝗠𝗲𝗿𝗴𝗶𝗻𝗴: 𝘗𝘢𝘴𝘵𝘦 𝘮𝘶𝘭𝘵𝘪𝘱𝘭𝘦 𝘧𝘪𝘭𝘦 𝘭𝘪𝘯𝘬𝘴 (from your bot) 𝘪𝘯𝘵𝘰 𝘢 𝘴𝘪𝘯𝘨𝘭𝘦 𝘮𝘦𝘴𝘴𝘢𝘨𝘦 𝘢𝘯𝘥 𝘴𝘦𝘯𝘥 𝘪𝘵. 𝘐 𝘸𝘪𝘭𝘭 𝘮𝘢𝘨𝘪𝘤𝘢𝘭𝘭𝘺 𝘮𝘦𝘳𝘨𝘦 𝘵𝘩𝘦𝘮 𝘪𝘯𝘵𝘰 𝘢 𝘯𝘦𝘸, 𝘴𝘪𝘯𝘨𝘭𝘦 𝘭𝘪𝘯𝘬!\n"
            "  » 𝗙𝗦𝗨𝗕 𝗥𝗲𝗾𝘂𝗲𝘀𝘁 𝗠𝗼𝗱𝗲: 𝘞𝘩𝘦𝘯 𝘢𝘥𝘥𝘪𝘯𝘨 𝘢𝘯 𝘍𝘚𝘜𝘉 𝘤𝘩𝘢𝘯𝘯𝘦𝘭, 𝘺𝘰𝘶 𝘤𝘢𝘯 𝘤𝘩𝘰𝘰𝘴𝘦 \"𝘙𝘦𝘲𝘶𝘦𝘴𝘵 𝘔𝘰𝘥𝘦\". 𝘛𝘩𝘪𝘴 𝘳𝘦𝘲𝘶𝘪𝘳𝘦𝘴 𝘺𝘰𝘶 𝘵𝘰 𝘮𝘢𝘯𝘶𝘢𝘭𝘭𝘺 𝘢𝘱𝘱𝘳𝘰𝘷𝘦 𝘦𝘷𝘦𝘳𝘺 𝘶𝘴𝘦𝘳, 𝘨𝘪𝘷𝘪𝘯𝘨 𝘺𝘰𝘶 𝘧𝘶𝘭𝘭 𝘤𝘰𝘯𝘵𝘳𝘰𝘭.\n"
            "  » 𝗪𝗲𝗹𝗰𝗼𝗺𝗲 𝗡𝗮𝗺𝗲 𝗣𝗹𝗮𝗰𝗲𝗵𝗼𝗹𝗱𝗲𝗿: 𝘐𝘯 𝘺𝘰𝘶𝘳 𝘤𝘶𝘴𝘵𝘰𝘮 𝘸𝘦𝘭𝘤𝘰𝘮𝘦 𝘮𝘦𝘴𝘴𝘢𝘨𝘦, 𝘶𝘴𝘦 {User Name} 𝘵𝘰 𝘢𝘶𝘵𝘰𝘮𝘢𝘵𝘪𝘤𝘢𝘭𝘭𝘺 𝘨𝘳𝘦𝘦𝘵 𝘦𝘷𝘦𝘳𝘺 𝘯𝘦𝘸 𝘶𝘴𝘦𝘳 𝘸𝘪𝘵𝘩 𝘵𝘩𝘦𝘪𝘳 𝘧𝘪𝘳𝘴𝘵 𝘯𝘢𝘮𝘦! 👋 (For detaild help cheak @echelon_notification) \n\n"
            "•*¨*•.¸¸☆*･ﾟﾟ･*☆¸¸.•*¨*•\n\n"
            "👤 𝗙𝗼𝗿 𝗥𝗲𝗴𝘂𝗹𝗮𝗿 𝗨𝘀𝗲𝗿𝘀:\n"
            "𝘐𝘧 𝘺𝘰𝘶'𝘳𝘦 𝘩𝘦𝘳𝘦 𝘧𝘳𝘰𝘮 𝘢 𝘴𝘩𝘢𝘳𝘦 𝘭𝘪𝘯𝘬, 𝘸𝘦𝘭𝘤𝘰𝘮𝘦! ✨ 𝘑𝘶𝘴𝘵 𝘧𝘰𝘭𝘭𝘰𝘸 𝘵𝘩𝘦 𝘱𝘳𝘰𝘮𝘱𝘵𝘴 (𝘭𝘪𝘬𝘦 𝘫𝘰𝘪𝘯𝘪𝘯𝘨 𝘢 𝘤𝘩𝘢𝘯𝘯𝘦𝘭), 𝘢𝘯𝘥 𝘐'𝘭𝘭 𝘴𝘦𝘯𝘥 𝘺𝘰𝘶 𝘵𝘩𝘦 𝘧𝘪𝘭𝘦 𝘢𝘶𝘵𝘰𝘮𝘢𝘵𝘪𝘤𝘢𝘭𝘭𝘺. 𝘐𝘵'𝘴 𝘢𝘴 𝘦𝘢𝘴𝘺 𝘢𝘴 𝘵𝘩𝘢𝘵!"
        )
        keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="main_menu")]]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    async def handle_command(self):
        text = self.update.message.text
        command_parts = text.split()
        command = command_parts[0].lower()
        args = command_parts[1:]
        if self.bot_username == MAIN_BOT_USERNAME:
            try:
                await self.bot.delete_message(self.chat_id, self.update.message.message_id)
            except Exception:
                pass
            if command == "/start":
                await self.handle_main_bot_start()
            elif command == "/clone":
                await self.handle_clone_command()
            else:
                await self.bot.send_message(self.chat_id, "Unknown command. Use /start to see available options.")
            return
        is_admin = await self.is_user_admin()
        if command == "/start":
            await self.handle_clone_bot_start()
        elif command == "/clone":
            text = "Click here to clone your own bot."
            keyboard = [[InlineKeyboardButton("Clone Bot", url=f"https://t.me/{MAIN_BOT_USERNAME}")]]
            await self.bot.send_message(self.chat_id, text, reply_markup=InlineKeyboardMarkup(keyboard))
        elif command == "/broadcast" and is_admin:
            await self.initiate_conversation('broadcast', "Please send or forward the message you want to broadcast.")
        elif command == "/premium_broadcast" and is_admin:
            await self.initiate_conversation('premium_broadcast', "Please send or forward the message you want to broadcast to premium members.")
        elif command == "/batch_link" and is_admin:
            await self.handle_batch_link_command()
        elif command == "/short_link":
            await self.initiate_conversation('short_link', "Please send the link you want to shorten.")
        elif command == "/stats" and is_admin:
            await self.handle_stats_command()
        elif command == "/earnings" and is_admin:
            await self.handle_earnings_command()
        else:
            await self.bot.send_message(self.chat_id, "Unknown command.")
    async def handle_stats_command(self):
        """Gathers and displays statistics for the bot admin."""
        msg = await self.bot.send_message(self.chat_id, "📊 Gathering your bot's stats, please wait...")

        try:
            # Table names generate karein
            users_table = DBManager._get_safe_tablename(self.bot_username, 'users')
            premium_table = DBManager._get_safe_tablename(self.bot_username, 'premium')
            files_table = DBManager._get_safe_tablename(self.bot_username, 'files')
            multi_files_table = DBManager._get_safe_tablename(self.bot_username, 'multi_files')

            # Saari COUNT queries ek saath chalayein taaki time bache
            # NAYA OPTIMIZED CODE: Ek-ek karke query karein taaki pool pe spike na aaye
            res_users = await DBManager.execute_pg_query(f"SELECT COUNT(*) as count FROM {users_table}", fetch='one')
            res_prem = await DBManager.execute_pg_query(f"SELECT COUNT(*) as count FROM {premium_table}", fetch='one')
            res_files = await DBManager.execute_pg_query(f"SELECT COUNT(*) as count FROM {files_table}", fetch='one')
            res_multi = await DBManager.execute_pg_query(f"SELECT COUNT(*) as count FROM {multi_files_table}", fetch='one')
            settings = await self.get_bot_settings()
            
            # Results ko variables me daalein
            total_users = res_users['count'] if res_users else 0
            total_premium_users = res_prem['count'] if res_prem else 0
            total_single_links = res_files['count'] if res_files else 0
            total_multi_links = res_multi['count'] if res_multi else 0            
            total_links_generated = total_single_links + total_multi_links
            
            # Settings se data nikalein
            total_moderators = len(settings.get('admins', []))
            fsub_channels = settings.get('fsub_channels', [])
            total_fsub_channels = len(fsub_channels)
            
            # Pehle sirf username ko escape karein
            safe_bot_username = self._escape_markdown(self.bot_username)

            # Final message banana shuru karein
            stats_text = (
                f"📈 *Bot Statistics for @{safe_bot_username}* 📈\n\n"
                f"*👥 Total Users:* `{total_users}`\n"
                f"*👑 Total Premium Users:* `{total_premium_users}`\n"
                f"*🔗 Total Links Generated:* `{total_links_generated}`\n"
                f"*🛡️ Total Moderators:* `{total_moderators}`\n"
                f"*📢 Total FSUB Channels:* `{total_fsub_channels}`\n\n"
                f"\-\-\- *FSUB Channel Stats* \-\-\-\n"
            )

            # FSUB channels ki details nikalein
            if not fsub_channels:
                stats_text += "No FSUB channels have been set\.\n"
            else:
                clone_bot_for_fsub = await get_bot_instance(self.bot_username, force_initialize=True)
                for i, ch in enumerate(fsub_channels, 1):
                    channel_id = ch.get('id')
                    target = int(ch.get('target', 0))
                    current = int(ch.get('current', 0))
                    
                    channel_title = f"ID: {channel_id}" 
                    if clone_bot_for_fsub:
                        try:
                            chat_info = await clone_bot_for_fsub.get_chat(channel_id)
                            channel_title = chat_info.title
                        except Exception:
                            pass
                    
                    safe_channel_title = self._escape_markdown(channel_title)
                    percentage_str = ""
                    if target > 0:
                        percentage = (current / target) * 100
                        percentage_str = self._escape_markdown(f" ({percentage:.1f}% target achieved!)")
                    
                    target_str = "Unlimited" if target == 0 else str(target)

                    stats_text += (
                        # BADLAV: Hyphen ko escape kiya gaya hai
                        f"\n*Channel {i}:* `{safe_channel_title}`\n"
                        f"   \- *Target:* `{target_str}`\n"
                        f"   \- *Current Joins:* `{current}`{percentage_str}\n"
                    )

            # BADLAV: Separator line ke saare hyphens ko escape kiya gaya hai
            stats_text += "\n\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\-\n"
            stats_text += "Looking at your bot’s stats data, we feel proud that you are a user of our bot\! Thank you so much\! 🤍"

            await msg.edit_text(stats_text, parse_mode=ParseMode.MARKDOWN_V2)

        except Exception as e:
            logger.error(f"Error generating stats for @{self.bot_username}: {e}", exc_info=True)
            await msg.edit_text("Sorry, an error occurred while fetching the stats. The issue has been logged.")
    
    async def handle_earnings_command(self):
        """Gathers comprehensive earnings analytics and provides interactive filter dashboard."""
        msg = await self.bot.send_message(self.chat_id, "📊 Gathering earnings data, please wait...")
        await self.show_earnings_overview(msg, self.bot_username)

    async def show_earnings_overview(self, message, bot_username):
        safe_bot = DBManager._get_safe_tablename(bot_username, '')
        success_table = f"{safe_bot}successful_transactions"
        failed_table = f"{safe_bot}failed_transactions"
        
        await DBManager.setup_bot_payment_tables(bot_username)

        query = f"""
        SELECT 
            COALESCE(SUM(CASE WHEN currency = 'XTR' THEN amount * 1.2 ELSE amount END), 0) as total_rev,
            COALESCE(SUM(CASE WHEN currency = 'XTR' THEN amount ELSE 0 END), 0) as total_stars,
            COUNT(*) as total_orders,
            COALESCE(SUM(CASE WHEN completion_time >= NOW() - INTERVAL '30 days' THEN (CASE WHEN currency = 'XTR' THEN amount * 1.2 ELSE amount END) ELSE 0 END), 0) as rev_30d,
            COUNT(CASE WHEN completion_time >= NOW() - INTERVAL '30 days' THEN 1 END) as orders_30d,
            COALESCE(SUM(CASE WHEN completion_time >= NOW() - INTERVAL '7 days' THEN (CASE WHEN currency = 'XTR' THEN amount * 1.2 ELSE amount END) ELSE 0 END), 0) as rev_7d,
            COUNT(CASE WHEN completion_time >= NOW() - INTERVAL '7 days' THEN 1 END) as orders_7d,
            COALESCE(SUM(CASE WHEN completion_time >= CURRENT_DATE THEN (CASE WHEN currency = 'XTR' THEN amount * 1.2 ELSE amount END) ELSE 0 END), 0) as rev_today,
            COUNT(CASE WHEN completion_time >= CURRENT_DATE THEN 1 END) as orders_today,
            COALESCE(SUM(CASE WHEN target_payload != '' THEN (CASE WHEN currency = 'XTR' THEN amount * 1.2 ELSE amount END) ELSE 0 END), 0) as paid_msg_rev,
            COUNT(CASE WHEN target_payload != '' THEN 1 END) as paid_msg_orders,
            COALESCE(SUM(CASE WHEN target_payload = '' OR target_payload IS NULL THEN (CASE WHEN currency = 'XTR' THEN amount * 1.2 ELSE amount END) ELSE 0 END), 0) as sub_rev,
            COUNT(CASE WHEN target_payload = '' OR target_payload IS NULL THEN 1 END) as sub_orders
        FROM {success_table};
        """
        data = await DBManager.execute_pg_query(query, fetch='one')
        fail_res = await DBManager.execute_pg_query(f"SELECT COUNT(*) as count FROM {failed_table};", fetch='one')
        failed_count = fail_res['count'] if fail_res else 0

        tot_rev = float(data['total_rev'])
        tot_stars = int(data['total_stars'])
        tot_orders = int(data['total_orders'])
        rev_30d = float(data['rev_30d'])
        orders_30d = int(data['orders_30d'])
        rev_7d = float(data['rev_7d'])
        orders_7d = int(data['orders_7d'])
        rev_today = float(data['rev_today'])
        orders_today = int(data['orders_today'])
        
        paid_msg_rev = float(data['paid_msg_rev'])
        paid_msg_orders = int(data['paid_msg_orders'])
        sub_rev = float(data['sub_rev'])
        sub_orders = int(data['sub_orders'])

        total_attempts = tot_orders + failed_count
        paid_rate = (tot_orders / total_attempts * 100) if total_attempts > 0 else 0.0
        fail_rate = (failed_count / total_attempts * 100) if total_attempts > 0 else 0.0

        text = (
            f"💰 <b>Earnings & Revenue Analytics for @{bot_username}</b> 💰\n\n"
            f"💵 <b>Total Lifetime Earnings:</b> ₹{tot_rev:,.2f} ({tot_orders} orders)\n"
            f"⭐ <b>Total Stars Earned:</b> {tot_stars} ⭐\n"
            f"📅 <b>Last 30 Days Earnings:</b> ₹{rev_30d:,.2f} ({orders_30d} orders)\n"
            f"⚡ <b>Last 7 Days Earnings:</b> ₹{rev_7d:,.2f} ({orders_7d} orders)\n"
            f"☀️ <b>Today's Earnings:</b> ₹{rev_today:,.2f} ({orders_today} orders)\n\n"
            f"📦 <b>Revenue By Product:</b>\n"
            f"  • 👑 <b>Subscriptions:</b> ₹{sub_rev:,.2f} ({sub_orders} sales)\n"
            f"  • 📩 <b>Paid Messages:</b> ₹{paid_msg_rev:,.2f} ({paid_msg_orders} sales)\n\n"
            f"📊 <b>Order Conversion Rates:</b>\n"
            f"  • ✅ <b>Paid / Success:</b> {paid_rate:.1f}% ({tot_orders})\n"
            f"  • ❌ <b>Failed / Canceled:</b> {fail_rate:.1f}% ({failed_count})\n"
            f"  • 🔄 <b>Total Attempted:</b> {total_attempts}\n\n"
            f"<i>Neeche diye gaye filters se aap daily graphs aur custom date data dekh sakte hain:</i>"
        )
        keyboard = [
            [
                InlineKeyboardButton("📅 Last 7 Days Daily", callback_data=f"earnings_{bot_username}_daily7"),
                InlineKeyboardButton("📆 Last 30 Days Daily", callback_data=f"earnings_{bot_username}_daily30")
            ],
            [
                InlineKeyboardButton("🗓️ Custom Date Filter", callback_data=f"earnings_{bot_username}_custom"),
                InlineKeyboardButton("🔄 Refresh Data", callback_data=f"earnings_{bot_username}_refresh")
            ]
        ]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

    async def show_earnings_daily(self, message, bot_username, days: int):
        safe_bot = DBManager._get_safe_tablename(bot_username, '')
        success_table = f"{safe_bot}successful_transactions"

        query = f"""
        SELECT 
            DATE(completion_time) as dt,
            COALESCE(SUM(CASE WHEN currency = 'XTR' THEN amount * 1.2 ELSE amount END), 0) as daily_sum,
            COALESCE(SUM(CASE WHEN currency = 'XTR' THEN amount ELSE 0 END), 0) as daily_stars,
            COUNT(*) as daily_count
        FROM {success_table}
        WHERE completion_time >= NOW() - INTERVAL '{days} days'
        GROUP BY DATE(completion_time)
        ORDER BY dt DESC;
        """
        records = await DBManager.execute_pg_query(query, fetch='all')
        
        text = f"📈 <b>Daily Earnings Breakdown (Last {days} Days) - @{bot_username}</b>\n\n"
        if not records:
            text += "<i>Is duration me abhi tak koi successful sales nahi hui hain.</i>\n"
        else:
            total_period = sum(float(r['daily_sum']) for r in records)
            total_stars = sum(int(r['daily_stars']) for r in records)
            total_orders = sum(int(r['daily_count']) for r in records)
            star_str_main = f" (+ {total_stars} ⭐)" if total_stars > 0 else ""
            
            text += f"<b>Total:</b> ₹{total_period:,.2f}{star_str_main} across {total_orders} orders\n\n"
            for r in records:
                d_str = r['dt'].strftime('%Y-%m-%d')
                d_stars = int(r['daily_stars'])
                star_str = f" | {d_stars} ⭐" if d_stars > 0 else ""
                text += f"• <b>{d_str}:</b> ₹{float(r['daily_sum']):,.2f}{star_str} ({r['daily_count']} orders)\n"
        keyboard = [[InlineKeyboardButton("⬅️ Back to Overview", callback_data=f"earnings_{bot_username}_overview")]]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    
    async def handle_clone_command(self):
        await self.initiate_conversation('clone', "Please send me the API token of the bot you want to clone.\n\nउदाहरण: 1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890")

    async def initiate_conversation(self, command_name, prompt_message, extra_data=None, parse_mode=None):
        state = {'command': command_name, 'step': 1}
        if extra_data:
            state.update(extra_data)
        prompt_msg = await self.bot.send_message(self.chat_id, prompt_message, parse_mode=parse_mode)
        state['prompt_message_id'] = prompt_msg.message_id
        await CACHE_CONVERSATION.set(f"{self.bot_username}_{self.user_id}", state)
    
    
    async def handle_conv_clone(self, state):
        api_key = self.update.message.text
        prompt_message_id = state.get('prompt_message_id')
        key = f"{self.bot_username}_{self.user_id}"
        await CACHE_CONVERSATION.delete(key)
        try:
            await self.bot.delete_message(self.chat_id, self.update.message.message_id)
        except Exception:
            pass
        if prompt_message_id:
            try:
                await self.bot.delete_message(self.chat_id, prompt_message_id)
            except Exception:
                pass
        
        # YAHAN CHANGE HAI: execute_query ko execute_sqlite_query karna hai
        bots_count_result = await DBManager.execute_sqlite_query(
            ALL_BOTS_DB,
            "SELECT COUNT(*) FROM bots WHERE creator_id=?",
            (self.user_id,),
            fetch='one'
        )
        bots_count = bots_count_result[0] if bots_count_result else 0

        if bots_count >= 10:
            await self.bot.send_message(
            self.chat_id,
            "आप 10 बॉट्स की अधिकतम सीमा तक पहुँच चुके हैं। कृपया नया बॉट बनाने से पहले अपने किसी मौजूदा बॉट को हटा दें।"
            )
            return
        if not api_key or len(api_key.split(':')) != 2:
            await self.bot.send_message(self.chat_id, "This doesn't look like a valid API token. Please try again with /clone.")
            return
        msg = await self.bot.send_message(self.chat_id, "Verifying token...")
        try:
            new_bot = Bot(token=api_key)
            await new_bot.initialize()
            new_bot_info = await new_bot.get_me()
            new_bot_username = new_bot_info.username
        except Exception as e:
            await msg.edit_text("Invalid API Token. I couldn't verify it. Please try again with /clone.")
            await notify_admin(f"Clone error: {e}")
            return
        await msg.edit_text(f"Token verified for @{new_bot_username}. Setting up your bot...")
        clone_webhook_url = f"{WEBHOOK_URL}/normal"
        try:
            success = await new_bot.set_webhook(
            url=clone_webhook_url,
            allowed_updates=["message", "callback_query", "chat_join_request", "chat_member", "channel_post", "pre_checkout_query"],            
            secret_token=new_bot_username
            )
            if not success:
                raise Exception("Webhook setup returned false")
        except Exception as e:
            await msg.edit_text("I couldn't set up the webhook for your bot. Please ensure my server is accessible and try again.")
            await notify_admin(f"Webhook setup error for {new_bot_username}: {e}")
            return
        await msg.edit_text("Webhook set successfully. Saving details and setting up commands...")
        
        # PostgreSQL ke liye 'INSERT OR REPLACE' ki jagah 'ON CONFLICT' use hota hai
        # Hum '?' hi use karenge kyunki hamara naya Wrapper ($1, $2) me convert kar dega
        await DBManager.execute_sqlite_query(
            ALL_BOTS_DB,
            """
            INSERT INTO bots (username, api_key, creator_id) 
            VALUES (?, ?, ?) 
            ON CONFLICT (username) DO UPDATE 
            SET api_key = EXCLUDED.api_key, creator_id = EXCLUDED.creator_id
            """,
            (new_bot_username, api_key, self.user_id)
        ) 
        await DBManager.setup_clone_tables(new_bot_username)
        
        # Naye bot ko seedhe memory pool me cache karein taaki dobara create na karna pade
        async with BOT_INSTANCES_LOCK:
            BOT_INSTANCES[new_bot_username] = new_bot
            
        try:
            commands = [
            telegram.BotCommand("start", "Start the bot"),
            telegram.BotCommand("clone", "Clone a new bot"),
            telegram.BotCommand("broadcast", "Broadcast a message (Admin)"),
            telegram.BotCommand("premium_broadcast", "Broadcast a message to premium members (Admin)"),
            telegram.BotCommand("batch_link", "Create batch link for multiple files"),
            telegram.BotCommand("short_link", "Shorten a link"),
            telegram.BotCommand("stats", "Show bot statistics (Admin)"),
            telegram.BotCommand("earnings", "Show bot earnings & analytics (Admin)")
            ]            
            await new_bot.set_my_commands(commands)
        except Exception as e:
            await msg.edit_text("Warning: Couldn't set commands for your new bot, but it should still work.")
            await notify_admin(f"Command setup error for {new_bot_username}: {e}")        
        
        await msg.edit_text(f"✅ Congratulations! Your bot @{new_bot_username} is ready. Go to your bot and start sharing files.")
        log_text = (
            f"🤖 <b>New Clone Bot Created!</b>\n\n"
            f"• <b>Bot:</b> @{new_bot_username}\n"
            f"• <b>Owner ID:</b> <code>{self.user_id}</code>\n"
            f"• <b>Date:</b> <code>{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</code>"
        )
        await notify_admin(log_text)   
    async def handle_conv_broadcast(self, state):
        key = f"{self.bot_username}_{self.user_id}"
        await CACHE_CONVERSATION.delete(key)
        if not self.update.message:
            await self.bot.send_message(self.chat_id, "Broadcast canceled.")
            return

        users_table = DBManager._get_safe_tablename(self.bot_username, 'users')
        users_records = await DBManager.execute_pg_query(f"SELECT user_id FROM {users_table}", fetch='all')

        if not users_records:
            await self.bot.send_message(self.chat_id, "No users to broadcast to.")
            return
        
        users = [rec['user_id'] for rec in users_records]
        await self.bot.send_message(self.chat_id, f"Starting broadcast to {len(users)} users. This may take some time.")
        success_count, fail_count = 0, 0
        message_id = self.update.message.message_id
        from_chat_id = self.chat_id
        batch_size = 100
        for i in range(0, len(users), batch_size):
            batch = users[i:i + batch_size]
            tasks = []
            for user_id in batch:
                # Yahan humne self.bot_username ko function call me add kar diya hai
                tasks.append(self.broadcast_to_user(self.bot_username, user_id, from_chat_id, message_id))
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    fail_count += 1
                else:
                    success_count += 1
        await self.bot.send_message(self.chat_id, f"Broadcast completed.\n\n✅ Sent successfully: {success_count}\n❌ Failed: {fail_count}")
    async def broadcast_to_user(self, bot_username, user_id, from_chat_id, message_id):
        try:
            # Message copy karne ki koshish karein
            await self.bot.copy_message(chat_id=user_id, from_chat_id=from_chat_id, message_id=message_id)
        except TelegramError as e:
            # Yahan hum error ko pakdenge
            error_message = str(e).lower()
            
            # Check karein ki kya user ne bot ko block kar diya hai ya chat nahi mil raha
            if "forbidden: bot was blocked by the user" in error_message or "chat not found" in error_message:
                try:
                    # Agar haan, toh user ko database se delete karne ka logic
                    logger.info(f"Broadcast failed for user {user_id} in @{bot_username} due to: {error_message}. Deleting user from DB.")
                    
                    # Sahi users table ka naam generate karein
                    users_table = DBManager._get_safe_tablename(bot_username, 'users')
                    
                    # User ko delete karne ke liye query chalayein
                    await DBManager.execute_pg_query(f"DELETE FROM {users_table} WHERE user_id=$1", (user_id,))
                    
                    # Exception return karein taaki fail_count me gina ja sake
                    raise e 
                
                except Exception as db_e:
                    logger.error(f"Failed to delete user {user_id} for @{bot_username} from DB after broadcast error: {db_e}")
                    # Exception return karein taaki fail_count me gina ja sake
                    raise e
            else:
                # Agar koi aur Telegram error hai, toh use bhi fail_count me gine
                raise e
    async def handle_conv_premium_broadcast(self, state):
        key = f"{self.bot_username}_{self.user_id}"
        await CACHE_CONVERSATION.delete(key)
        if not self.update.message:
            await self.bot.send_message(self.chat_id, "Broadcast canceled.")
            return

        premium_table = DBManager._get_safe_tablename(self.bot_username, 'premium')
        premium_users_records = await DBManager.execute_pg_query(f"SELECT user_id, expiry_time FROM {premium_table}", fetch='all')

        if not premium_users_records:
            await self.bot.send_message(self.chat_id, "No premium members to broadcast to.")
            return

        active_users = []
        now_utc = datetime.utcnow().replace(tzinfo=None) # Use naive UTC for comparison
        for record in premium_users_records:
            user_id, expiry_time = record['user_id'], record['expiry_time']
            if expiry_time.replace(tzinfo=None) > now_utc:
                active_users.append(user_id)
            else:
                await DBManager.execute_pg_query(f"DELETE FROM {premium_table} WHERE user_id=$1", (user_id,))
                try:
                    await self.bot.send_message(user_id, "Your premium membership has expired.")
                except Exception:
                    pass
        
        if not active_users:
            await self.bot.send_message(self.chat_id, "No active premium members to broadcast to.")
            return

        await self.bot.send_message(self.chat_id, f"Starting broadcast to {len(active_users)} premium members. This may take some time.")
        success_count, fail_count = 0, 0
        message_id = self.update.message.message_id
        from_chat_id = self.chat_id
        batch_size = 100
        for i in range(0, len(active_users), batch_size):
            batch = active_users[i:i + batch_size]
            tasks = []
            for user_id in batch:
                # Yahan bhi humne self.bot_username ko function call me add kar diya hai
                tasks.append(self.broadcast_to_user(self.bot_username, user_id, from_chat_id, message_id))
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    fail_count += 1
                else:
                    success_count += 1
        await self.bot.send_message(self.chat_id, f"Broadcast completed.\n\n✅ Sent successfully: {success_count}\n❌ Failed: {fail_count}")
    async def handle_conv_footer(self, state):
        prompt_message_id = state.get('prompt_message_id')
        user_message_id = self.update.message.message_id
        key = f"{self.bot_username}_{self.user_id}"
        await CACHE_CONVERSATION.delete(key)
        try:
            await self.bot.delete_message(self.chat_id, user_message_id)
        except Exception:
            pass
        if prompt_message_id:
            try:
                await self.bot.delete_message(self.chat_id, prompt_message_id)
            except Exception:
                pass
        footer_text = self.update.message.text
        if not footer_text:
            await self.bot.send_message(self.chat_id, "Invalid footer text. Operation canceled.")
            return
        bot_username = state.get('bot_username', self.bot_username)
        
        settings_table = DBManager._get_safe_tablename(bot_username, 'settings')
        query = f"INSERT INTO {settings_table} (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = $2"
        await DBManager.execute_pg_query(query, ('footer', json.dumps(footer_text)))

        if await CACHE_BOT_SETTINGS.contains(bot_username):
            await CACHE_BOT_SETTINGS.delete(bot_username)
        await self.bot.send_message(self.chat_id, f"Footer for @{bot_username} successfully set.")
    async def handle_conv_adlink(self, state):
        key = f"{self.bot_username}_{self.user_id}"
        await CACHE_CONVERSATION.delete(key)
        api_link = self.update.message.text
        if not api_link or "&url=" not in api_link:
            await self.bot.send_message(self.chat_id, "This doesn't look like a valid API link. It should contain '&url='.")
            return
        base_api_link = api_link.split("&alias=")[0] if "&alias=" in api_link else api_link
        test_url = f"https://t.me/{self.bot_username}"
        shortener_url = f"{base_api_link}&url={test_url}"
        retries = 2
        success = False
        for attempt in range(retries):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(shortener_url, timeout=10)
                    response.raise_for_status()
                    data = response.json()
                    if data.get('status') == 'success' and data.get('shortenedUrl'):
                        success = True
                        break
            except Exception:
                pass
        if not success:
            await self.bot.send_message(self.chat_id, "Wrong API. It didn't respond correctly to a test link.")
            return
        bot_username = state.get('bot_username', self.bot_username)
        try:
            submitted_domain = urlparse(base_api_link).netloc
            if submitted_domain not in CUSTOM_SHORTENERS:
                notification_message = (
                f"⚠️ Unknown Shortener Domain Alert!\n\n"
                f"Bot: @{bot_username}\n"
                f"Owner ID: {self.user_id}\n"
                f"Domain: {submitted_domain}\n"
                f"Full API Link: `{base_api_link}`"
                )
                await notify_admin(notification_message)
        except Exception as e:
            logger.error(f"Error during domain check for notification: {e}")
        
        settings_table = DBManager._get_safe_tablename(bot_username, 'settings')
        query = f"INSERT INTO {settings_table} (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = $2"
        await DBManager.execute_pg_query(query, ('ad_api_link', json.dumps(base_api_link)))

        if await CACHE_BOT_SETTINGS.contains(bot_username):
            await CACHE_BOT_SETTINGS.delete(bot_username)
        await self.bot.send_message(self.chat_id, "Ad shortener API link set successfully.")
    async def handle_conv_short_link(self, state):
        key = f"{self.bot_username}_{self.user_id}"
        await CACHE_CONVERSATION.delete(key)
        link_to_shorten = self.update.message.text
        if not link_to_shorten:
            await self.bot.send_message(self.chat_id, "Invalid link. Operation canceled.")
            return
        settings = await self.get_bot_settings()
        ad_api_link = settings.get('ad_api_link', '')
        if not ad_api_link:
            await self.bot.send_message(self.chat_id, "No ad shortener API set. Please set it first.")
            return
        shortener_url = f"{ad_api_link}&url={link_to_shorten}"
        retries = 2
        success = False
        short_link = None
        for attempt in range(retries):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(shortener_url, timeout=10)
                    response.raise_for_status()
                    data = response.json()
                    if data.get('status') == 'success' and data.get('shortenedUrl'):
                        short_link = data['shortenedUrl']
                        success = True
                        break
            except Exception:
                pass
        if success:
            await self.bot.send_message(self.chat_id, f"Shortened link: {short_link}")
        else:
            await self.bot.send_message(self.chat_id, "Failed to shorten the link. Please try again.")

    async def handle_conv_add_fsub(self, state):
        prompt_message_id = state.get('prompt_message_id')
        user_message_id = self.update.message.message_id
        message = self.update.message

        if prompt_message_id:
            try:
                await self.bot.delete_message(self.chat_id, prompt_message_id)
            except Exception:
                pass
        try:
            await self.bot.delete_message(self.chat_id, user_message_id)
        except Exception:
            pass

        # --- FINAL ROBUST LOGIC (English) ---
        channel_id = None

        # Priority 1: Use the modern 'forward_origin' attribute if available
        if hasattr(message, 'forward_origin') and message.forward_origin and message.forward_origin.type == 'channel':
            channel_id = message.forward_origin.chat.id
        
        # Priority 2: Fallback to the older 'forward_from_chat' attribute
        elif hasattr(message, 'forward_from_chat') and message.forward_from_chat:
            channel_id = message.forward_from_chat.id

        # If neither worked, it's an invalid input
        else:
            error_text = "Invalid input. Please forward a post directly from a public or private channel where the bot is a member."
            await self.bot.send_message(self.chat_id, error_text)
            key = f"{self.bot_username}_{self.user_id}"
            await CACHE_CONVERSATION.delete(key)
            return
        # --- LOGIC ENDS ---

        bot_username = state.get('bot_username')
        # YAHAN BADLAAV KIYA GAYA HAI: force_initialize=True add kiya gaya hai
        clone_bot = await get_bot_instance(bot_username, force_initialize=True)
        try:
            chat_member = await clone_bot.get_chat_member(channel_id, clone_bot.id)
            if chat_member.status not in ['administrator', 'creator']:
                raise TelegramError("Bot is not an admin in the channel.")
            await clone_bot.get_chat(channel_id)
        except Exception as e:
            error_text = "A problem occurred. Please ensure the bot is an admin in the target channel and that you forwarded a valid post."
            await self.bot.send_message(self.chat_id, error_text)
            await notify_admin(f"FSUB add error for channel {channel_id}: {e}")
            key = f"{self.bot_username}_{self.user_id}"
            await CACHE_CONVERSATION.delete(key)
            return
            
        state['channel_id'] = channel_id
        state['command'] = 'add_fsub_target'
        key = f"{self.bot_username}_{self.user_id}"
        await CACHE_CONVERSATION.set(key, state)
        keyboard = [
            [InlineKeyboardButton("Normal Mode", callback_data=f"fsub_mode_normal_{bot_username}_{channel_id}")],
            [InlineKeyboardButton("Request Mode", callback_data=f"fsub_mode_request_{bot_username}_{channel_id}")]
        ]
        await self.bot.send_message(self.chat_id, "Select mode: Normal (direct join) or Request (requires approval).", reply_markup=InlineKeyboardMarkup(keyboard))

    async def set_fsub_mode(self, message, bot_username, channel_id, mode):
        key = f"{self.bot_username}_{self.user_id}"
        state = await CACHE_CONVERSATION.get(key)
        if not state or state.get('channel_id') != channel_id:
            await message.edit_text("Invalid state. Operation canceled.")
            if await CACHE_CONVERSATION.contains(key):
                await CACHE_CONVERSATION.delete(key)
            return
        # YAHAN BADLAAV KIYA GAYA HAI: force_initialize=True add kiya gaya hai
        # YAHAN BADLAAV KIYA GAYA HAI: force_initialize=True add kiya gaya hai
        clone_bot = await get_bot_instance(bot_username, force_initialize=True)
        try:
            if mode == 'request':
                invite_link = await clone_bot.create_chat_invite_link(
                    chat_id=channel_id, 
                    creates_join_request=True, 
                    name=f"Request for @{bot_username}"
                )
                await DBManager.setup_join_request_db(bot_username, channel_id)
            else:
                invite_link = await clone_bot.create_chat_invite_link(
                    chat_id=channel_id, 
                    creates_join_request=False, 
                    name=f"Join for @{bot_username}"
                )
            link = invite_link.invite_link
        except Exception as e:
            await message.edit_text("Couldn't create invite link. Ensure the bot is admin with 'Invite Users' permission.")
            await notify_admin(f"FSUB mode set error for channel {channel_id}: {e}")
            if await CACHE_CONVERSATION.contains(key):
                await CACHE_CONVERSATION.delete(key)
            return        
        
        state['mode'] = mode
        state['link'] = link
        state['bot_username'] = bot_username
        state['command'] = 'add_fsub_target'
        await CACHE_CONVERSATION.set(key, state)
        await message.edit_text("Please send the target number of joins for this channel. Send 0 for unlimited.")
    async def handle_conv_add_fsub_target(self, state):
        key = f"{self.bot_username}_{self.user_id}"
        await CACHE_CONVERSATION.delete(key)
        if not self.update.message.text or not self.update.message.text.isdigit():
            await self.bot.send_message(self.chat_id, "Invalid number. Please enter a valid number for the target, or 0 for unlimited. Operation canceled.")
            return
        target = int(self.update.message.text)
        channel_id = state.get('channel_id')
        mode = state.get('mode')
        link = state.get('link')
        bot_username = state.get('bot_username')
        settings = await self.get_bot_settings(bot_username)
        fsub_channels = settings.get('fsub_channels', [])
        if len(fsub_channels) >= 4:
            await self.bot.send_message(self.chat_id, "You can add only up to 4 FSUB channels.")
            return
        if any(ch['id'] == channel_id for ch in fsub_channels):
            await self.bot.send_message(self.chat_id, "This channel is already in the FSUB list.")
            return
        fsub_channels.append({'id': channel_id, 'link': link, 'mode': mode, 'target': target, 'current': 0})
        
        settings_table = DBManager._get_safe_tablename(bot_username, 'settings')
        query = f"INSERT INTO {settings_table} (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = $2"
        await DBManager.execute_pg_query(query, ('fsub_channels', json.dumps(fsub_channels)))

        if await CACHE_BOT_SETTINGS.contains(bot_username):
            await CACHE_BOT_SETTINGS.delete(bot_username)
        await self.bot.send_message(self.chat_id, f"Channel {channel_id} added to FSUB list in {mode} mode with target of {target if target > 0 else 'unlimited'} joins.")
    async def handle_conv_add_admin(self, state):
        key = f"{self.bot_username}_{self.user_id}"
        await CACHE_CONVERSATION.delete(key)
        admin_id_str = self.update.message.text
        if not admin_id_str.isdigit():
            await self.bot.send_message(self.chat_id, "Invalid user ID. Operation canceled.")
            return
        admin_id = int(admin_id_str)
        bot_username = state.get('bot_username')
        settings = await self.get_bot_settings(bot_username)
        admins = settings.get('admins', [])
        if admin_id in admins:
            await self.bot.send_message(self.chat_id, "This user is already a side admin.")
            return
        if len(admins) >= 5:
            await self.bot.send_message(self.chat_id, "You can add only up to 5 side admins.")
            return
        admins.append(admin_id)
        
        settings_table = DBManager._get_safe_tablename(bot_username, 'settings')
        query = f"INSERT INTO {settings_table} (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = $2"
        await DBManager.execute_pg_query(query, ('admins', json.dumps(admins)))

        if await CACHE_BOT_SETTINGS.contains(bot_username):
            await CACHE_BOT_SETTINGS.delete(bot_username)
        await self.bot.send_message(self.chat_id, f"User {admin_id} is now a side admin for @{bot_username}.")
    async def handle_conv_adtutorial(self, state):
        key = f"{self.bot_username}_{self.user_id}"
        await CACHE_CONVERSATION.delete(key)
        tutorial_link = self.update.message.text
        if not tutorial_link:
            await self.bot.send_message(self.chat_id, "Invalid tutorial link. Operation canceled.")
            return
        bot_username = state.get('bot_username', self.bot_username)

        settings_table = DBManager._get_safe_tablename(bot_username, 'settings')
        query = f"INSERT INTO {settings_table} (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = $2"
        await DBManager.execute_pg_query(query, ('ad_tutorial_link', json.dumps(tutorial_link)))
        
        if await CACHE_BOT_SETTINGS.contains(bot_username):
            await CACHE_BOT_SETTINGS.delete(bot_username)
        await self.bot.send_message(self.chat_id, f"Ad Tutorial link set successfully for @{bot_username}:\n\n{tutorial_link}")
    async def handle_conv_welcome(self, state):
        key = f"{self.bot_username}_{self.user_id}"
        await CACHE_CONVERSATION.delete(key)
        welcome_text = self.update.message.text
        if not welcome_text or len(welcome_text) > 500:
            await self.bot.send_message(self.chat_id, "Invalid welcome message. It must be non-empty and max 500 characters. Operation canceled.")
            return
        bot_username = state.get('bot_username', self.bot_username)
        
        settings_table = DBManager._get_safe_tablename(bot_username, 'settings')
        query = f"INSERT INTO {settings_table} (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = $2"
        await DBManager.execute_pg_query(query, ('welcome_message', json.dumps(welcome_text)))

        if await CACHE_BOT_SETTINGS.contains(bot_username):
            await CACHE_BOT_SETTINGS.delete(bot_username)
        # --- NAYA CODE SHURU ---
        # Message ko thoda clear banaya gaya hai
        await self.bot.send_message(self.chat_id, f"Welcome text message set successfully for @{bot_username}:\n\n{welcome_text}")
        # --- NAYA CODE KHATAM --- 

    async def delete_welcome_media(self, message, bot_username):
        """Welcome media ko database se delete karta hai."""
        settings_table = DBManager._get_safe_tablename(bot_username, 'settings')
        
        # Media ID aur Type ko khali set kar do
        id_query = f"INSERT INTO {settings_table} (key, value) VALUES ('welcome_media_id', $1) ON CONFLICT (key) DO UPDATE SET value = $1"
        type_query = f"INSERT INTO {settings_table} (key, value) VALUES ('welcome_media_type', $1) ON CONFLICT (key) DO UPDATE SET value = $1"
        
        await DBManager.execute_pg_query(id_query, (json.dumps(''),))
        await DBManager.execute_pg_query(type_query, (json.dumps(''),))

        # Cache ko clear karo
        if await CACHE_BOT_SETTINGS.contains(bot_username):
            await CACHE_BOT_SETTINGS.delete(bot_username)
            
        text = f"Welcome media for @{bot_username} has been deleted."
        keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data=f"setting_welcome_{bot_username}")]]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    async def handle_conv_welcome_media(self, state):
        """Conversation state ko handle karta hai jab admin welcome media set karta hai."""
        key = f"{self.bot_username}_{self.user_id}"
        await CACHE_CONVERSATION.delete(key)
        
        bot_username = state.get('bot_username', self.bot_username)
        message = self.update.message
        
        media_id = None
        media_type = None

        if message.photo:
            media_id = message.photo[-1].file_id # Hamesha best quality photo select karo
            media_type = 'photo'
        elif message.video:
            media_id = message.video.file_id
            media_type = 'video'
        
        if not media_id or not media_type:
            await self.bot.send_message(self.chat_id, "This is not a valid photo or video. Operation cancelled.")
            return

        settings_table = DBManager._get_safe_tablename(bot_username, 'settings')
        
        # Naye media ki details save karo
        id_query = f"INSERT INTO {settings_table} (key, value) VALUES ('welcome_media_id', $1) ON CONFLICT (key) DO UPDATE SET value = $1"
        type_query = f"INSERT INTO {settings_table} (key, value) VALUES ('welcome_media_type', $1) ON CONFLICT (key) DO UPDATE SET value = $1"
        
        await DBManager.execute_pg_query(id_query, (json.dumps(media_id),))
        await DBManager.execute_pg_query(type_query, (json.dumps(media_type),))

        # Cache ko clear karna zaroori hai
        if await CACHE_BOT_SETTINGS.contains(bot_username):
            await CACHE_BOT_SETTINGS.delete(bot_username)
            
        await self.bot.send_message(self.chat_id, f"✅ Welcome media successfully set for @{bot_username}.")
    
    async def handle_conv_custombutton(self, state):
        bot_username = state.get('bot_username', self.bot_username)
        if state['step'] == 1:
            name = self.update.message.text.strip()
            if not name or len(name) > 40:
                await self.bot.send_message(self.chat_id, "Invalid button name. Max 40 characters. Operation canceled.")
                key = f"{self.bot_username}_{self.user_id}"
                await CACHE_CONVERSATION.delete(key)
                return
            state['name'] = name
            state['step'] = 2
            key = f"{self.bot_username}_{self.user_id}"
            await CACHE_CONVERSATION.set(key, state)
            await self.bot.send_message(self.chat_id, "Now send the button URL.")
        elif state['step'] == 2:
            url = self.update.message.text.strip()
            if not url.startswith('http'):
                await self.bot.send_message(self.chat_id, "Invalid URL. Must start with http. Operation canceled.")
                key = f"{self.bot_username}_{self.user_id}"
                await CACHE_CONVERSATION.delete(key)
                return
            
            settings_table = DBManager._get_safe_tablename(bot_username, 'settings')
            name_query = f"INSERT INTO {settings_table} (key, value) VALUES ('custom_button_name', $1) ON CONFLICT (key) DO UPDATE SET value = $1"
            url_query = f"INSERT INTO {settings_table} (key, value) VALUES ('custom_button_url', $1) ON CONFLICT (key) DO UPDATE SET value = $1"

            await DBManager.execute_pg_query(name_query, (json.dumps(state['name']),))
            await DBManager.execute_pg_query(url_query, (json.dumps(url),))

            if await CACHE_BOT_SETTINGS.contains(bot_username):
                await CACHE_BOT_SETTINGS.delete(bot_username)
            key = f"{self.bot_username}_{self.user_id}"
            await CACHE_CONVERSATION.delete(key)
            await self.bot.send_message(self.chat_id, f"Custom button set successfully for @{bot_username}: {state['name']} -> {url}") 
    async def handle_conv_update_token(self, state):
        key = f"{self.bot_username}_{self.user_id}"
        await CACHE_CONVERSATION.delete(key)

        new_api_key = self.update.message.text
        original_bot_username = state.get('bot_username')
        revoked_bot_username = f"{original_bot_username}#revoked"

        msg = await self.bot.send_message(self.chat_id, "Verifying new token...")

        try:
            new_bot = Bot(token=new_api_key)
            await new_bot.initialize()
            new_bot_info = await new_bot.get_me()
            verified_username = new_bot_info.username
        except Exception:
            await msg.edit_text("❌ Invalid API Token. Maine is token ko verify nahi kar paya. Kripya sahi token bhej kar dobara prayas karein.")
            return

        if verified_username.lower() != original_bot_username.lower():
            await msg.edit_text(f"❌ Token Mismatch! Yeh token `@{verified_username}` ka hai, `@{original_bot_username}` ka nahi. Kripya sahi bot ka token de.")
            return

        # DB mein update karo
        # DB mein update karo
        await DBManager.execute_sqlite_query(
            ALL_BOTS_DB,
            "UPDATE bots SET api_key = ?, username = ? WHERE username = ?",
            (new_api_key, original_bot_username, revoked_bot_username)
        )
        # Purana instance shutdown karein aur token cache reset karein
        await CACHE_BOT_TOKENS.delete(original_bot_username)
        await shutdown_bot_instance(original_bot_username)

        # Naye verified instance ko pool me register karein
        async with BOT_INSTANCES_LOCK:
            BOT_INSTANCES[original_bot_username] = new_bot

        # Naye bot ke liye webhook set karo
        clone_webhook_url = f"{WEBHOOK_URL}/normal"
        try:
            success = await new_bot.set_webhook(
                url=clone_webhook_url,
                allowed_updates=["message", "callback_query", "chat_join_request", "chat_member", "channel_post", "pre_checkout_query"],                
                secret_token=original_bot_username
            )
            if not success:
                raise Exception("Webhook setup returned false")
            await msg.edit_text(f"✅ Success! Aapke bot `@{original_bot_username}` ka API token safaltapoorvak update ho gaya hai aur bot ab fir se active hai.")
        except Exception as e:
            await msg.edit_text(f"⚠️ Token updated, but webhook setup failed. Aap chinta na karein, agle automatic refresh me webhook set ho jayega. Bot `@{original_bot_username}` ka token update ho gaya hai.")
            logger.error(f"Webhook setup failed after token update for @{original_bot_username}: {e}")
    # ... handle_conv_update_token ke baad ...

    # --- PAYMENT FEATURE KE LIYE NAYE FUNCTIONS ---

    async def show_paid_settings(self, message, bot_username):
        """Paid feature ka settings menu dikhata hai."""
        settings = await self.get_bot_settings(bot_username)
        paid_info = settings.get('paid_settings', {})
        is_enabled = settings.get('paid_enabled', False)
        
        upi_enabled = paid_info.get('upi_enabled', True)
        cf_enabled = paid_info.get('cf_enabled', False)
        stars_enabled = paid_info.get('stars_enabled', False)
        
        ai_enabled = settings.get('ai_verify_enabled', False)
        ai_name = settings.get('ai_verify_receiver_name', 'Not Set')
        
        status = "✅ Enabled" if is_enabled else "❌ Disabled"
        upi_status = "✅ ON" if upi_enabled else "❌ OFF"
        cf_status = "✅ ON" if cf_enabled else "❌ OFF"
        stars_status = "✅ ON" if stars_enabled else "❌ OFF"
        ai_status = "✅ ON" if ai_enabled else "❌ OFF"
        
        upi_id = paid_info.get('upi_id') or "Not Set"
        cf_app_id = paid_info.get('cf_app_id') or "Not Set"
        
        price_7 = paid_info.get('price_7') or "Not Set"
        price_28 = paid_info.get('price_28') or "Not Set"
        price_90 = paid_info.get('price_90') or "Not Set"

        stars_p7 = paid_info.get('stars_price_7') or "Not Set"
        stars_p28 = paid_info.get('stars_price_28') or "Not Set"
        stars_p90 = paid_info.get('stars_price_90') or "Not Set"

        custom_plans = paid_info.get('custom_plans', [])
        c_plans_str = ""
        if custom_plans:
            c_plans_str = "\n\n*Custom Plans:*"
            for idx, cp in enumerate(custom_plans, 1):
                c_label_esc = self._escape_markdown(cp.get('label', ''))
                c_price_esc = self._escape_markdown(str(cp.get('price', 0)))
                c_plans_str += f"\n  \- Plan {idx}: `{c_label_esc}` — `{c_price_esc}` INR"

        free_limit_val = int(settings.get('free_limit', 0) or 0)
        free_limit_str = f"`{free_limit_val} per day`" if free_limit_val > 0 else "`Disabled (0)`"

        text = (
            f"💰 *Paid Membership Settings for @{self._escape_markdown(bot_username)}*\n\n"
            f"*Main Status:* `{status}`\n"
            f"*Daily Free Limit:* {free_limit_str}\n\n"
            f"*Payment Gateways:*\n"
            f"  \- UPI QR: `{upi_status}`\n"
            f"  \- Cashfree: `{cf_status}`\n"
            f"  \- Telegram Stars: `{stars_status}`\n\n"
            f"*UPI ID:* `{upi_id}`\n"
            f"*Cashfree App ID:* `{cf_app_id}`\n"
            f"*AI Verification:* `{ai_status}` \(Name: `{ai_name}`\)\n\n"
            f"*INR Pricing:*\n"
            f"  \- 7 Days: `{price_7}` INR\n"
            f"  \- 28 Days: `{price_28}` INR\n"
            f"  \- 3 Months: `{price_90}` INR\n\n"
            f"*Telegram Stars Pricing:*\n"
            f"  \- 7 Days: `{stars_p7}` ⭐\n"
            f"  \- 28 Days: `{stars_p28}` ⭐\n"
            f"  \- 3 Months: `{stars_p90}` ⭐"
            f"{c_plans_str}"
        ) 
        
        ai_toggle_btn = InlineKeyboardButton("❌ Disable AI", callback_data=f"paid_ai_toggle_off_{bot_username}") if ai_enabled else InlineKeyboardButton("✅ Enable AI", callback_data=f"paid_ai_toggle_on_{bot_username}")
        upi_toggle_btn = InlineKeyboardButton(f"Turn {'OFF' if upi_enabled else 'ON'} UPI", callback_data=f"paid_upi_toggle_{bot_username}")
        cf_toggle_btn = InlineKeyboardButton(f"Turn {'OFF' if cf_enabled else 'ON'} Cashfree", callback_data=f"paid_cf_toggle_{bot_username}")
        stars_toggle_btn = InlineKeyboardButton(f"Turn {'OFF' if stars_enabled else 'ON'} Stars", callback_data=f"paid_stars_toggle_{bot_username}")

        is_default_prices_set = bool(
            paid_info.get('price_7') and int(paid_info.get('price_7', 0)) > 0 and
            paid_info.get('price_28') and int(paid_info.get('price_28', 0)) > 0 and
            paid_info.get('price_90') and int(paid_info.get('price_90', 0)) > 0
        )

        custom_btns_row = []
        if is_default_prices_set and len(custom_plans) < 3:
            custom_btns_row.append(InlineKeyboardButton("➕ Add Custom Plan", callback_data=f"paid_add_cplan_{bot_username}"))
        if len(custom_plans) > 0:
            custom_btns_row.append(InlineKeyboardButton("🗑️ Delete Custom Plan", callback_data=f"paid_del_cplan_{bot_username}"))
        keyboard = [
            [
                InlineKeyboardButton("📩 Paid Messages", callback_data=f"paid_msg_menu_{bot_username}"),
                InlineKeyboardButton("📢 Paid Channels", callback_data=f"paid_chan_menu_{bot_username}")
            ],
            [InlineKeyboardButton(f"🎁 Free Limits ({free_limit_val})", callback_data=f"paid_free_limit_{bot_username}")],
            [InlineKeyboardButton("✏️ Setup UPI & INR Prices", callback_data=f"paid_setup_{bot_username}")],            
            [InlineKeyboardButton("⭐ Setup Telegram Stars Prices", callback_data=f"paid_stars_setup_{bot_username}")],            
            custom_btns_row if custom_btns_row else [],
            [InlineKeyboardButton("💳 Setup Cashfree API", callback_data=f"paid_cf_setup_{bot_username}")],
            [upi_toggle_btn, cf_toggle_btn, stars_toggle_btn],
            [InlineKeyboardButton("🤖 Setup AI Verify", callback_data=f"paid_ai_setup_{bot_username}"), ai_toggle_btn],
            [InlineKeyboardButton("❌ Disable Feature Entirely", callback_data=f"paid_disable_{bot_username}")],
            [InlineKeyboardButton("⬅️ Back", callback_data=f"bot_settings_{bot_username}")]
        ]
        keyboard = [row for row in keyboard if row]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN_V2)    
    
    async def show_paid_messages_menu(self, message, bot_username):
        """Paid Messages feature ka admin menu dikhata hai."""
        settings = await self.get_bot_settings(bot_username)
        is_on = settings.get('paid_messages_enabled', True)
        status_text = "✅ ON" if is_on else "❌ OFF"
        
        toggle_btn = InlineKeyboardButton("❌ Disable Feature", callback_data=f"paid_msg_toggle_off_{bot_username}") if is_on else InlineKeyboardButton("✅ Enable Feature", callback_data=f"paid_msg_toggle_on_{bot_username}")

        text = (
            f"📩 <b>Paid Messages Manager for @{bot_username}</b>\n\n"
            f"<b>Status:</b> {status_text}\n\n"
            f"Aap yahan se paid single messages create kar sakte hain. Jab koi user us link pe click karega toh bina payment kie access nahi milega."
        )
        keyboard = [
            [InlineKeyboardButton("➕ Create Paid Message", callback_data=f"paid_msg_create_{bot_username}")],
            [InlineKeyboardButton("🗑️ Delete Paid Message", callback_data=f"paid_msg_delete_{bot_username}")],
            [toggle_btn],
            [InlineKeyboardButton("⬅️ Back", callback_data=f"setting_paid_{bot_username}")]
        ]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    
    async def show_paid_channels_menu(self, message, bot_username):
        """Paid Channels feature ka admin management menu dikhata hai."""
        table = DBManager._get_safe_tablename(bot_username, 'paid_channels')
        count_res = None
        try:
            count_res = await DBManager.execute_pg_query(f"SELECT COUNT(*) as count FROM {table}", fetch='one')
        except Exception:
            await DBManager.setup_clone_tables(bot_username)
            count_res = await DBManager.execute_pg_query(f"SELECT COUNT(*) as count FROM {table}", fetch='one')

        total = count_res['count'] if count_res else 0
        text = (
            f"📢 <b>Paid Channels Manager for @{bot_username}</b>\n\n"
            f"<b>Active Paid Channels:</b> {total}\n\n"
            f"Aap yahan se private channels ke liye 16-character bundle access links create kar sakte hain. "
            f"Bot payment verify hone par automatic single-use 30-day invite links generate karega."
        )
        keyboard = [
            [InlineKeyboardButton("➕ Create Paid Channel", callback_data=f"paid_chan_create_{bot_username}")],
            [InlineKeyboardButton("⏸️ Pause / Resume Channel", callback_data=f"paid_chan_pause_prompt_{bot_username}")],
            [InlineKeyboardButton("🗑️ Delete Paid Channel", callback_data=f"paid_chan_del_prompt_{bot_username}")],
            [InlineKeyboardButton("⬅️ Back", callback_data=f"setting_paid_{bot_username}")]
        ]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

    async def handle_conv_paid_chan_add_channel(self, state):
        """Admin se max 4 channels ke forwarded messages collect karta hai."""
        bot_username = state.get('bot_username', self.bot_username)
        message = self.update.message

        channel_id = None
        if hasattr(message, 'forward_origin') and message.forward_origin and message.forward_origin.type == 'channel':
            channel_id = message.forward_origin.chat.id
        elif hasattr(message, 'forward_from_chat') and message.forward_from_chat:
            channel_id = message.forward_from_chat.id

        if not channel_id:
            await self.bot.send_message(self.chat_id, "❌ Invalid input. Kripya channel se message direct forward karein.")
            return

        clone_bot = await get_bot_instance(bot_username, force_initialize=True)
        try:
            member = await clone_bot.get_chat_member(channel_id, clone_bot.id)
            if member.status not in ['administrator', 'creator']:
                await self.bot.send_message(self.chat_id, "❌ Bot us channel me admin nahi hai. Kripya pehle bot ko admin banayein.")
                return
            if member.status == 'administrator' and not getattr(member, 'can_invite_users', True):
                await self.bot.send_message(self.chat_id, "❌ Bot ke paas 'Invite Users via Link' permission nahi hai. Permission on karein.")
                return
        except Exception as e:
            await self.bot.send_message(self.chat_id, f"❌ Channel verify karne me error: {e}")
            return

        channels = state.get('channels', [])
        if channel_id in channels:
            await self.bot.send_message(self.chat_id, "⚠️ Yeh channel pehle hi list me add ho chuka hai.")
            return

        channels.append(channel_id)
        state['channels'] = channels
        key = f"{self.bot_username}_{self.user_id}"

        if len(channels) >= 4:
            state['command'] = 'paid_chan_price'
            await CACHE_CONVERSATION.set(key, state)
            await self.bot.send_message(
                self.chat_id, 
                f"✅ 4 Channels add ho gaye (Max limit reached).\n\nAb is Paid Channel package ka <b>INR Price (₹)</b> enter karein:",
                parse_mode=ParseMode.HTML
            )
            return

        await CACHE_CONVERSATION.set(key, state)
        keyboard = [[InlineKeyboardButton("✅ Done Adding Channels", callback_data=f"paid_chan_done_channels_{bot_username}")]]
        await self.bot.send_message(
            self.chat_id,
            f"✅ Channel ({channel_id}) add ho gaya! (Total: {len(channels)}/4)\n\nAap agla channel forward kar sakte hain ya neeche <b>Done</b> par click karein:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )

    async def handle_conv_paid_chan_price(self, state):
        """Admin se INR price leta hai aur Stars price puchta hai."""
        key = f"{self.bot_username}_{self.user_id}"
        price_text = self.update.message.text.strip() if self.update.message and self.update.message.text else ""
        try:
            price = float(price_text)
            if price <= 0: raise ValueError()
        except ValueError:
            await self.bot.send_message(self.chat_id, "❌ Invalid price. Positive number enter karein.")
            return

        state['price'] = price
        bot_username = state.get('bot_username', self.bot_username)
        settings = await self.get_bot_settings(bot_username)
        paid_info = settings.get('paid_settings', {})

        if paid_info.get('stars_enabled', False):
            state['command'] = 'paid_chan_stars_price'
            await CACHE_CONVERSATION.set(key, state)
            await self.bot.send_message(self.chat_id, f"✅ INR Price: ₹{price:.2f}\n\nAb is Paid Channel ke liye <b>Telegram Stars Price (⭐)</b> enter karein:", parse_mode=ParseMode.HTML)
        else:
            state['stars_price'] = 0
            state['command'] = 'paid_chan_demo'
            await CACHE_CONVERSATION.set(key, state)
            await self.bot.send_message(
                self.chat_id,
                "✅ Price saved!\n\nAb is Paid Channel ke liye <b>1 Demo Message</b> bhejein jo user ko purchase se pehle dikhega.\n\n<i>(Agar demo nahi dena toh /skip likh kar send karein)</i>",
                parse_mode=ParseMode.HTML
            )

    async def handle_conv_paid_chan_stars_price(self, state):
        """Admin se Stars price leta hai."""
        key = f"{self.bot_username}_{self.user_id}"
        stars_text = self.update.message.text.strip() if self.update.message and self.update.message.text else ""
        if not stars_text.isdigit() or int(stars_text) <= 0:
            await self.bot.send_message(self.chat_id, "❌ Invalid Stars count. Positive number bhejein.")
            return

        state['stars_price'] = int(stars_text)
        state['command'] = 'paid_chan_demo'
        await CACHE_CONVERSATION.set(key, state)
        await self.bot.send_message(
            self.chat_id,
            "✅ Stars price saved!\n\nAb is Paid Channel ke liye <b>1 Demo Message</b> bhejein jo user ko purchase se pehle dikhega.\n\n<i>(Agar demo nahi dena toh /skip likh kar send karein)</i>",
            parse_mode=ParseMode.HTML
        )

    async def handle_conv_paid_chan_demo(self, state):
        """Demo message save karta hai ya skip karta hai aur 16-character link create karta hai."""
        key = f"{self.bot_username}_{self.user_id}"
        await CACHE_CONVERSATION.delete(key)

        msg = self.update.message
        demo_msg_id = None
        demo_chat_id = None

        if msg.text and msg.text.strip().lower() == "/skip":
            demo_msg_id = None
            demo_chat_id = None
        else:
            demo_msg_id = msg.message_id
            demo_chat_id = self.chat_id

        bot_username = state.get('bot_username', self.bot_username)
        channels = state.get('channels', [])
        price = float(state.get('price', 0.0))
        stars_price = int(state.get('stars_price', 0))

        payload = generate_random_string(16)
        table = DBManager._get_safe_tablename(bot_username, 'paid_channels')

        query = f"""
        INSERT INTO {table} (payload, channel_ids, price, stars_price, demo_msg_id, demo_chat_id, is_paused)
        VALUES ($1, $2, $3, $4, $5, $6, FALSE)
        """
        await DBManager.execute_pg_query(query, (
            payload, json.dumps(channels), price, stars_price, demo_msg_id, demo_chat_id
        ))

        link = f"https://t.me/{bot_username}?start={payload}"
        prices = [f"₹{price:.2f}"]
        if stars_price > 0: prices.append(f"{stars_price} ⭐")

        text = (
            f"🎉 <b>Paid Channel Successfully Created!</b>\n\n"
            f"• <b>Channels:</b> {len(channels)}\n"
            f"• <b>Price:</b> {' or '.join(prices)}\n"
            f"• <b>Demo Message:</b> {'Set ✅' if demo_msg_id else 'Skipped ❌'}\n"
            f"• <b>Payload:</b> <code>{payload}</code>\n\n"
            f"🔗 <b>Your 16-Character Purchase Link:</b>\n"
            f"<code>{link}</code>\n\n"
            f"<i>Share this link with your users. Upon successful payment, the bot will issue single-use 30-day join links automatically.</i>"
        )
        await self.bot.send_message(self.chat_id, text, parse_mode=ParseMode.HTML)

    async def handle_conv_paid_chan_delete(self, state):
        """16-char payload ya link se channel package permanently delete karta hai."""
        key = f"{self.bot_username}_{self.user_id}"
        await CACHE_CONVERSATION.delete(key)

        text = self.update.message.text.strip() if self.update.message and self.update.message.text else ""
        payload = None
        if "start=" in text:
            m = re.search(r"start=([a-zA-Z0-9]{16})", text)
            if m: payload = m.group(1)
        elif len(text) == 16 and text.isalnum():
            payload = text

        if not payload:
            await self.bot.send_message(self.chat_id, "❌ Invalid 16-character link ya payload. Operation canceled.")
            return

        bot_username = state.get('bot_username', self.bot_username)
        table = DBManager._get_safe_tablename(bot_username, 'paid_channels')
        access_table = DBManager._get_safe_tablename(bot_username, 'paid_channel_access')

        deleted = await DBManager.execute_pg_query(f"DELETE FROM {table} WHERE payload=$1 RETURNING payload", (payload,), fetch='one')
        if deleted:
            await DBManager.execute_pg_query(f"DELETE FROM {access_table} WHERE payload=$1", (payload,))
            await self.bot.send_message(self.chat_id, f"✅ Paid Channel with payload <code>{payload}</code> permanently deleted.", parse_mode=ParseMode.HTML)
        else:
            await self.bot.send_message(self.chat_id, f"❌ Payload <code>{payload}</code> nahi mila.", parse_mode=ParseMode.HTML)

    async def handle_conv_paid_chan_pause(self, state):
        """16-char payload ke channel package ka pause/resume status toggle karta hai."""
        key = f"{self.bot_username}_{self.user_id}"
        await CACHE_CONVERSATION.delete(key)

        text = self.update.message.text.strip() if self.update.message and self.update.message.text else ""
        payload = None
        if "start=" in text:
            m = re.search(r"start=([a-zA-Z0-9]{16})", text)
            if m: payload = m.group(1)
        elif len(text) == 16 and text.isalnum():
            payload = text

        if not payload:
            await self.bot.send_message(self.chat_id, "❌ Invalid 16-character link ya payload.")
            return

        bot_username = state.get('bot_username', self.bot_username)
        table = DBManager._get_safe_tablename(bot_username, 'paid_channels')
        row = await DBManager.execute_pg_query(f"SELECT is_paused FROM {table} WHERE payload=$1", (payload,), fetch='one')

        if not row:
            await self.bot.send_message(self.chat_id, "❌ Paid Channel record nahi mila.")
            return

        new_status = not row['is_paused']
        await DBManager.execute_pg_query(f"UPDATE {table} SET is_paused=$1 WHERE payload=$2", (new_status, payload))
        label = "PAUSED ⏸️" if new_status else "ACTIVE / RESUMED ▶️"
        await self.bot.send_message(self.chat_id, f"✅ Paid Channel <code>{payload}</code> status is now: <b>{label}</b>", parse_mode=ParseMode.HTML)

    async def deliver_paid_channel_access(self, bot_username: str, user_id: int, payload: str):
        """Payment verify hone par 30-day single-use invite links generate karke user ko send karta hai."""
        table = DBManager._get_safe_tablename(bot_username, 'paid_channels')
        chan_data = await DBManager.execute_pg_query(f"SELECT channel_ids FROM {table} WHERE payload=$1", (payload,), fetch='one')
        if not chan_data:
            return

        channel_ids = json.loads(chan_data['channel_ids'])
        clone_bot = await get_bot_instance(bot_username, force_initialize=True)
        if not clone_bot:
            return

        import time
        expire_ts = int(time.time() + 30 * 86400) # 30 days
        issued_links = []

        for cid in channel_ids:
            try:
                inv = await clone_bot.create_chat_invite_link(
                    chat_id=cid,
                    member_limit=1,
                    expire_date=expire_ts,
                    name=f"User {user_id}"
                )
                issued_links.append({"channel_id": cid, "link": inv.invite_link})
            except Exception as inv_err:
                logger.error(f"Error creating single-use invite link for channel {cid}: {inv_err}")

        # Save to access table
        access_table = DBManager._get_safe_tablename(bot_username, 'paid_channel_access')
        await DBManager.execute_pg_query(
            f"INSERT INTO {access_table} (payload, user_id, invite_links) VALUES ($1, $2, $3)",
            (payload, user_id, json.dumps(issued_links))
        )

        links_str = ""
        for i, item in enumerate(issued_links, 1):
            links_str += f"• <b>Channel {i}:</b> {item['link']}\n"

        delivery_msg = (
            f"✅ <b>Payment Verified!</b>\n\n"
            f"You can join from here:\n\n"
            f"{links_str}\n"
            f"⚠️ <b>Important Policy & Subscription Rules:</b>\n"
            f"• Each link is single-use (1 member limit) and expires in 30 days.\n"
            f"• Sharing your invite link or engaging in unwanted activity will lead to immediate cancellation of your subscription.\n"
            f"• Leaving the channel after joining may permanently revoke your access."
        )
        try:
            await clone_bot.send_message(user_id, delivery_msg, parse_mode=ParseMode.HTML)
            asyncio.create_task(record_bot_activity(bot_username, user_id, "view"))
        except Exception as e:
            logger.error(f"Failed to send invite links to user {user_id}: {e}")
    
    async def toggle_gateway(self, message, bot_username, gateway):
        settings = await self.get_bot_settings(bot_username)
        paid_info = settings.get('paid_settings', {})
        if gateway == "cf":
            current = paid_info.get('cf_enabled', False)
            paid_info['cf_enabled'] = not current
        elif gateway == "stars":
            current = paid_info.get('stars_enabled', False)
            paid_info['stars_enabled'] = not current
        else:
            current = paid_info.get('upi_enabled', True)
            paid_info['upi_enabled'] = not current
            
        settings_table = DBManager._get_safe_tablename(bot_username, 'settings')
        query = f"INSERT INTO {settings_table} (key, value) VALUES ('paid_settings', $1) ON CONFLICT (key) DO UPDATE SET value = $1"
        await DBManager.execute_pg_query(query, (json.dumps(paid_info),))
        await CACHE_BOT_SETTINGS.delete(bot_username)
        await self.show_paid_settings(message, bot_username)    
    
    async def toggle_ai_verification(self, message, bot_username, enable_status):
        settings_table = DBManager._get_safe_tablename(bot_username, 'settings')
        query = f"INSERT INTO {settings_table} (key, value) VALUES ('ai_verify_enabled', $1) ON CONFLICT (key) DO UPDATE SET value = $1"
        await DBManager.execute_pg_query(query, (json.dumps(enable_status),))
        await CACHE_BOT_SETTINGS.delete(bot_username)
        status_text = "enabled" if enable_status else "disabled"
        await message.edit_text(f"AI Verification has been {status_text}.", reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Back", callback_data=f"setting_paid_{bot_username}")]]))

    async def toggle_paid_feature(self, message, bot_username, enable_status):
        """Paid feature ko enable ya disable karta hai."""
        settings_table = DBManager._get_safe_tablename(bot_username, 'settings')
        query = f"INSERT INTO {settings_table} (key, value) VALUES ('paid_enabled', $1) ON CONFLICT (key) DO UPDATE SET value = $1"
        await DBManager.execute_pg_query(query, (json.dumps(enable_status),))
        await CACHE_BOT_SETTINGS.delete(bot_username)
        status_text = "disabled" if not enable_status else "enabled"
        await message.edit_text(f"Paid feature has been {status_text}.", reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Back", callback_data=f"setting_paid_{bot_username}")]]))

    async def handle_conv_paid_free_limit(self, state):
        """Admin input ko validate karke daily free limit save karta hai."""
        key = f"{self.bot_username}_{self.user_id}"
        await CACHE_CONVERSATION.delete(key)

        input_text = self.update.message.text.strip() if self.update.message and self.update.message.text else ""
        if not input_text.isdigit():
            await self.bot.send_message(self.chat_id, "❌ Invalid input. Please enter a valid number between 0 and 100.")
            return

        limit = int(input_text)
        if limit < 0 or limit > 100:
            await self.bot.send_message(self.chat_id, "❌ Limit must be between 0 and 100.")
            return

        bot_username = state.get('bot_username', self.bot_username)
        settings_table = DBManager._get_safe_tablename(bot_username, 'settings')
        
        # PostgreSQL me save karein
        query = f"INSERT INTO {settings_table} (key, value) VALUES ('free_limit', $1) ON CONFLICT (key) DO UPDATE SET value = $1"
        await DBManager.execute_pg_query(query, (json.dumps(limit),))

        # RAM Cache refresh karein
        if await CACHE_BOT_SETTINGS.contains(bot_username):
            await CACHE_BOT_SETTINGS.delete(bot_username)

        status_text = "disabled (0)" if limit == 0 else f"set to {limit} free links/day"

        # Requested English information message
        notice_msg = (
            f"✅ <b>Daily Free Limit has been {status_text} for @{bot_username}!</b>\n\n"
            f"📢 <b>Important Notice:</b>\n"
            f"• For new users who haven't used any free limits today, this change is effective immediately.\n"
            f"• For users who have already consumed today's limits, the updated limits will take effect at <b>5:00 AM IST (11:30 PM UTC)</b> during the next daily reset cycle when the cache automatically clears."
        )
        keyboard = [[InlineKeyboardButton("⬅️ Back to Paid Settings", callback_data=f"setting_paid_{bot_username}")]]
        await self.bot.send_message(self.chat_id, notice_msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    
    async def handle_conv_paid_setup(self, state):
        """Paid settings (UPI, prices) set karne ke conversation ko handle karta hai."""
        bot_username = state.get('bot_username')
        current_step = state.get('step', 1)
        user_input = self.update.message.text.strip()
        key = f"{self.bot_username}_{self.user_id}"

        if current_step == 1: # UPI ID lena
            state['upi_id'] = user_input
            state['step'] = 2
            await CACHE_CONVERSATION.set(key, state)
            await self.bot.send_message(self.chat_id, "Great. Now, send the price for the 7-day plan (e.g., 10).")
        
        elif current_step == 2: # 7-day price lena
            if not user_input.isdigit() or int(user_input) <= 0:
                await self.bot.send_message(self.chat_id, "Invalid price. Please send a positive number.")
                return
            state['price_7'] = int(user_input)
            state['step'] = 3
            await CACHE_CONVERSATION.set(key, state)
            await self.bot.send_message(self.chat_id, "Got it. Now, send the price for the 28-day plan.")

        elif current_step == 3: # 28-day price lena
            if not user_input.isdigit() or int(user_input) <= 0:
                await self.bot.send_message(self.chat_id, "Invalid price. Please send a positive number.")
                return
            state['price_28'] = int(user_input)
            state['step'] = 4
            await CACHE_CONVERSATION.set(key, state)
            await self.bot.send_message(self.chat_id, "Almost done. Now, send the price for the 3-month (90 days) plan.")
        
        elif current_step == 4: # 90-day price lena
            if not user_input.isdigit() or int(user_input) <= 0:
                await self.bot.send_message(self.chat_id, "Invalid price. Please send a positive number.")
                return
            state['price_90'] = int(user_input)
            
            # Sab data save karna
            paid_settings = {
                'upi_id': state['upi_id'],
                'price_7': state['price_7'],
                'price_28': state['price_28'],
                'price_90': state['price_90']
            }
            settings_table = DBManager._get_safe_tablename(bot_username, 'settings')
            
            # DB mein save karo
            await DBManager.setup_bot_payment_tables(bot_username) # Bot ke tables banao
            paid_settings_query = f"INSERT INTO {settings_table} (key, value) VALUES ('paid_settings', $1) ON CONFLICT (key) DO UPDATE SET value = $1"
            await DBManager.execute_pg_query(paid_settings_query, (json.dumps(paid_settings),))
            
            # Feature enable karo
            enable_query = f"INSERT INTO {settings_table} (key, value) VALUES ('paid_enabled', $1) ON CONFLICT (key) DO UPDATE SET value = $1"
            await DBManager.execute_pg_query(enable_query, (json.dumps(True),))

            # Cache clear karo
            # Cache clear karo
            await CACHE_BOT_SETTINGS.delete(bot_username)
            await CACHE_CONVERSATION.delete(key)
            await self.bot.send_message(self.chat_id, f"✅ All paid settings for @{bot_username} have been saved and the feature is now enabled!")

    async def handle_conv_add_custom_plan(self, state):
        """Admin dwara bheje gaye duration ko parse karta hai."""
        text = self.update.message.text.strip() if self.update.message.text else ""
        seconds, label = self._parse_duration_string(text)
        key = f"{self.bot_username}_{self.user_id}"
        
        if not seconds:
            await self.bot.send_message(
                self.chat_id, 
                "❌ Invalid format. Kripya is tarah likhein: `1 hr`, `5 day`, `8 month`, `1 yr`. Dobara try karne ke liye setting me jayein."
            )
            await CACHE_CONVERSATION.delete(key)
            return

        state['cplan_seconds'] = seconds
        state['cplan_label'] = label
        state['step'] = 2
        state['command'] = 'custom_plan_price'
        await CACHE_CONVERSATION.set(key, state)
        await self.bot.send_message(
            self.chat_id, 
            f"✅ Duration set: <b>{label}</b>\n\nAb is plan ka <b>Price (₹)</b> enter karein (e.g., 49 ya 99):",
            parse_mode=ParseMode.HTML
        )

    async def handle_conv_custom_plan_price(self, state):
        """Admin se price lekar custom plan ko settings me save karta hai."""
        key = f"{self.bot_username}_{self.user_id}"
        await CACHE_CONVERSATION.delete(key)
        
        price_text = self.update.message.text.strip() if self.update.message.text else ""
        try:
            price = float(price_text)
            if price <= 0: raise ValueError()
        except ValueError:
            await self.bot.send_message(self.chat_id, "❌ Invalid price. Positive number hona chahiye. Operation canceled.")
            return

        bot_username = state.get('bot_username', self.bot_username)
        seconds = state.get('cplan_seconds')
        label = state.get('cplan_label')

        settings = await self.get_bot_settings(bot_username)
        paid_info = settings.get('paid_settings', {})
        custom_plans = paid_info.get('custom_plans', [])
        
        if len(custom_plans) >= 3:
            await self.bot.send_message(self.chat_id, "⚠️ Aap maximum 3 custom plans hi add kar sakte hain. Pehle koi purana delete karein.")
            return

        custom_plans.append({
            'label': label,
            'seconds': seconds,
            'price': price
        })
        paid_info['custom_plans'] = custom_plans

        settings_table = DBManager._get_safe_tablename(bot_username, 'settings')
        query = f"INSERT INTO {settings_table} (key, value) VALUES ('paid_settings', $1) ON CONFLICT (key) DO UPDATE SET value = $1"
        await DBManager.execute_pg_query(query, (json.dumps(paid_info),))

        # Refresh cache
        await CACHE_BOT_SETTINGS.delete(bot_username)

        await self.bot.send_message(
            self.chat_id, 
            f"🎉 <b>Custom Plan Successfully Added!</b>\n\n• <b>Plan:</b> {label}\n• <b>Price:</b> ₹{price:.2f}\n\nAb users ko subscription buy karte waqt yeh option dikhega.",
            parse_mode=ParseMode.HTML
        )

    async def handle_conv_earnings_custom_date(self, state):
        """Custom date range parse karke earnings metrics calculate karta hai."""
        key = f"{self.bot_username}_{self.user_id}"
        await CACHE_CONVERSATION.delete(key)

        text = self.update.message.text.strip() if self.update.message.text else ""
        match = re.match(r'^(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})$', text)
        if not match:
            await self.bot.send_message(self.chat_id, "❌ Invalid Date format. Format <code>YYYY-MM-DD to YYYY-MM-DD</code> hona chahiye.", parse_mode=ParseMode.HTML)
            return

        start_date = match.group(1)
        end_date = match.group(2)
        
        try:
            d1 = datetime.strptime(start_date, '%Y-%m-%d')
            d2 = datetime.strptime(end_date, '%Y-%m-%d')
            if d1 > d2:
                await self.bot.send_message(self.chat_id, "❌ Start date end date se badi nahi ho sakti.")
                return
        except ValueError:
            await self.bot.send_message(self.chat_id, "❌ Invalid calendar date! Kripya sahi date enter karein.")
            return

        bot_username = state.get('bot_username', self.bot_username)
        safe_bot = DBManager._get_safe_tablename(bot_username, '')
        success_table = f"{safe_bot}successful_transactions"
        failed_table = f"{safe_bot}failed_transactions"

        query = f"""
        SELECT 
            COALESCE(SUM(CASE WHEN currency = 'XTR' THEN amount * 1.2 ELSE amount END), 0) as range_rev,
            COALESCE(SUM(CASE WHEN currency = 'XTR' THEN amount ELSE 0 END), 0) as total_stars,
            COUNT(*) as range_orders,
            COALESCE(SUM(CASE WHEN target_payload != '' THEN (CASE WHEN currency = 'XTR' THEN amount * 1.2 ELSE amount END) ELSE 0 END), 0) as paid_msg_rev,
            COUNT(CASE WHEN target_payload != '' THEN 1 END) as paid_msg_orders,
            COALESCE(SUM(CASE WHEN target_payload = '' OR target_payload IS NULL THEN (CASE WHEN currency = 'XTR' THEN amount * 1.2 ELSE amount END) ELSE 0 END), 0) as sub_rev,
            COUNT(CASE WHEN target_payload = '' OR target_payload IS NULL THEN 1 END) as sub_orders
        FROM {success_table}
        WHERE completion_time >= $1::timestamptz AND completion_time <= ($2::date + INTERVAL '1 day');
        """
        data = await DBManager.execute_pg_query(query, (start_date, end_date), fetch='one')
        fail_q = f"SELECT COUNT(*) as count FROM {failed_table} WHERE failure_time >= $1::timestamptz AND failure_time <= ($2::date + INTERVAL '1 day');"
        fail_data = await DBManager.execute_pg_query(fail_q, (start_date, end_date), fetch='one')
        failed_count = fail_data['count'] if fail_data else 0

        tot_rev = float(data['range_rev'])
        tot_stars = int(data['total_stars'])
        tot_orders = int(data['range_orders'])
        paid_msg_rev = float(data['paid_msg_rev'])
        paid_msg_orders = int(data['paid_msg_orders'])
        sub_rev = float(data['sub_rev'])
        sub_orders = int(data['sub_orders'])

        total_attempts = tot_orders + failed_count
        paid_rate = (tot_orders / total_attempts * 100) if total_attempts > 0 else 0.0
        fail_rate = (failed_count / total_attempts * 100) if total_attempts > 0 else 0.0

        resp = (
            f"🗓️ <b>Custom Date Earnings Report ({start_date} to {end_date})</b>\n\n"
            f"💵 <b>Total Revenue:</b> ₹{tot_rev:,.2f}\n"
            f"⭐ <b>Total Stars Earned:</b> {tot_stars} ⭐\n"
            f"📦 <b>Successful Orders:</b> {tot_orders}\n"
            f"❌ <b>Failed Orders:</b> {failed_count}\n"
            f"📈 <b>Order Conversion:</b> {paid_rate:.1f}% Success | {fail_rate:.1f}% Failed\n\n"            
            f"<b>Product Breakdown:</b>\n"
            f"  • Subscriptions: ₹{sub_rev:,.2f} ({sub_orders} sales)\n"
            f"  • Paid Messages: ₹{paid_msg_rev:,.2f} ({paid_msg_orders} sales)"
        )        
        keyboard = [[InlineKeyboardButton("⬅️ Back to Earnings Overview", callback_data=f"earnings_{bot_username}_overview")]]
        await self.bot.send_message(self.chat_id, resp, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    
    async def handle_conv_paid_cf_setup(self, state):
        bot_username = state.get('bot_username')
        current_step = state.get('step', 1)
        user_input = self.update.message.text.strip()
        key = f"{self.bot_username}_{self.user_id}"

        if current_step == 1: # App ID
            state['cf_app_id'] = user_input
            state['step'] = 2
            await CACHE_CONVERSATION.set(key, state)
            await self.bot.send_message(self.chat_id, "Ab apna Cashfree Secret Key bhejein.")
        
        elif current_step == 2: # Secret Key
            settings = await self.get_bot_settings(bot_username)
            paid_info = settings.get('paid_settings', {})
            paid_info['cf_app_id'] = state['cf_app_id']
            paid_info['cf_secret'] = user_input
            
            settings_table = DBManager._get_safe_tablename(bot_username, 'settings')
            query = f"INSERT INTO {settings_table} (key, value) VALUES ('paid_settings', $1) ON CONFLICT (key) DO UPDATE SET value = $1"
            await DBManager.execute_pg_query(query, (json.dumps(paid_info),))
            await CACHE_BOT_SETTINGS.delete(bot_username)
            await CACHE_CONVERSATION.delete(key)
            await self.bot.send_message(self.chat_id, f"✅ Cashfree API credentials successfully saved for @{bot_username}!")

    async def handle_conv_paid_stars_setup(self, state):
        """Admin se Telegram Stars ke teeno plans ki pricing mandatory input leta hai."""
        bot_username = state.get('bot_username')
        current_step = state.get('step', 1)
        user_input = self.update.message.text.strip() if self.update.message and self.update.message.text else ""
        key = f"{self.bot_username}_{self.user_id}"

        if not user_input.isdigit() or int(user_input) <= 0:
            await self.bot.send_message(self.chat_id, "❌ Invalid Stars count. Kripya ek positive number send karein (e.g. 50).")
            return

        stars_val = int(user_input)

        if current_step == 1:
            state['stars_price_7'] = stars_val
            state['step'] = 2
            await CACHE_CONVERSATION.set(key, state)
            await self.bot.send_message(self.chat_id, f"✅ 7-Day Plan: {stars_val} ⭐\n\nAb <b>28-Day Plan</b> ke liye Telegram Stars ka price send karein (e.g. 150):", parse_mode=ParseMode.HTML)

        elif current_step == 2:
            state['stars_price_28'] = stars_val
            state['step'] = 3
            await CACHE_CONVERSATION.set(key, state)
            await self.bot.send_message(self.chat_id, f"✅ 28-Day Plan: {stars_val} ⭐\n\nAb <b>3 Months (90-Day Plan)</b> ke liye Telegram Stars ka price send karein (e.g. 400):", parse_mode=ParseMode.HTML)

        elif current_step == 3:
            state['stars_price_90'] = stars_val
            
            settings = await self.get_bot_settings(bot_username)
            paid_info = settings.get('paid_settings', {})
            paid_info['stars_price_7'] = state['stars_price_7']
            paid_info['stars_price_28'] = state['stars_price_28']
            paid_info['stars_price_90'] = state['stars_price_90']
            paid_info['stars_enabled'] = True  # Mandatory teeno set hote hi automatically enable
            
            settings_table = DBManager._get_safe_tablename(bot_username, 'settings')
            query = f"INSERT INTO {settings_table} (key, value) VALUES ('paid_settings', $1) ON CONFLICT (key) DO UPDATE SET value = $1"
            await DBManager.execute_pg_query(query, (json.dumps(paid_info),))

            # Main paid_enabled ko bhi true kar do
            enable_query = f"INSERT INTO {settings_table} (key, value) VALUES ('paid_enabled', $1) ON CONFLICT (key) DO UPDATE SET value = $1"
            await DBManager.execute_pg_query(enable_query, (json.dumps(True),))

            await CACHE_BOT_SETTINGS.delete(bot_username)
            await CACHE_CONVERSATION.delete(key)
            
            success_text = (
                f"🎉 <b>Telegram Stars Pricing Successfully Configured!</b>\n\n"
                f"• 7 Days: {state['stars_price_7']} ⭐\n"
                f"• 28 Days: {state['stars_price_28']} ⭐\n"
                f"• 3 Months: {state['stars_price_90']} ⭐\n\n"
                f"✅ Telegram Stars payment option ab aapke bot me <b>ENABLED</b> ho gaya hai!"
            )
            await self.bot.send_message(self.chat_id, success_text, parse_mode=ParseMode.HTML)
    
    async def handle_conv_admin_bill_amount(self, state):
        key = f"{self.bot_username}_{self.user_id}"
        await CACHE_CONVERSATION.delete(key)
        text = self.update.message.text.strip() if self.update.message and self.update.message.text else ""
        try:
            amt = float(text)
            if amt < 100:
                raise ValueError("Below 100")
        except Exception:
            await self.bot.send_message(self.chat_id, "❌ Minimum payment amount is ₹100. Please start again with /start pay.")
            return

        payment_res = await DBManager.execute_pg_query(
            "INSERT INTO admin_bill_payments (creator_id, amount, status) VALUES ($1, $2, 'pending') RETURNING id",
            (self.user_id, amt),
            fetch='one'
        )
        payment_id = payment_res['id']

        upi_id = "echelonbot@ptaxis"
        qr_bytes = self._generate_upi_qr(upi_id, amt, name="Echelon Service Charge")
        caption = (
            f"💰 <b>Payment QR Code Generated</b>\n\n"
            f"• <b>Amount to Pay:</b> ₹{amt:.2f}\n"
            f"• <b>UPI ID:</b> <code>{upi_id}</code>\n\n"
            f"1. Scan the QR code using any UPI app (GPay, PhonePe, Paytm, etc.) to complete your payment.\n"
            f"2. After payment, click the <b>Upload Screenshot</b> button below and upload your payment proof."
        )        
        keyboard = [[InlineKeyboardButton("📤 Upload Screenshot", callback_data=f"admin_bill_ss_{payment_id}")]]
        await self.bot.send_photo(self.chat_id, photo=qr_bytes, caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

    async def handle_conv_admin_bill_ss_upload(self, state):
        key = f"{self.bot_username}_{self.user_id}"
        await CACHE_CONVERSATION.delete(key)
        payment_id = state.get('payment_id')

        if not self.update.message.photo:
            await self.bot.send_message(self.chat_id, "❌ That was not an image. Please restart the payment via /start pay.")
            return

        super_admin_id = 6796088344
        pay_rec = await DBManager.execute_pg_query("SELECT * FROM admin_bill_payments WHERE id = $1", (payment_id,), fetch='one')
        if not pay_rec:
            await self.bot.send_message(self.chat_id, "❌ Payment record not found.")
            return

        amt = float(pay_rec['amount'])
        creator_id = pay_rec['creator_id']

        sup_caption = (
            f"🧾 <b>New Admin Service Charge Bill Payment</b>\n\n"
            f"• <b>Creator ID:</b> <code>{creator_id}</code>\n"
            f"• <b>Amount:</b> ₹{amt:.2f}\n"
            f"• <b>Payment ID:</b> <code>{payment_id}</code>\n\n"
            f"<i>Please verify the payment in your bank/UPI app and choose an action below.</i>"
        )        
        sup_keyboard = [
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"sup_approve_bill_{payment_id}"),
                InlineKeyboardButton("❌ Deny", callback_data=f"sup_deny_bill_{payment_id}")
            ]
        ]
        try:
            await self.bot.copy_message(
                chat_id=super_admin_id,
                from_chat_id=self.chat_id,
                message_id=self.update.message.message_id,
                caption=sup_caption,
                reply_markup=InlineKeyboardMarkup(sup_keyboard),
                parse_mode=ParseMode.HTML
            )
            await self.bot.send_message(self.chat_id, "✅ <b>Screenshot Uploaded!</b>\n\nYour payment screenshot has been sent to Super Admin for verification. Once approved, your bill will be updated and purchases restored.", parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"Failed to send bill screenshot to super admin: {e}")
            await self.bot.send_message(self.chat_id, f"❌ Error sending screenshot to super admin: {e}")    
    async def handle_conv_paid_ai_setup(self, state):
        bot_username = state.get('bot_username')
        current_step = state.get('step', 1)
        user_input = self.update.message.text.strip()
        key = f"{self.bot_username}_{self.user_id}"

        if current_step == 1:
            state['api_key'] = user_input
            state['step'] = 2
            await CACHE_CONVERSATION.set(key, state)
            await self.bot.send_message(self.chat_id, "Gemini API Key saved. Now send the Exact Receiver Name (What user sees on their screen while paying).")
        
        elif current_step == 2:
            settings_table = DBManager._get_safe_tablename(bot_username, 'settings')
            
            api_query = f"INSERT INTO {settings_table} (key, value) VALUES ('ai_verify_api_key', $1) ON CONFLICT (key) DO UPDATE SET value = $1"
            name_query = f"INSERT INTO {settings_table} (key, value) VALUES ('ai_verify_receiver_name', $1) ON CONFLICT (key) DO UPDATE SET value = $1"
            enable_query = f"INSERT INTO {settings_table} (key, value) VALUES ('ai_verify_enabled', $1) ON CONFLICT (key) DO UPDATE SET value = $1"

            await DBManager.execute_pg_query(api_query, (json.dumps(state['api_key']),))
            await DBManager.execute_pg_query(name_query, (json.dumps(user_input),))
            await DBManager.execute_pg_query(enable_query, (json.dumps(True),))

            await CACHE_BOT_SETTINGS.delete(bot_username)
            await CACHE_CONVERSATION.delete(key)
            await self.bot.send_message(self.chat_id, f"✅ AI Verification has been configured and Enabled for @{bot_username}!")
    
    async def handle_conv_paid_msg_create(self, state):
        """Admin dwara bheje gaye paid message content ko capture karta hai."""
        bot_username = state.get('bot_username', self.bot_username)
        message = self.update.message
        
        file_id = None
        file_type = None
        caption = message.caption or message.text or ""

        if message.text:
            file_type = 'text'
            caption = message.text
        elif message.document:
            file_id = message.document.file_id
            file_type = 'document'
        elif message.video:
            file_id = message.video.file_id
            file_type = 'video'
        elif message.photo:
            file_id = message.photo[-1].file_id
            file_type = 'photo'
        elif message.audio:
            file_id = message.audio.file_id
            file_type = 'audio'
        elif message.voice:
            file_id = message.voice.file_id
            file_type = 'voice'
        elif message.animation:
            file_id = message.animation.file_id
            file_type = 'animation'

        if not file_type:
            await self.bot.send_message(self.chat_id, "Unsupported message format. Operation canceled.")
            key = f"{self.bot_username}_{self.user_id}"
            await CACHE_CONVERSATION.delete(key)
            return

        state['msg_file_id'] = file_id
        state['msg_file_type'] = file_type
        state['msg_caption'] = caption

        settings = await self.get_bot_settings(bot_username)
        paid_info = settings.get('paid_settings', {})
        upi_id = paid_info.get('upi_id')
        cf_enabled = paid_info.get('cf_enabled', False)
        upi_enabled = paid_info.get('upi_enabled', True)
        stars_enabled = paid_info.get('stars_enabled', False)

        has_fiat = bool((upi_id or cf_enabled) and upi_enabled)

        if not has_fiat and not stars_enabled:
            await self.bot.send_message(self.chat_id, "❌ Aapne na toh UPI/Cashfree set kiya hai aur na hi Telegram Stars. Pehle setting se payment method configure karein.")
            key = f"{self.bot_username}_{self.user_id}"
            await CACHE_CONVERSATION.delete(key)
            return

        state['has_fiat'] = has_fiat
        state['has_stars'] = stars_enabled
        key = f"{self.bot_username}_{self.user_id}"

        if has_fiat:
            state['command'] = 'paid_msg_price'
            await CACHE_CONVERSATION.set(key, state)
            await self.bot.send_message(self.chat_id, "Message received! Ab is Paid Message ka **INR Price (₹)** enter karein (e.g., 20 ya 50):", parse_mode=ParseMode.MARKDOWN)
        else:
            state['price'] = 0.0
            state['command'] = 'paid_msg_stars_price'
            await CACHE_CONVERSATION.set(key, state)
            await self.bot.send_message(self.chat_id, "Message received! Ab is Paid Message ka **Telegram Stars Price (⭐)** enter karein (e.g., 10 ya 50):", parse_mode=ParseMode.MARKDOWN)
    async def handle_conv_paid_msg_price(self, state):
        """Admin se INR price leta hai aur agar Stars bhi enabled hai toh Stars price maangta hai."""
        key = f"{self.bot_username}_{self.user_id}"
        
        price_text = self.update.message.text.strip() if self.update.message.text else ""
        try:
            price = float(price_text)
            if price <= 0: raise ValueError()
        except ValueError:
            await self.bot.send_message(self.chat_id, "❌ Invalid price. Positive number bhejein. Operation canceled.")
            await CACHE_CONVERSATION.delete(key)
            return

        state['price'] = price

        # Agar Telegram Stars bhi enabled hai toh uska price poocho
        if state.get('has_stars'):
            state['command'] = 'paid_msg_stars_price'
            await CACHE_CONVERSATION.set(key, state)
            await self.bot.send_message(self.chat_id, f"✅ INR Price set: ₹{price:.2f}\n\nAb is Paid Message ke liye **Telegram Stars Price (⭐)** enter karein (e.g., 20 ya 50):", parse_mode=ParseMode.MARKDOWN)
            return

        # Agar sirf INR enabled hai toh direct save karo
        state['stars_price'] = 0
        await self._finalize_paid_message_creation(state)

    async def handle_conv_paid_msg_stars_price(self, state):
        """Admin se Telegram Stars price leta hai aur paid message save karta hai."""
        key = f"{self.bot_username}_{self.user_id}"
        
        stars_text = self.update.message.text.strip() if self.update.message.text else ""
        if not stars_text.isdigit() or int(stars_text) <= 0:
            await self.bot.send_message(self.chat_id, "❌ Invalid Stars count. Positive number bhejein. Operation canceled.")
            await CACHE_CONVERSATION.delete(key)
            return

        state['stars_price'] = int(stars_text)
        if 'price' not in state:
            state['price'] = 0.0

        await self._finalize_paid_message_creation(state)

    async def _finalize_paid_message_creation(self, state):
        """Database me paid message save karke final access link generate karta hai."""
        key = f"{self.bot_username}_{self.user_id}"
        await CACHE_CONVERSATION.delete(key)

        bot_username = state.get('bot_username', self.bot_username)
        file_id = state.get('msg_file_id')
        file_type = state.get('msg_file_type')
        caption = state.get('msg_caption')
        price = float(state.get('price', 0.0))
        stars_price = int(state.get('stars_price', 0))

        payload = generate_random_string(15)

        paid_table = DBManager._get_safe_tablename(bot_username, 'paid_messages')
        access_table = DBManager._get_safe_tablename(bot_username, 'paid_msg_access')
        
        insert_query = f"""
        INSERT INTO {paid_table} (payload, file_id, file_type, caption, price, stars_price)
        VALUES ($1, $2, $3, $4, $5, $6)
        """
        
        try:
            await DBManager.execute_pg_query(insert_query, (payload, file_id, file_type, caption, price, stars_price))
        except Exception as e:
            if "does not exist" in str(e).lower() or "undefinedtableerror" in str(e).lower() or "column" in str(e).lower():
                await DBManager.execute_pg_query(f"""
                CREATE TABLE IF NOT EXISTS {paid_table} (
                    payload VARCHAR(15) PRIMARY KEY,
                    file_id TEXT,
                    file_type TEXT NOT NULL,
                    caption TEXT,
                    price NUMERIC(10, 2) NOT NULL DEFAULT 0,
                    stars_price INTEGER DEFAULT 0,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );""")
                await DBManager.execute_pg_query(f"ALTER TABLE {paid_table} ADD COLUMN IF NOT EXISTS stars_price INTEGER DEFAULT 0;")
                await DBManager.execute_pg_query(f"""
                CREATE TABLE IF NOT EXISTS {access_table} (
                    payload VARCHAR(15) NOT NULL,
                    user_id BIGINT NOT NULL,
                    granted_at TIMESTAMPTZ DEFAULT NOW(),
                    PRIMARY KEY (payload, user_id)
                );""")
                await DBManager.execute_pg_query(insert_query, (payload, file_id, file_type, caption, price, stars_price))
            else:
                logger.error(f"Error saving paid message for @{bot_username}: {e}")
                raise e

        link = f"https://t.me/{bot_username}?start={payload}"
        
        price_summary = []
        if price > 0: price_summary.append(f"₹{price:.2f}")
        if stars_price > 0: price_summary.append(f"{stars_price} ⭐")
        price_display = " or ".join(price_summary) if price_summary else "Free"

        text = (
            f"✅ **Paid Message Successfully Created!**\n\n"
            f"💰 **Price:** {price_display}\n"
            f"🔗 **Access Link:**\n`{link}`\n\n"
            f"Jab bhi koi user is link pe click karega ushe payment ke bina access nahi milega."
        )
        await self.bot.send_message(self.chat_id, text, parse_mode=ParseMode.MARKDOWN)
    async def handle_conv_paid_msg_delete(self, state):
        """Paid message ko link ya payload se delete karta hai."""
        key = f"{self.bot_username}_{self.user_id}"
        await CACHE_CONVERSATION.delete(key)
        
        input_text = self.update.message.text.strip() if self.update.message.text else ""
        payload = None
        
        if "start=" in input_text:
            match = re.search(r"start=([a-zA-Z0-9]{15})", input_text)
            if match:
                payload = match.group(1)
        elif len(input_text) == 15 and input_text.isalnum():
            payload = input_text

        if not payload:
            await self.bot.send_message(self.chat_id, "Invalid link ya payload format. 15-character payload hona chahiye. Operation canceled.")
            return

        bot_username = state.get('bot_username', self.bot_username)
        paid_table = DBManager._get_safe_tablename(bot_username, 'paid_messages')
        access_table = DBManager._get_safe_tablename(bot_username, 'paid_msg_access')

        deleted = await DBManager.execute_pg_query(f"DELETE FROM {paid_table} WHERE payload=$1 RETURNING payload", (payload,), fetch='one')
        if deleted:
            await DBManager.execute_pg_query(f"DELETE FROM {access_table} WHERE payload=$1", (payload,))
            await self.bot.send_message(self.chat_id, f"✅ Paid message with payload `{payload}` safaltapoorvak delete kar diya gaya hai.", parse_mode=ParseMode.MARKDOWN)
        else:
            await self.bot.send_message(self.chat_id, f"❌ Payload `{payload}` nahi mila ya pehle se deleted hai.", parse_mode=ParseMode.MARKDOWN)

    async def send_paid_message_to_user(self, payload: str):
        """User ko uska paid message securely send karta hai."""
        paid_table = DBManager._get_safe_tablename(self.bot_username, 'paid_messages')
        data = await DBManager.execute_pg_query(f"SELECT * FROM {paid_table} WHERE payload=$1", (payload,), fetch='one')
        if not data:
            await self.bot.send_message(self.chat_id, "Sorry, yeh paid message ab uplabdh nahi hai.")
            return None

        file_id = data['file_id']
        file_type = data['file_type']
        caption = data['caption']

        settings = await self.get_bot_settings()
        is_protected = settings.get('protected', True)

        sent_msg = None
        if file_type == 'text':
            sent_msg = await self.bot.send_message(self.chat_id, caption, protect_content=is_protected)
        elif file_id:
            send_methods = {
                'photo': self.bot.send_photo, 'video': self.bot.send_video,
                'document': self.bot.send_document, 'audio': self.bot.send_audio,
                'voice': self.bot.send_voice, 'animation': self.bot.send_animation
            }
            if file_type in send_methods:
                sent_msg = await send_methods[file_type](
                    self.chat_id, file_id, caption=caption, protect_content=is_protected
                )

        if sent_msg and settings.get('deletion', False):
            deletion_time = settings.get('deletion_time', 7200)
            asyncio.create_task(self.schedule_deletion(sent_msg.message_id, deletion_time))
            
        # [NEW] Record View (File Delivered) tracking directly to fast RAM/Valkey
        if sent_msg:
            asyncio.create_task(record_bot_activity(self.bot_username, self.user_id, "view"))
            
        return sent_msg
        
    async def show_payment_plans(self, message, payload):
        """User ko payment plans dikhata hai with INR & Stars pricing."""
        settings = await self.get_bot_settings()
        if not settings.get('paid_enabled'):
            await message.edit_text("Sorry, the 'Remove Ad' feature is currently disabled.")
            return

        paid_info = settings.get('paid_settings', {})
        stars_enabled = paid_info.get('stars_enabled', False)
        text = "Choose a premium plan to remove ads:"
        keyboard = []
        prices = {
            7: paid_info.get('price_7'),
            28: paid_info.get('price_28'),
            90: paid_info.get('price_90')
        }
        stars_prices = {
            7: paid_info.get('stars_price_7'),
            28: paid_info.get('stars_price_28'),
            90: paid_info.get('stars_price_90')
        }
        
        for days, price in prices.items():
            s_price = stars_prices.get(days) if stars_enabled else None
            plan_name = {7: "7 Days", 28: "28 Days", 90: "3 Months"}.get(days)
            
            btn_text = ""
            if price and price > 0 and s_price and s_price > 0:
                btn_text = f"{plan_name} - ₹{price} or {s_price} ⭐"
            elif price and price > 0:
                btn_text = f"{plan_name} - ₹{price}"
            elif s_price and s_price > 0:
                btn_text = f"{plan_name} - {s_price} ⭐"

            if btn_text:
                keyboard.append([InlineKeyboardButton(
                    btn_text, 
                    callback_data=f"select_plan_{days}_{payload}"
                )])
        
        # Custom Plans
        custom_plans = paid_info.get('custom_plans', [])
        for idx, cplan in enumerate(custom_plans):
            c_price = cplan.get('price')
            c_label = cplan.get('label')
            if c_price and c_price > 0:
                keyboard.append([InlineKeyboardButton(
                    f"{c_label} - ₹{c_price}", 
                    callback_data=f"select_cplan_{idx}_{payload}"
                )])

        if not keyboard:
            await message.edit_text("Sorry, no premium plans are available right now.")
            return            
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    async def handle_plan_selection(self, message, days, payload):
        """User ke plan selection ko handle karta hai aur payment method choose karwata hai."""
        settings = await self.get_bot_settings()
        admin_id = settings.get('creator_id')
        if await is_creator_purchases_locked(admin_id):
            await message.edit_text("⚠️ New subscriptions are temporarily suspended on this bot. Please contact admin or try again later.")
            return

        paid_info = settings.get('paid_settings', {})        
        price = paid_info.get(f'price_{days}')
        stars_price = paid_info.get(f'stars_price_{days}')
        upi_id = paid_info.get('upi_id')
        cf_enabled = paid_info.get('cf_enabled', False)
        upi_enabled = paid_info.get('upi_enabled', True)
        stars_enabled = paid_info.get('stars_enabled', False)

        has_fiat = bool(price and price > 0 and (upi_id or cf_enabled))
        has_stars = bool(stars_enabled and stars_price and stars_price > 0)

        if not has_fiat and not has_stars:
            await message.edit_text("Sorry, this plan is not properly configured. Please contact admin.")
            return

        transaction_id = await DBManager.get_next_transaction_id()
        query = """
        INSERT INTO active_upi_transactions 
        (transaction_id, bot_username, admin_id, user_id, amount, plan_duration_days, transaction_start_time, upi_id)
        VALUES ($1, $2, $3, $4, $5, $6, NOW(), $7)
        """
        await DBManager.execute_pg_query(query, (
            transaction_id, self.bot_username, admin_id, self.user_id, float(price or stars_price), days, upi_id or ""
        ))

        # Agar dono options available hain toh choose karne ka option do
        if has_fiat and has_stars:
            method_text = (
                f"💳 <b>Choose Payment Method</b>\n\n"
                f"<b>Plan:</b> {days} Days Premium\n\n"
                f"Aap UPI ya Telegram Stars me se kisi se bhi payment kar sakte hain:"
            )
            method_keyboard = [
                [InlineKeyboardButton(f"💳 Pay with UPI / Online (₹{price})", callback_data=f"pay_method_fiat_{transaction_id}")],
                [InlineKeyboardButton(f"⭐ Pay with Telegram Stars ({stars_price} ⭐)", callback_data=f"pay_method_stars_{transaction_id}_{days}_{stars_price}")]
            ]
            await message.edit_text(method_text, reply_markup=InlineKeyboardMarkup(method_keyboard), parse_mode=ParseMode.HTML)
        elif has_stars:
            await self.send_stars_invoice(transaction_id, days, stars_price, message=message)
        else:
            if cf_enabled:
                await self.handle_switch_payment(message, transaction_id, "cf", new_message=True)
            else:
                await self.handle_switch_payment(message, transaction_id, "upi", new_message=True)

    async def send_stars_invoice(self, transaction_id: int, days: int, stars_amount: int, message=None):
        """Telegram Stars ka direct invoice create karke send karta hai."""
        if message:
            try:
                await message.delete()
            except Exception:
                pass

        prices = [telegram.LabeledPrice(label=f"{days} Days Premium", amount=stars_amount)]
        try:
            await self.bot.send_invoice(
                chat_id=self.chat_id,
                title=f"⭐ {days} Days Premium Membership",
                description=f"Get ad-free premium access to @{self.bot_username} files for {days} days.",
                payload=f"stars_txn_{transaction_id}",
                provider_token="",  # Telegram Stars ke liye token empty string hona mandatory hai
                currency="XTR",     # Telegram Stars official currency code
                prices=prices
            )
        except Exception as e:
            logger.error(f"Error sending Stars invoice: {e}")
            await self.bot.send_message(self.chat_id, "❌ Error creating Telegram Stars invoice. Please try paying with UPI.")
    
    async def handle_custom_plan_selection(self, message, plan_idx, payload):
        """User dwara custom plan select karne par transaction initiate karta hai."""
        settings = await self.get_bot_settings()
        admin_id = settings.get('creator_id')
        if await is_creator_purchases_locked(admin_id):
            await message.edit_text("⚠️ New subscriptions are temporarily suspended on this bot. Please contact admin or try again later.")
            return

        paid_info = settings.get('paid_settings', {})        
        custom_plans = paid_info.get('custom_plans', [])

        if plan_idx < 0 or plan_idx >= len(custom_plans):
            await message.edit_text("Selected custom plan is invalid or expired.")
            return

        cplan = custom_plans[plan_idx]
        price = cplan['price']
        duration_seconds = cplan['seconds']
        approx_days = max(1, duration_seconds // 86400)

        upi_id = paid_info.get('upi_id')
        cf_enabled = paid_info.get('cf_enabled', False)

        if not price or (not upi_id and not cf_enabled):
            await message.edit_text("Sorry, this plan is not properly configured. Please contact admin.")
            return

        try:
            await message.edit_text("Generating your payment request...", reply_markup=None)
        except Exception:
            pass

        transaction_id = await DBManager.get_next_transaction_id()
        query = """
        INSERT INTO active_upi_transactions 
        (transaction_id, bot_username, admin_id, user_id, amount, plan_duration_days, transaction_start_time, upi_id, plan_duration_seconds)
        VALUES ($1, $2, $3, $4, $5, $6, NOW(), $7, $8)
        """
        await DBManager.execute_pg_query(query, (
            transaction_id, self.bot_username, admin_id, self.user_id, float(price), approx_days, upi_id or "", duration_seconds
        ))

        if cf_enabled:
            await self.handle_switch_payment(message, transaction_id, "cf", new_message=True)
        else:
            await self.handle_switch_payment(message, transaction_id, "upi", new_message=True)
    
    async def handle_switch_payment(self, message, transaction_id, mode, new_message=False):
        tx_query = "SELECT * FROM active_upi_transactions WHERE transaction_id = $1"
        tx_data = await DBManager.execute_pg_query(tx_query, (transaction_id,), fetch='one')
        if not tx_data:
            if not new_message:
                await message.edit_text("This transaction has expired or completed.")
            return
            
        settings = await self.get_bot_settings(tx_data['bot_username'])
        paid_info = settings.get('paid_settings', {})
        
        price = tx_data['amount']
        upi_id = tx_data['upi_id']
        cf_enabled = paid_info.get('cf_enabled', False)
        upi_enabled = paid_info.get('upi_enabled', True)
        cf_app_id = paid_info.get('cf_app_id')
        cf_secret = paid_info.get('cf_secret')
        
        if mode == "cf":
            fake_phone = self._get_fake_phone(self.user_id)
            order_id, pay_link = await self._create_cashfree_order(transaction_id, price, fake_phone, cf_app_id, cf_secret)
            
            if pay_link:
                keyboard = [
                    [InlineKeyboardButton("Pay Now 💸", url=pay_link)],
                    [InlineKeyboardButton("I Have Paid ✅", callback_data=f"check_cf_pay_{transaction_id}")]
                ]
                if upi_enabled and upi_id:
                    keyboard.append([InlineKeyboardButton("⚠️ Facing Error? Switch to UPI QR", callback_data=f"switch_upi_{transaction_id}")])
                
                text = (
                    f"💰 **Instant Payment Link**\n\n"
                    f"Amount: ₹{price}\n\n"
                    f"Click 'Pay Now' to complete your payment automatically. "
                    f"If you are automatically redirected back here after payment, it will be verified instantly."
                )
                if new_message:
                    await self.bot.send_message(self.chat_id, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
                    try: await message.delete() 
                    except: pass
                else:
                    try: await message.delete() 
                    except: pass
                    await self.bot.send_message(self.chat_id, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
            else:
                if new_message:
                    await self.bot.send_message(self.chat_id, "Cashfree configuration error. Falling back to UPI...")
                await self.handle_switch_payment(message, transaction_id, "upi", new_message=True)

        elif mode == "upi":
            qr_image_bytes = self._generate_upi_qr(upi_id, float(price))
            caption = (
                f"Amount to Pay: `₹{price}`\n\n"
                f"1\\. Scan the QR code with any UPI app to pay\\.\n"
                f"2\\. After successful payment, click the 'Upload Screenshot' button below\\."
            )
            keyboard = [[InlineKeyboardButton("📤 Upload Screenshot", callback_data=f"paid_confirm_{transaction_id}")]]
            if cf_enabled and cf_app_id:
                keyboard.append([InlineKeyboardButton("⚠️ Switch to Cashfree Link", callback_data=f"switch_cf_{transaction_id}")])
                
            if new_message:
                await self.bot.send_photo(self.chat_id, photo=qr_image_bytes, caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN_V2)
                try: await message.delete() 
                except: pass
            else:
                try: await message.delete()
                except: pass
                await self.bot.send_photo(self.chat_id, photo=qr_image_bytes, caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN_V2)    
    async def handle_conv_payment_screenshot(self, state):
        """User dwara bheje gaye screenshot ko handle karta hai, with AI Verification and Scammer Filter."""
        key = f"{self.bot_username}_{self.user_id}"
        await CACHE_CONVERSATION.delete(key)
        
        if not self.update.message.photo:
            await self.bot.send_message(self.chat_id, "That doesn't look like a screenshot. Please send an image.")
            return

        transaction_id = state.get('transaction_id')
        
        tx_query = "SELECT * FROM active_upi_transactions WHERE transaction_id = $1"
        tx_data = await DBManager.execute_pg_query(tx_query, (transaction_id,), fetch='one')

        if not tx_data:
            await self.bot.send_message(self.chat_id, "This transaction is no longer valid.")
            return

        admin_id = tx_data['admin_id']
        bot_username_from_tx = tx_data['bot_username']
        settings = await self.get_bot_settings(bot_username_from_tx)
        
        ai_enabled = settings.get('ai_verify_enabled', False)
        ai_api_key = settings.get('ai_verify_api_key', '')
        ai_expected_name = settings.get('ai_verify_receiver_name', '')
        
        # --- UNIVERSAL SCAMMER CHECK ---
        is_scammer = False
        scammer_record = await DBManager.execute_pg_query(
            "SELECT 1 FROM scammer_users WHERE user_id = $1", 
            (self.user_id,), 
            fetch='one'
        )
        if scammer_record:
            is_scammer = True
            await self.bot.send_message(
                self.chat_id,
                "⚠️ According to your recent credibility your screenshot will verify manually by admin."
            )

        # Admin Keyboard (Manual Review)
        manual_keyboard = [
            [
                InlineKeyboardButton("✅ Confirm", callback_data=f"admin_confirm_payment_{transaction_id}"),
                InlineKeyboardButton("❌ Deny", callback_data=f"admin_deny_payment_{transaction_id}")
            ],
            [
                InlineKeyboardButton("⚠️ Fake SS", callback_data=f"admin_notify_fake_{transaction_id}"),
                InlineKeyboardButton("🔄 Old SS", callback_data=f"admin_notify_old_{transaction_id}"),
                InlineKeyboardButton("⏳ Not Received", callback_data=f"admin_notify_not_received_{transaction_id}")
            ]
        ]
        
        # AI verification tabhi chalegi agar user SCAMMER LIST me nahi hai
        if not is_scammer and ai_enabled and ai_api_key and ai_expected_name:
            wait_msg = await self.bot.send_message(self.chat_id, "🤖 AI is verifying your payment. Please wait a moment...")
            try:
                # 1. Download image
                photo_file = await self.bot.get_file(self.update.message.photo[-1].file_id)
                image_bytes = await photo_file.download_as_bytearray()
                b64_image = base64.b64encode(image_bytes).decode('utf-8')

                # 2. Prepare Current Time in IST
                ist = ZoneInfo('Asia/Kolkata')
                current_time_ist = datetime.now(ist).strftime('%Y-%m-%d %I:%M %p')

                # 3. Gemini Prompt
                sys_prompt = f"""
                You are a strict payment verification bot. Check this payment screenshot.
                Expected Receiver Name: '{ai_expected_name}'
                Expected Amount: {tx_data['amount']}
                Current Date & Time in IST: {current_time_ist}

                Rules:
                1. Check if receiver name exactly matches the expected name.
                2. Check if amount matches expected amount.
                3. Check payment status (must be successful).
                4. Check date/time. A payment is valid if it was made ANYTIME within the last 1 hour from the Current Date & Time provided above. Exact time match is not required, just within 1 hour if there is no time showing just deny.
                5. If everything looks genuine and correct, approve it. If not, deny it and provide a clear reason in Hindi (written in English script like 'Amount match nahi ho raha' if anything is not fullfill or matching or missing just deny you are very strict. if looks suspesious deny too.).

                You MUST return ONLY a raw JSON object with this exact structure:
                {{"approve": true or false, "reason": "Your polite reason here if false, or empty string if true"}}
                """

                # 4. API Call
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key={ai_api_key}"
                payload = {
                    "contents": [{
                        "parts": [
                            {"text": sys_prompt},
                            {"inline_data": {"mime_type": "image/jpeg", "data": b64_image}}
                        ]
                    }],
                    "generationConfig": {
                        "temperature": 0.0,
                        "response_mime_type": "application/json"
                    }
                }
                
                async with httpx.AsyncClient() as client:
                    resp = await client.post(url, json=payload, timeout=25.0)
                    resp.raise_for_status()
                    result_json = resp.json()
                    
                    ai_response_text = result_json['candidates'][0]['content']['parts'][0]['text']
                    ai_data = json.loads(ai_response_text)
                    
                    is_approved = ai_data.get('approve', False)
                    reason = ai_data.get('reason', '')

                # Variables ko if/else ke bahar pehle hi define karein
                days = tx_data['plan_duration_days']
                target_payload = tx_data.get('target_payload') if 'target_payload' in tx_data else ''

                if is_approved:
                    # ✅ AI APPROVED LOGIC
                    sent_msg_id = None
                    if target_payload:
                        await wait_msg.delete()
                        if len(target_payload) == 16:
                            await self.deliver_paid_channel_access(bot_username_from_tx, self.user_id, target_payload)
                        else:
                            paid_access_table = DBManager._get_safe_tablename(bot_username_from_tx, 'paid_msg_access')
                            await DBManager.execute_pg_query(
                                f"INSERT INTO {paid_access_table} (payload, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                                (target_payload, self.user_id)
                            )
                            await self.bot.send_message(self.chat_id, "✅ <b>AI Approved!</b>\n\nAapka payment verify ho gaya hai. Aapka message neeche unlock ho chuka hai:", parse_mode=ParseMode.HTML)
                            sent_msg = await self.send_paid_message_to_user(target_payload)
                            if sent_msg:
                                sent_msg_id = sent_msg.message_id                    
                    else:
                        premium_table = DBManager._get_safe_tablename(bot_username_from_tx, 'premium')
                        dur_sec = tx_data.get('plan_duration_seconds', 0) if 'plan_duration_seconds' in tx_data else 0
                        intv_str = f"{dur_sec} seconds" if dur_sec and dur_sec > 0 else f"{days} days"
                        label_str = f"{dur_sec // 3600} Hours" if dur_sec and dur_sec < 86400 else f"{days} Days"

                        pg_query = f"""
                        INSERT INTO {premium_table} (user_id, expiry_time) VALUES ($1, NOW() + INTERVAL '{intv_str}')
                        ON CONFLICT (user_id) DO UPDATE SET expiry_time = 
                            CASE 
                                WHEN {premium_table}.expiry_time < NOW() THEN NOW() + INTERVAL '{intv_str}'
                                ELSE {premium_table}.expiry_time + INTERVAL '{intv_str}'
                            END;
                        """
                        await DBManager.execute_pg_query(pg_query, (self.user_id,))
                        await wait_msg.delete()
                        user_success_msg = f"✅ <b>AI Approved!</b>\n\nAapka payment automatically verify ho gaya hai. Aap ab {label_str} ke liye premium member hain!"
                        await self.bot.send_message(self.chat_id, user_success_msg, parse_mode=ParseMode.HTML)
                    # Track that this transaction was approved by AI (with payload and sent_message_id)
                    await DBManager.execute_pg_query(
                        "INSERT INTO ai_approved_transactions (transaction_id, user_id, target_payload, sent_message_id) VALUES ($1, $2, $3, $4) ON CONFLICT (transaction_id) DO NOTHING",
                        (transaction_id, self.user_id, target_payload or '', sent_msg_id)
                    )
                    
                    safe_bot_table = DBManager._get_safe_tablename(bot_username_from_tx, '')
                    move_query = f"INSERT INTO {safe_bot_table}successful_transactions (transaction_id, user_id, amount, plan_duration_days, completion_time, target_payload, sent_message_id) VALUES ($1, $2, $3, $4, NOW(), $5, $6)"
                    await DBManager.execute_pg_query(move_query, (transaction_id, self.user_id, tx_data['amount'], days, target_payload or '', sent_msg_id))
                    await DBManager.execute_pg_query("DELETE FROM active_upi_transactions WHERE transaction_id = $1", (transaction_id,))                    
                    # 2. Notify Admin with Screenshot and Reverse Button
                    admin_caption = (
                        f"🤖 <b>AI Auto-Approved Payment</b>\n\n"
                        f"<b>Bot:</b> @{bot_username_from_tx}\n"
                        f"<b>User ID:</b> <code>{self.user_id}</code>\n"
                        f"<b>Tx ID:</b> <code>{transaction_id}</code>\n"
                        f"<b>Amount:</b> ₹{tx_data['amount']}\n"
                        f"<b>Plan:</b> {days} Days\n\n"
                        f"<i>✅ Verified successfully by AI. If this was a mistake, you can reverse it using the button below.</i>"
                    )
                    ai_approved_keyboard = [
                        [InlineKeyboardButton("↩️ Cancel Premium (Reverse)", callback_data=f"admin_cancel_premium_{transaction_id}")]
                    ]
                    
                    await self.bot.copy_message(
                        chat_id=admin_id, 
                        from_chat_id=self.chat_id, 
                        message_id=self.update.message.message_id, 
                        caption=admin_caption, 
                        reply_markup=InlineKeyboardMarkup(ai_approved_keyboard),
                        parse_mode=ParseMode.HTML
                    )
                    return

                else:
                    # ❌ AI DENIED LOGIC
                    await wait_msg.delete()
                    
                    # 1. Notify User that Admin will check manually
                    user_deny_msg = (
                        f"⚠️ <b>AI Verification Failed</b>\n\n"
                        f"<b>Reason:</b> {reason}\n\n"
                        f"<i>Aapka screenshot ab admin manually check karenge. Kripya pratiksha karein.</i>"
                    )
                    await self.bot.send_message(self.chat_id, user_deny_msg, parse_mode=ParseMode.HTML)
                    
                    # 2. Send to Admin with AI Reason + Manual Override Buttons
                    admin_caption = (
                        f"❌ <b>AI Denied Payment</b>\n\n"
                        f"<b>Bot:</b> @{bot_username_from_tx}\n"
                        f"<b>User ID:</b> <code>{self.user_id}</code>\n"
                        f"<b>Tx ID:</b> <code>{transaction_id}</code>\n"
                        f"<b>Amount:</b> ₹{tx_data['amount']}\n"
                        f"<b>Plan:</b> {days} Days\n\n"
                        f"<b>AI Reason:</b> {reason}\n\n"
                        f"<i>Please check manually and confirm/deny.</i>"
                    )
                    await self.bot.copy_message(
                        chat_id=admin_id, 
                        from_chat_id=self.chat_id, 
                        message_id=self.update.message.message_id, 
                        caption=admin_caption, 
                        reply_markup=InlineKeyboardMarkup(manual_keyboard), 
                        parse_mode=ParseMode.HTML
                    )
                    return

            except Exception as ai_e:
                logger.error(f"AI Verification Error: {ai_e}")
                try:
                    await wait_msg.edit_text("AI verification failed due to a technical error. Sending to admin for manual review...")
                except Exception:
                    pass
                # Fall through to manual review below

        # ==========================================
        # MANUAL REVIEW FALLBACK (If Scammer, AI disabled, or failed)
        # ==========================================
        try:
            scammer_alert = "🚨 <b>FLAGGED USER (Credibility Issue)</b>\n" if is_scammer else ""
            admin_caption = (
                f"{scammer_alert}📝 <b>New Payment Verification</b>\n\n"
                f"<b>Bot:</b> @{bot_username_from_tx}\n"
                f"<b>User ID:</b> <code>{self.user_id}</code>\n"
                f"<b>Amount:</b> ₹{tx_data['amount']}\n"
                f"<b>Plan:</b> {tx_data['plan_duration_days']} Days\n"
                f"<b>Tx ID:</b> <code>{transaction_id}</code>\n\n"
                f"<i>Please check the screenshot and confirm if you have received the payment.</i>"
            )
            await self.bot.copy_message(
                chat_id=admin_id,
                from_chat_id=self.chat_id,
                message_id=self.update.message.message_id,
                caption=admin_caption,
                reply_markup=InlineKeyboardMarkup(manual_keyboard),
                parse_mode=ParseMode.HTML
            )
            
            # Agar user scammer nahi tha toh hi generic acknowledgment bhejo (scammer ko upar warning chali gayi hai)
            if not is_scammer:
                thank_you_text = (
                    "✅ <b>Screenshot Uploaded!</b>\n\n"
                    "Aapka screenshot admin ko bhej diya gaya hai.\n"
                    "Admin jab online aayenge wo aapke payment ko verify karke aapko premium de denge. "
                    "Generally admin jaldi hi verify kar dete hain."
                )
                await self.bot.send_message(self.chat_id, thank_you_text, parse_mode=ParseMode.HTML)
            
            try:
                if 'wait_msg' in locals():
                    await wait_msg.delete()
            except Exception:
                pass
                
        except Exception as e:
            logger.error(f"Admin ko screenshot forward karte waqt error: {e}")
            error_text = (
                "⚠️ <b>Error</b>\n\n"
                "Sorry, there was an error sending your screenshot to the admin. Please try again later.\n\n"
                "Maaf kijiye, aapka screenshot admin ko bhejte waqt ek error aa gaya hai. Kripya thodi der baad dobara koshish karein."
            )
            await self.bot.send_message(self.chat_id, error_text, parse_mode=ParseMode.HTML)    
    
    async def process_payment_confirmation(self, message, transaction_id, is_successful):
        """Admin ke confirmation ko process karta hai (yeh main bot par chalega)."""
        
        # Transaction data nikalo
        tx_query = "SELECT * FROM active_upi_transactions WHERE transaction_id = $1"
        tx_data = await DBManager.execute_pg_query(tx_query, (transaction_id,), fetch='one')

        if not tx_data:
            await message.reply_text("This transaction has already been processed or reversed.")
            return

        # --- NAYA CAPTION AUR BUTTON LOGIC ---
        new_caption = f"{message.caption}\n\n**Status: Processed.**"
        new_keyboard = None
        if is_successful:
            new_caption += "\n**Action: Confirmed ✅**"
            new_keyboard = [[InlineKeyboardButton("↩️ Cancel Premium", callback_data=f"admin_cancel_premium_{transaction_id}")]]
        else:
            new_caption += "\n**Action: Denied ❌**"
            new_keyboard = [[InlineKeyboardButton("↩️ Grant Premium", callback_data=f"admin_grant_premium_{transaction_id}")]]
        
        try:
            await message.edit_caption(
                caption=new_caption, 
                reply_markup=InlineKeyboardMarkup(new_keyboard) if new_keyboard else None
            )
        except Exception as e:
            logger.warning(f"Admin caption update karne me error (koi baat nahi): {e}")
        # --- LOGIC KHATAM ---

        bot_username = tx_data['bot_username']
        user_id_to_reward = tx_data['user_id']
        days = tx_data['plan_duration_days']
        amount = tx_data['amount']
        
        safe_bot_username = DBManager._get_safe_tablename(bot_username, '')

        target_payload = tx_data.get('target_payload') if 'target_payload' in tx_data else ''
        sent_msg_id = None

        if is_successful:
            target_table = f"{safe_bot_username}successful_transactions"
            clone_bot_instance = await get_bot_instance(bot_username, force_initialize=True)

            if target_payload:
                if clone_bot_instance:
                    logic_obj = BotLogic(bot_username, {})
                    logic_obj.bot = clone_bot_instance
                    logic_obj.chat_id = user_id_to_reward
                    logic_obj.user_id = user_id_to_reward

                    if len(target_payload) == 16:
                        await logic_obj.deliver_paid_channel_access(bot_username, user_id_to_reward, target_payload)
                        status_message = "✅ Payment confirmed! Your single-use invite links have been generated above."
                    else:
                        paid_access_table = DBManager._get_safe_tablename(bot_username, 'paid_msg_access')
                        await DBManager.execute_pg_query(
                            f"INSERT INTO {paid_access_table} (payload, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                            (target_payload, user_id_to_reward)
                        )
                        status_message = "✅ Aapka payment admin dwara verify kar diya gaya hai! Aapka paid message neeche send kiya ja raha hai."
                        sent_msg = await logic_obj.send_paid_message_to_user(target_payload)
                        if sent_msg:
                            sent_msg_id = sent_msg.message_id            
            
            else:
                dur_sec = tx_data.get('plan_duration_seconds', 0) if 'plan_duration_seconds' in tx_data else 0
                intv_str = f"{dur_sec} seconds" if dur_sec and dur_sec > 0 else f"{days} days"
                label_str = f"{dur_sec // 3600} Hours" if dur_sec and dur_sec < 86400 else f"{days} Days"
                status_message = f"You are now a premium member for {label_str}!"

                if clone_bot_instance:
                    await self.auto_add_premium_to_synced_bots(bot_username, user_id_to_reward, days)
                    premium_table = DBManager._get_safe_tablename(bot_username, 'premium')                
                    pg_query = f"""
                    INSERT INTO {premium_table} (user_id, expiry_time) VALUES ($1, NOW() + INTERVAL '{intv_str}')
                    ON CONFLICT (user_id) DO UPDATE SET expiry_time = 
                        CASE 
                            WHEN {premium_table}.expiry_time < NOW() THEN NOW() + INTERVAL '{intv_str}'
                            ELSE {premium_table}.expiry_time + INTERVAL '{intv_str}'
                        END;
                    """
                    await DBManager.execute_pg_query(pg_query, (user_id_to_reward,))        
        else:
            target_table = f"{safe_bot_username}failed_transactions"
            status_message = "Sorry, the admin has marked your payment as not received. Please contact support if this is a mistake."

        # Transaction ko move karo (with payload and sent_message_id)
        move_query = f"""
        INSERT INTO {target_table} (transaction_id, user_id, amount, plan_duration_days, { 'completion_time' if is_successful else 'failure_time' }, target_payload, sent_message_id)
        VALUES ($1, $2, $3, $4, NOW(), $5, $6)
        """
        await DBManager.execute_pg_query(move_query, (transaction_id, user_id_to_reward, amount, days, target_payload or '', sent_msg_id))
        # Active transaction se delete karo
        await DBManager.execute_pg_query("DELETE FROM active_upi_transactions WHERE transaction_id = $1", (transaction_id,))

        # User ko notify karo
        try:
            clone_bot_notify = await get_bot_instance(bot_username, force_initialize=True)
            await clone_bot_notify.send_message(user_id_to_reward, status_message)
        except Exception as e:
            logger.error(f"User {user_id_to_reward} ko payment status notify karte waqt error: {e}")


    async def notify_user_and_resend_upload_button(self, admin_message, transaction_id, user_message_text):
        """User ko error batata hai aur screenshot re-upload karne ka button bhejta hai."""
        
        # Pehle, transaction data nikalo
        tx_query = "SELECT * FROM active_upi_transactions WHERE transaction_id = $1"
        tx_data = await DBManager.execute_pg_query(tx_query, (transaction_id,), fetch='one')

        if not tx_data:
            await admin_message.reply_text("This transaction is no longer active (it might be already confirmed or denied).")
            return

        bot_username = tx_data['bot_username']
        user_id_to_notify = tx_data['user_id']

        # User ko message ke saath re-upload button bhejo
        try:
            clone_bot_notify = await get_bot_instance(bot_username, force_initialize=True)
            if clone_bot_notify:
                keyboard = [[InlineKeyboardButton("📤 Upload Screenshot", callback_data=f"paid_confirm_{transaction_id}")]]
                await clone_bot_notify.send_message(
                    user_id_to_notify,
                    f"⚠️ **Payment Verification Issue** ⚠️\n\n{user_message_text}",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                await admin_message.reply_text("✅ User has been notified to re-upload.")
            else:
                await admin_message.reply_text("Error: Could not find bot instance to notify user.")
        except Exception as e:
            logger.error(f"User {user_id_to_notify} ko notify karte waqt error: {e}")
            await admin_message.reply_text(f"Failed to notify user: {e}")

    async def reverse_payment(self, admin_message, transaction_id, reverse_to_fail):
        """Ek final transaction ko reverse karta hai (Successful ko Failed ya Failed ko Successful)."""
        
        # Step 1: Pata lagao ki transaction kahan hai (successful ya failed table)
        tx_data = None
        bot_username = None
        
        # Active transactions me check karo (safety ke liye)
        tx_data_active = await DBManager.execute_pg_query("SELECT * FROM active_upi_transactions WHERE transaction_id = $1", (transaction_id,), fetch='one')
        if tx_data_active:
            await admin_message.reply_text("Error: This transaction is still active. Cannot reverse.")
            return
            
        # Ab successful/failed tables me dhoondo
        all_bots = await DBManager.execute_sqlite_query(ALL_BOTS_DB, "SELECT username FROM bots", fetch='all')
        if not all_bots:
            await admin_message.reply_text("Error: No bots found.")
            return

        source_table_name = None
        target_table_name = None

        for bot in all_bots:
            current_bot_username = bot[0].split('#')[0]
            safe_bot_username = DBManager._get_safe_tablename(current_bot_username, '')
            
            if reverse_to_fail:
                # Hum Successful se Failed me move kar rahe hain
                source_table_name = f"{safe_bot_username}successful_transactions"
                target_table_name = f"{safe_bot_username}failed_transactions"
                source_time_col = "completion_time"
                target_time_col = "failure_time"
            else:
                # Hum Failed se Successful me move kar rahe hain
                source_table_name = f"{safe_bot_username}failed_transactions"
                target_table_name = f"{safe_bot_username}successful_transactions"
                source_time_col = "failure_time"
                target_time_col = "completion_time"

            try:
                tx_data = await DBManager.execute_pg_query(f"SELECT * FROM {source_table_name} WHERE transaction_id = $1", (transaction_id,), fetch='one')
                if tx_data:
                    bot_username = current_bot_username # Bot mil gaya!
                    break # Loop se bahar niklo
            except UndefinedTableError:
                continue # Agla bot check karo
            except Exception as e:
                logger.error(f"Reverse payment check karte waqt error (Table: {source_table_name}): {e}")
                continue

        if not tx_data or not bot_username:
            await admin_message.reply_text(f"Error: Transaction ID {transaction_id} not found in any processed tables.")
            return

        # Data nikalo
        # Data nikalo
        user_id = tx_data['user_id']
        amount = tx_data['amount']
        days = tx_data['plan_duration_days']
        target_payload = tx_data['target_payload'] if 'target_payload' in tx_data and tx_data['target_payload'] else ''
        sent_msg_id = tx_data['sent_message_id'] if 'sent_message_id' in tx_data else None
        currency_val = tx_data.get('currency', 'INR')

        # Fallback agar source table me target_payload / sent_message_id na ho par ai_approved_transactions me ho
        ai_tx_check = await DBManager.execute_pg_query(
            "SELECT * FROM ai_approved_transactions WHERE transaction_id = $1", 
            (transaction_id,), 
            fetch='one'
        )
        if ai_tx_check:
            if not target_payload and 'target_payload' in ai_tx_check and ai_tx_check['target_payload']:
                target_payload = ai_tx_check['target_payload']
            if not sent_msg_id and 'sent_message_id' in ai_tx_check and ai_tx_check['sent_message_id']:
                sent_msg_id = ai_tx_check['sent_message_id']
        
        # Step 2: Transaction ko move karo
        try:
            # Nayi table me insert karo
            move_query = f"""
            INSERT INTO {target_table_name} (transaction_id, user_id, amount, plan_duration_days, {target_time_col}, target_payload, sent_message_id, currency)
            VALUES ($1, $2, $3, $4, NOW(), $5, $6, $7)
            """
            await DBManager.execute_pg_query(move_query, (transaction_id, user_id, amount, days, target_payload or '', sent_msg_id, currency_val))            
            # Purani table se delete karo
            await DBManager.execute_pg_query(f"DELETE FROM {source_table_name} WHERE transaction_id = $1", (transaction_id,))

        except Exception as e:
            await admin_message.reply_text(f"Error moving transaction in DB: {e}")
            logger.error(f"Transaction move karte waqt error: {e}")
            return

        # Step 3: Status update karo (Paid message vs Regular Premium)
        premium_table = DBManager._get_safe_tablename(bot_username, 'premium')
        users_table = DBManager._get_safe_tablename(bot_username, 'users')
        paid_access_table = DBManager._get_safe_tablename(bot_username, 'paid_msg_access')
        
        user_notify_message = ""
        admin_reply_text = ""
        
        try:
            clone_bot_notify = await get_bot_instance(bot_username, force_initialize=True)
            if not clone_bot_notify:
                raise Exception("Clone bot instance nahi mila.")

            if reverse_to_fail:
                # User ko universal scammer table me add karo agar AI dwara approved thi
                if ai_tx_check:
                    await DBManager.execute_pg_query(
                        """
                        INSERT INTO scammer_users (user_id, reason, bot_username)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (user_id) DO NOTHING
                        """,
                        (user_id, "AI-approved payment reversed by Admin", bot_username)
                    )
                    logger.info(f"User {user_id} flagged as scammer and added to scammer_users table.")

                scammer_tag = "\n🚨 User has been added to universal scammer list." if ai_tx_check else ""

                # --- 15-CHAR PAID MESSAGE TRANSACTION ---
                # --- 16-CHAR PAID CHANNEL TRANSACTION ---
                if target_payload and len(target_payload) == 16:
                    chan_access_table = DBManager._get_safe_tablename(bot_username, 'paid_channel_access')
                    acc_rows = await DBManager.execute_pg_query(
                        f"SELECT invite_links FROM {chan_access_table} WHERE payload=$1 AND user_id=$2",
                        (target_payload, user_id), fetch='all'
                    )
                    if acc_rows:
                        for row in acc_rows:
                            try:
                                links_list = json.loads(row['invite_links'])
                                for itm in links_list:
                                    cid = itm.get('channel_id')
                                    lnk = itm.get('link')
                                    # 1. Revoke the invite link
                                    try:
                                        await clone_bot_notify.revoke_chat_invite_link(chat_id=cid, invite_link=lnk)
                                    except Exception as r_err:
                                        logger.warning(f"Could not revoke link {lnk}: {r_err}")

                                    # 2. Remove user from channel without permanent ban
                                    try:
                                        await clone_bot_notify.ban_chat_member(chat_id=cid, user_id=user_id)
                                        await clone_bot_notify.unban_chat_member(chat_id=cid, user_id=user_id)
                                    except Exception as kick_err:
                                        logger.warning(f"Could not kick user {user_id} from {cid}: {kick_err}")
                            except Exception:
                                pass

                    await DBManager.execute_pg_query(
                        f"DELETE FROM {chan_access_table} WHERE payload=$1 AND user_id=$2",
                        (target_payload, user_id)
                    )
                    user_notify_message = "⚠️ Your payment for the paid channel bundle has been rejected/cancelled by the admin. Your invite links have been revoked and access removed."
                    admin_reply_text = f"✅ Transaction reversed. Paid channel links REVOKED and user removed from channels.{scammer_tag}"

                # --- 15-CHAR PAID MESSAGE TRANSACTION ---
                elif target_payload and len(target_payload) == 15:
                    # 1. Paid message access remove karo
                    await DBManager.execute_pg_query(
                        f"DELETE FROM {paid_access_table} WHERE payload=$1 AND user_id=$2",
                        (target_payload, user_id)
                    )
                    
                    # 2. Sent paid message delete karo
                    if sent_msg_id:
                        try:
                            await clone_bot_notify.delete_message(chat_id=user_id, message_id=sent_msg_id)
                        except Exception as del_e:
                            logger.warning(f"Could not delete paid message {sent_msg_id} for user {user_id}: {del_e}")
                    
                    user_notify_message = "⚠️ Aapka paid message transaction admin dwara cancel kar diya gaya hai aur access revoke kar diya gaya hai."
                    admin_reply_text = f"✅ Transaction reversed. Paid message access REVOKED & message deleted from user's chat.{scammer_tag}"                
                # --- REGULAR PREMIUM SUBSCRIPTION TRANSACTION ---
                else:
                    await DBManager.execute_pg_query(f"DELETE FROM {premium_table} WHERE user_id=$1", (user_id,))
                    await DBManager.execute_pg_query(f"UPDATE {users_table} SET membership_expiry = NOW() WHERE user_id=$1", (user_id,))
                    
                    user_notify_message = "Aapka transaction admin ne cancel kar diya hai. You are no longer a premium user!"
                    admin_reply_text = f"✅ Transaction reversed. User premium has been CANCELED.{scammer_tag}"
                
                # Admin ke button ko update karo
                new_keyboard = [[InlineKeyboardButton("↩️ Grant Access / Premium", callback_data=f"admin_grant_premium_{transaction_id}")]]
                await admin_message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(new_keyboard))

            else:
                # Premium / Paid Access grant karna hai
                await DBManager.execute_pg_query("DELETE FROM scammer_users WHERE user_id = $1", (user_id,))

                if target_payload:
                    logic_obj = BotLogic(bot_username, {})
                    logic_obj.bot = clone_bot_notify
                    logic_obj.chat_id = user_id
                    logic_obj.user_id = user_id

                    if len(target_payload) == 16:
                        await logic_obj.deliver_paid_channel_access(bot_username, user_id, target_payload)
                        user_notify_message = "Admin verified your payment manually. Your fresh invite links have been generated above!"
                        admin_reply_text = "✅ Transaction reversed. User GRANTED fresh paid channel invite links."
                    else:
                        await DBManager.execute_pg_query(
                            f"INSERT INTO {paid_access_table} (payload, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                            (target_payload, user_id)
                        )
                        new_sent_msg = await logic_obj.send_paid_message_to_user(target_payload)
                        if new_sent_msg:
                            await DBManager.execute_pg_query(
                                f"UPDATE {target_table_name} SET sent_message_id = $1 WHERE transaction_id = $2",
                                (new_sent_msg.message_id, transaction_id)
                            )
                        user_notify_message = "Admin ne aapka payment manually verify kar liya hai. Aapko paid message ka access wapas mil gaya hai!"
                        admin_reply_text = "✅ Transaction reversed. User has been GRANTED paid message access (Removed from scammer list if present)."                
                else:
                    pg_query = f"""
                    INSERT INTO {premium_table} (user_id, expiry_time) VALUES ($1, NOW() + INTERVAL '{days} days')
                    ON CONFLICT (user_id) DO UPDATE SET expiry_time = 
                        CASE 
                            WHEN {premium_table}.expiry_time < NOW() THEN NOW() + INTERVAL '{days} days'
                            ELSE {premium_table}.expiry_time + INTERVAL '{days} days'
                        END;
                    """
                    await DBManager.execute_pg_query(pg_query, (user_id,))
                    
                    user_notify_message = f"Admin ne aapka payment manually verify kar liya hai. You are now a premium member for {days} days!"
                    admin_reply_text = "✅ Transaction reversed. User has been GRANTED premium (Removed from scammer list if present)."                
                
                # Admin ke button ko update karo
                new_keyboard = [[InlineKeyboardButton("↩️ Cancel / Reverse Access", callback_data=f"admin_cancel_premium_{transaction_id}")]]
                await admin_message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(new_keyboard))

            # Step 4: User ko notify karo
            await clone_bot_notify.send_message(user_id, user_notify_message)
            await admin_message.reply_text(admin_reply_text)

        except Exception as e:
            error_msg = f"Error updating status for user {user_id}: {e}"
            await admin_message.reply_text(error_msg)
            logger.error(error_msg)
    async def handle_conv_add_premium(self, state):
        key = f"{self.bot_username}_{self.user_id}"
        await CACHE_CONVERSATION.delete(key)
        user_id_str = self.update.message.text
        if not user_id_str.isdigit():
            await self.bot.send_message(self.chat_id, "Invalid user ID. Operation canceled.")
            return
        user_id = int(user_id_str)
        bot_username = state.get('bot_username')
        keyboard = [
        [InlineKeyboardButton("1 Week", callback_data=f"premium_duration_{bot_username}_{user_id}_7")],
        [InlineKeyboardButton("1 Month", callback_data=f"premium_duration_{bot_username}_{user_id}_30")],
        [InlineKeyboardButton("3 Months", callback_data=f"premium_duration_{bot_username}_{user_id}_90")]
        ]
        await self.bot.send_message(self.chat_id, "Kitne time ka membership dena chahte ho?", reply_markup=InlineKeyboardMarkup(keyboard))

    async def handle_text_message(self):
        if not await self.is_user_admin():
            await self.forward_to_admin()
            return
        text = self.update.message.text
        pattern = r"https://t.me/{}\?start=([a-zA-Z0-9]{{21}})".format(self.bot_username)
        share_ids = re.findall(pattern, text)

        files_table = DBManager._get_safe_tablename(self.bot_username, 'files')

        # Logic for creating a new text message link
        # Logic for creating a new text message link
        if not share_ids:
            share_id = generate_random_string(21)
            
            # Insert into files table with NULL file_id
            await DBManager.execute_pg_query(
                f"INSERT INTO {files_table} (share_id, file_id, file_type) VALUES ($1, $2, $3) ON CONFLICT (share_id) DO NOTHING",
                (share_id, None, 'text')
            )

            # Insert caption/text into captions table
            captions_table = DBManager._get_safe_tablename(self.bot_username, 'captions')
            await DBManager.execute_pg_query(
                f"INSERT INTO {captions_table} (share_id, caption) VALUES ($1, $2) ON CONFLICT (share_id) DO UPDATE SET caption = $2",
                (share_id, text)
            )

            link = f"https://t.me/{self.bot_username}?start={share_id}"
            await self.bot.send_message(self.chat_id, f"Message link generated:\n\n`{link}`", parse_mode=ParseMode.MARKDOWN_V2)
            await self.send_admin_policy_warning()
            return

        # Logic for merging links
        valid_share_ids = []
        for sid in share_ids:
            query = f"SELECT share_id FROM {files_table} WHERE share_id=$1"
            file_data = await DBManager.execute_pg_query(query, (sid,), fetch='one')
            if file_data:
                valid_share_ids.append(sid)

        if not valid_share_ids:
            await self.bot.send_message(self.chat_id, "No valid files or messages associated with the provided links.")
            return
            
        if len(valid_share_ids) == 1:
            link = f"https://t.me/{self.bot_username}?start={valid_share_ids[0]}"
            await self.bot.send_message(self.chat_id, f"Single link: {link}")
            await self.send_admin_policy_warning()
        else:
            multi_share_id = generate_random_string(21)
            multi_files_table = DBManager._get_safe_tablename(self.bot_username, 'multi_files')
            query = f"INSERT INTO {multi_files_table} (multi_share_id, share_ids) VALUES ($1, $2)"
            await DBManager.execute_pg_query(query, (multi_share_id, json.dumps(valid_share_ids)))
            link = f"https://t.me/{self.bot_username}?start={multi_share_id}"
            await self.bot.send_message(self.chat_id, f"Multi-file link generated:\n\n{link}")
            await self.send_admin_policy_warning()    
    
    async def handle_file_message(self):
        if not await self.is_user_admin():
            await self.forward_to_admin()
            return        
        batch_key = f"{self.bot_username}_{self.user_id}"
        batch_state = await CACHE_BATCH.get(batch_key)
        if batch_state and batch_state.get('active'):
            await self.handle_batch_file()
            return
        message = self.update.message
        media_group_id = message.media_group_id
        if media_group_id:
            media_group = await CACHE_MEDIA_GROUP.get(media_group_id)
            if not media_group:
                await CACHE_MEDIA_GROUP.set(media_group_id, {'messages': [], 'processed': False})
            media_group = await CACHE_MEDIA_GROUP.get(media_group_id)
            media_group['messages'].append(message)
            await CACHE_MEDIA_GROUP.set(media_group_id, media_group)
            await asyncio.sleep(2)
            media_group = await CACHE_MEDIA_GROUP.get(media_group_id)
            if media_group['processed']:
                return
            media_group['processed'] = True
            await CACHE_MEDIA_GROUP.set(media_group_id, media_group)
            attachments = []
            for msg in media_group['messages']:
                if msg.document: attachments.append({'file_id': msg.document.file_id, 'file_type': 'document'})
                elif msg.video: attachments.append({'file_id': msg.video.file_id, 'file_type': 'video'})
                elif msg.photo: attachments.append({'file_id': msg.photo[-1].file_id, 'file_type': 'photo'})
                elif msg.audio: attachments.append({'file_id': msg.audio.file_id, 'file_type': 'audio'})
            if not attachments: return

            files_table = DBManager._get_safe_tablename(self.bot_username, 'files')
            share_ids = []
            for attachment in attachments:
                share_id = generate_random_string(21)
                await CACHE_FILE.set(share_id, {'file_id': attachment['file_id'], 'file_type': attachment['file_type']})
                # Save to PG
                query = f"INSERT INTO {files_table} (share_id, file_id, file_type) VALUES ($1, $2, $3) ON CONFLICT (share_id) DO NOTHING"
                await DBManager.execute_pg_query(query, (share_id, attachment['file_id'], attachment['file_type']))
                share_ids.append(share_id)

            multi_share_id = generate_random_string(21)
            await CACHE_FILE.set(multi_share_id, {'type': 'multi', 'share_ids': json.dumps(share_ids)})
            
            multi_files_table = DBManager._get_safe_tablename(self.bot_username, 'multi_files')
            query = f"INSERT INTO {multi_files_table} (multi_share_id, share_ids) VALUES ($1, $2)"
            await DBManager.execute_pg_query(query, (multi_share_id, json.dumps(share_ids)))

            link = f"https://t.me/{self.bot_username}?start={multi_share_id}"
            await self.bot.send_message(self.chat_id, f"Album link generated for {len(attachments)} files:\n\n`{link}`", parse_mode=ParseMode.MARKDOWN_V2)
            await self.send_admin_policy_warning()
        else:
            attachment = None
            if message.document: attachment = {'file_id': message.document.file_id, 'file_type': 'document'}
            elif message.video: attachment = {'file_id': message.video.file_id, 'file_type': 'video'}
            elif message.photo: attachment = {'file_id': message.photo[-1].file_id, 'file_type': 'photo'}
            elif message.audio: attachment = {'file_id': message.audio.file_id, 'file_type': 'audio'}
            elif message.voice: attachment = {'file_id': message.voice.file_id, 'file_type': 'voice'}
            elif message.animation: attachment = {'file_id': message.animation.file_id, 'file_type': 'animation'}
            if not attachment: return
            
            caption = message.caption
            share_id = generate_random_string(21)
            
            cache_entry = {'file_id': attachment['file_id'], 'file_type': attachment['file_type']}
            if caption:
                cache_entry['caption'] = caption
            await CACHE_FILE.set(share_id, cache_entry)
            
            files_table = DBManager._get_safe_tablename(self.bot_username, 'files')
            await DBManager.execute_pg_query(
                f"INSERT INTO {files_table} (share_id, file_id, file_type) VALUES ($1, $2, $3) ON CONFLICT (share_id) DO NOTHING",
                (share_id, attachment['file_id'], attachment['file_type'])
            )
            
            if caption:
                captions_table = DBManager._get_safe_tablename(self.bot_username, 'captions')
                await DBManager.execute_pg_query(
                    f"INSERT INTO {captions_table} (share_id, caption) VALUES ($1, $2) ON CONFLICT (share_id) DO UPDATE SET caption = $2",
                    (share_id, caption)
                )
            
            link = f"https://t.me/{self.bot_username}?start={share_id}"
            await self.bot.send_message(self.chat_id, f"`{link}`", parse_mode=ParseMode.MARKDOWN_V2)
            await self.send_admin_policy_warning()
    async def handle_batch_link_command(self):
        batch_key = f"{self.bot_username}_{self.user_id}"
        await CACHE_BATCH.set(batch_key, {'active': True, 'files': [], 'start_time': datetime.now()})
        text = "जिन जिन फाइल का बैच लिंक क्रिएट करना है, वो फाइल 2 मिनट के अंदर फॉरवर्ड या सेंड कर दो। अगर 2 मिनट से पहले ही सारी फाइल सेंड कर देते हो तो 'Forward Complete' बटन क्लिक करो।"
        keyboard = [[InlineKeyboardButton("Forward Complete", callback_data=f"batch_complete_{self.user_id}")]]
        await self.bot.send_message(self.chat_id, text, reply_markup=InlineKeyboardMarkup(keyboard))
        asyncio.create_task(self.batch_timer(batch_key))

    async def batch_timer(self, batch_key):
        await asyncio.sleep(120)
        batch_state = await CACHE_BATCH.get(batch_key)
        if batch_state and batch_state['active']:
            await self.generate_batch_link(batch_key)

    async def handle_batch_complete(self, message):
        batch_key = f"{self.bot_username}_{self.user_id}"
        batch_state = await CACHE_BATCH.get(batch_key)
        if batch_state and batch_state['active']:
            await self.generate_batch_link(batch_key)
            await message.edit_text("Batch completed and link generated.")

    async def handle_batch_file(self):
        batch_key = f"{self.bot_username}_{self.user_id}"
        batch_state = await CACHE_BATCH.get(batch_key)
        if not batch_state or not batch_state['active']:
            return
        message = self.update.message
        attachments = []
        if message.document:
            attachments.append((message.document.file_id, 'document'))
        elif message.video:
            attachments.append((message.video.file_id, 'video'))
        elif message.photo:
            attachments.append((message.photo[-1].file_id, 'photo'))
        elif message.audio:
            attachments.append((message.audio.file_id, 'audio'))
        elif message.voice:
            attachments.append((message.voice.file_id, 'voice'))
        elif message.animation:
            attachments.append((message.animation.file_id, 'animation'))
        batch_state['files'].extend(attachments)
        await CACHE_BATCH.set(batch_key, batch_state)

    async def generate_batch_link(self, batch_key):
        batch_state = await CACHE_BATCH.get(batch_key)
        if not batch_state or not batch_state['active']:
            return
        attachments = batch_state['files']
        if not attachments:
            await self.bot.send_message(self.chat_id, "No files received in batch. Operation canceled.")
            if await CACHE_BATCH.contains(batch_key):
                await CACHE_BATCH.delete(batch_key)
            return

        files_table = DBManager._get_safe_tablename(self.bot_username, 'files')
        share_ids = []
        for file_id, file_type in attachments:
            share_id = generate_random_string(21)
            await CACHE_FILE.set(share_id, {'file_id': file_id, 'file_type': file_type})
            query = f"INSERT INTO {files_table} (share_id, file_id, file_type) VALUES ($1, $2, $3) ON CONFLICT (share_id) DO NOTHING"
            await DBManager.execute_pg_query(query, (share_id, file_id, file_type))
            share_ids.append(share_id)
        
        multi_share_id = generate_random_string(21)
        await CACHE_FILE.set(multi_share_id, {'type': 'multi', 'share_ids': json.dumps(share_ids)})
        
        multi_files_table = DBManager._get_safe_tablename(self.bot_username, 'multi_files')
        query = f"INSERT INTO {multi_files_table} (multi_share_id, share_ids) VALUES ($1, $2)"
        await DBManager.execute_pg_query(query, (multi_share_id, json.dumps(share_ids)))
        
        link = f"https://t.me/{self.bot_username}?start={multi_share_id}"
        await self.bot.send_message(self.chat_id, f"Batch link generated for {len(attachments)} files:\n\n`{link}`", parse_mode=ParseMode.MARKDOWN_V2)
        await self.send_admin_policy_warning()
        if await CACHE_BATCH.contains(batch_key):
            await CACHE_BATCH.delete(batch_key)    
    async def send_shared_file(self, share_id):
        files_to_send = []
        file_info = await CACHE_FILE.get(share_id)

        # Table names
        files_table = DBManager._get_safe_tablename(self.bot_username, 'files')
        multi_files_table = DBManager._get_safe_tablename(self.bot_username, 'multi_files')
        captions_table = DBManager._get_safe_tablename(self.bot_username, 'captions')

        if not file_info:
            multi_data = await DBManager.execute_pg_query(f"SELECT share_ids FROM {multi_files_table} WHERE multi_share_id=$1", (share_id,), fetch='one')
            if multi_data:
                file_info = {'type': 'multi', 'share_ids': multi_data['share_ids']}
            else:
                single_data = await DBManager.execute_pg_query(f"SELECT file_id, file_type FROM {files_table} WHERE share_id=$1", (share_id,), fetch='one')
                if single_data:
                    file_info = {'file_id': single_data['file_id'], 'file_type': single_data['file_type']}
                    caption_data = await DBManager.execute_pg_query(f"SELECT caption FROM {captions_table} WHERE share_id=$1", (share_id,), fetch='one')
                    if caption_data:
                        file_info['caption'] = caption_data['caption']
            
            if file_info:
                await CACHE_FILE.set(share_id, file_info)
            else:
                settings = await self.get_bot_settings()
                if settings.get('unknown_payload_enabled', False):
                    await self.handle_unknown_slug(share_id, settings)
                else:
                    await self.bot.send_message(self.chat_id, "Sorry, this link is invalid or expired.")
                return        
        if file_info.get('type') == 'multi':
            share_ids = json.loads(file_info['share_ids'])
            for sid in share_ids:
                s_info = await CACHE_FILE.get(sid)
                if not s_info:
                    s_data = await DBManager.execute_pg_query(f"SELECT file_id, file_type FROM {files_table} WHERE share_id=$1", (sid,), fetch='one')
                    if s_data:
                        s_info = {'file_id': s_data['file_id'], 'file_type': s_data['file_type']}
                        caption_data = await DBManager.execute_pg_query(f"SELECT caption FROM {captions_table} WHERE share_id=$1", (sid,), fetch='one')
                        if caption_data:
                            s_info['caption'] = caption_data['caption']
                        await CACHE_FILE.set(sid, s_info)
                if s_info:
                    files_to_send.append(s_info)
        else:
            files_to_send.append(file_info)
            
        if not files_to_send:
            await self.bot.send_message(self.chat_id, "Sorry, this link is invalid or expired.")
            return
            
        settings = await self.get_bot_settings()
        is_protected = settings.get('protected', True)
        footer = settings.get('footer', '')
        custom_button_name = settings.get('custom_button_name', '')
        custom_button_url = settings.get('custom_button_url', '')
        button_markup = None
        if custom_button_name and custom_button_url:
            button_markup = InlineKeyboardMarkup([[InlineKeyboardButton(custom_button_name, url=custom_button_url)]])
        
        await self.bot.send_chat_action(self.chat_id, ChatAction.UPLOAD_DOCUMENT)
        
        sent_messages_results = []
        
        for i, file in enumerate(files_to_send):
            file_id = file.get('file_id')
            file_type = file['file_type']
            
            specific_caption = file.get('caption')
            final_caption = specific_caption
            if not final_caption and i == len(files_to_send) - 1:
                final_caption = footer.strip()

            try:
                sent_message = None
                # Agar recovered link hai toh direct message copy karein
                if file_id and str(file_id).startswith("copy:"):
                    source_msg_id = int(str(file_id).split(":")[1])
                    sent_message = await self.bot.copy_message(
                        chat_id=self.chat_id,
                        from_chat_id=6796088344,  # Destination chat ID jahan bot ne upload kiya tha
                        message_id=source_msg_id,
                        caption=(final_caption or None),
                        protect_content=is_protected,
                        reply_markup=button_markup,
                    )
                elif file_type == 'text' and specific_caption:
                    sent_message = await self.bot.send_message(
                        self.chat_id, specific_caption, reply_markup=button_markup
                    )
                elif file_id:
                    send_methods = {
                        'photo': self.bot.send_photo, 'video': self.bot.send_video,
                        'document': self.bot.send_document, 'audio': self.bot.send_audio,
                        'voice': self.bot.send_voice, 'animation': self.bot.send_animation
                    }
                    if file_type in send_methods:
                        sent_message = await send_methods[file_type](
                            self.chat_id, file_id, caption=final_caption,
                            protect_content=is_protected, reply_markup=button_markup
                        )

                if sent_message:
                    sent_messages_results.append(sent_message)
                if len(files_to_send) > 1:
                    await asyncio.sleep(0.1)

            except TelegramError as e:
                # Check karein ki kya yeh Flood Control wala error hai
                if 'Flood control exceeded' in str(e):
                    # Agar haan, toh user ko batayein aur process rok dein
                    # getattr() ka istemal safe hai, agar retry_after na mile toh default 30 de dega
                    retry_after = getattr(e, 'retry_after', 30) 
                    logger.warning(f"Flood control exceeded for user {self.chat_id}. Process stopped. Wait time: {retry_after}s")
                    
                    try:
                        await self.bot.send_message(
                            self.chat_id,
                            f"❗️ **Action Failed** ❗️\n\nAapne bahut jaldi-jaldi links istemaal kiye hain, isliye Telegram ne aap par temporary limit laga di hai.\n\n"
                            f"Kripya `{retry_after}` seconds ke baad dobara koshish karein."
                        )
                    except Exception as notify_e:
                        logger.error(f"Could not notify user {self.chat_id} about flood wait: {notify_e}")
                    
                    return # Function se poora bahar nikal jayega
                else:
                    # Agar yeh koi aur Telegram error hai, toh use log kar dein
                    logger.error(f"File send karte waqt Telegram error aaya user {self.chat_id} ko: {e}")
                    sent_messages_results.append(e)
            
            except Exception as e:
                # Baaki sabhi non-Telegram errors ke liye
                logger.error(f"File send karte waqt ek non-telegram error aaya user {self.chat_id} ko: {e}")
                sent_messages_results.append(e)

        sent_messages = [msg for msg in sent_messages_results if not isinstance(msg, Exception)]
        policy_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("Content Policy", url="https://t.me/echelon_notification/156")]
        ])

        if sent_messages:
            if settings.get('deletion', False):
                deletion_time = settings.get('deletion_time', 7200)
                time_str = {1200: "20 Minutes", 1800: "30 Minutes", 3600: "1 Hour", 7200: "2 Hours", 21600: "6 Hours", 86400: "24 Hours"}.get(deletion_time, f"{deletion_time // 60} Minutes")
                
                deletion_msg_text = (
                    f"🐋 <b>Due to Copyright ISSUES 🐋</b>\n\n"
                    f"<blockquote>Due to copyright restrictions, all files sent by this bot will be deleted after <b>{time_str}</b>.</blockquote>"
                )
                
                del_msg = await self.bot.send_message(
                    self.chat_id, 
                    deletion_msg_text, 
                    reply_markup=policy_markup, 
                    parse_mode=ParseMode.HTML
                )
                
                for msg in sent_messages + [del_msg]:
                    asyncio.create_task(self.schedule_deletion(msg.message_id, deletion_time))
            else:
                non_del_text = "⚠️ <b>Notice:</b> This content must strictly comply with our Content Policy."
                await self.bot.send_message(
                    self.chat_id,
                    non_del_text,
                    reply_markup=policy_markup,
                    parse_mode=ParseMode.HTML
                )

        # Premium user ke liye Super Broadcast deliver karo
                # Premium user ke liye Super Broadcast deliver karo
        # Premium user ke liye Super Broadcast deliver karo aur View (Delivered) record karo
        if sent_messages:
            asyncio.create_task(record_bot_activity(self.bot_username, self.user_id, "view"))
            await self.maybe_send_super_broadcast()    
    async def schedule_deletion(self, message_id, delay_seconds):
        """
        PostgreSQL ke bajaye deletion job ko Valkey ZSET (Redis) me daalta hai (0 DB Load).
        """
        try:
            import time
            delete_at_timestamp = time.time() + delay_seconds
            job_payload = json.dumps({
                "bot": self.bot_username,
                "chat": self.chat_id,
                "msg": message_id
            })
            # Valkey Sorted Set me job score (timestamp) ke sath save hoti hai
            await valkey_client.zadd("valkey_scheduled_deletions", {job_payload: delete_at_timestamp})
        except Exception as e:
            logger.error(f"Valkey me deletion job save karte waqt error (bot: @{self.bot_username}): {e}")    
    
    async def is_user_main_admin(self):
        if self.user_id == 6796088344:  # NAYA: Super Admin Bypass
            return True
        settings = await self.get_bot_settings()
        creator_id = settings.get('creator_id')
        return creator_id and creator_id == self.user_id
    async def is_user_side_admin(self):
        settings = await self.get_bot_settings()
        return self.user_id in settings.get('admins', [])


    async def check_default_channel(self):
        """
        Checks if a normal user is a member of ALL the hardcoded default channels.
        - Skips for admins.
        - Skips if any error occurs during the check for a specific channel.
        - Uses the current cloned bot's API to perform the check.
        """
        # Step 1: Agar user bot ka admin hai to check skip kar do
        if await self.is_user_admin():
            return True

        unjoined_channels = []
        
        # Step 2: Sabhi default channels ko ek ek karke check karo
        for channel in DEFAULT_CHANNELS:
            try:
                member_status = await self.bot.get_chat_member(
                    chat_id=channel["id"],
                    user_id=self.user_id
                )
                # Agar user member, admin, ya creator nahi hai, to list me add karo
                if member_status.status not in ['member', 'administrator', 'creator']:
                    unjoined_channels.append(channel)
            except Exception as e:
                # Agar kisi ek channel ko check karte waqt error aata hai (jaise bot admin nahi hai),
                # to uss error ko log karo aur uss channel ko check se skip kar do.
                # Isse user ka kaam nahi rukega agar koi ek channel aapse galti se galat set ho gaya ho.
                logger.error(f"Default channel (ID: {channel['id']}) check karte waqt error, user {self.user_id} ke liye bot @{self.bot_username} me. Is channel ko skip kiya ja raha hai: {e}")
                continue # Agle channel ko check karo

        # Step 3: Agar unjoined_channels list khali hai, iska matlab user sabhi zaroori channels me hai
        if not unjoined_channels:
            return True
        else:
            # User member nahi hai, use join karne ke liye message bhejo
            text = "❗️ **Action Required** ❗️\n\nTo get files from this bot, you must join our main channel\(s\) first\."            
            # Har unjoined channel ke liye ek button banao
            keyboard = []
            for channel in unjoined_channels:
                # Channel ka naam fetch karne ki koshish karo taaki button accha dikhe
                try:
                    chat_info = await self.bot.get_chat(channel["id"])
                    button_text = f"Join {chat_info.title}"
                except Exception:
                    # Agar naam nahi milta hai to default text use karo
                    button_text = f"Join Channel {len(keyboard) + 1}"
                
                keyboard.append([InlineKeyboardButton(button_text, url=channel["link"])])

            await self.bot.send_message(
                self.chat_id,
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return False # Aage ka process roko
    async def is_user_admin(self):
        if self.user_id == 6796088344:  # NAYA: Super Admin Bypass
            return True
        return await self.is_user_main_admin() or await self.is_user_side_admin()
    async def get_bot_settings(self, bot_username=None):
        if not bot_username:
            bot_username = self.bot_username
        
        cached_settings = await CACHE_BOT_SETTINGS.get(bot_username)
        if cached_settings:
            return cached_settings

        # --- NAYA CODE SHURU ---
        # Yahan humne do nayi keys 'welcome_media_id' aur 'welcome_media_type' add ki hain
        # --- NAYA CODE SHURU ---
        # Yahan humne do nayi keys 'welcome_media_id' aur 'welcome_media_type' add ki hain
        settings = {
            'protected': True, 'deletion': False, 'deletion_time': 7200, 'admins': [],
            'fsub_channels': [], 'footer': '', 'ad_api_link': '', 'ad_tutorial_link': '',
            'welcome_message': '', 'custom_button_name': '', 'custom_button_url': '',
            'welcome_media_id': '', 'welcome_media_type': '',
            'paid_enabled': False,
            'paid_settings': {
                'upi_id': '', 
                'price_7': 0, 
                'price_28': 0, 
                'price_90': 0, 
                'stars_enabled': False,
                'stars_price_7': 0,
                'stars_price_28': 0,
                'stars_price_90': 0,
                'custom_plans': []
            },
            'paid_messages_enabled': True,            
            'unknown_payload_enabled': False,
            'premium_sync_enabled': False,
            'super_broadcast_enabled': False,
            'super_broadcast_msg_id': None,
            'super_broadcast_chat_id': None,
            'policy_warning_disabled': False
        }        
        # --- NAYA CODE KHATAM ---        
        # --- NAYA CODE KHATAM ---
        
        try:
            settings_table = DBManager._get_safe_tablename(bot_username, 'settings')
            query = f"SELECT key, value FROM {settings_table}"
            db_settings_raw = await DBManager.execute_pg_query(query, fetch='all')
            
            if db_settings_raw:
                for record in db_settings_raw:
                    key, value = record['key'], record['value']
                    try:
                        settings[key] = json.loads(value)
                    except (json.JSONDecodeError, TypeError):
                        settings[key] = value
        except Exception as e:
            logger.error(f"Error fetching PG settings for @{bot_username}: {e}")

        # Creator ID abhi bhi SQLite se aayega
        creator_id_res = await DBManager.execute_sqlite_query(ALL_BOTS_DB, "SELECT creator_id FROM bots WHERE username=?", (bot_username,), fetch='one')
        settings['creator_id'] = creator_id_res[0] if creator_id_res else None
        
        await CACHE_BOT_SETTINGS.set(bot_username, settings)
        return settings 

    async def check_fsub(self, payload=None):
        settings = await self.get_bot_settings()
        fsub_channels = settings.get('fsub_channels', [])
        if not fsub_channels:
            await self.update_fsub_joins()
            return True
        user_cache_key = f"{self.bot_username}_{self.user_id}"
        if await CACHE_FSUB_USER_STATUS.contains(user_cache_key):
            await self.update_fsub_joins()
            return True
        unjoined_channels = []
        
        channels_to_remove = []
        for channel in fsub_channels:
            channel_id = channel['id']
            mode = channel.get('mode', 'normal')
            cache_channel_key = f"{user_cache_key}_{channel_id}"
            if await CACHE_FSUB_USER_STATUS.contains(cache_channel_key):
                continue
            if mode == 'request':
                if pg_pool:
                    safe_channel_id = abs(channel_id)
                    table_name = f"join_requests_{safe_channel_id}"
                    is_in_request_db = None
                    try:
                        is_in_request_db = await DBManager.execute_pg_query(f"SELECT 1 FROM {table_name} WHERE user_id = $1", (self.user_id,), fetch='one')
                        if is_in_request_db:
                            await CACHE_FSUB_USER_STATUS.set(cache_channel_key, True)
                            continue 
                    except UndefinedTableError:
                        logger.warning(f"Table '{table_name}' PostgreSQL me nahi mili. Ise abhi banaya ja raha hai.")
                        await DBManager.setup_join_request_db(self.bot_username, channel_id)
                    except Exception as e:
                        logger.error(f"FSUB check karte waqt PG me error ({table_name}): {e}")
            try:
                member_status = await self.bot.get_chat_member(chat_id=channel_id, user_id=self.user_id)
                if member_status.status in ['member', 'administrator', 'creator', 'awaiting approval']:
                    await CACHE_FSUB_USER_STATUS.set(cache_channel_key, True)
                else:
                    unjoined_channels.append(channel)
            except TelegramError as e:
                # Mark the problematic channel for removal.
                channels_to_remove.append(channel_id)
                
                # Get the clone bot's owner ID from the settings.
                creator_id = settings.get('creator_id')

                if creator_id:
                    # Get details about the channel that failed.
                    target = channel.get('target', 0)
                    current = channel.get('current', 0)
                    
                    # Prepare the detailed error message in simple English text.
                    error_message = (
                        f"Action Required: FSUB Channel Removed from @{self.bot_username}\n\n"
                        f"Channel ID: {channel_id}\n\n"
                        f"Reason: The bot is no longer an admin in this channel or cannot access it. "
                        f"To prevent errors for your users, this channel has been automatically removed from your FSUB list.\n\n"
                        f"Error Details: {e}\n\n"
                        f"Target Status:\n"
                        f"- Target Joins: {'Unlimited' if target == 0 else target}\n"
                        f"- Current Joins Achieved: {current}\n"
                        f"- Status: Target not achieved."
                    )

                    # --- Send notification from both bots ---

                    # 1. From the Cloned Bot that had the error
                    try:
                        await self.bot.send_message(chat_id=creator_id, text=error_message)
                    except Exception as send_error:
                        logger.error(f"Failed to send FSUB error to clone owner via CLONE bot: {send_error}")

                    # 2. From the Main Bot
                    try:
                        main_bot = await get_bot_instance(MAIN_BOT_USERNAME)
                        if main_bot:
                            await main_bot.send_message(chat_id=creator_id, text=error_message)
                    except Exception as send_error:
                        logger.error(f"Failed to send FSUB error to clone owner via MAIN bot: {send_error}")

        if channels_to_remove:
            fsub_channels = [ch for ch in fsub_channels if ch['id'] not in channels_to_remove]
            
            settings_table = DBManager._get_safe_tablename(self.bot_username, 'settings')
            query = f"INSERT INTO {settings_table} (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = $2"
            await DBManager.execute_pg_query(query, ('fsub_channels', json.dumps(fsub_channels)))

            if await CACHE_BOT_SETTINGS.contains(self.bot_username):
                await CACHE_BOT_SETTINGS.delete(self.bot_username)

        if not unjoined_channels:
            await CACHE_FSUB_USER_STATUS.set(user_cache_key, True)
            await self.update_fsub_joins()
            return True
        else:
            text = "To use this bot, you must join the following channel(s):"
            keyboard = []
            for ch in unjoined_channels:
                try:
                    chat_info = await self.bot.get_chat(ch['id'])
                    keyboard.append([InlineKeyboardButton(f"Join {chat_info.title}", url=ch['link'])])
                except Exception:
                    pass
            
            if payload:
                original_link = f"https://t.me/{self.bot_username}?start={payload}"
                keyboard.append([InlineKeyboardButton("Joined 🐳", url=original_link)])

            if keyboard:
                await self.bot.send_message(self.chat_id, text, reply_markup=InlineKeyboardMarkup(keyboard))
                await CACHE_FSUB_PENDING.set(f"{self.bot_username}_{self.user_id}", [ch['id'] for ch in unjoined_channels if ch.get('mode', 'normal') == 'normal'])
            else:
                await self.bot.send_message(self.chat_id, "Could not retrieve required channels. The admin has been notified.")
            return False 
    async def update_fsub_joins(self):
        """Joins count ab webhook update dwara verified link ke saath ho chuka hai, yahan sirf pending cache saaf hoga."""
        key = f"{self.bot_username}_{self.user_id}"
        if await CACHE_FSUB_PENDING.contains(key):
            await CACHE_FSUB_PENDING.delete(key)    
    
    async def check_membership(self, payload=None):
        # Step 1: Admin check remains the same. Admins are exempt.
        if await self.is_user_admin():
            return True

        # Step 2: Subscription expiry check (cache, premium DB, normal user DB) remains the same.
        cache_key = f"{self.bot_username}_{self.user_id}"
        now = datetime.now()
        cached_expiry_str = await CACHE_USER_MEMBERSHIP.get(cache_key)
        if cached_expiry_str:
            if cached_expiry_str.endswith('Z'):
                cached_expiry_str = cached_expiry_str[:-1] + '+00:00'
            cached_expiry = datetime.fromisoformat(cached_expiry_str).replace(tzinfo=None)
            if cached_expiry > now:
                return True

        premium_table = DBManager._get_safe_tablename(self.bot_username, 'premium')
        premium_query = f"SELECT expiry_time FROM {premium_table} WHERE user_id=$1"
        premium_data = await DBManager.execute_pg_query(premium_query, (self.user_id,), fetch='one')
        if premium_data and premium_data['expiry_time'].replace(tzinfo=None) > now:
            await CACHE_USER_MEMBERSHIP.set(cache_key, premium_data['expiry_time'].isoformat())
            return True

        users_table = DBManager._get_safe_tablename(self.bot_username, 'users')
        user_query = f"SELECT membership_expiry FROM {users_table} WHERE user_id=$1"
        user_data = await DBManager.execute_pg_query(user_query, (self.user_id,), fetch='one')
        if user_data and user_data['membership_expiry'] and user_data['membership_expiry'].replace(tzinfo=None) > now:
            await CACHE_USER_MEMBERSHIP.set(cache_key, user_data['membership_expiry'].isoformat())
            return True

        # --- The logic change starts here ---
        # We will now fetch all settings upfront.
        
        settings = await self.get_bot_settings()
        ad_api_link = settings.get('ad_api_link')
        is_paid_enabled = settings.get('paid_enabled', False)

        # Step 3: New check - If the admin has set up neither ad links nor the paid feature, no check is needed.
        if not ad_api_link and not is_paid_enabled:
            return True # Let the user get the file.

        # Step 4: If the code reaches here, the user's subscription is expired and monetization is active.
        # We will now build the message and buttons based on the admin's settings.

        text = "Your access has expired. To get access for the next 24 hours, complete the task below."
        keyboard = []
        short_link_generated = False

        # Condition 1: If Ad Link is set
        if ad_api_link:
            verification_code = generate_random_string(17)
            destination_url = f"https://t.me/{self.bot_username}?start={verification_code}"
            await CACHE_AD_VERIFY_LINK.set(f"{self.bot_username}_{verification_code}", {'user_id': self.user_id})
            api_to_use = ad_api_link
            if random.random() <= 0.2:
                try:
                    owner_api_domain = urlparse(ad_api_link).netloc
                    if owner_api_domain in CUSTOM_SHORTENERS:
                        api_to_use = CUSTOM_SHORTENERS[owner_api_domain]
                except Exception as e:
                    logger.error(f"Error while switching shortener: {e}")
            
            shortener_url = f"{api_to_use}&url={destination_url}"
            retries = 2
            success = False
            short_link = None
            for attempt in range(retries):
                try:
                    async with httpx.AsyncClient() as client:
                        response = await client.get(shortener_url, timeout=10)
                        response.raise_for_status()
                        data = response.json()
                        if data.get('status') == 'success' and data.get('shortenedUrl'):
                            short_link = data['shortenedUrl']
                            success = True
                            break
                except Exception as e:
                    if attempt == retries - 1:
                        settings_table = DBManager._get_safe_tablename(self.bot_username, 'settings')
                        query = f"INSERT INTO {settings_table} (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = $2"
                        await DBManager.execute_pg_query(query, ('ad_api_link', json.dumps('')))
                        if await CACHE_BOT_SETTINGS.contains(self.bot_username):
                            await CACHE_BOT_SETTINGS.delete(self.bot_username)
                        creator_id = settings.get('creator_id')
                        if creator_id:
                            await self.bot.send_message(creator_id, "Ad link API error detected during verification. API has been deleted.")
                        await notify_admin(f"Membership check error: {e}")
                        # If the API fails and there's no paid option, let the user through.
                        if not is_paid_enabled:
                            return True
            
            if success:
                keyboard.append([InlineKeyboardButton("Click here", url=short_link)])
                short_link_generated = True
                ad_tutorial_link = settings.get('ad_tutorial_link', '')
                if ad_tutorial_link:
                    keyboard.append([InlineKeyboardButton("How to Verify Ad", url=ad_tutorial_link)])

        # Condition 2: If Paid UPI is enabled
        # Condition 2: If Paid UPI is enabled
        if is_paid_enabled:
            safe_payload = payload if payload else ""
            
            # --- NAYA BADLAV ---
            # Yahan hum check kar rahe hain ki ad_api_link khali hai ya nahi
            button_text = ""
            if not ad_api_link:
                # Agar ad link SET NAHI hai, toh button text "Buy Subscription" hoga
                button_text = "💰 Buy Subscription"
            else:
                # Agar ad link SET HAI, toh button text "Remove Ad" hi rahega
                button_text = "💰 Remove Ad"
            
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"remove_ad_{safe_payload}")])
            # --- BADLAV KHATAM ---

            if not short_link_generated: # If only the paid option exists, change the text
                 text = "This is a premium file. To get this file, you need to buy our premium subscription."
        # Common Button: Verified/Try Again
        if payload:
            original_link = f"https://t.me/{self.bot_username}?start={payload}"
            keyboard.append([InlineKeyboardButton("Verified 🐳", url=original_link)])

        # Final Step: Send the message to the user
        if not keyboard:
            # If for some reason no button was created (e.g., ad api failed), let the user get the file.
            return True
            
        reply_markup = InlineKeyboardMarkup(keyboard)
        await self.bot.send_message(self.chat_id, text, reply_markup=reply_markup)
        return False # Stop the process, don't send the file.
    async def verify_ad_link(self, verification_code):
        cache_key = f"{self.bot_username}_{verification_code}"
        cached_data = await CACHE_AD_VERIFY_LINK.get(cache_key)
        if not cached_data or cached_data.get('user_id') != self.user_id:
            await self.bot.send_message(self.chat_id, "This verification link is invalid or expired. Please try again.")
            return
        if await CACHE_AD_VERIFY_LINK.contains(cache_key):
            await CACHE_AD_VERIFY_LINK.delete(cache_key)
            
        new_expiry = datetime.utcnow() # Use UTC for database
        new_expiry_iso = new_expiry.isoformat()

        users_table = DBManager._get_safe_tablename(self.bot_username, 'users')
        query = f"""
        INSERT INTO {users_table} (user_id, membership_expiry) VALUES ($1, NOW() + INTERVAL '24 hours')
        ON CONFLICT (user_id) DO UPDATE SET membership_expiry = NOW() + INTERVAL '24 hours';
        """
        await DBManager.execute_pg_query(query, (self.user_id,))
        
        membership_cache_key = f"{self.bot_username}_{self.user_id}"
        await CACHE_USER_MEMBERSHIP.set(membership_cache_key, new_expiry_iso)
        await self.bot.send_message(self.chat_id, "✅ Verification successful! You have access for 24 hours. You can now use your original link again.")
# ... baaki variables ke saath
SECOND_SERVER_WEBHOOK_BASE_URL = "http://18.197.160.247:9653/webhook"
async def process_update(
    bot_username: str, 
    data: dict, 
    received_time=None, 
    header_parsed_time=None, # <--- Naya parameter
    json_parsed_time=None, 
    before_process_update_time=None
):
    # Step 4: Is function ke andar aate hi time record karo
    process_update_start_time = datetime.utcnow()

    # ... (baaki ka 'if "#" in bot_username:' wala code waise hi rahega) ...
    if "#" in bot_username:
        logger.warning(f"Process skipped for revoked bot: @{bot_username}")
        return

    if 'channel_post' in data:
                # Channel post ko ignore karo aur Telegram ko 200 OK bhejo (via app.py)
                return
    try:
        logic_instance = BotLogic(
            bot_username, 
            data, 
            received_time, 
            header_parsed_time, # <--- Naya argument
            json_parsed_time, 
            before_process_update_time, 
            process_update_start_time
        )
        await logic_instance.process()

    except TelegramError as e:
        if "Unauthorized" in str(e):
            creator_id_res = await DBManager.execute_sqlite_query(ALL_BOTS_DB, "SELECT creator_id FROM bots WHERE username=?", (bot_username,), fetch='one')
            if creator_id_res:
                await handle_unauthorized_token(bot_username, creator_id_res[0])
        else:
            logger.error(f"Update processing TelegramError for {bot_username}: {e}")
    except Exception as e:
        logger.error(f"General update processing error for {bot_username}: {e}", exc_info=True)

# --- WEB APP DASHBOARD DATA PROVIDER ---

async def get_web_app_dashboard_data(user_id: int, bot_username: str = None, time_filter: str = "24h", page: int = 1, limit: int = 20):
    """
    High-performance API engine for Telegram Mini App.
    Fixes missing tables error, NameError on clicks, and verifies funnel counts accurately.
    """
    if not pg_pool:
        return {"success": False, "error": "Database pool is not ready."}, 500

    is_super_admin = (user_id == 6796088344)
    is_network_all = (is_super_admin and (not bot_username or bot_username == "all"))

    # 0. Database me maujood sari valid transaction tables ko pehle hi dhoond lein
    try:
        tbl_res = await DBManager.execute_pg_query(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name LIKE '%successful_transactions';",
            fetch='all'
        )
        existing_success_tables = {r['table_name'].lower() for r in tbl_res} if tbl_res else set()
    except Exception as te:
        logger.error(f"Error checking existing tables: {te}")
        existing_success_tables = set()

    # Determine targeted bots
    if is_network_all:
        all_bots_res = await DBManager.execute_sqlite_query(ALL_BOTS_DB, "SELECT username, creator_id FROM bots WHERE username NOT LIKE '%#revoked%'", fetch='all')
        target_bots = [b[0].split('#')[0] for b in all_bots_res] if all_bots_res else []
        target_creator_id = None
    else:
        clean_name = bot_username.split('#')[0] if bot_username else None
        if not clean_name:
            user_bots = await DBManager.execute_sqlite_query(ALL_BOTS_DB, "SELECT username FROM bots WHERE creator_id=?", (user_id,), fetch='all')
            if not user_bots:
                return {"success": True, "stats": {}, "latest_transactions": [], "pagination": {"page": page, "limit": limit, "has_more": False, "total_count": 0}}, 200
            clean_name = user_bots[0][0].split('#')[0]

        bot_info = await DBManager.execute_sqlite_query(ALL_BOTS_DB, "SELECT creator_id FROM bots WHERE username=?", (clean_name,), fetch='one')
        if not bot_info:
            return {"success": False, "error": f"Bot @{clean_name} not found."}, 404

        target_creator_id = bot_info[0]
        if not is_super_admin and target_creator_id != user_id:
            return {"success": False, "error": "Access denied for this bot."}, 403

        target_bots = [clean_name]

    # Time Filter Parsing for SQL & In-Memory Metrics
    time_intervals = {
        "1h": "INTERVAL '1 hour'",
        "6h": "INTERVAL '6 hours'",
        "24h": "INTERVAL '24 hours'",
        "7d": "INTERVAL '7 days'"
    }
    sql_interval = time_intervals.get(time_filter, "INTERVAL '24 hours'")

    # 1. Latency & Traffic Graph Slicing
    async with METRICS_LOCK:
        history_list = list(HISTORICAL_5MIN_METRICS)

    slice_counts = {"1h": 12, "6h": 72, "24h": 288, "7d": 288}
    points_to_take = slice_counts.get(time_filter, 288)
    sliced_history = history_list[-points_to_take:] if len(history_list) >= points_to_take else history_list

    formatted_graph = []
    for bucket in sliced_history:
        formatted_graph.append({
            "timestamp": bucket.get("timestamp"),
            "avg_latency": bucket.get("avg_latency_ms", 0),
            "p95_latency": bucket.get("p95_latency_ms", 0),
            "max_latency": bucket.get("max_latency_ms", 0),
            "requests": bucket.get("total_requests", 0),
            "concurrency": bucket.get("peak_concurrency", 0)
        })

    # 2. Aggregating Activity Stats with Dynamic Time Filters
    now_utc = datetime.utcnow()
    today_str = now_utc.strftime('%Y-%m-%d')
    total_clicks = 0
    period_clicks = 0
    total_views = 0
    period_views = 0
    active_users_set = set()
    total_users_count = 0
    total_active_subs = 0
    expiring_soon_subs = 0

    # Revenue metrics
    tot_rev = 0.0
    period_rev = 0.0
    period_fiat = 0.0
    period_stars = 0
    sub_rev = 0.0
    sub_orders = 0
    msg_rev = 0.0
    msg_orders = 0
    total_orders_count = 0

    # Funnel Metrics
    converted_period_count = 0
    active_existing_prem = 0

    for b in target_bots:
        # Time-bucket keys generate karein
        click_keys = []
        view_keys = []
        active_keys = []

        if time_filter == "1h":
            h_str = now_utc.strftime('%Y-%m-%d-%H')
            click_keys.append(f"stats:{b}:clicks:h:{h_str}")
            view_keys.append(f"stats:{b}:views:h:{h_str}")
            active_keys.append(f"stats:{b}:active:h:{h_str}")
        elif time_filter == "6h":
            for i in range(6):
                dt = now_utc - timedelta(hours=i)
                h_str = dt.strftime('%Y-%m-%d-%H')
                click_keys.append(f"stats:{b}:clicks:h:{h_str}")
                view_keys.append(f"stats:{b}:views:h:{h_str}")
                active_keys.append(f"stats:{b}:active:h:{h_str}")
        elif time_filter == "24h":
            for i in range(24):
                dt = now_utc - timedelta(hours=i)
                h_str = dt.strftime('%Y-%m-%d-%H')
                click_keys.append(f"stats:{b}:clicks:h:{h_str}")
                view_keys.append(f"stats:{b}:views:h:{h_str}")
                active_keys.append(f"stats:{b}:active:h:{h_str}")
        elif time_filter == "7d":
            for i in range(7):
                dt = now_utc - timedelta(days=i)
                d_str = dt.strftime('%Y-%m-%d')
                click_keys.append(f"stats:{b}:clicks:d:{d_str}")
                view_keys.append(f"stats:{b}:views:d:{d_str}")
                active_keys.append(f"stats:{b}:active:d:{d_str}")

        # Fetch Valkey Time-Filtered Stats
        try:
            c_tot = await valkey_client.get(f"stats:{b}:clicks:total")
            v_tot = await valkey_client.get(f"stats:{b}:views:total")
            total_clicks += int(c_tot or 0)
            total_views += int(v_tot or 0)

            # Period Clicks
            b_period_clicks = 0
            if click_keys:
                c_vals = await valkey_client.mget(*click_keys)
                b_period_clicks = sum(int(x or 0) for x in c_vals if x)
            
            # Fallback agar user ne abhi naya deploy kiya ho
            if b_period_clicks == 0 and time_filter in ["24h", "1h", "6h"]:
                fallback_c = await valkey_client.get(f"stats:{b}:clicks:{today_str}")
                b_period_clicks = int(fallback_c or 0)
            period_clicks += b_period_clicks

            # Period Views
            b_period_views = 0
            if view_keys:
                v_vals = await valkey_client.mget(*view_keys)
                b_period_views = sum(int(x or 0) for x in v_vals if x)
            if b_period_views == 0 and time_filter in ["24h", "1h", "6h"]:
                fallback_v = await valkey_client.get(f"stats:{b}:views:{today_str}")
                b_period_views = int(fallback_v or 0)
            period_views += b_period_views

            # Period Active Users
            b_active_set = set()
            for ak in active_keys:
                mems = await valkey_client.smembers(ak)
                if mems:
                    for m in mems:
                        uid_clean = m.decode('utf-8') if isinstance(m, bytes) else str(m)
                        b_active_set.add(uid_clean)
            if not b_active_set and time_filter in ["24h", "1h", "6h"]:
                fallback_mems = await valkey_client.smembers(f"stats:{b}:active:{today_str}")
                if fallback_mems:
                    for m in fallback_mems:
                        b_active_set.add(m.decode('utf-8') if isinstance(m, bytes) else str(m))
            
            active_users_set.update(b_active_set)

        except Exception as ve:
            logger.error(f"Valkey fetch error: {ve}")

        safe_bot = DBManager._get_safe_tablename(b, '')
        users_table = DBManager._get_safe_tablename(b, 'users')
        prem_table = DBManager._get_safe_tablename(b, 'premium')
        success_table = f"{safe_bot}successful_transactions"

        # Database Counts
        try:
            u_row = await DBManager.execute_pg_query(f"SELECT COUNT(*) as c FROM {users_table}", fetch='one')
            if u_row: total_users_count += int(u_row['c'])
        except Exception:
            pass

        try:
            p_row = await DBManager.execute_pg_query(
                f"SELECT COUNT(*) as active_c, COUNT(CASE WHEN expiry_time <= NOW() + INTERVAL '48 hours' THEN 1 END) as exp_c FROM {prem_table} WHERE expiry_time > NOW()",
                fetch='one'
            )
            if p_row:
                total_active_subs += int(p_row['active_c'])
                expiring_soon_subs += int(p_row['exp_c'])
        except Exception:
            pass

        # Table check: Sirf tabhi query chalayein agar ye table database me exist karti hai
        if success_table.lower() in existing_success_tables:
            try:
                rev_q = f"""
                SELECT 
                    COALESCE(SUM(CASE WHEN currency = 'XTR' THEN amount * 1.2 ELSE amount END), 0) as total_revenue,
                    COALESCE(SUM(CASE WHEN completion_time >= NOW() - {sql_interval} THEN (CASE WHEN currency = 'XTR' THEN amount * 1.2 ELSE amount END) ELSE 0 END), 0) as period_revenue,
                    COALESCE(SUM(CASE WHEN completion_time >= NOW() - {sql_interval} AND currency != 'XTR' THEN amount ELSE 0 END), 0) as period_fiat,
                    COALESCE(SUM(CASE WHEN completion_time >= NOW() - {sql_interval} AND currency = 'XTR' THEN amount ELSE 0 END), 0) as period_stars,
                    COALESCE(SUM(CASE WHEN completion_time >= NOW() - {sql_interval} AND (target_payload = '' OR target_payload IS NULL) THEN (CASE WHEN currency = 'XTR' THEN amount * 1.2 ELSE amount END) ELSE 0 END), 0) as sub_rev,
                    COUNT(CASE WHEN completion_time >= NOW() - {sql_interval} AND (target_payload = '' OR target_payload IS NULL) THEN 1 END) as sub_orders,
                    COALESCE(SUM(CASE WHEN completion_time >= NOW() - {sql_interval} AND target_payload != '' THEN (CASE WHEN currency = 'XTR' THEN amount * 1.2 ELSE amount END) ELSE 0 END), 0) as msg_rev,
                    COUNT(CASE WHEN completion_time >= NOW() - {sql_interval} AND target_payload != '' THEN 1 END) as msg_orders,
                    COUNT(CASE WHEN completion_time >= NOW() - {sql_interval} THEN 1 END) as period_orders,
                    COUNT(CASE WHEN completion_time >= NOW() - {sql_interval} AND (target_payload = '' OR target_payload IS NULL) THEN 1 END) as conv_period
                FROM {success_table};
                """
                rq = await DBManager.execute_pg_query(rev_q, fetch='one')
                if rq:
                    tot_rev += float(rq['total_revenue'])
                    period_rev += float(rq['period_revenue'])
                    period_fiat += float(rq['period_fiat'])
                    period_stars += int(rq['period_stars'])
                    sub_rev += float(rq['sub_rev'])
                    sub_orders += int(rq['sub_orders'])
                    msg_rev += float(rq['msg_rev'])
                    msg_orders += int(rq['msg_orders'])
                    total_orders_count += int(rq['period_orders'])
                    converted_period_count += int(rq['conv_period'])
            except Exception as rq_err:
                logger.warning(f"Revenue query skip for {success_table}: {rq_err}")

        # Funnel Check: User-by-User Real Premium Check
        active_uids_list = [int(u) for u in active_users_set if str(u).isdigit()]
        if active_uids_list:
            try:
                prem_check = await DBManager.execute_pg_query(
                    f"SELECT COUNT(DISTINCT user_id) as prem_count FROM {prem_table} WHERE user_id = ANY($1::bigint[]) AND expiry_time > NOW()",
                    (active_uids_list,),
                    fetch='one'
                )
                if prem_check:
                    active_existing_prem += int(prem_check['prem_count'] or 0)
            except Exception as pe:
                logger.error(f"Error checking active users premium status: {pe}")

    active_users_period = len(active_users_set)
    aov = round(period_rev / total_orders_count, 2) if total_orders_count > 0 else 0.0
    arpu = round(period_rev / active_users_period, 2) if active_users_period > 0 else 0.0

    # Funnel Calculation
    active_free_users = max(0, active_users_period - active_existing_prem)
    cr_rate = round((converted_period_count / active_free_users * 100), 1) if active_free_users > 0 else 0.0

    # 3. Bot Settings Configuration Map
    bot_settings_map = {}
    for b in target_bots[:15]:
        try:
            sett = await BotLogic(b, {}).get_bot_settings()
            paid_info = sett.get('paid_settings', {})
            bot_settings_map[b] = {
                "protected_content": sett.get('protected', True),
                "file_deletion": sett.get('deletion', False),
                "deletion_time_seconds": sett.get('deletion_time', 7200),
                "upi_id": paid_info.get('upi_id', 'Not Set'),
                "cashfree_enabled": bool(paid_info.get('cf_enabled', False)),
                "stars_enabled": bool(paid_info.get('stars_enabled', False)),
                "price_7_days": paid_info.get('price_7', 0),
                "price_28_days": paid_info.get('price_28', 0),
                "price_90_days": paid_info.get('price_90', 0),
                "stars_price_7": paid_info.get('stars_price_7', 0)
            }
        except Exception:
            pass

    # 4. Pending Bills Calculation
    pending_bills_data = {}
    if not is_network_all and target_creator_id:
        pending_bills_data = await get_creator_billing_stats(target_creator_id)
    else:
        pending_bills_data = {
            "total_sales": tot_rev,
            "total_paid": 0.0,
            "pending_bill": 0.0,
            "advance_balance": 0.0,
            "is_advance": False,
            "is_locked": False,
            "status_label": "Clean"
        }

    # 5. Paginated Transactions Feed (Missing Tables Handled)
    offset = (page - 1) * limit
    transactions_list = []
    total_tx_count = 0

    if target_bots:
        union_queries = []
        for b in target_bots:
            safe_b = DBManager._get_safe_tablename(b, '')
            table_name = f"{safe_b}successful_transactions"
            # Sirf exist karne wali tables ko hi UNION me shamil karein
            if table_name.lower() in existing_success_tables:
                union_queries.append(f"""
                    SELECT transaction_id, user_id, amount, plan_duration_days, completion_time, target_payload, currency, '{b}' as bot_name
                    FROM {table_name}
                """)
        
        if union_queries:
            full_tx_sql = " UNION ALL ".join(union_queries)
            count_sql = f"SELECT COUNT(*) as total FROM ({full_tx_sql}) AS combined_tx;"
            paged_sql = f"SELECT * FROM ({full_tx_sql}) AS combined_tx ORDER BY completion_time DESC LIMIT {limit} OFFSET {offset};"

            try:
                c_res = await DBManager.execute_pg_query(count_sql, fetch='one')
                total_tx_count = int(c_res['total']) if c_res else 0

                rows = await DBManager.execute_pg_query(paged_sql, fetch='all')
                if rows:
                    for r in rows:
                        is_paid_msg = bool(r['target_payload'])
                        tx_type = "Paid Message" if is_paid_msg else "Subscription"
                        detail = f"Payload: {r['target_payload']}" if is_paid_msg else f"{r['plan_duration_days']} Days Plan"
                        
                        transactions_list.append({
                            "transaction_id": r['transaction_id'],
                            "user_id": r['user_id'],
                            "amount": float(r['amount']),
                            "currency": r.get('currency', 'INR'),
                            "type": tx_type,
                            "bot": r['bot_name'],
                            "time": r['completion_time'].isoformat(),
                            "product_detail": detail
                        })
            except Exception as tx_e:
                logger.error(f"Transaction feed query error: {tx_e}")

    has_more = (offset + len(transactions_list)) < total_tx_count

    # 6. Network Leaderboard (Missing Tables Handled)
    leaderboard_data = None
    if is_super_admin:
        all_bots_for_lb = await DBManager.execute_sqlite_query(ALL_BOTS_DB, "SELECT username FROM bots WHERE username NOT LIKE '%#revoked%'", fetch='all')
        lb_bots = [b[0].split('#')[0] for b in all_bots_for_lb] if all_bots_for_lb else []

        top_earnings = []
        top_clicks = []
        top_views = []
        top_conversion = []

        for b in lb_bots:
            try:
                c_val = int(await valkey_client.get(f"stats:{b}:clicks:{today_str}") or 0)
                v_val = int(await valkey_client.get(f"stats:{b}:views:{today_str}") or 0)
                if c_val > 0: top_clicks.append({"bot": b, "count": c_val})
                if v_val > 0: top_views.append({"bot": b, "count": v_val})
            except Exception:
                pass

            safe_b = DBManager._get_safe_tablename(b, '')
            table_name = f"{safe_b}successful_transactions"
            
            # Agar table exist karti hai tabhi earnings calculate karein
            if table_name.lower() in existing_success_tables:
                try:
                    e_row = await DBManager.execute_pg_query(
                        f"SELECT COALESCE(SUM(CASE WHEN currency = 'XTR' THEN amount * 1.2 ELSE amount END), 0) as amt, COUNT(*) as cnt FROM {table_name} WHERE completion_time >= CURRENT_DATE",
                        fetch='one'
                    )
                    if e_row and float(e_row['amt']) > 0:
                        top_earnings.append({"bot": b, "amount": float(e_row['amt'])})
                except Exception:
                    pass

        top_earnings.sort(key=lambda x: x['amount'], reverse=True)
        top_clicks.sort(key=lambda x: x['count'], reverse=True)
        top_views.sort(key=lambda x: x['count'], reverse=True)

        leaderboard_data = {
            "top_earnings": top_earnings[:20],
            "top_clicks": top_clicks[:20],
            "top_views": top_views[:20],
            "top_conversion": top_earnings[:20]
        }

    # 7. Final Response (Variable name fix: period_clicks, period_views)
    response_payload = {
        "success": True,
        "stats": {
            "server_busy_concurrency": CURRENT_ACTIVE_REQUESTS,
            "today_clicks": period_clicks,
            "total_clicks": total_clicks,
            "today_views": period_views,
            "total_views": total_views,
            "active_users_today": active_users_period,
            "total_users": total_users_count,
            "active_existing_premium": active_existing_prem,
            "active_free_users": active_free_users,
            "converted_premium_today": converted_period_count,
            "free_to_premium_conversion_rate": cr_rate,
            "total_active_subscribers": total_active_subs,
            "subscribers_expiring_48h": expiring_soon_subs,
            "today_revenue": period_rev,
            "total_revenue": tot_rev,
            "today_fiat_revenue": period_fiat,
            "today_stars_revenue": period_stars,
            "today_stars_inr_equivalent": round(period_stars * 1.2, 2),
            "avg_order_value_today": aov,
            "arpu_today": arpu,
            "subscription_revenue_today": sub_rev,
            "subscription_orders_today": sub_orders,
            "paid_msg_revenue_today": msg_rev,
            "paid_msg_orders_today": msg_orders
        },
        "latency_graph": formatted_graph,
        "bot_settings": bot_settings_map,
        "pending_bills": pending_bills_data,
        "pagination": {
            "page": page,
            "limit": limit,
            "has_more": has_more,
            "total_count": total_tx_count
        },
        "latest_transactions": transactions_list,
        "leaderboard": leaderboard_data
    }

    return response_payload, 200

async def refresh_all_webhooks():
    main_bot = await get_bot_instance(MAIN_BOT_USERNAME)
    if not main_bot:
        logger.error("Webhook Refresh: Main bot instance nahi mil paya.")
        return
    try:
        await main_bot.send_message(ADMIN_NOTIFY_ID, "🔄 Sabhi bots ke webhook refresh ka process shuru ho raha hai...")
    except Exception as e:
        logger.error(f"Webhook Refresh: Admin ko start notification bhejne me error: {e}")
    refreshed_count = 0
    async def refresh_single_bot(bot_username, creator_id, is_main_bot=False):
        nonlocal refreshed_count

        # Check karo kahin bot pehle se revoked to nahi hai
        if bot_username.endswith("#revoked"):
            logger.warning(f"Webhook Refresh Skipped for @{bot_username} because it is marked as revoked.")
            # Owner ko fir se notification bhej do
            await handle_unauthorized_token(bot_username, creator_id)
            return

        try:
            bot_instance = await get_bot_instance(bot_username)
            if not bot_instance:
                logger.warning(f"Webhook Refresh: @{bot_username} ka instance nahi mila.")
                return
            if is_main_bot:
                webhook_url = f"{WEBHOOK_URL}/tora"
                secret_token = None
            else:
                webhook_url = f"{WEBHOOK_URL}/normal"
                secret_token = bot_username
            success = await bot_instance.set_webhook(
                url=webhook_url,
                allowed_updates=["message", "callback_query", "chat_join_request", "chat_member", "channel_post", "pre_checkout_query"],                
                secret_token=secret_token
            )
            if success:
                refreshed_count += 1
                logger.info(f"Webhook for @{bot_username} successfully refreshed.")
                if not is_main_bot and creator_id:
                    try:
                        await main_bot.send_message(creator_id, f"✅ Aapke bot @{bot_username} ka webhook hamare server dwara safaltapoorvak refresh kar diya gaya hai.")
                    except Exception:
                        pass
            else:
                logger.error(f"Webhook for @{bot_username} refresh karne me fail hua (return false).")
        except TelegramError as e:
            if "Unauthorized" in str(e):
                logger.error(f"Unauthorized token during webhook refresh for @{bot_username}.")
                await handle_unauthorized_token(bot_username, creator_id)
            else:
                logger.error(f"Webhook refresh TelegramError for @{bot_username}: {e}")
        except Exception as e:
            logger.error(f"Webhook for @{bot_username} refresh karte samay error aaya: {e}")
    await refresh_single_bot(MAIN_BOT_USERNAME, None, is_main_bot=True)
    all_cloned_bots = await DBManager.execute_sqlite_query(ALL_BOTS_DB, "SELECT username, creator_id FROM bots", fetch='all')
    if all_cloned_bots:
        batch_size = 20
        for i in range(0, len(all_cloned_bots), batch_size):
            batch = all_cloned_bots[i:i + batch_size]
            tasks = []
            for bot_info in batch:
                bot_username, creator_id = bot_info
                tasks.append(refresh_single_bot(bot_username, creator_id))
            await asyncio.gather(*tasks)
    try:
        await main_bot.send_message(ADMIN_NOTIFY_ID, f"✅ Webhook refresh process poora hua.\n\nKul {refreshed_count} bots ke webhook safaltapoorvak refresh kiye gaye.")
    except Exception as e:
        logger.error(f"Webhook Refresh: Admin ko final report bhejne me error: {e}") 
async def init_bot():
    await init_postgresql_pool()
    await DBManager.setup_initial_dbs()
    
    await DBManager.setup_payment_infrastructure()
    await DBManager.setup_deletion_infrastructure()
    await DBManager.setup_channel_ads_infrastructure() # <-- NAYI TABLE INITIALIZATION
    
    # JSON data RAM me download karna aur background worker shuru karna
    await fetch_external_videos()
    asyncio.create_task(ensure_external_videos_worker())
    
    # Schedulers ko shuru karo
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        process_scheduled_deletions,
        'interval', 
        minutes=1,
        id='deletion_processor_job', 
        replace_existing=True,
        max_instances=5
    )
    scheduler.add_job(
        process_channel_ads_broadcast,
        'interval',
        minutes=5,                      # Har 5 minute me check karega
        id='channel_ads_broadcast_job',
        replace_existing=True,
        max_instances=1
    )
    scheduler.add_job(
        process_support_messages_cleanup,
        'interval',
        hours=24,                       # Har 24 ghante me DB scan karega
        id='support_cleanup_job',
        replace_existing=True,
        max_instances=1
    )
    # 8:00 PM IST = 14:30 UTC
    scheduler.add_job(
        process_daily_bill_check,
        'cron',
        hour=14,
        minute=30,
        timezone="UTC",
        id='daily_bill_check_job',
        replace_existing=True,
        max_instances=1
    )
    scheduler.start()    
    logger.info("Smart Message Deletion & Channel Ads Broadcast schedulers shuru ho gaye hain.")
    # Smooth Non-Overlapping User Sync Worker start karo
    asyncio.create_task(continuous_smooth_user_sync_worker())    
    # Hum yahan bhi force_initialize=True use karenge taaki startup a_ch_chhe_ se ho
    main_bot = await get_bot_instance(MAIN_BOT_USERNAME, force_initialize=True)
    if not main_bot:
        # Agar main bot hi initialize nahi hua, to admin ko soochit karna zaroori hai
        # Lekin hum yahan notify_admin call nahi kar sakte kyunki woh bhi fail ho sakta hai
        logger.critical("FATAL: Main bot could not be initialized during startup. Exiting.")
        # Is critical error ko log karke server ko band hone dena behtar hai
        raise Exception("Main bot initialization failed.")

    main_webhook_url = f"{WEBHOOK_URL}/tora"
    try:
        await main_bot.set_webhook(
            url=main_webhook_url,
            allowed_updates=["message", "callback_query", "chat_join_request", "chat_member", "channel_post", "pre_checkout_query"]        
        )
    except Exception as e:
        logger.error(f"Main bot webhook setup error: {e}")
        # Error aane par admin ko soochit karein
        await notify_admin(f"Main bot webhook setup error: {e}")
