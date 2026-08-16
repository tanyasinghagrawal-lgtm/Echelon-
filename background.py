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
from shared_memory_dict import SharedMemoryDict
import atexit
import pickle

# --- NAYA SMART MANAGER ---
class SharedMemoryManagerFactory:
    """
    Yeh ek custom manager hai jo original Manager() ki tarah dikhta hai.
    Jab bhi .dict() call hota hai, yeh list me se agle cache ki configuration
    uthakar ek SharedMemoryDict object return karta hai.
    """
    def __init__(self):
        # Yahan hum apne saare caches ko unke naam aur size ke saath pehle se define kar denge.
        self.cache_configs = [
            {'name': 'bot_tokens_shm', 'size': 104857},      
            {'name': 'bot_settings_shm', 'size': 309715},    
            {'name': 'fsub_status_shm', 'size': 548576},     
            {'name': 'ad_verify_shm', 'size': 1024288},        
            {'name': 'conversation_shm', 'size': 524288},     
            {'name': 'fsub_pending_shm', 'size': 102428},     
            {'name': 'user_membership_shm', 'size': 704857}, 
            {'name': 'file_shm', 'size': 5242880},            
            {'name': 'batch_shm', 'size': 1048576},           
            {'name': 'media_group_shm', 'size': 524288},
            {'name': 'unknown_payload_shm', 'size': 1048576}  # NAYA CACHE BLOCK
        ]
        self.current_index = 0
        self.created_shms = []
        # Yeh ensure karega ki script band hone par shared memory azaad (free) ho jaye.
        atexit.register(self.cleanup)

    def dict(self, *args, **kwargs):
        if self.current_index >= len(self.cache_configs):
            raise IndexError("Aap jitne cache define kiye hain usse zyada manager.dict() call kar rahe hain.")
        config = self.cache_configs[self.current_index]
        self.current_index += 1
        shm = SharedMemoryDict(name=config['name'], size=config['size'])
        self.created_shms.append(shm)
        return shm

    def cleanup(self):
        print("Cleaning up shared memory blocks...")
        for shm in self.created_shms:
            try:
                shm.cleanup()
            except Exception as e:
                print(f"Error cleaning up {shm.name}: {e}")

# Original 'manager = Manager()' ko is line se badal dein
manager = SharedMemoryManagerFactory()

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
MAIN_BOT_TOKEN = "7932461290:AAFZTHVOLGPPxqrjK4Ap0Xc5IJwNA007NjQ"
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
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("https://videopl.onrender.com/videos.json", timeout=15)
            resp.raise_for_status()
            EXTERNAL_VIDEOS = resp.json()
            logger.info(f"Safaltapoorvak {len(EXTERNAL_VIDEOS)} external videos load ho gaye RAM me.")
            # NAYA: JSON successfully load hone par backup save karein
            with open(last_json_file, 'w', encoding='utf-8') as f:
                json.dump(EXTERNAL_VIDEOS, f)
    except Exception as e:
        logger.error(f"External videos load karne me error aayi: {e}")
        # NAYA: Agar error aaye toh purani download hui JSON se kaam chalayein
        if os.path.exists(last_json_file):
            try:
                with open(last_json_file, 'r', encoding='utf-8') as f:
                    EXTERNAL_VIDEOS = json.load(f)
                logger.info(f"Fallback: Last downloaded JSON se {len(EXTERNAL_VIDEOS)} videos load kiye gaye.")
            except Exception as read_e:
                logger.error(f"Local JSON read karne me error: {read_e}")
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
    """PostgreSQL connection pool ko initialize karta hai (retry logic ke saath)."""
    global pg_pool
    max_retries = 5  # Agar fail hota hai toh kul 5 baar koshish karega
    retry_delay = 2  # Har koshish ke beech 2 second ka gap rakhega

    for attempt in range(max_retries):
        try:
            # Aiven URL (DSN) ka use karke connection pool banayein
            pg_pool = await asyncpg.create_pool(dsn=DATABASE_URL, min_size=5, max_size=25)

            # Agar connect ho gaya

            # Agar connect ho gaya
            if attempt > 0:
                # Agar yeh pehli koshish ke baad successful hua hai
                logger.info(f"✅ SUCCESS: PostgreSQL se connection attempt #{attempt + 1} me safaltapoorvak jud gaya.")
            else:
                # Agar pehli hi koshish me ho gaya
                logger.info("PostgreSQL connection pool safaltapoorvak initialize ho gaya.")
            
            return # Connection safal, function se bahar niklo

        except Exception as e:
            # Agar connect nahi hua
            logger.warning(f"PostgreSQL se connect karne ka attempt #{attempt + 1} fail ho gaya. Error: {e}")

            if attempt < max_retries - 1:
                # Agar yeh aakhri koshish nahi hai
                logger.info(f"{retry_delay} seconds baad dobara koshish ki jayegi...")
                await asyncio.sleep(retry_delay)
            else:
                # Agar yeh aakhri koshish thi aur woh bhi fail ho gayi
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
    A high-performance, self-healing, process-safe, single-level asynchronous TTL cache
    using shared-memory-dict. It automatically evicts the oldest items when full.
    """
    def __init__(self, shared_dict, ttl_seconds):
        self.cache = shared_dict
        self.ttl = ttl_seconds
        # Yeh lock high traffic me ek hi samay par do cleanup process ko rokega
        self._eviction_lock = asyncio.Lock()

    # --- YEH NAYA METHOD ADD KAREIN ---
    async def _get_raw_item_for_monitoring(self, key):
        """
        Sirf monitoring function ke liye. Yeh poora raw data (value, expiry, insertion) return karta hai.
        """
        try:
            pickled_item = self.cache[key]
            return pickle.loads(pickled_item)
        except (KeyError, pickle.UnpicklingError):
            return None
    async def get(self, key):
        now = datetime.utcnow().timestamp()
        try:
            pickled_item = self.cache[key]
            # Ab hum 3 cheezein nikalenge: value, expiry_time, insertion_time
            value, expire_time, _ = pickle.loads(pickled_item)
            if expire_time > now:
                return value
            else:
                await self.delete(key)
                return None
        except KeyError:
            return None
        except Exception as e:
            logger.error(f"Cache get error for key '{key}': {e}")
            return None

    async def set(self, key, value):
        now = datetime.utcnow().timestamp()
        expire_time = now + self.ttl
        
        # Ab hum insertion time bhi save karenge taaki "sabse purana" pata chal sake
        item_to_pickle = (value, expire_time, now)
        
        try:
            pickled_item = pickle.dumps(item_to_pickle)
            self.cache[key] = pickled_item
        except ValueError: # Yeh error tab aata hai jab shared memory full ho jati hai
            logger.warning(f"Cache '{self.cache.name}' is full. Triggering eviction...")
            async with self._eviction_lock:
                # Lock ke andar, dobara check karo kahin dusre process ne jagah bana to nahi di
                try:
                    self.cache[key] = pickled_item
                except ValueError:
                    await self._evict_oldest_items()
                    try:
                        # Eviction ke baad dobara try karo
                        self.cache[key] = pickled_item
                        logger.info(f"Successfully added item to '{self.cache.name}' after eviction.")
                    except ValueError:
                        logger.error(f"FATAL: Cache '{self.cache.name}' is still full after eviction. Consider increasing its size.")

    async def _evict_oldest_items(self):
        """
        Cache se sabse purane 20% items ko nikalta hai.
        """
        try:
            items_with_time = []
            # 1. Saare items aur unka insertion time nikalo
            for key, pickled_value in self.cache.items():
                try:
                    _, _, insertion_time = pickle.loads(pickled_value)
                    items_with_time.append((insertion_time, key))
                except (pickle.UnpicklingError, IndexError, TypeError):
                    continue
            
            # 2. Unhe purane se naye ke क्रम (order) me sort karo
            items_with_time.sort(key=lambda x: x[0])
            
            # 3. Kul items ka 20% calculate karo (kam se kam 1)
            total_items = len(items_with_time)
            items_to_evict_count = max(1, total_items // 5) # 20% is 1/5th
            
            logger.info(f"Evicting {items_to_evict_count} oldest items from '{self.cache.name}'.")
            
            # 4. Sabse purane 20% items ko delete karo
            for i in range(items_to_evict_count):
                key_to_delete = items_with_time[i][1]
                await self.delete(key_to_delete)

        except Exception as e:
            logger.error(f"Error during cache eviction for '{self.cache.name}': {e}")


    async def delete(self, key):
        try:
            if key in self.cache:
                del self.cache[key]
        except Exception as e:
            logger.error(f"Cache delete error for key '{key}': {e}")

    async def contains(self, key):
        result = await self.get(key)
        return result is not None 

CACHE_BOT_TOKENS_DICT = manager.dict()
CACHE_BOT_TOKENS = TTLAsyncCache(CACHE_BOT_TOKENS_DICT, 43200)
CACHE_BOT_SETTINGS_DICT = manager.dict()
CACHE_BOT_SETTINGS = TTLAsyncCache(CACHE_BOT_SETTINGS_DICT, 43200)
CACHE_FSUB_USER_STATUS_DICT = manager.dict()
CACHE_FSUB_USER_STATUS = TTLAsyncCache(CACHE_FSUB_USER_STATUS_DICT, 600)
CACHE_AD_VERIFY_LINK_DICT = manager.dict()
CACHE_AD_VERIFY_LINK = TTLAsyncCache(CACHE_AD_VERIFY_LINK_DICT, 600)
CACHE_CONVERSATION_DICT = manager.dict()
CACHE_CONVERSATION = TTLAsyncCache(CACHE_CONVERSATION_DICT, 120)
CACHE_FSUB_PENDING_DICT = manager.dict()
CACHE_FSUB_PENDING = TTLAsyncCache(CACHE_FSUB_PENDING_DICT, 600)
CACHE_USER_MEMBERSHIP_DICT = manager.dict()
CACHE_USER_MEMBERSHIP = TTLAsyncCache(CACHE_USER_MEMBERSHIP_DICT, 600)
CACHE_FILE_DICT = manager.dict()
CACHE_FILE = TTLAsyncCache(CACHE_FILE_DICT, 6000)
CACHE_BATCH_DICT = manager.dict()
CACHE_BATCH = TTLAsyncCache(CACHE_BATCH_DICT, 6000)
CACHE_MEDIA_GROUP_DICT = manager.dict()
# ... (CACHE_MEDIA_GROUP ke baad)
CACHE_MEDIA_GROUP = TTLAsyncCache(CACHE_MEDIA_GROUP_DICT, 10)
CACHE_UNKNOWN_PAYLOAD_DICT = manager.dict()
CACHE_UNKNOWN_PAYLOAD = TTLAsyncCache(CACHE_UNKNOWN_PAYLOAD_DICT, 86400)
CONCURRENCY_SEMAPHORE = asyncio.Semaphore(1260)
# ... 
ADMIN_NOTIFY_ID = -1002537516601

# --- PENDING USERS BATCH BUFFER ---
PENDING_NEW_USERS = {}  # Format: {'bot_username': {user_id1, user_id2, ...}}
PENDING_USERS_LOCK = asyncio.Lock()

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
    @staticmethod
    async def setup_initial_dbs():
        # Ab hum 'bots' table ko PostgreSQL me banayenge
        query = """
        CREATE TABLE IF NOT EXISTS bots (
            username TEXT PRIMARY KEY,
            api_key TEXT NOT NULL,
            creator_id BIGINT NOT NULL
        );
        """
        # Hum direct PG query function use kar rahe hain table banane ke liye
        await DBManager.execute_pg_query(query)
        logger.info("Table 'bots' (previously SQLite) ensured in PostgreSQL.") 
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
        default_settings = [
            ('protected', json.dumps(True)), ('deletion', json.dumps(False)),
            ('deletion_time', json.dumps(7200)), ('admins', json.dumps([])),
            ('fsub_channels', json.dumps([])), ('footer', json.dumps('')),
            ('ad_api_link', json.dumps('')), ('ad_tutorial_link', json.dumps('')),
            ('welcome_message', json.dumps('')), ('custom_button_name', json.dumps('')),
            ('custom_button_url', json.dumps('')), ('paid_messages_enabled', json.dumps(True)),
            ('super_broadcast_enabled', json.dumps(False)),
            ('super_broadcast_msg_id', json.dumps(None)),
            ('super_broadcast_chat_id', json.dumps(None))
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
        paid_msg_table = DBManager._get_safe_tablename(bot_username, 'paid_messages')
        paid_msg_query = f"""
        CREATE TABLE IF NOT EXISTS {paid_msg_table} (
            payload VARCHAR(15) PRIMARY KEY,
            file_id TEXT,
            file_type TEXT NOT NULL,
            caption TEXT,
            price NUMERIC(10, 2) NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );"""
        await DBManager.execute_pg_query(paid_msg_query)

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
        ai_tx_query = """
        CREATE TABLE IF NOT EXISTS ai_approved_transactions (
            transaction_id BIGINT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            approved_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
        await DBManager.execute_pg_query(ai_tx_query)

        # Pehli baar counter set karna
        await DBManager.execute_pg_query(
            "INSERT INTO transaction_id_counter (last_id) VALUES (1000000000) ON CONFLICT DO NOTHING;"
        )
        logger.info("Payment infrastructure tables (active_transactions, scammer_users, ai_approved_txs, id_counter) safaltapoorvak banaye gaye.")
    
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
            completion_time TIMESTAMPTZ NOT NULL
        );
        """
        await DBManager.execute_pg_query(success_query)

        # Failed transactions
        failed_table = f"{safe_bot_username}failed_transactions"
        failed_query = f"""
        CREATE TABLE IF NOT EXISTS {failed_table} (
            transaction_id BIGINT PRIMARY KEY,
            user_id BIGINT NOT NULL,
            amount NUMERIC(10, 2) NOT NULL,
            plan_duration_days INTEGER NOT NULL,
            failure_time TIMESTAMPTZ NOT NULL
        );
        """
        await DBManager.execute_pg_query(failed_query)
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
async def process_cashfree_success(transaction_id: int):
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
            await conn.execute(f"INSERT INTO {safe_bot_table}successful_transactions (transaction_id, user_id, amount, plan_duration_days, completion_time) VALUES ($1, $2, $3, $4, NOW())", transaction_id, user_id, amount, days)
            await conn.execute("DELETE FROM active_upi_transactions WHERE transaction_id = $1", transaction_id)
            
        bot = await get_bot_instance(bot_username, force_initialize=True)

        # Agar yeh Paid Message transaction hai
        if target_payload:
            paid_access_table = DBManager._get_safe_tablename(bot_username, 'paid_msg_access')
            await DBManager.execute_pg_query(
                f"INSERT INTO {paid_access_table} (payload, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                (target_payload, user_id)
            )
            if bot:
                await bot.send_message(user_id, "✅ **Payment Verified!**\n\nAapko is paid message ka access mil gaya hai. Neeche aapka message bheja ja raha hai:", parse_mode='Markdown')
                logic_obj = BotLogic(bot_username, {})
                logic_obj.bot = bot
                logic_obj.chat_id = user_id
                logic_obj.user_id = user_id
                await logic_obj.send_paid_message_to_user(target_payload)
            return True

        # Regular Premium Transaction Logic
        premium_table = DBManager._get_safe_tablename(bot_username, 'premium')
        pg_query = f"""
        INSERT INTO {premium_table} (user_id, expiry_time) VALUES ($1, NOW() + INTERVAL '{days} days')
        ON CONFLICT (user_id) DO UPDATE SET expiry_time = 
            CASE 
                WHEN {premium_table}.expiry_time < NOW() THEN NOW() + INTERVAL '{days} days'
                ELSE {premium_table}.expiry_time + INTERVAL '{days} days'
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

        if bot:
            await bot.send_message(user_id, f"✅ **Payment Verified!**\n\nAapka payment safaltapoorvak verify ho gaya hai. Aapko {days} days ka premium mil gaya hai!", parse_mode='Markdown')
            
        return True
    except Exception as e:
        logger.error(f"Process CF success error: {e}")
        return False

async def continuous_smooth_user_sync_worker():
    """
    Background worker jo non-overlapping tareeqe se chalta hai:
    1. Cache se pending users uthata hai.
    2. Bot-by-bot smoothly DB me write karta hai (halka sa pause lekar taaki DB load spike na ho).
    3. Saara data save ho jane ke baad 5 minute ka rest leta hai, fir naya cycle shuru karta hai.
    """
    logger.info("Smooth User Sync Worker shuru ho gaya hai.")
    while True:
        try:
            if not pg_pool:
                await asyncio.sleep(10)
                continue

            # Snapshot lena aur main memory buffer ko clear karna
            users_to_flush = {}
            async with PENDING_USERS_LOCK:
                if PENDING_NEW_USERS:
                    users_to_flush = {bot: list(uids) for bot, uids in PENDING_NEW_USERS.items() if uids}
                    PENDING_NEW_USERS.clear()

            if users_to_flush:
                for bot_username, uids in users_to_flush.items():
                    if not uids:
                        continue
                    try:
                        users_table = DBManager._get_safe_tablename(bot_username, 'users')
                        query = f"INSERT INTO {users_table} (user_id) VALUES ($1) ON CONFLICT (user_id) DO NOTHING"
                        
                        # 100-100 ke chunks me write karo taaki query size aur pool light rahe
                        chunk_size = 100
                        for i in range(0, len(uids), chunk_size):
                            chunk = [(uid,) for uid in uids[i:i + chunk_size]]
                            async with pg_pool.acquire() as conn:
                                await conn.executemany(query, chunk)
                            # Chota sa micro-pause taaki database I/O smooth rahe
                            await asyncio.sleep(0.05)

                    except Exception as bot_err:
                        logger.error(f"Error syncing users for @{bot_username}: {bot_err}")
                        # Fail hone par wapas buffer me add kar do
                        async with PENDING_USERS_LOCK:
                            if bot_username not in PENDING_NEW_USERS:
                                PENDING_NEW_USERS[bot_username] = set()
                            PENDING_NEW_USERS[bot_username].update(uids)

            # Saara data likhne ke baad hi agle batch ke liye 5 minute (300s) wait karega
            await asyncio.sleep(300)

        except Exception as e:
            logger.error(f"User sync worker loop error: {e}")
            await asyncio.sleep(60)
# -----------------------------------------------
# background.py mein yeh naye imports add karein (file ke shuru mein)
import psutil
from datetime import datetime

# Yeh poora naya function background.py mein add karein
# Yeh poora naya function background.py mein add karein
async def run_cache_cleanup_and_ram_monitor():
    """
    Ek background task jo hamesha chalta rehta hai:
    1. Expired cache items ko proactively delete karta hai (active cleanup).
    2. RAM usage ko monitor karke admin ko regular reports bhejta hai.
    """
    logger.info("Cache Cleanup & RAM Monitor service shuru ho gayi hai.")
    
    # Report bhejne ka interval (seconds me)
    REPORT_INTERVAL_SECONDS = 3600 # Har 1 ghante me report bhejega
    
    # State track karne ke liye variables
    last_ram_percent = psutil.virtual_memory().percent
    ram_history = []
    
    caches_to_monitor = [
        (CACHE_BOT_SETTINGS, "Bot Settings"), (CACHE_FSUB_USER_STATUS, "FSUB Status"),
        (CACHE_AD_VERIFY_LINK, "Ad Verify Link"), (CACHE_CONVERSATION, "Conversation"),
        (CACHE_FSUB_PENDING, "FSUB Pending"), (CACHE_USER_MEMBERSHIP, "User Membership"),
        (CACHE_FILE, "File"), (CACHE_BATCH, "Batch"),
        (CACHE_MEDIA_GROUP, "Media Group"),
        (CACHE_UNKNOWN_PAYLOAD, "Unknown Payload")  # <--- YEH NAYI LINE ADD KAR DO
    ]    
    time_since_last_report = 0

    while True:
        try:
            # Har 5 minute me check karo
            check_interval = 300
            await asyncio.sleep(check_interval)
            time_since_last_report += check_interval
            
            now_ts = datetime.utcnow().timestamp()
            
            # --- 1. Expired items ko actively delete karo ---
            expired_cleaned_count = 0
            for cache_instance, cache_name in caches_to_monitor:
                # keys() shared memory me slow ho sakta hai, isliye copy bana rahe hain
                keys_to_check = list(cache_instance.cache.keys())
                for key in keys_to_check:
                    # Hum naye private method ka istemal karenge
                    raw_item = await cache_instance._get_raw_item_for_monitoring(key)
                    if raw_item:
                        # raw_item[1] hamara 'expire_time' hai
                        if raw_item[1] < now_ts:
                            await cache_instance.delete(key)
                            expired_cleaned_count += 1
            
            # --- 2. RAM ki jaankari collect karo ---
            ram = psutil.virtual_memory()
            current_ram_percent = ram.percent
            
            # History me daalo
            ram_history.append({'time': now_ts, 'percent': current_ram_percent})
            
            # 2 ghante se purani history delete kardo
            two_hours_ago = now_ts - 7200
            ram_history = [r for r in ram_history if r['time'] > two_hours_ago]

            # --- 3. Agar report bhejne ka time ho gaya hai ---
            if time_since_last_report >= REPORT_INTERVAL_SECONDS:
                # Pichle check se tulna
                ram_change_since_last = current_ram_percent - last_ram_percent
                
                # Pichle 1 ghante se tulna
                one_hour_ago = now_ts - 3600
                ram_one_hour_ago = None
                for reading in ram_history:
                    if reading['time'] >= one_hour_ago:
                        ram_one_hour_ago = reading['percent']
                        break
                
                ram_change_last_hour = "N/A"
                if ram_one_hour_ago is not None:
                    change = current_ram_percent - ram_one_hour_ago
                    ram_change_last_hour = f"{change:+.1f}%"

                # Message taiyar karo
                report_message = (
                    f"📊 **Server Health & Cache Report** 📊\n\n"
                    f"📅 **Timestamp:** `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n\n"
                    f"🧠 **RAM Usage:**\n"
                    f"   - **Current:** `{current_ram_percent:.1f}%`\n"
                    f"   - **Used:** `{ram.used / (1024**3):.2f} GB`\n"
                    f"   - **Total:** `{ram.total / (1024**3):.2f} GB`\n\n"
                    f"📈 **RAM Changes:**\n"
                    f"   - **Since last 5 mins:** `{ram_change_since_last:+.1f}%`\n"
                    f"   - **In last 1 hour:** `{ram_change_last_hour}`\n\n"
                    f"🧹 **Cache Cleanup:**\n"
                    f"   - **Expired items cleaned now:** `{expired_cleaned_count}`"
                )
                
                # Admin ko report bhejo
                await notify_admin(report_message)
                
                # State reset karo
                time_since_last_report = 0
                last_ram_percent = current_ram_percent

        except Exception as e:
            logger.error(f"Cache cleanup/monitor task mein error aaya: {e}", exc_info=True)

# --- NAYA SMART DELETION PROCESSOR FUNCTION ---
async def process_scheduled_deletions():
    """
    Har minute chalta hai aur database se purane deletion jobs ko process karta hai.
    Yeh multiple-worker safe hai aur flood-waits ko handle karta hai.
    """
    if not pg_pool:
        logger.warning("Deletion processor: PG Pool available nahi hai, skip kar raha hoon.")
        return

    conn = None
    jobs_to_process = []
    
    try:
        conn = await pg_pool.acquire()
        
        # === Step 1: Jobs ko atomically claim karna ===
        async with conn.transaction():
            # 100 jobs claim karo jo pending hain aur jinka time ho gaya hai
            # ORDER BY... FOR UPDATE SKIP LOCKED hi multi-worker safety ki guarantee hai
            query = """
            SELECT id, bot_username, chat_id, message_id 
            FROM scheduled_deletions 
            WHERE status = 'pending' AND delete_at <= NOW()
            ORDER BY delete_at
            LIMIT 100
            FOR UPDATE SKIP LOCKED;
            """
            jobs_to_process = await conn.fetch(query)

            if not jobs_to_process:
                return # Koi kaam nahi hai

            # Jobs ko 'processing' mark karo taaki dusra worker na uthaye
            job_ids = [job['id'] for job in jobs_to_process]
            await conn.execute(
                "UPDATE scheduled_deletions SET status = 'processing' WHERE id = ANY($1::int[])",
                job_ids
            )
        
        # === Step 2: Claim kiye gaye jobs ko process karna ===
        logger.info(f"Deletion processor: {len(jobs_to_process)} message(s) delete karne hain.")
        
        for job in jobs_to_process:
            try:
                # force_initialize=True taaki bot API call ke liye ready ho
                bot_instance = await get_bot_instance(job['bot_username'], force_initialize=True)
                
                if not bot_instance:
                    raise Exception(f"Bot @{job['bot_username']} ka instance nahi mila.")
                
                await bot_instance.delete_message(job['chat_id'], job['message_id'])
                
                # Safal: DB se job delete karo
                await conn.execute("DELETE FROM scheduled_deletions WHERE id = $1", job['id'])

            except TelegramError as te:
                error_str = str(te).lower()
                
                if "message to delete not found" in error_str or "message can't be deleted" in error_str:
                    # Message pehle se delete hai, job ko safal maano
                    await conn.execute("DELETE FROM scheduled_deletions WHERE id = $1", job['id'])
                
                elif "flood control exceeded" in error_str or "too many requests" in error_str:
                    # Flood Wait: Job ko reschedule karo
                    # getattr() ka istemal safe hai, agar retry_after na mile toh default 60 de dega
                    retry_after_seconds = getattr(te, 'retry_after', 60)
                    new_delete_at = datetime.utcnow() + timedelta(seconds=retry_after_seconds + 5) # 5 sec buffer
                    
                    await conn.execute(
                        """
                        UPDATE scheduled_deletions 
                        SET status = 'pending', delete_at = $1, retry_count = retry_count + 1, last_error = $2
                        WHERE id = $3
                        """,
                        new_delete_at, str(te), job['id']
                    )
                    logger.warning(f"Deletion job {job['id']} ko {retry_after_seconds}s ke liye reschedule kiya gaya (Flood Wait).")
                
                else:
                    # Koi aur Telegram error: Job ko failed mark karo
                    await conn.execute(
                        "UPDATE scheduled_deletions SET status = 'failed', retry_count = retry_count + 1, last_error = $1 WHERE id = $2",
                        str(te), job['id']
                    )

            except Exception as e:
                # Koi aur error (e.g., bot instance nahi mila): Job ko failed mark karo
                await conn.execute(
                    "UPDATE scheduled_deletions SET status = 'failed', retry_count = retry_count + 1, last_error = $1 WHERE id = $2",
                    str(e), job['id']
                )

    except Exception as e:
        logger.error(f"Deletion processor me bada error: {e}", exc_info=True)
    
    finally:
        if conn:
            await pg_pool.release(conn) # Connection ko pool me wapas bhejo
# --- NAYA SMART DELETION PROCESSOR FUNCTION KHATAM ---

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
    revoked_username = f"{bot_username.split('#')[0]}#revoked"
    await DBManager.execute_sqlite_query(
        ALL_BOTS_DB,
        "UPDATE bots SET username = ? WHERE username = ?",
        (revoked_username, bot_username.split('#')[0])
    )
    # Cache se purana token delete karo
    await CACHE_BOT_TOKENS.delete(bot_username.split('#')[0])
    logger.info(f"Marked @{bot_username} as revoked in the database.")
# background.py


async def get_bot_instance(bot_username, force_initialize=None):
    """
    Bot ka instance banata hai with Increased Timeout.
    """
    if "#revoked" in bot_username:
        logger.warning(f"get_bot_instance skipped for revoked bot: @{bot_username}")
        return None

    token = await CACHE_BOT_TOKENS.get(bot_username)
    if not token:
        if bot_username == MAIN_BOT_USERNAME:
            token = MAIN_BOT_TOKEN
        else:
            result = await DBManager.execute_sqlite_query(
                ALL_BOTS_DB, "SELECT api_key FROM bots WHERE username=?", (bot_username,), fetch='one'
            )
            token = result[0] if result else None
        if token:
            await CACHE_BOT_TOKENS.set(bot_username, token)
        else:
            logger.error(f"get_bot_instance: @{bot_username} ke liye token nahi mila.")
            return None

    # --- NAYA CODE: Timeout badhane ke liye Request Object ---
    # Connect timeout ko 30 seconds kar diya gaya hai (Default 5 hota hai)
    request_defaults = HTTPXRequest(
        connection_pool_size=8,
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0
    )
    
    bot = Bot(token=token, request=request_defaults)
    # ---------------------------------------------------------

    if force_initialize is not False:
        try:
            await bot.initialize()
        except Exception as e:
            logger.error(f"Bot initialize failed for {bot_username}: {e}")
            return None
    
    # ❌ Purana 'else' block hata diya gaya hai kyunki v20+ me '_username' attribute nahi hota.
    # Agar force_initialize=False hai, to hum bot ko initialize nahi karenge
    # aur username manually inject nahi karenge.
    # Aapka BotLogic class waise bhi 'self.bot_username' string use karta hai,
    # isliye bot object ke andar username set hona zaroori nahi hai.

    return bot
async def notify_admin(message):
    # Yahan hum force_initialize=True bhej rahe hain taaki main_bot theek se kaam kare
    main_bot = await get_bot_instance(MAIN_BOT_USERNAME, force_initialize=True)
    if not main_bot:
        logger.error("Failed to notify admin: Could not get main bot instance.")
        return
    try:
        await main_bot.send_message(ADMIN_NOTIFY_ID, message, parse_mode=ParseMode.MARKDOWN_V2)
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
    def _escape_markdown(self, text: str) -> str:
        """Telegram ke MARKDOWN_V2 ke liye special characters ko escape karta hai."""
        # Yeh woh saare characters hain jinhe escape karna zaroori hai
        escape_chars = r'\_*[]()~`>#+-=|{}.!'
        # re.sub ka istemal karke har special character ke aage backslash laga do
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
            elif self.update.message:
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

    async def handle_chat_join_request(self):
        if not self.update.chat_join_request:
            return
        join_request = self.update.chat_join_request
        user_id = join_request.from_user.id
        channel_id = join_request.chat.id

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
        
        settings = await self.get_bot_settings()
        fsub_channels = settings.get('fsub_channels', [])
        main_admin_id = settings.get('creator_id')
        if not main_admin_id:
            return
        updated = False
        channels_to_remove = []
        for ch in fsub_channels:
            if ch['id'] == channel_id:
                current_joins = int(ch.get('current', 0)) + 1
                ch['current'] = current_joins
                updated = True
                target_joins = int(ch.get('target', 0))
                if target_joins > 0 and current_joins >= target_joins:
                    channels_to_remove.append(ch['id'])
                    try:
                        await self.bot.send_message(main_admin_id, f"🎉 Target Achieved! 🎉\n\nChannel {ch['id']} has reached its target of {target_joins} joins and has been removed from the FSUB list.")
                    except Exception:
                        pass
                break
        if not channels_to_remove and not updated:
            return
        if channels_to_remove:
            fsub_channels = [ch for ch in fsub_channels if ch['id'] not in channels_to_remove]
        
        # YAHAN CHANGE HAI: config_db_path ki jagah PG table use karna hai
        settings_table = DBManager._get_safe_tablename(self.bot_username, 'settings')
        query = f"INSERT INTO {settings_table} (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = $2"
        await DBManager.execute_pg_query(query, ('fsub_channels', json.dumps(fsub_channels)))

        if await CACHE_BOT_SETTINGS.contains(self.bot_username):
            await CACHE_BOT_SETTINGS.delete(self.bot_username)
    async def run_pre_checks(self):
        if self.bot_username == MAIN_BOT_USERNAME:
            return True
        if self.update.message and self.update.message.text and self.update.message.text.startswith('/start'):
            return True
        if not await self.check_fsub():
            return False
        if not await self.check_membership():
            return False
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
        current = "ON" if settings.get('unknown_payload_enabled', False) else "OFF"
        text = f"Unknown Payload Response for @{bot_username} is currently {current}."
        keyboard = [
            [InlineKeyboardButton("✅ Enable", callback_data=f"unknown_payload_on_{bot_username}"),
             InlineKeyboardButton("❌ Disable", callback_data=f"unknown_payload_off_{bot_username}")],
            [InlineKeyboardButton("⬅️ Back", callback_data=f"bot_settings_{bot_username}")]
        ]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

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
        if not EXTERNAL_VIDEOS:
            await self.bot.send_message(self.chat_id, "Video list load nahi hui hai.")
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
        if sent_msg:
            await self.maybe_send_super_broadcast()    
    
    async def handle_clone_bot_start(self):
        start_time = self.update.message.date
        args = self.update.message.text.split()[1:] if len(self.update.message.text.split()) > 1 else []
        payload = args[0] if args else None

        # --- NAYA BADLAV: USER KO DATABASE ME SAVE KARNE KA CODE YAHAN ADD HOGA ---
        # Yeh code humesha user ko DB me add karne ki koshish karega
        # 'ON CONFLICT DO NOTHING' isse duplicate entry nahi banegi.
        # --- FAST RAM CACHE BUFFER (Har 5 min me batch me DB me jayega) ---
        if self.user_id:
            async with PENDING_USERS_LOCK:
                if self.bot_username not in PENDING_NEW_USERS:
                    PENDING_NEW_USERS[self.bot_username] = set()
                PENDING_NEW_USERS[self.bot_username].add(self.user_id)

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
        if payload and len(payload) == 15:
            paid_table = DBManager._get_safe_tablename(self.bot_username, 'paid_messages')
            msg_data = await DBManager.execute_pg_query(f"SELECT * FROM {paid_table} WHERE payload=$1", (payload,), fetch='one')
            
            if msg_data:
                settings = await self.get_bot_settings()
                if not settings.get('paid_messages_enabled', True):
                    await self.bot.send_message(self.chat_id, "⚠️ Yeh paid message abhi admin dwara temporarily disable kiya gaya hai.")
                    return

                # Check if user already has access
                access_table = DBManager._get_safe_tablename(self.bot_username, 'paid_msg_access')
                has_access = await DBManager.execute_pg_query(f"SELECT 1 FROM {access_table} WHERE payload=$1 AND user_id=$2", (payload, self.user_id), fetch='one')
                
                # Bot admin / Super admin ko automatically access rahega
                if has_access or await self.is_user_admin():
                    await self.send_paid_message_to_user(payload)
                    return

                # Agar access nahi hai -> Payment Request generate karo
                price = float(msg_data['price'])
                paid_info = settings.get('paid_settings', {})
                admin_id = settings.get('creator_id')
                upi_id = paid_info.get('upi_id')
                cf_enabled = paid_info.get('cf_enabled', False)
                upi_enabled = paid_info.get('upi_enabled', True)

                if not upi_id and not cf_enabled:
                    await self.bot.send_message(self.chat_id, "Admin ne payment gateway configure nahi kiya hai. Kripya admin se sampark karein.")
                    return

                transaction_id = await DBManager.get_next_transaction_id()
                query = """
                INSERT INTO active_upi_transactions 
                (transaction_id, bot_username, admin_id, user_id, amount, plan_duration_days, transaction_start_time, upi_id, target_payload)
                VALUES ($1, $2, $3, $4, $5, 0, NOW(), $6, $7)
                """
                await DBManager.execute_pg_query(query, (
                    transaction_id, self.bot_username, admin_id, self.user_id, price, upi_id or "", payload
                ))

                if cf_enabled:
                    await self.handle_switch_payment(self.update.message, transaction_id, "cf", new_message=True)
                else:
                    await self.handle_switch_payment(self.update.message, transaction_id, "upi", new_message=True)
                return
        # --- END PAID MESSAGE CHECK ---

        if not await self.check_fsub(payload):
            return            
        
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
            bot_username = data.split("_", 3)[3]
            await self.toggle_setting(query.message, bot_username, 'unknown_payload_enabled', True, "Enable unknown payload response")
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
            await query.answer("Checking payment status...", show_alert=False)
            tx_data = await DBManager.execute_pg_query("SELECT bot_username FROM active_upi_transactions WHERE transaction_id = $1", (transaction_id,), fetch='one')
            if not tx_data:
                await query.answer("Transaction already processed or expired.", show_alert=True)
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
                        try: await query.message.delete()
                        except: pass
                else:
                    await query.answer("Payment is PENDING or FAILED. Please wait or try again.", show_alert=True)
        
        elif data.startswith("paid_ai_setup_"):
            bot_username = data.split("_", 3)[3]
            await query.message.delete()
            await self.initiate_conversation('paid_ai_setup', "Please send your Gemini API Key for AI Verification.", extra_data={'bot_username': bot_username})
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

        elif data.startswith("update_revoked_token_"):
            bot_username_to_update = data.split("_", 3)[3]
            await query.message.delete()
            await self.initiate_conversation('update_token', f"Please send the new API token for `@{bot_username_to_update}`.", extra_data={'bot_username': bot_username_to_update})
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
        text = f"Are you sure you want to delete @{bot_username}?"
        keyboard = [
        [InlineKeyboardButton("✅ Yes", callback_data=f"bot_delete_yes_{bot_username}"), InlineKeyboardButton("⬅️ Back", callback_data="bot_delete_select")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]
        ]
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    async def perform_delete_bot(self, message, bot_username):
        # Step 1: SQLite list se bot ko delete karein
        await DBManager.execute_sqlite_query(ALL_BOTS_DB, "DELETE FROM bots WHERE username=?", (bot_username,))
        
        # Step 2: Bot ka webhook delete karein
        # YAHAN BADLAAV KIYA GAYA HAI: force_initialize=True add kiya gaya hai
        bot = await get_bot_instance(bot_username, force_initialize=True)
        if bot:
            try:
                await bot.delete_webhook()
                webhook_text = f"Bot @{bot_username} webhook deleted successfully."
            except Exception:
                webhook_text = f"Bot @{bot_username} webhook deletion ignored due to error."
        else:
            webhook_text = "Bot instance not found for webhook deletion."
        
        # Step 3: PostgreSQL se bot se judi saari tables delete karein
        # Step 3: PostgreSQL se bot se judi saari tables delete karein
        suffixes_to_delete = ['files', 'captions', 'multi_files', 'settings', 'users', 'premium', 'unknown_payloads', 'paid_messages', 'paid_msg_access']        
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

        # 1. Admin/Owner check (Testing purpose ke liye)
        is_premium = await self.is_user_admin()

        # 2. Premium table check
        if not is_premium:
            now = datetime.utcnow().replace(tzinfo=None)
            premium_table = DBManager._get_safe_tablename(self.bot_username, 'premium')
            
            premium_data = await DBManager.execute_pg_query(
                f"SELECT expiry_time FROM {premium_table} WHERE user_id=$1", 
                (self.user_id,), 
                fetch='one'
            )
            if premium_data and premium_data['expiry_time'].replace(tzinfo=None) > now:
                is_premium = True

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
            "𝗣𝘆𝘁𝗵𝗼𝗻 𝗩𝗲𝗿𝘀𝗶𝗼𝗻: 3.13"
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
            "  » 𝗪𝗲𝗹𝗰𝗼𝗺𝗲 𝗡𝗮𝗺𝗲 𝗣𝗹𝗮𝗰𝗲𝗵𝗼𝗹𝗱𝗲𝗿: 𝘐𝘯 𝘺𝘰𝘶𝘳 𝘤𝘶𝘴𝘵𝘰𝘮 𝘸𝘦𝘭𝘤𝘰𝘮𝘦 𝘮𝘦𝘴𝘴𝘢𝘨𝘦, 𝘶𝘴𝘦 {User Name} 𝘵𝘰 𝘢𝘶𝘵𝘰𝘮𝘢𝘵𝘪𝘤𝘢𝘭𝘭𝘺 𝘨𝘳𝘦𝘦𝘵 𝘦𝘷𝘦𝘳𝘺 𝘯𝘦𝘸 𝘶𝘴𝘦𝘳 𝘸𝘪𝘵𝘩 𝘵𝘩𝘦𝘪𝘳 𝘧𝘪𝘳𝘴𝘵 𝘯𝘢𝘮𝘦! 👋\n\n"
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
            results = await asyncio.gather(
                DBManager.execute_pg_query(f"SELECT COUNT(*) as count FROM {users_table}", fetch='one'),
                DBManager.execute_pg_query(f"SELECT COUNT(*) as count FROM {premium_table}", fetch='one'),
                DBManager.execute_pg_query(f"SELECT COUNT(*) as count FROM {files_table}", fetch='one'),
                DBManager.execute_pg_query(f"SELECT COUNT(*) as count FROM {multi_files_table}", fetch='one'),
                self.get_bot_settings() # Settings bhi fetch kar lein
            )
            
            # Results ko variables me daalein
            total_users = results[0]['count'] if results[0] else 0
            total_premium_users = results[1]['count'] if results[1] else 0
            total_single_links = results[2]['count'] if results[2] else 0
            total_multi_links = results[3]['count'] if results[3] else 0
            settings = results[4]
            
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
    async def handle_clone_command(self):
        await self.initiate_conversation('clone', "Please send me the API token of the bot you want to clone.\n\nउदाहरण: 1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890")

    async def initiate_conversation(self, command_name, prompt_message, extra_data=None):
        state = {'command': command_name, 'step': 1}
        if extra_data:
            state.update(extra_data)
        prompt_msg = await self.bot.send_message(self.chat_id, prompt_message)
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
            allowed_updates=["message", "callback_query", "chat_join_request", "channel_post"],
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
        
        try:
            commands = [
            telegram.BotCommand("start", "Start the bot"),
            telegram.BotCommand("clone", "Clone a new bot"),
            telegram.BotCommand("broadcast", "Broadcast a message (Admin)"),
            telegram.BotCommand("premium_broadcast", "Broadcast a message to premium members (Admin)"),
            telegram.BotCommand("batch_link", "Create batch link for multiple files"),
            telegram.BotCommand("short_link", "Shorten a link"),
            telegram.BotCommand("stats", "Show bot statistics (Admin)")
            ]
            await new_bot.set_my_commands(commands)
        except Exception as e:
            await msg.edit_text("Warning: Couldn't set commands for your new bot, but it should still work.")
            await notify_admin(f"Command setup error for {new_bot_username}: {e}")
        await msg.edit_text(f"✅ Congratulations! Your bot @{new_bot_username} is ready. Go to your bot and start sharing files.")
        await notify_admin(f"New clone created: @{new_bot_username} by user {self.user_id}")
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
        clone_bot = await get_bot_instance(bot_username, force_initialize=True)
        try:
            if mode == 'request':
                invite_link = await clone_bot.create_chat_invite_link(chat_id=channel_id, creates_join_request=True, name=f"Request for @{bot_username}")
                await DBManager.setup_join_request_db(bot_username, channel_id)
            else:
                link = await clone_bot.export_chat_invite_link(chat_id=channel_id)
                invite_link = type('Invite', (), {'invite_link': link})()
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
        await DBManager.execute_sqlite_query(
            ALL_BOTS_DB,
            "UPDATE bots SET api_key = ?, username = ? WHERE username = ?",
            (new_api_key, original_bot_username, revoked_bot_username)
        )
        # Token cache ko clear karo
        await CACHE_BOT_TOKENS.delete(original_bot_username)

        # Naye bot ke liye webhook set karo
        clone_webhook_url = f"{WEBHOOK_URL}/normal"
        try:
            success = await new_bot.set_webhook(
                url=clone_webhook_url,
                allowed_updates=["message", "callback_query", "chat_join_request", "channel_post"],
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
        
        ai_enabled = settings.get('ai_verify_enabled', False)
        ai_name = settings.get('ai_verify_receiver_name', 'Not Set')
        
        status = "✅ Enabled" if is_enabled else "❌ Disabled"
        upi_status = "✅ ON" if upi_enabled else "❌ OFF"
        cf_status = "✅ ON" if cf_enabled else "❌ OFF"
        ai_status = "✅ ON" if ai_enabled else "❌ OFF"
        
        upi_id = paid_info.get('upi_id') or "Not Set"
        cf_app_id = paid_info.get('cf_app_id') or "Not Set"
        
        price_7 = paid_info.get('price_7') or "Not Set"
        price_28 = paid_info.get('price_28') or "Not Set"
        price_90 = paid_info.get('price_90') or "Not Set"

        text = (
            f"💰 *Paid Membership Settings for @{self._escape_markdown(bot_username)}*\n\n"
            f"*Main Status:* `{status}`\n\n"
            f"*Payment Gateways:*\n"
            f"  \- UPI QR: `{upi_status}`\n"
            f"  \- Cashfree: `{cf_status}`\n\n"
            f"*UPI ID:* `{upi_id}`\n"
            f"*Cashfree App ID:* `{cf_app_id}`\n"
            f"*AI Verification:* `{ai_status}` \(Name: `{ai_name}`\)\n\n"
            f"*Pricing:*\n"
            f"  \- 7 Days: `{price_7}` INR\n"
            f"  \- 28 Days: `{price_28}` INR\n"
            f"  \- 3 Months: `{price_90}` INR"
        ) 
        
        ai_toggle_btn = InlineKeyboardButton("❌ Disable AI", callback_data=f"paid_ai_toggle_off_{bot_username}") if ai_enabled else InlineKeyboardButton("✅ Enable AI", callback_data=f"paid_ai_toggle_on_{bot_username}")
        upi_toggle_btn = InlineKeyboardButton(f"Turn {'OFF' if upi_enabled else 'ON'} UPI", callback_data=f"paid_upi_toggle_{bot_username}")
        cf_toggle_btn = InlineKeyboardButton(f"Turn {'OFF' if cf_enabled else 'ON'} Cashfree", callback_data=f"paid_cf_toggle_{bot_username}")

        keyboard = [
            [InlineKeyboardButton("📩 Paid Messages", callback_data=f"paid_msg_menu_{bot_username}")],
            [InlineKeyboardButton("✏️ Setup UPI & Prices", callback_data=f"paid_setup_{bot_username}")],
            [InlineKeyboardButton("💳 Setup Cashfree API", callback_data=f"paid_cf_setup_{bot_username}")],
            [upi_toggle_btn, cf_toggle_btn],
            [InlineKeyboardButton("🤖 Setup AI Verify", callback_data=f"paid_ai_setup_{bot_username}"), ai_toggle_btn],
            [InlineKeyboardButton("❌ Disable Feature Entirely", callback_data=f"paid_disable_{bot_username}")],
            [InlineKeyboardButton("⬅️ Back", callback_data=f"bot_settings_{bot_username}")]
        ]
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
    async def toggle_gateway(self, message, bot_username, gateway):
        settings = await self.get_bot_settings(bot_username)
        paid_info = settings.get('paid_settings', {})
        if gateway == "cf":
            current = paid_info.get('cf_enabled', False)
            paid_info['cf_enabled'] = not current
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
        state['step'] = 2
        state['command'] = 'paid_msg_price'
        
        key = f"{self.bot_username}_{self.user_id}"
        await CACHE_CONVERSATION.set(key, state)
        await self.bot.send_message(self.chat_id, "Message received! Ab is Paid Message ka **Price (₹)** enter karein (e.g., 20 ya 50):", parse_mode=ParseMode.MARKDOWN)

    async def handle_conv_paid_msg_price(self, state):
        """Admin se price lekar 15-character payload generate aur save karta hai."""
        key = f"{self.bot_username}_{self.user_id}"
        await CACHE_CONVERSATION.delete(key)
        
        price_text = self.update.message.text.strip() if self.update.message.text else ""
        try:
            price = float(price_text)
            if price <= 0: raise ValueError()
        except ValueError:
            await self.bot.send_message(self.chat_id, "Invalid price. Positive number bhejein. Operation canceled.")
            return

        bot_username = state.get('bot_username', self.bot_username)
        file_id = state.get('msg_file_id')
        file_type = state.get('msg_file_type')
        caption = state.get('msg_caption')

        # 15 character ka payload generate karo
        # 15 character ka payload generate karo
        payload = generate_random_string(15)

        paid_table = DBManager._get_safe_tablename(bot_username, 'paid_messages')
        access_table = DBManager._get_safe_tablename(bot_username, 'paid_msg_access')
        insert_query = f"""
        INSERT INTO {paid_table} (payload, file_id, file_type, caption, price)
        VALUES ($1, $2, $3, $4, $5)
        """
        
        try:
            await DBManager.execute_pg_query(insert_query, (payload, file_id, file_type, caption, price))
        except Exception as e:
            # Agar table pehle se maujood nahi hai toh on-the-fly create karo
            if "does not exist" in str(e).lower() or "undefinedtableerror" in str(e).lower():
                logger.info(f"Paid tables missing for @{bot_username}. Creating now on-demand...")
                await DBManager.execute_pg_query(f"""
                CREATE TABLE IF NOT EXISTS {paid_table} (
                    payload VARCHAR(15) PRIMARY KEY,
                    file_id TEXT,
                    file_type TEXT NOT NULL,
                    caption TEXT,
                    price NUMERIC(10, 2) NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );""")
                await DBManager.execute_pg_query(f"""
                CREATE TABLE IF NOT EXISTS {access_table} (
                    payload VARCHAR(15) NOT NULL,
                    user_id BIGINT NOT NULL,
                    granted_at TIMESTAMPTZ DEFAULT NOW(),
                    PRIMARY KEY (payload, user_id)
                );""")
                # Table create hote hi data insert kar do
                await DBManager.execute_pg_query(insert_query, (payload, file_id, file_type, caption, price))
            else:
                logger.error(f"Error saving paid message for @{bot_username}: {e}")
                raise e

        link = f"https://t.me/{bot_username}?start={payload}"        
        text = (
            f"✅ **Paid Message Successfully Created!**\n\n"
            f"💰 **Price:** ₹{price:.2f}\n"
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
            return

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
    
    async def show_payment_plans(self, message, payload):
        """User ko payment plans dikhata hai."""
        settings = await self.get_bot_settings()
        if not settings.get('paid_enabled'):
            await message.edit_text("Sorry, the 'Remove Ad' feature is currently disabled.")
            return

        paid_info = settings.get('paid_settings', {})
        text = "Choose a premium plan to remove ads:"
        keyboard = []
        prices = {
            7: paid_info.get('price_7'),
            28: paid_info.get('price_28'),
            90: paid_info.get('price_90')
        }
        
        for days, price in prices.items():
            if price and price > 0:
                plan_name = {7: "7 Days", 28: "28 Days", 90: "3 Months"}.get(days)
                keyboard.append([InlineKeyboardButton(
                    f"{plan_name} - ₹{price}", 
                    callback_data=f"select_plan_{days}_{payload}"
                )])
        
        if not keyboard:
            await message.edit_text("Sorry, no premium plans are available right now.")
            return
            
        await message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    async def handle_plan_selection(self, message, days, payload):
        """User ke plan selection ko handle karta hai, transaction banata hai aur payment deta hai."""
        settings = await self.get_bot_settings()
        admin_id = settings.get('creator_id')
        paid_info = settings.get('paid_settings', {})
        
        price = paid_info.get(f'price_{days}')
        upi_id = paid_info.get('upi_id')
        cf_enabled = paid_info.get('cf_enabled', False)
        upi_enabled = paid_info.get('upi_enabled', True)

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
        (transaction_id, bot_username, admin_id, user_id, amount, plan_duration_days, transaction_start_time, upi_id)
        VALUES ($1, $2, $3, $4, $5, $6, NOW(), $7)
        """
        await DBManager.execute_pg_query(query, (
            transaction_id, self.bot_username, admin_id, self.user_id, float(price), days, upi_id or ""
        ))

        # Default behaviour (Switch Cashfree if enabled, otherwise UPI)
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
                1. Check if receiver name matches the expected name.
                2. Check if amount matches expected amount.
                3. Check payment status (must be successful).
                4. Check date/time. A payment is valid if it was made ANYTIME within the last 1 hour from the Current Date & Time provided above. Exact time match is not required, just within 1 hour.
                5. If everything looks genuine and correct, approve it. If not, deny it and provide a clear reason in Hindi (written in English script like 'Amount match nahi ho raha').

                You MUST return ONLY a raw JSON object with this exact structure:
                {{"approve": true or false, "reason": "Your reason here if false, or empty string if true"}}
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
                    # Track that this transaction was approved by AI
                    await DBManager.execute_pg_query(
                        "INSERT INTO ai_approved_transactions (transaction_id, user_id) VALUES ($1, $2) ON CONFLICT (transaction_id) DO NOTHING",
                        (transaction_id, self.user_id)
                    )
                    if target_payload:
                        paid_access_table = DBManager._get_safe_tablename(bot_username_from_tx, 'paid_msg_access')
                        await DBManager.execute_pg_query(
                            f"INSERT INTO {paid_access_table} (payload, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                            (target_payload, self.user_id)
                        )
                    else:
                        premium_table = DBManager._get_safe_tablename(bot_username_from_tx, 'premium')                
                        pg_query = f"""
                        INSERT INTO {premium_table} (user_id, expiry_time) VALUES ($1, NOW() + INTERVAL '{days} days')
                        ON CONFLICT (user_id) DO UPDATE SET expiry_time = 
                            CASE 
                                WHEN {premium_table}.expiry_time < NOW() THEN NOW() + INTERVAL '{days} days'
                                ELSE {premium_table}.expiry_time + INTERVAL '{days} days'
                            END;
                        """
                        await DBManager.execute_pg_query(pg_query, (self.user_id,))
                    
                    safe_bot_table = DBManager._get_safe_tablename(bot_username_from_tx, '')
                    move_query = f"INSERT INTO {safe_bot_table}successful_transactions (transaction_id, user_id, amount, plan_duration_days, completion_time) VALUES ($1, $2, $3, $4, NOW())"
                    await DBManager.execute_pg_query(move_query, (transaction_id, self.user_id, tx_data['amount'], days))
                    await DBManager.execute_pg_query("DELETE FROM active_upi_transactions WHERE transaction_id = $1", (transaction_id,))
                    
                    await wait_msg.delete()
                    
                    # 1. Send Success Message / Paid Content to User
                    if target_payload:
                        await self.bot.send_message(self.chat_id, "✅ <b>AI Approved!</b>\n\nAapka payment verify ho gaya hai. Aapka message neeche unlock ho chuka hai:", parse_mode=ParseMode.HTML)
                        await self.send_paid_message_to_user(target_payload)
                    else:
                        user_success_msg = f"✅ <b>AI Approved!</b>\n\nAapka payment automatically verify ho gaya hai. Aap ab {days} days ke liye premium member hain!"
                        await self.bot.send_message(self.chat_id, user_success_msg, parse_mode=ParseMode.HTML)
                    
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

        if is_successful:
            target_table = f"{safe_bot_username}successful_transactions"
            clone_bot_instance = await get_bot_instance(bot_username, force_initialize=True)

            if target_payload:
                paid_access_table = DBManager._get_safe_tablename(bot_username, 'paid_msg_access')
                await DBManager.execute_pg_query(
                    f"INSERT INTO {paid_access_table} (payload, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                    (target_payload, user_id_to_reward)
                )
                status_message = "✅ Aapka payment admin dwara verify kar diya gaya hai! Aapka paid message neeche send kiya ja raha hai."
                if clone_bot_instance:
                    logic_obj = BotLogic(bot_username, {})
                    logic_obj.bot = clone_bot_instance
                    logic_obj.chat_id = user_id_to_reward
                    logic_obj.user_id = user_id_to_reward
                    await logic_obj.send_paid_message_to_user(target_payload)
            else:
                status_message = f"You are now a premium member for {days} days!"
                if clone_bot_instance:
                    await self.auto_add_premium_to_synced_bots(bot_username, user_id_to_reward, days)
                    premium_table = DBManager._get_safe_tablename(bot_username, 'premium')                
                    pg_query = f"""
                    INSERT INTO {premium_table} (user_id, expiry_time) VALUES ($1, NOW() + INTERVAL '{days} days')
                    ON CONFLICT (user_id) DO UPDATE SET expiry_time = 
                        CASE 
                            WHEN {premium_table}.expiry_time < NOW() THEN NOW() + INTERVAL '{days} days'
                            ELSE {premium_table}.expiry_time + INTERVAL '{days} days'
                        END;
                    """
                    await DBManager.execute_pg_query(pg_query, (user_id_to_reward,))        
        else:
            target_table = f"{safe_bot_username}failed_transactions"
            status_message = "Sorry, the admin has marked your payment as not received. Please contact support if this is a mistake."

        # Transaction ko move karo
        move_query = f"""
        INSERT INTO {target_table} (transaction_id, user_id, amount, plan_duration_days, { 'completion_time' if is_successful else 'failure_time' })
        VALUES ($1, $2, $3, $4, NOW())
        """
        await DBManager.execute_pg_query(move_query, (transaction_id, user_id_to_reward, amount, days))

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
        user_id = tx_data['user_id']
        amount = tx_data['amount']
        days = tx_data['plan_duration_days']
        
        # Step 2: Transaction ko move karo
        try:
            # Nayi table me insert karo
            move_query = f"""
            INSERT INTO {target_table_name} (transaction_id, user_id, amount, plan_duration_days, {target_time_col})
            VALUES ($1, $2, $3, $4, NOW())
            """
            await DBManager.execute_pg_query(move_query, (transaction_id, user_id, amount, days))
            
            # Purani table se delete karo
            await DBManager.execute_pg_query(f"DELETE FROM {source_table_name} WHERE transaction_id = $1", (transaction_id,))

        except Exception as e:
            await admin_message.reply_text(f"Error moving transaction in DB: {e}")
            logger.error(f"Transaction move karte waqt error: {e}")
            return

        # Step 3: Premium status update karo
        premium_table = DBManager._get_safe_tablename(bot_username, 'premium')
        users_table = DBManager._get_safe_tablename(bot_username, 'users')
        user_notify_message = ""
        admin_reply_text = ""
        
        try:
            clone_bot_notify = await get_bot_instance(bot_username, force_initialize=True)
            if not clone_bot_notify:
                raise Exception("Clone bot instance nahi mila.")

            if reverse_to_fail:
                # Check karo kya ye transaction AI dwara approve hui thi
                ai_tx_check = await DBManager.execute_pg_query(
                    "SELECT 1 FROM ai_approved_transactions WHERE transaction_id = $1", 
                    (transaction_id,), 
                    fetch='one'
                )
                if ai_tx_check:
                    # User ko universal scammer table me add karo
                    await DBManager.execute_pg_query(
                        """
                        INSERT INTO scammer_users (user_id, reason, bot_username)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (user_id) DO NOTHING
                        """,
                        (user_id, "AI-approved payment reversed by Admin", bot_username)
                    )
                    logger.info(f"User {user_id} flagged as scammer and added to scammer_users table.")

                # Premium cancel karna hai
                await DBManager.execute_pg_query(f"DELETE FROM {premium_table} WHERE user_id=$1", (user_id,))
                # User ka normal ad expiry bhi set kar do
                await DBManager.execute_pg_query(f"UPDATE {users_table} SET membership_expiry = NOW() WHERE user_id=$1", (user_id,))
                
                user_notify_message = "Aapka transaction admin ne cancel kar diya hai. You are no longer a premium user!"
                scammer_tag = "\n🚨 User has been added to universal scammer list." if ai_tx_check else ""
                admin_reply_text = f"✅ Transaction reversed. User premium has been CANCELED.{scammer_tag}"
                
                # Admin ke button ko update karo
                new_keyboard = [[InlineKeyboardButton("↩️ Grant Premium", callback_data=f"admin_grant_premium_{transaction_id}")]]
                await admin_message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(new_keyboard))

            else:
                # Premium grant karna hai — User ko scammer list se bhi hatao (agar pehle flag hua tha)
                await DBManager.execute_pg_query("DELETE FROM scammer_users WHERE user_id = $1", (user_id,))

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
                new_keyboard = [[InlineKeyboardButton("↩️ Cancel Premium", callback_data=f"admin_cancel_premium_{transaction_id}")]]
                await admin_message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(new_keyboard))

            # Step 4: User ko notify karo
            await clone_bot_notify.send_message(user_id, user_notify_message)
            await admin_message.reply_text(admin_reply_text)

        except Exception as e:
            error_msg = f"Error updating premium status for user {user_id}: {e}"
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
            await self.bot.send_message(self.chat_id, "Please use a command to interact.")
            return

        text = self.update.message.text
        pattern = r"https://t.me/{}\?start=([a-zA-Z0-9]{{21}})".format(self.bot_username)
        share_ids = re.findall(pattern, text)

        files_table = DBManager._get_safe_tablename(self.bot_username, 'files')

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
        else:
            multi_share_id = generate_random_string(21)
            multi_files_table = DBManager._get_safe_tablename(self.bot_username, 'multi_files')
            query = f"INSERT INTO {multi_files_table} (multi_share_id, share_ids) VALUES ($1, $2)"
            await DBManager.execute_pg_query(query, (multi_share_id, json.dumps(valid_share_ids)))
            link = f"https://t.me/{self.bot_username}?start={multi_share_id}"
            await self.bot.send_message(self.chat_id, f"Multi-file link generated:\n\n{link}")
    async def handle_file_message(self):
        if not await self.is_user_admin():
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
                if file_type == 'text' and specific_caption:
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
        if settings.get('deletion', False) and sent_messages:
            deletion_time = settings.get('deletion_time', 7200)
            time_str = {1200: "20 Minutes", 1800: "30 Minutes", 3600: "1 Hour", 7200: "2 Hours", 21600: "6 Hours", 86400: "24 Hours"}.get(deletion_time, f"{deletion_time // 60} Minutes")
            
            deletion_msg_text = (
                f"🐋 <b>Due to Copyright ISSUES 🐋</b>\n\n"
                f"<blockquote>Due to copyright restrictions, all files sent by this bot will be deleted after <b>{time_str}</b>.</blockquote>"
            )
            
            del_msg = await self.bot.send_message(self.chat_id, deletion_msg_text, parse_mode=ParseMode.HTML)
            
            for msg in sent_messages + [del_msg]:
                asyncio.create_task(self.schedule_deletion(msg.message_id, deletion_time))

        # Premium user ke liye Super Broadcast deliver karo
        if sent_messages:
            await self.maybe_send_super_broadcast()   
    
    async def schedule_deletion(self, message_id, delay_seconds):
        """
        asyncio.sleep ke bajaye, deletion job ko PostgreSQL DB me save karta hai.
        """
        try:
            # delete_at timestamp ko UTC me calculate karo
            delete_at_timestamp = datetime.utcnow() + timedelta(seconds=delay_seconds)
            
            # Sirf zaroori info insert karo, 'status' aur 'retry_count' default use karenge
            query = """
            INSERT INTO scheduled_deletions (bot_username, chat_id, message_id, delete_at)
            VALUES ($1, $2, $3, $4)
            """
            
            await DBManager.execute_pg_query(
                query,
                (self.bot_username, self.chat_id, message_id, delete_at_timestamp)
            )
        except Exception as e:
            logger.error(f"Deletion job ko DB me save karte waqt error (bot: @{self.bot_username}): {e}")
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
        settings = {
            'protected': True, 'deletion': False, 'deletion_time': 7200, 'admins': [],
            'fsub_channels': [], 'footer': '', 'ad_api_link': '', 'ad_tutorial_link': '',
            'welcome_message': '', 'custom_button_name': '', 'custom_button_url': '',
            'welcome_media_id': '', 'welcome_media_type': '',
            'paid_enabled': False,
            'paid_settings': {'upi_id': '', 'price_7': 0, 'price_28': 0, 'price_90': 0},
            'paid_messages_enabled': True,
            'unknown_payload_enabled': False,
            'premium_sync_enabled': False,
            'super_broadcast_enabled': False,
            'super_broadcast_msg_id': None,
            'super_broadcast_chat_id': None
        }       
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
        key = f"{self.bot_username}_{self.user_id}"
        pending_channels_ids = await CACHE_FSUB_PENDING.get(key)
        if not pending_channels_ids:
            return
        settings = await self.get_bot_settings()
        fsub_channels = settings.get('fsub_channels', [])
        main_admin_id = settings.get('creator_id')
        if not main_admin_id or not fsub_channels:
            if await CACHE_FSUB_PENDING.contains(key):
                await CACHE_FSUB_PENDING.delete(key)
            return
        updated = False
        channels_to_remove = []
        for ch in fsub_channels:
            if ch['id'] in pending_channels_ids and ch.get('mode', 'normal') == 'normal':
                current_joins = int(ch.get('current', 0)) + 1
                ch['current'] = current_joins
                updated = True
                target_joins = int(ch.get('target', 0))
                if target_joins > 0 and current_joins >= target_joins:
                    channels_to_remove.append(ch['id'])
                    try:
                        await self.bot.send_message(main_admin_id, f"🎉 Target Achieved! 🎉\n\nChannel {ch['id']} has reached its target of {target_joins} joins and has been removed from the FSUB list.")
                    except Exception:
                        pass
        if channels_to_remove:
            fsub_channels = [ch for ch in fsub_channels if ch['id'] not in channels_to_remove]
            updated = True
        if updated:
            settings_table = DBManager._get_safe_tablename(self.bot_username, 'settings')
            query = f"INSERT INTO {settings_table} (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = $2"
            await DBManager.execute_pg_query(query, ('fsub_channels', json.dumps(fsub_channels)))

            if await CACHE_BOT_SETTINGS.contains(self.bot_username):
                await CACHE_BOT_SETTINGS.delete(self.bot_username)
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
                allowed_updates=["message", "callback_query", "chat_join_request", "channel_post"],
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
    await DBManager.setup_deletion_infrastructure() # <-- YEH NAYI LINE HAI
    
    # JSON data RAM me download karna
    await fetch_external_videos()    
    # Deletion scheduler ko shuru karo
    # (Aapki file me AsyncIOScheduler pehle se imported hai)
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        process_scheduled_deletions,  # Hamara naya smart function
        'interval', 
        minutes=1,                      # Har 1 minute me chalega
        id='deletion_processor_job', 
        replace_existing=True,
        max_instances=5 # Ek saath 5 instance tak chalne do (multi-worker)
    )
    scheduler.start()
    logger.info("Smart Message Deletion Processor scheduler shuru ho gaya hai (har 1 min).")

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
            allowed_updates=["message", "callback_query", "chat_join_request", "channel_post"]
        )
    except Exception as e:
        logger.error(f"Main bot webhook setup error: {e}")
        # Error aane par admin ko soochit karein
        await notify_admin(f"Main bot webhook setup error: {e}")
