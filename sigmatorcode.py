import os
import asyncio
import random
import sys
import json
import sqlite3
import time
import logging
import glob
import smtplib
import re
import hashlib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from telethon import TelegramClient, events, functions, types, Button
from telethon.errors import FloodWaitError, RPCError, SessionPasswordNeededError
from telethon.tl.functions.account import UpdateStatusRequest, UpdateProfileRequest, UpdateUsernameRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.photos import UploadProfilePhotoRequest, DeletePhotosRequest
from telethon.tl.functions.messages import DeleteMessagesRequest, EditMessageRequest
from aiohttp import web
import aiohttp

# ==================== GLOBAL CONFIG & CONSTANTS ====================
MAX_ACCOUNTS_PER_USER = 5
MAX_ADMINS = 10
DAILY_REPORT_LIMIT = 100
MIN_DELAY = 1.0
MAX_DELAY = 3.0
FLOOD_EXTRA_SLEEP = 5
DEFAULT_AUTO_REPLY = "درود، بنده اف هستم..."
WORKER_SEMAPHORE = asyncio.Semaphore(15)

daily_report_counter = {}

SUB_PLANS = {
    "free": {"name": "Free Trial", "price": "0", "sessions": 5, "days": 15},
    "1month": {"name": "1 Month Premium", "price": "100,000 Toman", "sessions": 50, "days": 30},
    "3month": {"name": "3 Months Premium", "price": "200,000 Toman", "sessions": 100, "days": 90},
    "6month": {"name": "6 Months Premium", "price": "350,000 Toman", "sessions": 150, "days": 180},
    "1year": {"name": "1 Year Premium", "price": "500,000 Toman", "sessions": 200, "days": 365}
}

REPORTS = {
    "scam": ["This channel/user is engaging in fraudulent activities and scamming users."],
    "porn": ["Posting inappropriate and non-consensual explicit sexual material."],
    "violence": ["Promoting graphic violence, physical threats, and harmful actions."],
    "child": ["Sharing abusive, dangerous, and illegal content involving minors."],
    "copyright": ["Infringing copyright laws by distributing non-authorized content."],
    "fake": ["Impersonating public individuals, official organizations, or brands."]
}

ALL_REPORT_REASONS = {
    "spam": (types.InputReportReasonSpam(), "Spam & Unsolicited messages"),
    "scam": (types.InputReportReasonSpam(), "Scam & Fraudulent behavior"),
    "porn": (types.InputReportReasonPornography(), "Pornography & Explicit material"),
    "violence": (types.InputReportReasonViolence(), "Violence & Threats"),
    "child": (types.InputReportReasonChildAbuse(), "Child Abuse & Harmful material"),
    "copyright": (types.InputReportReasonCopyright(), "Copyright & Infringement"),
    "fake": (types.InputReportReasonFake(), "Fake account / Impersonation"),
    "illegal": (types.InputReportReasonOther(), "Illegal drugs or regulated goods"),
    "personal": (types.InputReportReasonPersonalDetails(), "Personal details posted without consent")
}

try:
    from zoneinfo import ZoneInfo
    TEHRAN_TZ = ZoneInfo("Asia/Tehran")
except Exception:
    try:
        import pytz
        TEHRAN_TZ = pytz.timezone("Asia/Tehran")
    except Exception:
        TEHRAN_TZ = None

def now_tehran():
    if TEHRAN_TZ:
        return datetime.now(TEHRAN_TZ)
    return datetime.now()

def format_tehran_time():
    return now_tehran().strftime("%H:%M")

def format_tehran_time_font(style="default"):
    t = now_tehran()
    if style == "default":
        return t.strftime("%H:%M")
    elif style == "full":
        return t.strftime("%Y-%m-%d %H:%M")
    elif style == "colon":
        return t.strftime("%H.%M")
    elif style == "dash":
        return t.strftime("%H-%M")
    elif style == "bracket":
        return "[" + t.strftime("%H:%M") + "]"
    elif style == "star":
        return "*" + t.strftime("%H:%M") + "*"
    elif style == "spaced":
        return t.strftime("%H %M")
    elif style == "fancy":
        return "« " + t.strftime("%H:%M") + " »"
    elif style == "emoji":
        return t.strftime("%H:%M") + " ⏰"
    else:
        return t.strftime("%H:%M")

def bold_unicode(text):
    result = ""
    for ch in text:
        if 'a' <= ch <= 'z':
            result += chr(0x1D41A + ord(ch) - ord('a'))
        elif 'A' <= ch <= 'Z':
            result += chr(0x1D400 + ord(ch) - ord('A'))
        elif '0' <= ch <= '9':
            result += chr(0x1D7CE + ord(ch) - ord('0'))
        else:
            result += ch
    return result

def italic_unicode(text):
    result = ""
    for ch in text:
        if 'a' <= ch <= 'z':
            result += chr(0x1D44E + ord(ch) - ord('a'))
        elif 'A' <= ch <= 'Z':
            result += chr(0x1D434 + ord(ch) - ord('A'))
        else:
            result += ch
    return result

def fancy_unicode(text):
    result = ""
    for ch in text:
        if 'a' <= ch <= 'z':
            result += chr(0x1D4EA + ord(ch) - ord('a'))
        elif 'A' <= ch <= 'Z':
            result += chr(0x1D4D0 + ord(ch) - ord('A'))
        else:
            result += ch
    return result

def monospace_unicode(text):
    result = ""
    for ch in text:
        if 'a' <= ch <= 'z':
            result += chr(0x1D68A + ord(ch) - ord('a'))
        elif 'A' <= ch <= 'Z':
            result += chr(0x1D670 + ord(ch) - ord('A'))
        elif '0' <= ch <= '9':
            result += chr(0x1D7F6 + ord(ch) - ord('0'))
        else:
            result += ch
    return result

def apply_font(text, font_type="bold"):
    if font_type == "bold":
        return bold_unicode(text)
    elif font_type == "italic":
        return italic_unicode(text)
    elif font_type == "fancy":
        return fancy_unicode(text)
    elif font_type == "mono":
        return monospace_unicode(text)
    else:
        return text

def mask_phone(phone):
    if not phone:
        return "***"
    phone = str(phone).strip()
    if len(phone) <= 6:
        return "*" * len(phone)
    return phone[:4] + "****" + phone[-3:]

def safe_session_name(session_path):
    name = os.path.basename(session_path).replace('.session', '')
    clean = name.replace('+', '').replace('-', '').replace(' ', '')
    if clean.isdigit() and len(clean) >= 10:
        return mask_phone(name)
    return name

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.FileHandler('bot_log.txt'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

API_ID = 25342127
API_HASH = '0b75a27b1ab66bd482b6d93a0989d34f'
BOT_TOKEN = '8428206780:AAFX28ITNNv3GIUaaslSJzxVAXbUPs2CDjo'
OWNER_USERNAME = '@TANxAMIRALI'
OWNER_ID = 7733193342
ADMIN_CONTACT = '@AMIRALIxTAN'

GLOBAL_TARGET = None
is_attacking = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_DIR = BASE_DIR
PROXIES_FILE = os.path.join(BASE_DIR, 'proxies.json')
ADMINS_FILE = os.path.join(BASE_DIR, 'admins.json')
EMAILS_FILE = os.path.join(BASE_DIR, 'emails.json')
SUBSCRIBERS_FILE = os.path.join(BASE_DIR, 'subscribers.json')
FREE_TRIAL_FILE = os.path.join(BASE_DIR, 'free_trial_used.json')
PAYMENTS_FILE = os.path.join(BASE_DIR, 'payments.json')
USER_SESSIONS_FILE = os.path.join(BASE_DIR, 'user_sessions.json')
SELF_ACTIVE_FILE = os.path.join(BASE_DIR, 'self_active.json')
AUTO_REPLY_FILE = os.path.join(BASE_DIR, 'auto_reply.json')
WORD_FILTER_FILE = os.path.join(BASE_DIR, 'word_filter.json')
CLOCK_FONT_FILE = os.path.join(BASE_DIR, 'clock_font.json')
REPORT_COUNT_FILE = os.path.join(BASE_DIR, 'report_count.json')
SELF_CONFIG_FILE = os.path.join(BASE_DIR, 'self_config.json')
SELF_STATS_FILE = os.path.join(BASE_DIR, 'self_stats.json')
SCHEDULER_FILE = os.path.join(BASE_DIR, 'scheduler.json')

session_locks = {}
_session_cache = {'sessions': [], 'last_scan': 0, 'lock': asyncio.Lock()}

is_clock_active = False
clock_task = None
is_auto_spam_active = False
auto_spam_task = None
self_monitors = {}
report_count_setting = 1
scheduled_messages = {}

def safe_load_json(filepath, default=None):
    if default is None:
        default = {}
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content:
                    return default
                return json.loads(content)
        except Exception as e:
            logger.error("Load " + filepath + " error: " + str(e))
    return default

def safe_save_json(filepath, data):
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error("Save " + filepath + " error: " + str(e))

def load_report_count():
    data = safe_load_json(REPORT_COUNT_FILE, {"count": 1})
    return data.get("count", 1)

def save_report_count(count):
    safe_save_json(REPORT_COUNT_FILE, {"count": count})

report_count_setting = load_report_count()

def load_user_sessions():
    return safe_load_json(USER_SESSIONS_FILE, {})

def save_user_sessions(data):
    safe_save_json(USER_SESSIONS_FILE, data)

user_sessions = load_user_sessions()

def get_user_accounts(user_id):
    user_id = str(user_id)
    if user_id in user_sessions:
        return user_sessions[user_id].get('sessions', [])
    return []

def add_user_account(user_id, session_name):
    user_id = str(user_id)
    session_name = session_name.replace('.session', '').replace('+', '')
    for uid, data in user_sessions.items():
        if uid != user_id and session_name in data.get('sessions', []):
            return False, "این شماره قبلا توسط کاربر دیگری ثبت شده"
    if user_id not in user_sessions:
        user_sessions[user_id] = {
            'sessions': [],
            'self_target': None,
            'self_active': False,
            'added_at': now_tehran().isoformat()
        }
    if session_name in user_sessions[user_id]['sessions']:
        return False, "این شماره قبلا توسط خودت اضافه شده"
    if len(user_sessions[user_id]['sessions']) >= MAX_ACCOUNTS_PER_USER:
        return False, "حداکثر " + str(MAX_ACCOUNTS_PER_USER) + " اکانت مجاز است"
    user_sessions[user_id]['sessions'].append(session_name)
    save_user_sessions(user_sessions)
    if len(user_sessions[user_id]['sessions']) == MAX_ACCOUNTS_PER_USER:
        user_sessions[user_id]['self_target'] = session_name
        user_sessions[user_id]['self_active'] = True
        save_user_sessions(user_sessions)
        return True, "SIGMATOR فعال شد"
    return True, "اضافه شد (" + str(len(user_sessions[user_id]['sessions'])) + "/" + str(MAX_ACCOUNTS_PER_USER) + ")"

def remove_user_account(user_id, session_name):
    user_id = str(user_id)
    session_name = session_name.replace('.session', '').replace('+', '')
    if user_id in user_sessions:
        if session_name in user_sessions[user_id]['sessions']:
            user_sessions[user_id]['sessions'].remove(session_name)
            if user_sessions[user_id].get('self_target') == session_name:
                user_sessions[user_id]['self_target'] = None
                user_sessions[user_id]['self_active'] = False
            save_user_sessions(user_sessions)

def is_session_owner(session_name, user_id):
    user_id = str(user_id)
    session_name = session_name.replace('.session', '').replace('+', '')
    if user_id in user_sessions:
        return session_name in user_sessions[user_id]['sessions']
    return False

def load_self_active():
    return safe_load_json(SELF_ACTIVE_FILE, {})

def save_self_active(data):
    safe_save_json(SELF_ACTIVE_FILE, data)

self_active = load_self_active()

def load_self_config():
    return safe_load_json(SELF_CONFIG_FILE, {})

def save_self_config(data):
    safe_save_json(SELF_CONFIG_FILE, data)

self_config = load_self_config()

def get_self_config(session_name):
    if session_name not in self_config:
        self_config[session_name] = {
            'edit_messages': False,
            'edit_font': 'bold',
            'edit_in_private': True,
            'edit_in_groups': True,
            'edit_in_channels': True,
            'anti_delete': False,
            'auto_bio': False,
            'bio_text': ''
        }
    return self_config[session_name]

def update_self_config(session_name, key, value):
    if session_name not in self_config:
        get_self_config(session_name)
    self_config[session_name][key] = value
    save_self_config(self_config)

def load_self_stats():
    return safe_load_json(SELF_STATS_FILE, {})

def save_self_stats(data):
    safe_save_json(SELF_STATS_FILE, data)

self_stats = load_self_stats()

def get_self_stats(session_name):
    if session_name not in self_stats:
        self_stats[session_name] = {
            'messages_sent': 0,
            'messages_edited': 0,
            'reports_sent': 0,
            'created_at': now_tehran().isoformat()
        }
    return self_stats[session_name]

def increment_stat(session_name, key):
    if session_name not in self_stats:
        get_self_stats(session_name)
    self_stats[session_name][key] = self_stats[session_name].get(key, 0) + 1
    save_self_stats(self_stats)

def load_subscribers():
    return safe_load_json(SUBSCRIBERS_FILE, {})

def save_subscribers(data):
    safe_save_json(SUBSCRIBERS_FILE, data)

subscribers = load_subscribers()

def get_user_sub(user_id):
    user_id = str(user_id)
    if user_id in subscribers:
        sub = subscribers[user_id]
        if sub.get('pending'):
            return sub
        try:
            expiry = datetime.fromisoformat(sub['expiry'])
            if expiry > datetime.now():
                return sub
            del subscribers[user_id]
            save_subscribers(subscribers)
        except Exception:
            pass
    return None

def add_subscription(user_id, plan):
    user_id = str(user_id)
    plan_info = SUB_PLANS[plan]
    expiry = datetime.now() + timedelta(days=plan_info['days'])
    subscribers[user_id] = {
        'plan': plan,
        'sessions': plan_info['sessions'],
        'expiry': expiry.isoformat(),
        'added': datetime.now().isoformat(),
        'pending': False
    }
    save_subscribers(subscribers)

def load_free_trials():
    return safe_load_json(FREE_TRIAL_FILE, {})

def save_free_trials(data):
    safe_save_json(FREE_TRIAL_FILE, data)

free_trials = load_free_trials()

def has_used_free_trial(user_id):
    return str(user_id) in free_trials

def mark_free_trial_used(user_id):
    free_trials[str(user_id)] = now_tehran().isoformat()
    save_free_trials(free_trials)

def load_payments():
    data = safe_load_json(PAYMENTS_FILE, [])
    if not isinstance(data, list):
        return []
    return data

def save_payments(data):
    safe_save_json(PAYMENTS_FILE, data)

payments = load_payments()

def add_payment(user_id, username, plan, amount, method):
    payment_id = max([p['id'] for p in payments], default=0) + 1
    payment = {
        'id': payment_id,
        'user_id': str(user_id),
        'username': username,
        'plan': plan,
        'amount': amount,
        'method': method,
        'status': 'pending',
        'created': now_tehran().isoformat(),
        'approved_at': None,
        'approved_by': None
    }
    payments.append(payment)
    save_payments(payments)
    return payment

def get_payment(payment_id):
    for p in payments:
        if p['id'] == payment_id:
            return p
    return None

def approve_payment(payment_id, admin_id):
    for p in payments:
        if p['id'] == payment_id:
            if p['status'] == 'pending':
                p['status'] = 'approved'
                p['approved_at'] = now_tehran().isoformat()
                p['approved_by'] = str(admin_id)
                save_payments(payments)
                add_subscription(p['user_id'], p['plan'])
                return True, p
    return False, None

def reject_payment(payment_id, admin_id, reason=""):
    for p in payments:
        if p['id'] == payment_id:
            if p['status'] == 'pending':
                p['status'] = 'rejected'
                p['rejected_at'] = now_tehran().isoformat()
                p['rejected_by'] = str(admin_id)
                p['reason'] = reason
                save_payments(payments)
                return True, p
    return False, None

def get_user_pending_payment(user_id):
    for p in payments:
        if p['user_id'] == str(user_id) and p['status'] == 'pending':
            return p
    return None

def load_admins():
    data = safe_load_json(ADMINS_FILE, None)
    if data is None:
        default = [7733193342, 8127994507]
        save_admins(default)
        return default
    return data

def save_admins(admins):
    safe_save_json(ADMINS_FILE, admins)

def add_admin(user_id):
    admins = load_admins()
    user_id = int(user_id)
    if user_id in admins:
        return False, "Already admin!"
    if len(admins) >= MAX_ADMINS:
        return False, "Admin limit! Max " + str(MAX_ADMINS) + "."
    admins.append(user_id)
    save_admins(admins)
    return True, "Admin " + str(user_id) + " added! (" + str(len(admins)) + "/" + str(MAX_ADMINS) + ")"

def remove_admin(user_id):
    admins = load_admins()
    user_id = int(user_id)
    if user_id not in admins:
        return False, "Not an admin!"
    admins.remove(user_id)
    save_admins(admins)
    return True, "Admin " + str(user_id) + " removed! (" + str(len(admins)) + "/" + str(MAX_ADMINS) + ")"

ADMINS = load_admins()

def is_admin(user_id):
    return int(user_id) in ADMINS or int(user_id) == OWNER_ID

def is_owner(user_id):
    return int(user_id) == OWNER_ID

def parse_mtproto_proxy(proxy_input):
    if not proxy_input or proxy_input.lower() == "none":
        return None
    proxy_input = proxy_input.strip()
    server = None
    port = None
    secret = None
    if '@' in proxy_input:
        parts = proxy_input.split('@')
        secret = parts[0]
        rest = parts[1] if len(parts) > 1 else proxy_input
    else:
        rest = proxy_input
    if ':' in rest:
        colon_idx = rest.rfind(':')
        server = rest[:colon_idx]
        remaining = rest[colon_idx+1:]
        if remaining.isdigit():
            port = int(remaining)
        elif ':' in remaining:
            port_str, secret = remaining.split(':', 1)
            try:
                port = int(port_str)
            except ValueError:
                return None
    if server and port:
        return (server, port, secret)
    return None

def load_proxies():
    data = safe_load_json(PROXIES_FILE, {})
    if not isinstance(data, dict):
        return {}
    return data

def save_proxies(proxies):
    safe_save_json(PROXIES_FILE, proxies)

def get_session_proxy_config(session_name):
    proxies = load_proxies()
    proxy_str = proxies.get(session_name, "")
    return parse_mtproto_proxy(proxy_str) if proxy_str else None

async def get_sessions_async(force_refresh=False):
    async with _session_cache['lock']:
        now = time.time()
        if not force_refresh and (now - _session_cache['last_scan']) < 30:
            return _session_cache['sessions'].copy()
        if not os.path.exists(SESSION_DIR):
            os.makedirs(SESSION_DIR, exist_ok=True)
            _session_cache['sessions'] = []
            _session_cache['last_scan'] = now
            return []
        sessions = []
        try:
            for f in os.listdir(SESSION_DIR):
                if not f.endswith('.session'):
                    continue
                if f.startswith('bot'):
                    continue
                if f.startswith('test_'):
                    continue
                full_path = os.path.join(SESSION_DIR, f)
                try:
                    if os.path.getsize(full_path) > 1024:
                        sessions.append(full_path)
                except OSError:
                    continue
        except Exception as e:
            logger.error("Scan sessions error: " + str(e))
        _session_cache['sessions'] = sessions
        _session_cache['last_scan'] = now
        return sessions.copy()

def get_sessions():
    if not os.path.exists(SESSION_DIR):
        os.makedirs(SESSION_DIR, exist_ok=True)
        return []
    sessions = []
    try:
        for f in os.listdir(SESSION_DIR):
            if not f.endswith('.session'):
                continue
            if f.startswith('bot'):
                continue
            if f.startswith('test_'):
                continue
            full_path = os.path.join(SESSION_DIR, f)
            try:
                if os.path.getsize(full_path) > 1024:
                    sessions.append(full_path)
            except OSError:
                continue
    except Exception:
        pass
    return sessions

def patch_session_db(session_path):
    try:
        conn = sqlite3.connect(session_path, timeout=10.0)
        conn.execute('PRAGMA journal_mode=WAL;')
        conn.execute('PRAGMA busy_timeout=5000;')
        conn.commit()
        conn.close()
    except Exception:
        pass

def create_stable_client(session_path, use_proxy=True):
    proxy = None
    if use_proxy:
        cfg = get_session_proxy_config(os.path.basename(session_path))
        if cfg:
            proxy = (cfg[0], cfg[1], cfg[2])
    return TelegramClient(session_path, API_ID, API_HASH, timeout=30,
                         connection_retries=3, retry_delay=1,
                         auto_reconnect=True, proxy=proxy)

def get_session_lock(session_name):
    if session_name not in session_locks:
        session_locks[session_name] = asyncio.Lock()
    return session_locks[session_name]

async def check_session_auth(session_path):
    try:
        patch_session_db(session_path)
        client = create_stable_client(session_path, use_proxy=False)
        try:
            await client.connect()
            authorized = await client.is_user_authorized()
            return authorized
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass
    except Exception:
        return False

async def check_all_user_sessions_auth():
    try:
        for user_id, data in list(user_sessions.items()):
            sessions = data.get('sessions', [])
            self_target = data.get('self_target')
            if not self_target:
                continue
            all_ok = True
            for session_name in sessions:
                session_path = os.path.join(SESSION_DIR, session_name + '.session')
                if not os.path.exists(session_path):
                    all_ok = False
                    break
                authorized = await check_session_auth(session_path)
                if not authorized:
                    all_ok = False
                    break
            if not all_ok and data.get('self_active'):
                data['self_active'] = False
                save_user_sessions(user_sessions)
                if self_target in self_active:
                    del self_active[self_target]
                    save_self_active(self_active)
                if self_target in self_monitors:
                    try:
                        await self_monitors[self_target].disconnect()
                    except Exception:
                        pass
                    del self_monitors[self_target]
    except Exception as e:
        logger.error("auth check error: " + str(e))

def load_auto_replies():
    return safe_load_json(AUTO_REPLY_FILE, {})

def save_auto_replies(data):
    safe_save_json(AUTO_REPLY_FILE, data)

auto_replies = load_auto_replies()

def set_auto_reply(session_name, text):
    auto_replies[session_name] = text
    save_auto_replies(auto_replies)

def get_auto_reply(session_name):
    return auto_replies.get(session_name, DEFAULT_AUTO_REPLY)

def clear_auto_reply(session_name):
    if session_name in auto_replies:
        del auto_replies[session_name]
        save_auto_replies(auto_replies)

def load_word_filters():
    return safe_load_json(WORD_FILTER_FILE, {})

def save_word_filters(data):
    safe_save_json(WORD_FILTER_FILE, data)

word_filters = load_word_filters()

def get_word_filter(session_name):
    return word_filters.get(session_name, [])

def add_word_filter(session_name, word):
    if session_name not in word_filters:
        word_filters[session_name] = []
    if word not in word_filters[session_name]:
        word_filters[session_name].append(word)
        save_word_filters(word_filters)
        return True
    return False

def remove_word_filter(session_name, word):
    if session_name in word_filters:
        if word in word_filters[session_name]:
            word_filters[session_name].remove(word)
            save_word_filters(word_filters)
            return True
    return False

def clear_word_filter(session_name):
    if session_name in word_filters:
        del word_filters[session_name]
        save_word_filters(word_filters)

def load_clock_fonts():
    return safe_load_json(CLOCK_FONT_FILE, {})

def save_clock_fonts(data):
    safe_save_json(CLOCK_FONT_FILE, data)

clock_fonts = load_clock_fonts()

def set_clock_font(session_name, font):
    clock_fonts[session_name] = font
    save_clock_fonts(clock_fonts)

def get_clock_font(session_name):
    return clock_fonts.get(session_name, "default")

def load_emails():
    data = safe_load_json(EMAILS_FILE, [])
    if not isinstance(data, list):
        return []
    return data

def save_emails(emails):
    safe_save_json(EMAILS_FILE, emails)

def _send_smtp(email, password, msg):
    try:
        smtp_server = 'smtp.gmail.com' if 'gmail.com' in email else 'smtp.mail.yahoo.com'
        with smtplib.SMTP(smtp_server, 587, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(email, password)
            smtp.send_message(msg)
        return "success"
    except Exception:
        return "failed"

def send_email_to_telegram_abuse(report_text, target, reporter_id):
    emails = load_emails()
    if not emails:
        return 0
    success = 0
    for em in emails:
        try:
            msg = MIMEMultipart()
            msg['From'] = em['email']
            msg['To'] = "abuse@telegram.org"
            msg['Subject'] = "Report against " + target
            body = "Report Type: " + report_text + "\n"
            body += "Target: " + target + "\n"
            body += "Reporter: " + str(reporter_id) + "\n"
            body += "---\nSIGMATOR BOT"
            msg.attach(MIMEText(body, 'plain'))
            result = _send_smtp(em['email'], em['password'], msg)
            if result == "success":
                success += 1
        except Exception:
            pass
    return success

def load_scheduler():
    return safe_load_json(SCHEDULER_FILE, {})

def save_scheduler(data):
    safe_save_json(SCHEDULER_FILE, data)

scheduled_messages = load_scheduler()

# ==================== WORKERS ====================
async def report_worker(session_path, target_clean, reason, message, do_email=False, report_count=1):
    patch_session_db(session_path)
    session_name = os.path.basename(session_path)
    if daily_report_counter.get(session_name, 0) >= DAILY_REPORT_LIMIT:
        return 0
    async with WORKER_SEMAPHORE:
        lock = get_session_lock(session_name)
        async with lock:
            client = create_stable_client(session_path, use_proxy=True)
            success = 0
            try:
                await client.connect()
                if not await client.is_user_authorized():
                    return -1
                try:
                    target_entity = await client.get_input_entity(target_clean)
                except Exception:
                    try:
                        target_entity = await client.get_entity(target_clean)
                    except Exception:
                        return -1
                for i in range(report_count):
                    try:
                        await asyncio.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
                        await client(functions.account.ReportPeerRequest(
                            peer=target_entity, reason=reason, message=message
                        ))
                        daily_report_counter[session_name] = daily_report_counter.get(session_name, 0) + 1
                        success += 1
                    except FloodWaitError as e:
                        await asyncio.sleep(min(e.seconds + FLOOD_EXTRA_SLEEP, 60))
                    except Exception:
                        pass
                return success
            except Exception:
                return success if success > 0 else -1
            finally:
                try:
                    await client.disconnect()
                except Exception:
                    pass

async def join_worker(session_path, target_link):
    patch_session_db(session_path)
    session_name = os.path.basename(session_path)
    async with WORKER_SEMAPHORE:
        lock = get_session_lock(session_name)
        async with lock:
            client = create_stable_client(session_path)
            try:
                await client.connect()
                if not await client.is_user_authorized():
                    return "unauthorized"
                if '/+' in target_link:
                    invite_hash = target_link.split('+')[-1]
                    await client(functions.messages.ImportChatInviteRequest(hash=invite_hash))
                    return "joined"
                elif 'joinchat' in target_link:
                    invite_hash = target_link.split('/')[-1]
                    await client(functions.messages.ImportChatInviteRequest(hash=invite_hash))
                    return "joined"
                else:
                    target = target_link.replace('@', '').replace('https://t.me/', '').strip()
                    entity = await client.get_entity(target)
                    await client(functions.channels.JoinChannelRequest(channel=entity))
                    return "joined"
            except FloodWaitError as e:
                await asyncio.sleep(min(e.seconds + 2, 60))
                return "flood"
            except Exception as e:
                err = str(e).lower()
                if "already" in err or "user already" in err:
                    return "already"
                if "too many" in err or "channels" in err:
                    return "limited"
                return "failed"
            finally:
                try:
                    await client.disconnect()
                except Exception:
                    pass

async def group_report_worker(session_path, group_link, selected_reasons, custom_message=None):
    patch_session_db(session_path)
    session_name = os.path.basename(session_path)
    async with WORKER_SEMAPHORE:
        lock = get_session_lock(session_name)
        async with lock:
            client = create_stable_client(session_path, use_proxy=True)
            try:
                await client.connect()
                if not await client.is_user_authorized():
                    return "unauthorized"
                try:
                    if group_link.startswith('https://t.me/'):
                        entity = await client.get_entity(group_link)
                    else:
                        clean = group_link.replace('@', '').strip()
                        entity = await client.get_entity(clean)
                except Exception:
                    return "failed"
                ok = 0
                for reason, default_msg in selected_reasons:
                    if daily_report_counter.get(session_name, 0) >= DAILY_REPORT_LIMIT:
                        break
                    msg = custom_message if custom_message else default_msg
                    try:
                        await client(functions.account.ReportPeerRequest(
                            peer=entity, reason=reason, message=msg
                        ))
                        daily_report_counter[session_name] = daily_report_counter.get(session_name, 0) + 1
                        ok += 1
                        await asyncio.sleep(random.uniform(0.8, 1.5))
                    except FloodWaitError as e:
                        await asyncio.sleep(min(e.seconds + 3, 60))
                    except Exception:
                        pass
                return "reported_" + str(ok) if ok > 0 else "failed"
            except Exception as e:
                logger.error("Group report error: " + str(e))
                return "failed"
            finally:
                try:
                    await client.disconnect()
                except Exception:
                    pass

async def bot_report_worker(session_path, bot_username):
    patch_session_db(session_path)
    session_name = os.path.basename(session_path)
    async with WORKER_SEMAPHORE:
        lock = get_session_lock(session_name)
        async with lock:
            client = create_stable_client(session_path, use_proxy=True)
            try:
                await client.connect()
                if not await client.is_user_authorized():
                    return "unauthorized"
                clean = bot_username.replace('@', '').strip()
                await client(functions.account.ReportPeerRequest(
                    peer=clean,
                    reason=types.InputReportReasonSpam(),
                    message="This bot is spamming users"
                ))
                daily_report_counter[session_name] = daily_report_counter.get(session_name, 0) + 1
                return "reported"
            except FloodWaitError as e:
                await asyncio.sleep(min(e.seconds + 3, 60))
                return "failed"
            except Exception:
                return "failed"
            finally:
                try:
                    await client.disconnect()
                except Exception:
                    pass

async def profile_report_worker(session_path, user_username, reason_key="fake"):
    patch_session_db(session_path)
    session_name = os.path.basename(session_path)
    async with WORKER_SEMAPHORE:
        lock = get_session_lock(session_name)
        async with lock:
            client = create_stable_client(session_path, use_proxy=True)
            try:
                await client.connect()
                if not await client.is_user_authorized():
                    return "unauthorized"
                reason, reason_msg = ALL_REPORT_REASONS.get(
                    reason_key, (types.InputReportReasonFake(), "Fake"))
                clean = user_username.replace('@', '').strip()
                await client(functions.account.ReportPeerRequest(
                    peer=clean, reason=reason,
                    message=reason_msg + " - User profile report"
                ))
                daily_report_counter[session_name] = daily_report_counter.get(session_name, 0) + 1
                return "reported"
            except FloodWaitError as e:
                await asyncio.sleep(min(e.seconds + 3, 60))
                return "failed"
            except Exception:
                return "failed"
            finally:
                try:
                    await client.disconnect()
                except Exception:
                    pass

async def send_msg_worker(session_path, target_user, message_text):
    patch_session_db(session_path)
    session_name = os.path.basename(session_path)
    async with WORKER_SEMAPHORE:
        lock = get_session_lock(session_name)
        async with lock:
            client = create_stable_client(session_path)
            try:
                await client.connect()
                if not await client.is_user_authorized():
                    return "unauthorized"
                await client.send_message(target_user, message_text)
                return "success"
            except FloodWaitError as e:
                await asyncio.sleep(min(e.seconds + 2, 60))
                return "flood"
            except Exception:
                return "failed"
            finally:
                try:
                    await client.disconnect()
                except Exception:
                    pass

async def leave_worker(session_path, target_link):
    patch_session_db(session_path)
    session_name = os.path.basename(session_path)
    async with WORKER_SEMAPHORE:
        lock = get_session_lock(session_name)
        async with lock:
            client = create_stable_client(session_path)
            try:
                await client.connect()
                if not await client.is_user_authorized():
                    return "unauthorized"
                target = target_link.replace('@', '').strip()
                await client(functions.channels.LeaveChannelRequest(channel=await client.get_entity(target)))
                return "left"
            except FloodWaitError as e:
                await asyncio.sleep(min(e.seconds + 2, 60))
                return "flood"
            except Exception:
                return "failed"
            finally:
                try:
                    await client.disconnect()
                except Exception:
                    pass

async def reaction_worker(session_path, target_channel, emojies):
    patch_session_db(session_path)
    session_name = os.path.basename(session_path)
    async with WORKER_SEMAPHORE:
        lock = get_session_lock(session_name)
        async with lock:
            client = create_stable_client(session_path)
            try:
                await client.connect()
                if not await client.is_user_authorized():
                    return "unauthorized"
                entity = await client.get_input_entity(target_channel.replace('@', '').strip())
                messages = await client.get_messages(entity, limit=3)
                ok = 0
                for msg in messages:
                    if not msg:
                        continue
                    try:
                        await client(functions.messages.SendReactionRequest(
                            peer=entity, msg_id=msg.id,
                            reaction=[types.ReactionEmoji(emoticon=random.choice(emojies))]
                        ))
                        ok += 1
                    except Exception:
                        pass
                return "success" if ok > 0 else "failed"
            except Exception:
                return "failed"
            finally:
                try:
                    await client.disconnect()
                except Exception:
                    pass

async def safe_edit(bot, chat_id, message_id, text, buttons=None):
    try:
        if buttons:
            await bot.edit_message(chat_id, message_id, text, buttons=buttons)
        else:
            await bot.edit_message(chat_id, message_id, text)
    except Exception:
        pass

# ==================== ATTACK EXECUTORS ====================
async def run_attack(bot, chat_id, message_id, mode, target, custom_message=None):
    global is_attacking
    is_attacking = True
    reasons = {
        "scam": types.InputReportReasonSpam(),
        "porn": types.InputReportReasonPornography(),
        "violence": types.InputReportReasonViolence(),
        "child": types.InputReportReasonChildAbuse(),
        "copyright": types.InputReportReasonCopyright(),
        "fake": types.InputReportReasonFake()
    }
    reason = reasons.get(mode, types.InputReportReasonSpam())
    texts = REPORTS.get(mode, ["Report"])
    sessions = await get_sessions_async()
    if not sessions:
        await safe_edit(bot, chat_id, message_id, "No sessions!")
        is_attacking = False
        return
    ok = 0
    fail = 0
    total = len(sessions)
    count = report_count_setting
    start_time = time.time()
    for idx, s in enumerate(sessions, 1):
        if not is_attacking:
            break
        msg_text = custom_message if custom_message else random.choice(texts)
        res = await report_worker(s, target.replace('@', '').strip(), reason, msg_text, do_email=False, report_count=count)
        if res == 1 or res > 0:
            ok += 1
        else:
            fail += 1
        elapsed = int(time.time() - start_time)
        if idx % 3 == 0 or idx == total:
            txt = "Attack [" + mode.upper() + "]\n"
            txt += str(idx) + "/" + str(total) + "\n"
            txt += "Success: " + str(ok) + "\n"
            txt += "Failed: " + str(fail) + "\n"
            txt += "Report x" + str(count) + "\n"
            txt += "Rate: " + str(round((ok / total * 100), 1)) + "%\n"
            txt += "Time: " + str(elapsed) + "s"
            await safe_edit(bot, chat_id, message_id, txt)
        await asyncio.sleep(random.uniform(1.5, 3.0))
    rate = round((ok / total * 100), 1) if total > 0 else 0
    elapsed = int(time.time() - start_time)
    final = "Attack [" + mode.upper() + "] DONE\n\n"
    final += "Success: " + str(ok) + "\n"
    final += "Failed: " + str(fail) + "\n"
    final += "Rate: " + str(rate) + "%\n"
    final += "Time: " + str(elapsed) + "s"
    await safe_edit(bot, chat_id, message_id, final)
    is_attacking = False
    if custom_message:
        try:
            email_sent = send_email_to_telegram_abuse(custom_message, target, chat_id)
            if email_sent > 0:
                try:
                    await bot.send_message(chat_id, "Emails sent: " + str(email_sent))
                except Exception:
                    pass
        except Exception:
            pass

async def run_join_group(bot, chat_id, message_id, target):
    global is_attacking
    is_attacking = True
    sessions = await get_sessions_async()
    if not sessions:
        await safe_edit(bot, chat_id, message_id, "No sessions!")
        is_attacking = False
        return
    ok = 0
    fail = 0
    already = 0
    limited = 0
    total = len(sessions)
    start_time = time.time()
    for idx, s in enumerate(sessions, 1):
        if not is_attacking:
            break
        res = await join_worker(s, target)
        if res == "joined":
            ok += 1
        elif res == "already":
            already += 1
        elif res == "limited":
            limited += 1
        else:
            fail += 1
        if idx % 3 == 0 or idx == total:
            elapsed = int(time.time() - start_time)
            rate = round((ok / total * 100), 1) if total > 0 else 0
            status = "join\n\n" + str(idx) + "/" + str(total) + "\n"
            status += "Joined: " + str(ok) + "\n"
            status += "Failed: " + str(fail) + "\n"
            status += "Already: " + str(already) + "\n"
            status += "Limited: " + str(limited) + "\n"
            status += "Rate: " + str(rate) + "%\n"
            status += "Time: " + str(elapsed) + "s"
            await safe_edit(bot, chat_id, message_id, status)
        await asyncio.sleep(random.uniform(1.5, 3.0))
    elapsed = int(time.time() - start_time)
    rate = round((ok / total * 100), 1) if total > 0 else 0
    is_attacking = False
    final = "join COMPLETE\n\n"
    final += "Joined: " + str(ok) + "\n"
    final += "Failed: " + str(fail) + "\n"
    final += "Rate: " + str(rate) + "%\n"
    final += "Time: " + str(elapsed) + "s"
    await safe_edit(bot, chat_id, message_id, final)

async def run_group_report(bot, chat_id, message_id, target, selected_reasons, custom_message=None):
    global is_attacking
    is_attacking = True
    sessions = await get_sessions_async()
    if not sessions:
        await safe_edit(bot, chat_id, message_id, "No sessions!")
        is_attacking = False
        return
    ok = 0
    fail = 0
    total_reports = 0
    total = len(sessions)
    start_time = time.time()
    for idx, s in enumerate(sessions, 1):
        if not is_attacking:
            break
        res = await group_report_worker(s, target, selected_reasons, custom_message)
        if res.startswith("reported"):
            ok += 1
            total_reports += int(res.split("_")[1])
        else:
            fail += 1
        if idx % 3 == 0 or idx == total:
            elapsed = int(time.time() - start_time)
            rate = round((ok / total * 100), 1) if total > 0 else 0
            txt = "GROUP REPORT\n\n"
            txt += str(idx) + "/" + str(total) + "\n"
            txt += "Success: " + str(ok) + "\n"
            txt += "Failed: " + str(fail) + "\n"
            txt += "Total Reports: " + str(total_reports) + "\n"
            txt += "Rate: " + str(rate) + "%\n"
            txt += "Time: " + str(elapsed) + "s"
            await safe_edit(bot, chat_id, message_id, txt)
        await asyncio.sleep(random.uniform(1.5, 3.0))
    elapsed = int(time.time() - start_time)
    rate = round((ok / total * 100), 1) if total > 0 else 0
    is_attacking = False
    final = "GROUP REPORT DONE\n\n"
    final += "Success: " + str(ok) + "\n"
    final += "Failed: " + str(fail) + "\n"
    final += "Total: " + str(total_reports) + "\n"
    final += "Rate: " + str(rate) + "%\n"
    final += "Time: " + str(elapsed) + "s"
    await safe_edit(bot, chat_id, message_id, final)
    if custom_message:
        try:
            email_sent = send_email_to_telegram_abuse(custom_message, target, chat_id)
            if email_sent > 0:
                try:
                    await bot.send_message(chat_id, "Emails sent: " + str(email_sent))
                except Exception:
                    pass
        except Exception:
            pass

async def run_bot_report(bot, chat_id, message_id, bot_username):
    global is_attacking
    is_attacking = True
    sessions = await get_sessions_async()
    if not sessions:
        await safe_edit(bot, chat_id, message_id, "No sessions!")
        is_attacking = False
        return
    ok = 0
    fail = 0
    total = len(sessions)
    start_time = time.time()
    for idx, s in enumerate(sessions, 1):
        if not is_attacking:
            break
        res = await bot_report_worker(s, bot_username)
        if res == "reported":
            ok += 1
        else:
            fail += 1
        if idx % 3 == 0 or idx == total:
            elapsed = int(time.time() - start_time)
            rate = round((ok / total * 100), 1) if total > 0 else 0
            txt = "BOT REPORT\n\n"
            txt += str(idx) + "/" + str(total) + "\n"
            txt += "Success: " + str(ok) + "\n"
            txt += "Failed: " + str(fail) + "\n"
            txt += "Rate: " + str(rate) + "%\n"
            txt += "Time: " + str(elapsed) + "s"
            await safe_edit(bot, chat_id, message_id, txt)
        await asyncio.sleep(random.uniform(1.5, 3.0))
    elapsed = int(time.time() - start_time)
    rate = round((ok / total * 100), 1) if total > 0 else 0
    is_attacking = False
    final = "BOT REPORT DONE\n\n"
    final += "Success: " + str(ok) + "\n"
    final += "Failed: " + str(fail) + "\n"
    final += "Rate: " + str(rate) + "%\n"
    final += "Time: " + str(elapsed) + "s"
    await safe_edit(bot, chat_id, message_id, final)

async def run_profile_report(bot, chat_id, message_id, user_username, reason_key="fake"):
    global is_attacking
    is_attacking = True
    sessions = await get_sessions_async()
    if not sessions:
        await safe_edit(bot, chat_id, message_id, "No sessions!")
        is_attacking = False
        return
    ok = 0
    fail = 0
    total = len(sessions)
    start_time = time.time()
    for idx, s in enumerate(sessions, 1):
        if not is_attacking:
            break
        res = await profile_report_worker(s, user_username, reason_key)
        if res == "reported":
            ok += 1
        else:
            fail += 1
        if idx % 3 == 0 or idx == total:
            elapsed = int(time.time() - start_time)
            rate = round((ok / total * 100), 1) if total > 0 else 0
            txt = "PROFILE REPORT\n\n"
            txt += str(idx) + "/" + str(total) + "\n"
            txt += "Success: " + str(ok) + "\n"
            txt += "Failed: " + str(fail) + "\n"
            txt += "Rate: " + str(rate) + "%\n"
            txt += "Time: " + str(elapsed) + "s"
            await safe_edit(bot, chat_id, message_id, txt)
        await asyncio.sleep(random.uniform(1.5, 3.0))
    elapsed = int(time.time() - start_time)
    rate = round((ok / total * 100), 1) if total > 0 else 0
    is_attacking = False
    final = "PROFILE REPORT DONE\n\n"
    final += "Success: " + str(ok) + "\n"
    final += "Failed: " + str(fail) + "\n"
    final += "Rate: " + str(rate) + "%\n"
    final += "Time: " + str(elapsed) + "s"
    await safe_edit(bot, chat_id, message_id, final)

async def fast_pyrogram_worker(session_path, target_clean, reason_key="spam", custom_message=None):
    patch_session_db(session_path)
    session_name = os.path.basename(session_path)
    async with WORKER_SEMAPHORE:
        lock = get_session_lock(session_name)
        async with lock:
            client = create_stable_client(session_path, use_proxy=True)
            try:
                await client.connect()
                if not await client.is_user_authorized():
                    return "unauthorized"
                try:
                    if target_clean.startswith('https://t.me/'):
                        target_entity = await client.get_entity(target_clean)
                    else:
                        clean = target_clean.replace('@', '').strip()
                        target_entity = await client.get_entity(clean)
                except Exception:
                    return "failed"
                reason, default_msg = ALL_REPORT_REASONS.get(
                    reason_key, (types.InputReportReasonSpam(), "Spam"))
                msg = custom_message if custom_message else default_msg
                try:
                    await client(functions.account.ReportPeerRequest(
                        peer=target_entity,
                        reason=reason,
                        message=msg
                    ))
                    daily_report_counter[session_name] = daily_report_counter.get(session_name, 0) + 1
                    return "reported"
                except FloodWaitError as e:
                    await asyncio.sleep(min(e.seconds + 5, 60))
                    return "failed"
                except Exception:
                    return "failed"
            except Exception:
                return "failed"
            finally:
                try:
                    await client.disconnect()
                except Exception:
                    pass

async def run_fast_pyrogram(bot, chat_id, message_id, target, reason_key="spam", custom_message=None):
    global is_attacking
    is_attacking = True
    sessions = await get_sessions_async()
    if not sessions:
        await safe_edit(bot, chat_id, message_id, "No sessions!")
        is_attacking = False
        return
    ok = 0
    fail = 0
    total = len(sessions)
    start_time = time.time()
    for idx, s in enumerate(sessions, 1):
        if not is_attacking:
            break
        res = await fast_pyrogram_worker(s, target, reason_key, custom_message)
        if res == "reported":
            ok += 1
        else:
            fail += 1
        if idx % 3 == 0 or idx == total:
            elapsed = int(time.time() - start_time)
            rate = round((ok / total * 100), 1) if total > 0 else 0
            txt = "FAST PYROGRAM\n\n"
            txt += str(idx) + "/" + str(total) + "\n"
            txt += "Success: " + str(ok) + "\n"
            txt += "Failed: " + str(fail) + "\n"
            txt += "Rate: " + str(rate) + "%\n"
            txt += "Time: " + str(elapsed) + "s"
            await safe_edit(bot, chat_id, message_id, txt)
        await asyncio.sleep(random.uniform(1.0, 2.0))
    elapsed = int(time.time() - start_time)
    rate = round((ok / total * 100), 1) if total > 0 else 0
    is_attacking = False
    final = "FAST PYROGRAM DONE\n\n"
    final += "Success: " + str(ok) + "\n"
    final += "Failed: " + str(fail) + "\n"
    final += "Rate: " + str(rate) + "%\n"
    final += "Time: " + str(elapsed) + "s"
    await safe_edit(bot, chat_id, message_id, final)

async def clock_task_func(client, session_name):
    global is_clock_active
    last = ""
    try:
        while is_clock_active:
            try:
                font = get_clock_font(session_name)
                now = format_tehran_time_font(font)
                if now != last:
                    await client(functions.account.UpdateProfileRequest(
                        first_name="SIGMATOR " + now, last_name=""
                    ))
                    last = now
            except FloodWaitError as e:
                await asyncio.sleep(min(e.seconds + 2, 120))
            except asyncio.CancelledError:
                break
            except Exception:
                break
            await asyncio.sleep(2)
    finally:
        try:
            if client.is_connected():
                await client.disconnect()
        except Exception:
            pass

async def auto_spam_worker(client, group, message, interval):
    global is_auto_spam_active
    try:
        while is_auto_spam_active:
            try:
                entity = await client.get_entity(group)
                await client.send_message(entity, message)
            except FloodWaitError as e:
                await asyncio.sleep(min(e.seconds + 2, 300))
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(5)
                continue
            await asyncio.sleep(interval)
    finally:
        try:
            if client.is_connected():
                await client.disconnect()
        except Exception:
            pass

async def mass_email_attack(bot, chat_id, message_id, subject, body, target_channel):
    emails = load_emails()
    if not emails:
        await safe_edit(bot, chat_id, message_id, "No emails!")
        return
    success = 0
    fail = 0
    for idx, em in enumerate(emails, 1):
        await safe_edit(bot, chat_id, message_id,
            "Email " + str(idx) + "/" + str(len(emails)) + "\nSuccess: " + str(success) + "\nFailed: " + str(fail))
        msg = MIMEMultipart()
        msg['From'] = em['email']
        msg['To'] = "abuse@telegram.org"
        msg['Subject'] = subject
        msg.attach(MIMEText("Report: " + target_channel + "\nFrom: " + em['email'] + "\n" + body + "\n---\nSIGMATOR", 'plain'))
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, lambda: _send_smtp(em['email'], em['password'], msg))
        except Exception:
            result = "failed"
        if result == "success":
            success += 1
        else:
            fail += 1
        await asyncio.sleep(random.uniform(2.0, 4.0))
    total = success + fail
    rate = round((success / total * 100), 1) if total > 0 else 0
    await safe_edit(bot, chat_id, message_id, "Done\n\nSuccess: " + str(success) + "\nFailed: " + str(fail) + "\nRate: " + str(rate) + "%")

RAILWAY_URL = os.environ.get('RAILWAY_PUBLIC_DOMAIN', '')
if RAILWAY_URL and not RAILWAY_URL.startswith('http'):
    RAILWAY_URL = "https://" + RAILWAY_URL

async def health_check(request):
    return web.Response(text="OK", status=200)

async def keep_alive_pinger():
    if not RAILWAY_URL:
        return
    await asyncio.sleep(30)
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(RAILWAY_URL + "/health", timeout=10) as resp:
                    logger.info("[Keep-Alive] Ping: " + str(resp.status))
        except Exception as e:
            logger.error("[Keep-Alive] Failed: " + str(e))
        await asyncio.sleep(13 * 60)

async def run_web_server():
    web_app = web.Application()
    web_app.router.add_get('/', health_check)
    web_app.router.add_get('/health', health_check)
    runner = web.AppRunner(web_app)
    await runner.setup()
    port = int(os.environ.get('PORT', 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info("[Web] Server on port " + str(port))
    while True:
        await asyncio.sleep(3600)

# ==================== SELF PANEL SYSTEM ====================
async def send_self_panel_to_bot(bot, chat_id, message_id, session_name, user_id):
    txt = "SIGMATOR PANEL\n\n"
    txt += "Account: " + mask_phone(session_name) + "\n"
    txt += "Status: Active\n\n"
    txt += "Choose an option:"
    buttons = [
        [Button.inline("Status", ("slf_status_" + session_name).encode())],
        [Button.inline("Auto Reply", ("slf_autoreply_" + session_name).encode())],
        [Button.inline("Word Filter", ("slf_filter_" + session_name).encode())],
        [Button.inline("Clock Font", ("slf_font_" + session_name).encode())],
        [Button.inline("Email", ("slf_email_" + session_name).encode())],
        [Button.inline("Edit Messages", ("slf_edit_" + session_name).encode())],
        [Button.inline("Anti-Delete", ("slf_antidel_" + session_name).encode())],
        [Button.inline("Bio", ("slf_bio_" + session_name).encode())],
        [Button.inline("Profile Photo", ("slf_photo_" + session_name).encode())],
        [Button.inline("Scheduler", ("slf_sched_" + session_name).encode())],
        [Button.inline("Stats", ("slf_stats_" + session_name).encode())],
        [Button.inline("Info", ("slf_info_" + session_name).encode())],
        [Button.inline("Lock", ("slf_lock_" + session_name).encode())],
        [Button.inline("Logout", ("slf_logout_" + session_name).encode())],
    ]
    await safe_edit(bot, chat_id, message_id, txt, buttons=buttons)

async def handle_self_panel_callback(event, session_name, data, is_bot_ctx=False, bot=None):
    try:
        if data == "slf_status_" + session_name:
            buttons = [
                [Button.inline("Online", ("slf_setstat_online_" + session_name).encode())],
                [Button.inline("Sleep", ("slf_setstat_sleep_" + session_name).encode())],
                [Button.inline("Playing", ("slf_setstat_playing_" + session_name).encode())],
                [Button.inline("Back", ("slf_back_" + session_name).encode())],
            ]
            if is_bot_ctx:
                await safe_edit(bot, event.chat_id, event.message_id, "Select status:", buttons=buttons)
            else:
                await event.edit("Select status:", buttons=buttons)
        elif data.startswith("slf_setstat_"):
            parts = data.split("_")
            if len(parts) >= 4:
                status = parts[2]
                client = self_monitors.get(session_name)
                if client:
                    try:
                        if status == "online":
                            await client(UpdateStatusRequest(offline=False))
                        elif status == "sleep":
                            await client(UpdateStatusRequest(offline=True))
                        elif status == "playing":
                            await client(UpdateProfileRequest(first_name="SIGMATOR Playing", last_name=""))
                        await event.answer("Status updated!", alert=True)
                    except Exception as e:
                        await event.answer("Error: " + str(e)[:50], alert=True)
                else:
                    await event.answer("Monitor not active!", alert=True)
        elif data == "slf_autoreply_" + session_name:
            current = get_auto_reply(session_name)
            txt = "Auto Reply\n\nCurrent:\n" + current
            buttons = [
                [Button.inline("Edit", ("slf_editreply_" + session_name).encode())],
                [Button.inline("Clear", ("slf_clearreply_" + session_name).encode())],
                [Button.inline("Back", ("slf_back_" + session_name).encode())],
            ]
            if is_bot_ctx:
                await safe_edit(bot, event.chat_id, event.message_id, txt, buttons=buttons)
            else:
                await event.edit(txt, buttons=buttons)
        elif data == "slf_editreply_" + session_name:
            if is_bot_ctx:
                async with bot.conversation(event.chat_id, timeout=120) as conv:
                    await conv.send_message("Send new auto-reply text:")
                    resp = await conv.get_response()
                    if resp.text:
                        set_auto_reply(session_name, resp.text.strip())
                        await conv.send_message("Saved!")
            else:
                await event.edit("Send new auto-reply text in this chat:")
        elif data == "slf_clearreply_" + session_name:
            clear_auto_reply(session_name)
            await event.answer("Cleared!", alert=True)
        elif data == "slf_filter_" + session_name:
            words = get_word_filter(session_name)
            words_text = "\n".join("- " + w for w in words) if words else "(empty)"
            txt = "Word Filter\n\nBlocked words:\n" + words_text
            buttons = [
                [Button.inline("Add Word", ("slf_addword_" + session_name).encode())],
                [Button.inline("Clear All", ("slf_clearwords_" + session_name).encode())],
                [Button.inline("Back", ("slf_back_" + session_name).encode())],
            ]
            if is_bot_ctx:
                await safe_edit(bot, event.chat_id, event.message_id, txt, buttons=buttons)
            else:
                await event.edit(txt, buttons=buttons)
        elif data == "slf_addword_" + session_name:
            if is_bot_ctx:
                async with bot.conversation(event.chat_id, timeout=120) as conv:
                    await conv.send_message("Send word to block:")
                    resp = await conv.get_response()
                    if resp.text:
                        add_word_filter(session_name, resp.text.strip())
                        await conv.send_message("Added!")
            else:
                await event.edit("Send word to block:")
        elif data == "slf_clearwords_" + session_name:
            clear_word_filter(session_name)
            await event.answer("Cleared!", alert=True)
        elif data == "slf_font_" + session_name:
            current = get_clock_font(session_name)
            txt = "Clock Font\n\nCurrent: " + current + "\n\nChoose a style:"
            buttons = [
                [Button.inline("Default 14:30", ("slf_setfont_default_" + session_name).encode())],
                [Button.inline("Full 2026-10-07 14:30", ("slf_setfont_full_" + session_name).encode())],
                [Button.inline("Dot 14.30", ("slf_setfont_colon_" + session_name).encode())],
                [Button.inline("Dash 14-30", ("slf_setfont_dash_" + session_name).encode())],
                [Button.inline("Bracket [14:30]", ("slf_setfont_bracket_" + session_name).encode())],
                [Button.inline("Star *14:30*", ("slf_setfont_star_" + session_name).encode())],
                [Button.inline("Spaced 14 30", ("slf_setfont_spaced_" + session_name).encode())],
                [Button.inline("Fancy «14:30»", ("slf_setfont_fancy_" + session_name).encode())],
                [Button.inline("Emoji 14:30", ("slf_setfont_emoji_" + session_name).encode())],
                [Button.inline("Back", ("slf_back_" + session_name).encode())],
            ]
            if is_bot_ctx:
                await safe_edit(bot, event.chat_id, event.message_id, txt, buttons=buttons)
            else:
                await event.edit(txt, buttons=buttons)
        elif data.startswith("slf_setfont_"):
            font_style = data.replace("slf_setfont_", "").replace("_" + session_name, "")
            if font_style:
                set_clock_font(session_name, font_style)
                await event.answer("Font saved: " + font_style, alert=True)
        elif data == "slf_email_" + session_name:
            emails = load_emails()
            txt = "Email Manager\n\nTotal: " + str(len(emails)) + "\n\n"
            for i, em in enumerate(emails[:10], 1):
                txt += str(i) + ". " + em['email'] + "\n"
            buttons = [
                [Button.inline("Add Email", ("slf_addemail_" + session_name).encode())],
                [Button.inline("Clear All", ("slf_clearemail_" + session_name).encode())],
                [Button.inline("Back", ("slf_back_" + session_name).encode())],
            ]
            if is_bot_ctx:
                await safe_edit(bot, event.chat_id, event.message_id, txt, buttons=buttons)
            else:
                await event.edit(txt, buttons=buttons)
        elif data == "slf_addemail_" + session_name:
            if is_bot_ctx:
                async with bot.conversation(event.chat_id, timeout=180) as conv:
                    await conv.send_message("Send email address:")
                    resp = await conv.get_response()
                    email_addr = resp.text.strip() if resp.text else ""
                    await conv.send_message("Send password (app password):")
                    resp2 = await conv.get_response()
                    password = resp2.text.strip() if resp2.text else ""
                    if email_addr and password:
                        emails = load_emails()
                        emails.append({"email": email_addr, "password": password})
                        save_emails(emails)
                        await conv.send_message("Saved! Total: " + str(len(emails)))
                    else:
                        await conv.send_message("Invalid!")
        elif data == "slf_clearemail_" + session_name:
            save_emails([])
            await event.answer("Cleared!", alert=True)
        elif data == "slf_edit_" + session_name:
            cfg = get_self_config(session_name)
            status = "ON" if cfg.get('edit_messages') else "OFF"
            font = cfg.get('edit_font', 'bold')
            txt = "Edit Messages\n\n"
            txt += "Status: " + status + "\n"
            txt += "Font: " + font + "\n"
            txt += "Private: " + ("Yes" if cfg.get('edit_in_private') else "No") + "\n"
            txt += "Groups: " + ("Yes" if cfg.get('edit_in_groups') else "No") + "\n"
            txt += "Channels: " + ("Yes" if cfg.get('edit_in_channels') else "No")
            buttons = [
                [Button.inline("Toggle ON/OFF", ("slf_toggleedit_" + session_name).encode())],
                [Button.inline("Font: Bold", ("slf_seteditfont_bold_" + session_name).encode())],
                [Button.inline("Font: Italic", ("slf_seteditfont_italic_" + session_name).encode())],
                [Button.inline("Font: Fancy", ("slf_seteditfont_fancy_" + session_name).encode())],
                [Button.inline("Font: Mono", ("slf_seteditfont_mono_" + session_name).encode())],
                [Button.inline("Toggle Private", ("slf_togglepriv_" + session_name).encode())],
                [Button.inline("Toggle Groups", ("slf_togglegrp_" + session_name).encode())],
                [Button.inline("Toggle Channels", ("slf_togglechan_" + session_name).encode())],
                [Button.inline("Back", ("slf_back_" + session_name).encode())],
            ]
            if is_bot_ctx:
                await safe_edit(bot, event.chat_id, event.message_id, txt, buttons=buttons)
            else:
                await event.edit(txt, buttons=buttons)
        elif data == "slf_toggleedit_" + session_name:
            cfg = get_self_config(session_name)
            new_val = not cfg.get('edit_messages', False)
            update_self_config(session_name, 'edit_messages', new_val)
            await event.answer("Edit: " + ("ON" if new_val else "OFF"), alert=True)
        elif data.startswith("slf_seteditfont_"):
            font = data.replace("slf_seteditfont_", "").replace("_" + session_name, "")
            update_self_config(session_name, 'edit_font', font)
            await event.answer("Font: " + font, alert=True)
        elif data == "slf_togglepriv_" + session_name:
            cfg = get_self_config(session_name)
            new_val = not cfg.get('edit_in_private', True)
            update_self_config(session_name, 'edit_in_private', new_val)
            await event.answer("Private: " + ("ON" if new_val else "OFF"), alert=True)
        elif data == "slf_togglegrp_" + session_name:
            cfg = get_self_config(session_name)
            new_val = not cfg.get('edit_in_groups', True)
            update_self_config(session_name, 'edit_in_groups', new_val)
            await event.answer("Groups: " + ("ON" if new_val else "OFF"), alert=True)
        elif data == "slf_togglechan_" + session_name:
            cfg = get_self_config(session_name)
            new_val = not cfg.get('edit_in_channels', True)
            update_self_config(session_name, 'edit_in_channels', new_val)
            await event.answer("Channels: " + ("ON" if new_val else "OFF"), alert=True)
        elif data == "slf_antidel_" + session_name:
            cfg = get_self_config(session_name)
            new_val = not cfg.get('anti_delete', False)
            update_self_config(session_name, 'anti_delete', new_val)
            await event.answer("Anti-Delete: " + ("ON" if new_val else "OFF"), alert=True)
        elif data == "slf_bio_" + session_name:
            cfg = get_self_config(session_name)
            txt = "Bio\n\nAuto-bio: " + ("ON" if cfg.get('auto_bio') else "OFF") + "\n"
            txt += "Text: " + (cfg.get('bio_text') or "(empty)")
            buttons = [
                [Button.inline("Toggle", ("slf_togglebio_" + session_name).encode())],
                [Button.inline("Set Text", ("slf_setbiotxt_" + session_name).encode())],
                [Button.inline("Back", ("slf_back_" + session_name).encode())],
            ]
            if is_bot_ctx:
                await safe_edit(bot, event.chat_id, event.message_id, txt, buttons=buttons)
            else:
                await event.edit(txt, buttons=buttons)
        elif data == "slf_togglebio_" + session_name:
            cfg = get_self_config(session_name)
            new_val = not cfg.get('auto_bio', False)
            update_self_config(session_name, 'auto_bio', new_val)
            await event.answer("Bio: " + ("ON" if new_val else "OFF"), alert=True)
        elif data == "slf_setbiotxt_" + session_name:
            if is_bot_ctx:
                async with bot.conversation(event.chat_id, timeout=120) as conv:
                    await conv.send_message("Send bio text:")
                    resp = await conv.get_response()
                    if resp.text:
                        update_self_config(session_name, 'bio_text', resp.text.strip())
                        await conv.send_message("Saved!")
        elif data == "slf_photo_" + session_name:
            await event.answer("Upload photo in Saved Messages to set profile", alert=True)
        elif data == "slf_sched_" + session_name:
            txt = "Scheduler\n\nNo scheduled messages."
            buttons = [
                [Button.inline("Add", ("slf_addsched_" + session_name).encode())],
                [Button.inline("Back", ("slf_back_" + session_name).encode())],
            ]
            if is_bot_ctx:
                await safe_edit(bot, event.chat_id, event.message_id, txt, buttons=buttons)
            else:
                await event.edit(txt, buttons=buttons)
        elif data == "slf_addsched_" + session_name:
            if is_bot_ctx:
                async with bot.conversation(event.chat_id, timeout=180) as conv:
                    await conv.send_message("Send target (username/ID):")
                    resp = await conv.get_response()
                    target = resp.text.strip() if resp.text else ""
                    await conv.send_message("Send message:")
                    resp2 = await conv.get_response()
                    msg = resp2.text.strip() if resp2.text else ""
                    await conv.send_message("Delay in seconds:")
                    resp3 = await conv.get_response()
                    try:
                        delay = int(resp3.text.strip())
                    except Exception:
                        delay = 60
                    if target and msg:
                        sched_id = str(int(time.time()))
                        scheduled_messages[sched_id] = {
                            'session': session_name,
                            'target': target,
                            'message': msg,
                            'delay': delay,
                            'created': now_tehran().isoformat()
                        }
                        save_scheduler(scheduled_messages)
                        asyncio.create_task(execute_scheduled(sched_id))
                        await conv.send_message("Scheduled! Delay: " + str(delay) + "s")
        elif data == "slf_stats_" + session_name:
            stats = get_self_stats(session_name)
            txt = "Stats\n\n"
            txt += "Messages Sent: " + str(stats.get('messages_sent', 0)) + "\n"
            txt += "Messages Edited: " + str(stats.get('messages_edited', 0)) + "\n"
            txt += "Reports Sent: " + str(stats.get('reports_sent', 0)) + "\n"
            txt += "Created: " + str(stats.get('created_at', ''))[:10]
            buttons = [[Button.inline("Back", ("slf_back_" + session_name).encode())]]
            if is_bot_ctx:
                await safe_edit(bot, event.chat_id, event.message_id, txt, buttons=buttons)
            else:
                await event.edit(txt, buttons=buttons)
        elif data == "slf_info_" + session_name:
            session_path = os.path.join(SESSION_DIR, session_name + '.session')
            info_text = "Account Info\n\n"
            info_text += "Phone: " + mask_phone(session_name) + "\n"
            info_text += "File: " + session_name + ".session\n"
            info_text += "Status: " + ("Active" if os.path.exists(session_path) else "Missing")
            buttons = [[Button.inline("Back", ("slf_back_" + session_name).encode())]]
            if is_bot_ctx:
                await safe_edit(bot, event.chat_id, event.message_id, info_text, buttons=buttons)
            else:
                await event.edit(info_text, buttons=buttons)
        elif data == "slf_lock_" + session_name:
            await event.answer("Lock feature coming soon", alert=True)
        elif data == "slf_logout_" + session_name:
            await event.answer("Logout disabled for safety", alert=True)
        elif data == "slf_back_" + session_name:
            txt = "SIGMATOR PANEL\n\n"
            txt += "Account: " + mask_phone(session_name) + "\n"
            txt += "Status: Active"
            buttons = [
                [Button.inline("Status", ("slf_status_" + session_name).encode())],
                [Button.inline("Auto Reply", ("slf_autoreply_" + session_name).encode())],
                [Button.inline("Word Filter", ("slf_filter_" + session_name).encode())],
                [Button.inline("Clock Font", ("slf_font_" + session_name).encode())],
                [Button.inline("Email", ("slf_email_" + session_name).encode())],
                [Button.inline("Edit Messages", ("slf_edit_" + session_name).encode())],
                [Button.inline("Anti-Delete", ("slf_antidel_" + session_name).encode())],
                [Button.inline("Bio", ("slf_bio_" + session_name).encode())],
                [Button.inline("Profile Photo", ("slf_photo_" + session_name).encode())],
                [Button.inline("Scheduler", ("slf_sched_" + session_name).encode())],
                [Button.inline("Stats", ("slf_stats_" + session_name).encode())],
                [Button.inline("Info", ("slf_info_" + session_name).encode())],
                [Button.inline("Lock", ("slf_lock_" + session_name).encode())],
                [Button.inline("Logout", ("slf_logout_" + session_name).encode())],
            ]
            if is_bot_ctx:
                await safe_edit(bot, event.chat_id, event.message_id, txt, buttons=buttons)
            else:
                await event.edit(txt, buttons=buttons)
    except Exception as e:
        logger.error("handle_self_panel_callback error: " + str(e))

async def execute_scheduled(sched_id):
    await asyncio.sleep(5)
    if sched_id not in scheduled_messages:
        return
    data = scheduled_messages[sched_id]
    session_name = data['session']
    try:
        client = self_monitors.get(session_name)
        if client:
            await asyncio.sleep(data['delay'])
            await client.send_message(data['target'], data['message'])
            del scheduled_messages[sched_id]
            save_scheduler(scheduled_messages)
    except Exception as e:
        logger.error("Scheduler error: " + str(e))

async def start_self_monitor(session_path, user_id):
    session_name = os.path.basename(session_path).replace('.session', '')
    if session_name in self_monitors:
        return True
    patch_session_db(session_path)
    client = create_stable_client(session_path, use_proxy=True)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            return False

        @client.on(events.NewMessage(chats='me'))
        async def saved_messages_handler(event):
            try:
                text = (event.message.text or '').strip()
                logger.info("SAVED MSG: " + str(text)[:100])
                if not text:
                    return
                if text.upper() == 'SIGMATOR':
                    if not is_admin(user_id):
                        return
                    txt = "SIGMATOR PANEL\n\n"
                    txt += "Account: " + mask_phone(session_name) + "\n"
                    txt += "Status: Active\n\n"
                    txt += "Choose an option:"
                    buttons = [
                        [Button.inline("Status", ("slf_status_" + session_name).encode())],
                        [Button.inline("Auto Reply", ("slf_autoreply_" + session_name).encode())],
                        [Button.inline("Word Filter", ("slf_filter_" + session_name).encode())],
                        [Button.inline("Clock Font", ("slf_font_" + session_name).encode())],
                        [Button.inline("Email", ("slf_email_" + session_name).encode())],
                        [Button.inline("Edit Messages", ("slf_edit_" + session_name).encode())],
                        [Button.inline("Anti-Delete", ("slf_antidel_" + session_name).encode())],
                        [Button.inline("Bio", ("slf_bio_" + session_name).encode())],
                        [Button.inline("Profile Photo", ("slf_photo_" + session_name).encode())],
                        [Button.inline("Scheduler", ("slf_sched_" + session_name).encode())],
                        [Button.inline("Stats", ("slf_stats_" + session_name).encode())],
                        [Button.inline("Info", ("slf_info_" + session_name).encode())],
                        [Button.inline("Lock", ("slf_lock_" + session_name).encode())],
                        [Button.inline("Logout", ("slf_logout_" + session_name).encode())],
                    ]
                    await event.reply(txt, buttons=buttons)
            except Exception as ex:
                logger.error("Saved msg handler error: " + str(ex))

        @client.on(events.CallbackQuery)
        async def self_callback_handler(event):
            try:
                data = event.data.decode()
                if not data.startswith("slf_"):
                    return
                if not is_admin(user_id):
                    await event.answer("Only admins!", alert=True)
                    return
                await handle_self_panel_callback(event, session_name, data, is_bot_ctx=False)
            except Exception as ex:
                logger.error("Self callback error: " + str(ex))

        @client.on(events.NewMessage(incoming=True))
        async def private_auto_reply(event):
            try:
                if not event.is_private:
                    return
                if event.out:
                    return
                sender = await event.get_sender()
                if not sender:
                    return
                if getattr(sender, 'bot', False):
                    return
                reply_text = get_auto_reply(session_name)
                if reply_text:
                    await asyncio.sleep(3)
                    await event.reply(reply_text)
            except Exception:
                pass

        @client.on(events.NewMessage(outgoing=True))
        async def outgoing_edit_handler(event):
            try:
                cfg = get_self_config(session_name)
                if not cfg.get('edit_messages'):
                    return
                if not event.message.text:
                    return
                is_private = event.is_private
                is_group = event.is_group
                is_channel = event.is_channel
                should_edit = False
                if is_private and cfg.get('edit_in_private', True):
                    should_edit = True
                if is_group and cfg.get('edit_in_groups', True):
                    should_edit = True
                if is_channel and cfg.get('edit_in_channels', True):
                    should_edit = True
                if not should_edit:
                    return
                font = cfg.get('edit_font', 'bold')
                new_text = apply_font(event.message.text, font)
                if new_text and new_text != event.message.text:
                    try:
                        await asyncio.sleep(0.5)
                        await event.edit(new_text)
                        increment_stat(session_name, 'messages_edited')
                    except Exception:
                        pass
            except Exception:
                pass

        @client.on(events.MessageDeleted())
        async def anti_delete_handler(event):
            try:
                cfg = get_self_config(session_name)
                if not cfg.get('anti_delete'):
                    return
                for msg_id in event.deleted_ids:
                    try:
                        logger.info("Deleted msg: " + str(msg_id))
                    except Exception:
                        pass
            except Exception:
                pass

        self_monitors[session_name] = client
        logger.info("Self monitor started: " + session_name)
        return True
    except Exception as e:
        logger.error("Start self monitor error: " + str(e))
        try:
            await client.disconnect()
        except Exception:
            pass
        return False

async def stop_self_monitor(session_name):
    if session_name in self_monitors:
        try:
            await self_monitors[session_name].disconnect()
        except Exception:
            pass
        del self_monitors[session_name]
        return True
    return False

async def get_chat_info(client, target):
    try:
        entity = await client.get_entity(target)
        info = {}
        info['id'] = entity.id
        info['username'] = getattr(entity, 'username', None)
        info['first_name'] = getattr(entity, 'first_name', None)
        info['last_name'] = getattr(entity, 'last_name', None)
        info['phone'] = getattr(entity, 'phone', None)
        info['title'] = getattr(entity, 'title', None)
        try:
            full = await client(GetFullUserRequest(entity))
            info['bio'] = full.full_user.about
        except Exception:
            info['bio'] = None
        return info
    except Exception as e:
        return {'error': str(e)}

async def self_target_info(session_name, target):
    client = self_monitors.get(session_name)
    if not client:
        return {'error': 'Monitor not active'}
    return await get_chat_info(client, target)

# ==================== MENU & NAVIGATION ====================
async def get_menu(user_id=None):
    global is_clock_active, is_auto_spam_active
    is_admin_user = is_admin(user_id) if user_id else False
    is_owner_user = is_owner(user_id) if user_id else False
    sub = get_user_sub(user_id) if user_id and not is_admin_user else None
    has_sub = sub is not None and not sub.get('pending', False)

    if user_id and not is_admin_user and not has_sub:
        if sub and sub.get('pending'):
            current = len(get_user_accounts(user_id))
            limit = sub['sessions']
            text = "SIGMATOR BOT\n\nPENDING ACTIVATION\n\n"
            text += "Add " + str(limit) + " accounts to activate.\n"
            text += "Progress: " + str(current) + "/" + str(limit) + "\n\n"
            text += "Use /add to add accounts.\n"
            text += "Contact: " + ADMIN_CONTACT
            buttons = [[Button.inline("Check Progress", b"sub_status")]]
        elif has_used_free_trial(user_id):
            pending = get_user_pending_payment(user_id)
            if pending:
                text = "PAYMENT PENDING\n\n"
                text += "ID: #" + str(pending['id']) + "\n"
                text += "Plan: " + SUB_PLANS[pending['plan']]['name'] + "\n"
                text += "Amount: " + pending['amount'] + "\n\n"
                text += "Contact: " + ADMIN_CONTACT
                buttons = [
                    [Button.inline("Status", b"sub_status")],
                    [Button.inline("Cancel", ("cancel_payment_" + str(pending['id'])).encode())]
                ]
            else:
                text = "SIGMATOR BOT\n\nFREE TRIAL EXPIRED\n\n"
                text += "Buy premium to continue.\n\n"
                text += "1 Month - 100k\n3 Months - 200k\n6 Months - 350k\n1 Year - 500k\n\n"
                text += "Contact: " + ADMIN_CONTACT
                buttons = [
                    [Button.inline("Buy Premium", b"buy_premium")],
                    [Button.inline("My Status", b"sub_status")]
                ]
        else:
            text = "SIGMATOR BOT\n\nACCESS DENIED\n\n"
            text += "Free Trial (15 days, 5 accounts)\n"
            text += "Only available ONCE per user\n\n"
            text += "Premium:\n1 Month - 100k\n3 Months - 200k\n6 Months - 350k\n1 Year - 500k\n\n"
            text += "Commands:\n/subscribe | /add | /status | /pay | /myid"
            buttons = [
                [Button.inline("Start Free Trial", b"sub_free")],
                [Button.inline("Buy Premium", b"buy_premium")],
                [Button.inline("My Status", b"sub_status")]
            ]
        return text, buttons

    target_display = GLOBAL_TARGET if GLOBAL_TARGET else "Not set"
    tehran_time = format_tehran_time()

    if is_owner_user:
        sub_line = "Owner"
    elif is_admin_user:
        sub_line = "Admin"
    elif sub and not sub.get('pending'):
        try:
            expiry = datetime.fromisoformat(sub['expiry'])
            days_left = (expiry - datetime.now()).days
            sub_line = SUB_PLANS[sub['plan']]['name'] + " (" + str(days_left) + "d)"
        except Exception:
            sub_line = "Active"
    else:
        sub_line = "None"

    text = "SIGMATOR BOT\n--------------------\n"
    text += "Time: " + tehran_time + "\n"
    text += "Plan: " + sub_line + "\n"
    text += "Target: " + target_display + "\n"
    text += "Sessions: " + str(len(get_sessions())) + "\n"
    text += "Proxies: " + str(len(load_proxies())) + "\n"
    text += "Emails: " + str(len(load_emails())) + "\n"
    text += "Clock: " + ("ON" if is_clock_active else "OFF") + "\n"
    text += "Spam: " + ("ON" if is_auto_spam_active else "OFF") + "\n"
    text += "Report x" + str(report_count_setting) + "\n"
    text += "Status: " + ("RUNNING" if is_attacking else "IDLE") + "\n"
    text += "--------------------"

    buttons = [
        [Button.inline("SET TARGET", b"set")],
        [Button.inline("SCAM", b"a_scam"), Button.inline("PORN", b"a_porn")],
        [Button.inline("VIOLENCE", b"a_violence"), Button.inline("CHILD", b"a_child")],
        [Button.inline("COPYRIGHT", b"a_copyright"), Button.inline("FAKE", b"a_fake")],
        [Button.inline("FAST PYROGRAM", b"fast_pyrogram")],
        [Button.inline("JOIN", b"join_group"), Button.inline("GROUP REPORT", b"group_report_menu")],
        [Button.inline("BOT REPORT", b"bot_report_menu")],
        [Button.inline("PROFILE REPORT", b"profile_report_menu")],
        [Button.inline("SEND MSG", b"msg_menu")],
        [Button.inline("LEAVE", b"leave_ch"), Button.inline("REACT +", b"react_pos")],
        [Button.inline("REACT -", b"react_neg")],
        [Button.inline("PROXY", b"proxy_main"), Button.inline("EMAIL", b"email_menu")],
        [Button.inline("CLOCK", b"clock_menu")],
        [Button.inline("AUTO SPAM", b"auto_spam_menu")],
        [Button.inline("REPORT COUNT: x" + str(report_count_setting), b"set_report_count")],
        [Button.inline("MONITOR", b"monit")],
        [Button.inline("PING", b"ping"), Button.inline("STOP ALL", b"stop")],
    ]

    if user_id and (is_admin_user or has_sub):
        buttons.append([Button.inline("MY SUBSCRIPTION", b"sub_menu")])

    if is_admin_user:
        buttons.append([Button.inline("SELF PANEL", b"self_panel_menu")])
        buttons.append([Button.inline("ADMINS", b"admin_menu")])
        buttons.append([Button.inline("PAYMENTS", b"payments_panel")])

    return text, buttons

async def subscription_menu(bot, chat_id, user_id):
    sub = get_user_sub(user_id)
    is_admin_user = is_admin(user_id)
    if is_admin_user:
        text = "ADMIN ACCOUNT\n\nUnlimited access.\nContact: " + ADMIN_CONTACT
        buttons = [[Button.inline("Back", b"back")]]
    elif sub and not sub.get('pending'):
        expiry = datetime.fromisoformat(sub['expiry'])
        days_left = (expiry - datetime.now()).days
        text = "YOUR SUBSCRIPTION\n\n"
        text += "Plan: " + SUB_PLANS[sub['plan']]['name'] + "\n"
        text += "Sessions: " + str(len(get_user_accounts(user_id))) + "/" + str(sub['sessions']) + "\n"
        text += "Days Left: " + str(days_left) + "\n"
        text += "Expires: " + expiry.strftime('%Y-%m-%d')
        buttons = [
            [Button.inline("Refresh", b"sub_status")],
            [Button.inline("Renew", b"buy_premium")],
            [Button.inline("Back", b"back")]
        ]
    elif sub and sub.get('pending'):
        current = len(get_user_accounts(user_id))
        limit = sub['sessions']
        text = "PENDING ACTIVATION\n\nAdd " + str(limit) + " accounts.\nProgress: " + str(current) + "/" + str(limit)
        buttons = [
            [Button.inline("Refresh", b"sub_status")],
            [Button.inline("Back", b"back")]
        ]
    else:
        pending = get_user_pending_payment(user_id)
        if pending:
            text = "PAYMENT PENDING\n\nID: #" + str(pending['id']) + "\nPlan: " + SUB_PLANS[pending['plan']]['name'] + "\nAmount: " + pending['amount']
            buttons = [
                [Button.inline("Refresh", b"sub_status")],
                [Button.inline("Cancel", ("cancel_payment_" + str(pending['id'])).encode())],
                [Button.inline("Back", b"back")]
            ]
        else:
            text = "SUBSCRIPTION PLANS\n\n"
            text += "Free (15d, 5 accounts) - FREE\n"
            text += "1 Month - 100k\n3 Months - 200k\n6 Months - 350k\n1 Year - 500k\n\n"
            text += "Contact: " + ADMIN_CONTACT
            buttons = []
            if not has_used_free_trial(user_id):
                buttons.append([Button.inline("Start Free Trial", b"sub_free")])
            buttons.append([Button.inline("Buy Premium", b"buy_premium")])
            buttons.append([Button.inline("My Status", b"sub_status")])
            buttons.append([Button.inline("Back", b"back")])
    try:
        await bot.send_message(chat_id, text, buttons=buttons)
    except Exception:
        pass

async def buy_premium_menu(bot, chat_id, user_id):
    text = "PREMIUM PLANS\n\n"
    text += "1 Month - 50 accounts - 100,000 Toman\n"
    text += "3 Months - 100 accounts - 200,000 Toman\n"
    text += "6 Months - 150 accounts - 350,000 Toman\n"
    text += "1 Year - 200 accounts - 500,000 Toman\n\n"
    text += "Contact: " + ADMIN_CONTACT
    buttons = [
        [Button.inline("1 Month - 100k", b"plan_1month")],
        [Button.inline("3 Months - 200k", b"plan_3month")],
        [Button.inline("6 Months - 350k", b"plan_6month")],
        [Button.inline("1 Year - 500k", b"plan_1year")],
        [Button.inline("Back", b"back")]
    ]
    try:
        await bot.send_message(chat_id, text, buttons=buttons)
    except Exception:
        pass

async def payment_method_menu(bot, chat_id, plan_key):
    plan = SUB_PLANS[plan_key]
    text = "PAYMENT: " + plan['name'] + "\n\n"
    text += "Amount: " + plan['price'] + "\n"
    text += "Sessions: " + str(plan['sessions']) + "\n"
    text += "Duration: " + str(plan['days']) + " days"
    buttons = [
        [Button.inline("Card-to-Card", ("paymethod_card_" + plan_key).encode())],
        [Button.inline("Contact Admin", b"contact_admin")],
        [Button.inline("Back", b"buy_premium")]
    ]
    try:
        await bot.send_message(chat_id, text, buttons=buttons)
    except Exception:
        pass

async def show_report_reason_menu(e):
    buttons = []
    items = list(ALL_REPORT_REASONS.items())
    row = []
    for key, (_, label) in items:
        row.append(Button.inline(label, ("gr_" + key).encode()))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([Button.inline("ALL 9 REASONS", b"gr_all")])
    buttons.append([Button.inline("Back", b"back")])
    await e.edit("SELECT REPORT REASON:", buttons=buttons)

async def show_self_panel_menu(bot, chat_id, message_id, user_id):
    accounts = get_user_accounts(user_id)
    if not accounts:
        await safe_edit(bot, chat_id, message_id, "No accounts! Use /add first.")
        return
    if len(accounts) == 1:
        await send_self_panel_to_bot(bot, chat_id, message_id, accounts[0], user_id)
        return
    buttons = []
    for i, acc in enumerate(accounts[:10], 1):
        buttons.append([Button.inline(str(i) + ". " + mask_phone(acc), ("selacc_" + acc).encode())])
    buttons.append([Button.inline("Back", b"back")])
    await safe_edit(bot, chat_id, message_id, "SELECT ACCOUNT:", buttons=buttons)

async def show_payments_panel(bot, chat_id, message_id=None):
    pending = [p for p in payments if p['status'] == 'pending']
    if not pending:
        text = "PAYMENTS PANEL\n\nNo pending payments."
        buttons = [[Button.inline("All", b"all_payments")], [Button.inline("Back", b"back")]]
        if message_id:
            await safe_edit(bot, chat_id, message_id, text, buttons=buttons)
        else:
            await bot.send_message(chat_id, text, buttons=buttons)
        return
    text = "PAYMENTS PANEL\n\nPending: " + str(len(pending)) + "\n\n"
    for p in pending[-10:]:
        text += "#" + str(p['id']) + " | " + p['username'] + " | " + p['plan'] + " | " + p['amount'] + "\n"
    buttons = []
    for p in pending[-5:]:
        buttons.append([Button.inline("Review #" + str(p['id']), ("review_payment_" + str(p['id'])).encode())])
    buttons.append([Button.inline("All Payments", b"all_payments")])
    buttons.append([Button.inline("Back", b"back")])
    if message_id:
        await safe_edit(bot, chat_id, message_id, text, buttons=buttons)
    else:
        await bot.send_message(chat_id, text, buttons=buttons)

# ==================== ACCOUNT BUILDER & CHECKS ====================
async def session_builder(bot, chat_id, user_id):
    sub = get_user_sub(user_id)
    is_admin_user = is_admin(user_id)

    if not is_admin_user and not sub:
        await bot.send_message(chat_id, "No subscription!\nUse /subscribe\nContact: " + ADMIN_CONTACT)
        return

    if not is_admin_user:
        user_accounts = get_user_accounts(user_id)
        if sub.get('pending'):
            if len(user_accounts) >= MAX_ACCOUNTS_PER_USER:
                await bot.send_message(chat_id, "Limit reached! " + str(len(user_accounts)) + "/" + str(MAX_ACCOUNTS_PER_USER))
                return
        else:
            if len(user_accounts) >= sub['sessions']:
                await bot.send_message(chat_id, "Limit reached! " + str(len(user_accounts)) + "/" + str(sub['sessions']) + "\nContact: " + ADMIN_CONTACT)
                return

    try:
        async with bot.conversation(chat_id, timeout=300) as conv:
            await conv.send_message("Send phone number:\nExample: +989123456789")
            resp = await conv.get_response()
            phone = resp.text.strip() if resp.text else ""
            if not phone:
                await conv.send_message("Empty! Use /add again.")
                return
            if not phone.startswith('+'):
                phone = '+' + phone

            session_name = phone.replace('+', '')
            session_path = os.path.join(SESSION_DIR, session_name)
            client = None

            try:
                client = TelegramClient(session_path, API_ID, API_HASH)
                await client.connect()
                send_code = await client.send_code_request(phone)

                await conv.send_message(
                    "Code sent to " + mask_phone(phone) + "\n\n"
                    "Enter 5-digit code (FAST - expires in 2 min):"
                )
                resp = await conv.get_response()
                code = resp.text.strip() if resp.text else ""

                if not code:
                    await conv.send_message("Empty code! Use /add again.")
                    try:
                        await client.disconnect()
                    except Exception:
                        pass
                    return

                try:
                    await client.sign_in(phone, code, phone_code_hash=send_code.phone_code_hash)
                except SessionPasswordNeededError:
                    await conv.send_message("2FA password:")
                    resp = await conv.get_response()
                    password = resp.text.strip() if resp.text else ""
                    if not password:
                        await conv.send_message("Empty password! Use /add again.")
                        try:
                            await client.disconnect()
                        except Exception:
                            pass
                        return
                    await client.sign_in(password=password)
                except Exception as sign_err:
                    if "expired" in str(sign_err).lower():
                        await conv.send_message("Code expired! New code...")
                        send_code = await client.send_code_request(phone)
                        await conv.send_message("New code sent! Enter quickly:")
                        resp = await conv.get_response()
                        code = resp.text.strip() if resp.text else ""
                        if not code:
                            await conv.send_message("Empty code! Use /add again.")
                            try:
                                await client.disconnect()
                            except Exception:
                                pass
                            return
                        await client.sign_in(phone, code, phone_code_hash=send_code.phone_code_hash)
                    else:
                        raise sign_err

                me = await client.get_me()
                _session_cache['last_scan'] = 0

                success, reason = add_user_account(user_id, session_name)
                if not success:
                    await conv.send_message("Warning: " + reason)
                    try:
                        await client.disconnect()
                    except Exception:
                        pass
                    return

                new_count = len(get_user_accounts(user_id))
                limit = sub['sessions'] if sub else "Unlimited"

                msg = "Account Added!\n\n"
                msg += "Name: " + str(me.first_name) + "\n"
                msg += "Phone: " + mask_phone(phone) + "\n"
                msg += "Progress: " + str(new_count) + "/" + str(limit)

                if sub and sub.get('pending') and new_count >= MAX_ACCOUNTS_PER_USER:
                    add_subscription(user_id, "free")
                    msg += "\n\nFree Trial Activated!\n15 days subscription enabled!"
                    msg += "\n\nSIGMATOR SELF enabled on this account."
                    msg += "\nOpen Saved Messages on this account and type: SIGMATOR"
                    asyncio.create_task(start_self_monitor(session_path, user_id))

                await conv.send_message(msg)
            except Exception as e:
                logger.error("Session builder error: " + str(e))
                await conv.send_message("Error: " + str(e)[:100])
                try:
                    sp_file = session_path + ".session"
                    if os.path.exists(sp_file):
                        os.remove(sp_file)
                except Exception:
                    pass
            finally:
                if client:
                    try:
                        await client.disconnect()
                    except Exception:
                        pass
    except asyncio.TimeoutError:
        pass
    except Exception as e:
        logger.error("Session builder outer: " + str(e))

async def check_expired(bot):
    while True:
        try:
            expired = []
            for uid, sub in list(subscribers.items()):
                if not sub.get('pending'):
                    try:
                        expiry = datetime.fromisoformat(sub['expiry'])
                        if datetime.now() > expiry:
                            expired.append(uid)
                    except Exception:
                        pass
            for uid in expired:
                del subscribers[uid]
                try:
                    await bot.send_message(int(uid), "Subscription Expired!\n\nContact: " + ADMIN_CONTACT)
                except Exception:
                    pass
            if expired:
                save_subscribers(subscribers)
        except Exception as e:
            logger.error("Check expired error: " + str(e))
        await asyncio.sleep(3600)

async def auth_check_loop():
    while True:
        try:
            await check_all_user_sessions_auth()
        except Exception as e:
            logger.error("auth_check_loop error: " + str(e))
        await asyncio.sleep(600)

async def auto_reply_incoming_handler(bot, event):
    pass

# ==================== MAIN TELEGRAM BOT RUNNER ====================
async def main():
    global GLOBAL_TARGET, is_attacking, is_clock_active, ADMINS, clock_task
    global is_auto_spam_active, auto_spam_task, report_count_setting

    bot = TelegramClient(
        'bot_main',
        API_ID,
        API_HASH,
        connection_retries=10,
        retry_delay=3,
        timeout=60,
        auto_reconnect=True
    )
    await bot.start(bot_token=BOT_TOKEN)
    logger.info("[+] SIGMATOR BOT STARTED")
    logger.info("[+] Owner: " + OWNER_USERNAME)
    logger.info("[+] Admins: " + str(ADMINS))

    asyncio.create_task(check_expired(bot))
    asyncio.create_task(run_web_server())
    asyncio.create_task(keep_alive_pinger())
    asyncio.create_task(auth_check_loop())

    for user_id, data in user_sessions.items():
        if data.get('self_active') and data.get('self_target'):
            session_path = os.path.join(SESSION_DIR, data['self_target'] + '.session')
            if os.path.exists(session_path):
                asyncio.create_task(start_self_monitor(session_path, user_id))

    @bot.on(events.NewMessage(pattern='/start'))
    async def start_cmd(e):
        try:
            text, buttons = await get_menu(e.sender_id)
            await e.respond(text, buttons=buttons)
        except Exception as ex:
            logger.error("Start cmd error: " + str(ex))

    @bot.on(events.NewMessage(pattern='/subscribe'))
    async def sub_cmd(e):
        await subscription_menu(bot, e.chat_id, e.sender_id)

    @bot.on(events.NewMessage(pattern='/add'))
    async def add_cmd(e):
        await session_builder(bot, e.chat_id, e.sender_id)

    @bot.on(events.NewMessage(pattern='/status'))
    async def status_cmd(e):
        sub = get_user_sub(e.sender_id)
        is_admin_user = is_admin(e.sender_id)
        if is_admin_user:
            role = "Owner" if is_owner(e.sender_id) else "Admin"
            await e.respond(role + " - Unlimited")
            return
        if sub:
            if sub.get('pending'):
                await e.respond("Pending: " + str(len(get_user_accounts(e.sender_id))) + "/" + str(sub['sessions']))
            else:
                expiry = datetime.fromisoformat(sub['expiry'])
                days = (expiry - datetime.now()).days
                await e.respond(SUB_PLANS[sub['plan']]['name'] + "\n" + str(len(get_user_accounts(e.sender_id))) + "/" + str(sub['sessions']) + "\nDays: " + str(days))
        else:
            await e.respond("No subscription!\nUse /subscribe")

    @bot.on(events.NewMessage(pattern='/myid'))
    async def myid_cmd(e):
        await e.respond("Your ID: `" + str(e.sender_id) + "`")

    @bot.on(events.NewMessage(pattern='/pay'))
    async def pay_cmd(e):
        await buy_premium_menu(bot, e.chat_id, e.sender_id)

    @bot.on(events.NewMessage(pattern='/admin'))
    async def admin_cmd(e):
        if not is_admin(e.sender_id):
            await e.respond("Access denied!")
            return
        await show_payments_panel(bot, e.chat_id)

    @bot.on(events.NewMessage(pattern='/SIGMATOR'))
    async def sigmotor_cmd(e):
        if not is_admin(e.sender_id):
            await e.respond("Access denied! Only admins.")
            return
        await show_self_panel_menu(bot, e.chat_id, 0, e.sender_id)

    @bot.on(events.NewMessage(pattern='/sig'))
    async def sig_cmd(e):
        if not is_admin(e.sender_id):
            await e.respond("Access denied! Only admins.")
            return
        await show_self_panel_menu(bot, e.chat_id, 0, e.sender_id)

    @bot.on(events.NewMessage(pattern='/panel'))
    async def panel_cmd(e):
        if not is_admin(e.sender_id):
            await e.respond("Access denied! Only admins.")
            return
        await show_self_panel_menu(bot, e.chat_id, 0, e.sender_id)

    @bot.on(events.NewMessage(pattern='/email'))
    async def email_cmd(e):
        if not is_admin(e.sender_id):
            await e.respond("Access denied!")
            return
        accounts = get_user_accounts(e.sender_id)
        if not accounts:
            await e.respond("No accounts! Use /add first.")
            return
        accounts_available = accounts
        target_session = accounts_available[0]
        emails = load_emails()
        txt = "Email Manager\n\nTotal: " + str(len(emails)) + "\n\n"
        for i, em in enumerate(emails[:10], 1):
            txt += str(i) + ". " + em['email'] + "\n"
        buttons = [
            [Button.inline("Add Email", ("slf_addemail_" + target_session).encode())],
            [Button.inline("Clear All", ("slf_clearemail_" + target_session).encode())],
            [Button.inline("Back", b"back")]
        ]
        await e.respond(txt, buttons=buttons)

    @bot.on(events.NewMessage(pattern='/stats'))
    async def stats_cmd(e):
        if not is_admin(e.sender_id):
            await e.respond("Access denied!")
            return
        sessions = get_sessions()
        txt = "BOT STATS\n\n"
        txt += "Sessions: " + str(len(sessions)) + "\n"
        txt += "Users: " + str(len(user_sessions)) + "\n"
        txt += "Subscribers: " + str(len(subscribers)) + "\n"
        txt += "Payments: " + str(len(payments)) + "\n"
        txt += "Pending Payments: " + str(len([p for p in payments if p['status'] == 'pending'])) + "\n"
        txt += "Emails: " + str(len(load_emails())) + "\n"
        txt += "Proxies: " + str(len(load_proxies())) + "\n"
        txt += "Report Count: x" + str(report_count_setting) + "\n"
        txt += "Self Monitors: " + str(len(self_monitors)) + "\n"
        txt += "Clock: " + ("ON" if is_clock_active else "OFF") + "\n"
        txt += "Spam: " + ("ON" if is_auto_spam_active else "OFF")
        await e.respond(txt)

    @bot.on(events.CallbackQuery)
    async def callback(e):
        global GLOBAL_TARGET, is_attacking, is_clock_active, ADMINS, clock_task
        global is_auto_spam_active, auto_spam_task, report_count_setting

        is_admin_user = is_admin(e.sender_id)
        sub = get_user_sub(e.sender_id) if not is_admin_user else None
        has_sub = sub is not None and not sub.get('pending', False)

        data = e.data.decode()

        if not is_admin_user and not has_sub:
            allowed = ["sub_free", "sub_buy", "sub_status", "buy_premium", "contact_admin", "back"]
            allowed_prefixes = ["plan_", "paymethod_", "cancel_payment_", "submit_receipt_"]
            is_allowed = data in allowed or any(data.startswith(p) for p in allowed_prefixes)
            if not is_allowed:
                await e.answer("Subscribe first!", alert=True)
                return

        await e.answer()

        if data.startswith("slf_"):
            session_name = None
            for acc in get_user_accounts(e.sender_id):
                if acc in data:
                    session_name = acc
                    break
            if not session_name:
                return
            if not is_admin(e.sender_id):
                await e.answer("Only admins!", alert=True)
                return
            fake_event = type('obj', (object,), {
                'answer': e.answer,
                'chat_id': e.chat_id,
                'message_id': e.message_id,
                'edit': lambda self, text, buttons=None: safe_edit(bot, e.chat_id, e.message_id, text, buttons=buttons),
                'sender_id': e.sender_id,
                'get_sender': e.get_sender
            })()
            await handle_self_panel_callback(fake_event, session_name, data, is_bot_ctx=True, bot=bot)
            return

        if data.startswith("selacc_"):
            session_name = data.replace("selacc_", "")
            if is_admin(e.sender_id):
                await send_self_panel_to_bot(bot, e.chat_id, e.message_id, session_name, e.sender_id)
            return

        if data == "self_panel_menu":
            await show_self_panel_menu(bot, e.chat_id, e.message_id, e.sender_id)
            return

        if data.startswith("a_"):
            if not GLOBAL_TARGET:
                await e.respond("Set target first!")
                return
            mode = data.split('_')[1]
            await e.edit("Enter report message text for " + mode.upper() + ":")
            try:
                async with bot.conversation(e.chat_id, timeout=180) as conv:
                    resp = await conv.get_response()
                    custom_text = ""
                    if resp.text:
                        custom_text = resp.text.strip()
                    if not custom_text:
                        custom_text = REPORTS.get(mode, ["Report"])[0]
                    msg = await bot.send_message(e.chat_id, "Starting " + mode + " x" + str(report_count_setting) + "...")
                    asyncio.create_task(run_attack(bot, e.chat_id, msg.id, mode, GLOBAL_TARGET, custom_text))
            except asyncio.TimeoutError:
                await e.respond("Timeout!")

        elif data == "fast_pyrogram":
            if not GLOBAL_TARGET:
                await e.respond("Set target first!")
                return
            await e.edit("Enter report message text for FAST PYROGRAM:")
            try:
                async with bot.conversation(e.chat_id, timeout=180) as conv:
                    resp = await conv.get_response()
                    custom_text = ""
                    if resp.text:
                        custom_text = resp.text.strip()
                    if not custom_text:
                        custom_text = "Spam report"
                    msg = await bot.send_message(e.chat_id, "Starting FAST PYROGRAM...")
                    asyncio.create_task(run_fast_pyrogram(bot, e.chat_id, msg.id, GLOBAL_TARGET, "spam", custom_text))
            except asyncio.TimeoutError:
                await e.respond("Timeout!")

        elif data == "join_group":
            if not GLOBAL_TARGET:
                await e.respond("Set target first!")
                return
            msg = await e.respond("joining...")
            asyncio.create_task(run_join_group(bot, e.chat_id, msg.id, GLOBAL_TARGET))

        elif data == "group_report_menu":
            if not GLOBAL_TARGET:
                await e.respond("Set target first!")
                return
            await show_report_reason_menu(e)

        elif data == "gr_all":
            if not GLOBAL_TARGET:
                await e.respond("Set target first!")
                return
            reasons = list(ALL_REPORT_REASONS.values())
            await e.edit("Enter custom report text (or /skip):")
            try:
                async with bot.conversation(e.chat_id, timeout=180) as conv:
                    resp = await conv.get_response()
                    custom_text = resp.text.strip() if resp.text else ""
                    if custom_text == "/skip" or not custom_text:
                        custom_text = None
                    msg = await bot.send_message(e.chat_id, "ALL " + str(len(reasons)) + " reasons...")
                    asyncio.create_task(run_group_report(bot, e.chat_id, msg.id, GLOBAL_TARGET, reasons, custom_text))
            except asyncio.TimeoutError:
                await e.respond("Timeout!")

        elif data.startswith("gr_"):
            key = data[3:]
            if key in ALL_REPORT_REASONS:
                if not GLOBAL_TARGET:
                    await e.respond("Set target first!")
                    return
                reason, msg_text = ALL_REPORT_REASONS[key]
                await e.edit("Enter custom report text (or /skip):")
                try:
                    async with bot.conversation(e.chat_id, timeout=180) as conv:
                        resp = await conv.get_response()
                        custom_text = resp.text.strip() if resp.text else ""
                        if custom_text == "/skip" or not custom_text:
                            custom_text = None
                        msg = await bot.send_message(e.chat_id, msg_text + "...")
                        asyncio.create_task(run_group_report(bot, e.chat_id, msg.id, GLOBAL_TARGET, [(reason, msg_text)], custom_text))
                except asyncio.TimeoutError:
                    await e.respond("Timeout!")

        elif data == "gr_back":
            await show_report_reason_menu(e)

        elif data == "bot_report_menu":
            try:
                async with bot.conversation(e.chat_id, timeout=120) as conv:
                    await conv.send_message("Bot username:\nExample: @SomeBot")
                    resp = await conv.get_response()
                    bot_username = resp.text.strip() if resp.text else ""
                    if bot_username:
                        msg = await conv.send_message("Reporting...")
                        asyncio.create_task(run_bot_report(bot, e.chat_id, msg.id, bot_username))
            except asyncio.TimeoutError:
                await e.respond("Timeout!")

        elif data == "profile_report_menu":
            buttons = []
            items = list(ALL_REPORT_REASONS.items())
            row = []
            for key, (_, label) in items:
                row.append(Button.inline(label, ("pr_" + key).encode()))
                if len(row) == 2:
                    buttons.append(row)
                    row = []
            if row:
                buttons.append(row)
            buttons.append([Button.inline("Back", b"back")])
            await e.edit("SELECT PROFILE REPORT REASON:", buttons=buttons)

        elif data.startswith("pr_"):
            key = data[3:]
            if key in ALL_REPORT_REASONS:
                try:
                    async with bot.conversation(e.chat_id, timeout=120) as conv:
                        await conv.send_message("Target username:\nExample: @username")
                        resp = await conv.get_response()
                        user_username = resp.text.strip() if resp.text else ""
                        if user_username:
                            msg = await conv.send_message("Reporting...")
                            asyncio.create_task(run_profile_report(bot, e.chat_id, msg.id, user_username, key))
                except asyncio.TimeoutError:
                    await e.respond("Timeout!")

        elif data == "set":
            try:
                async with bot.conversation(e.chat_id, timeout=120) as conv:
                    await conv.send_message("Send target (username, ID, or link):")
                    resp = await conv.get_response()
                    new_target = resp.text.strip() if resp.text else ""
                    if new_target:
                        GLOBAL_TARGET = new_target
                        await conv.send_message("Target: " + GLOBAL_TARGET)
                        text, buttons = await get_menu(e.sender_id)
                        await conv.send_message(text, buttons=buttons)
            except asyncio.TimeoutError:
                await e.respond("Timeout!")

        elif data == "monit":
            sessions = get_sessions()
            text = "Sessions (" + str(len(sessions)) + "):\n\n"
            for i, s in enumerate(sessions[:30], 1):
                text += str(i) + ". " + safe_session_name(s) + "\n"
            await e.edit(text, buttons=[[Button.inline("Back", b"back")]])

        elif data == "stop":
            is_attacking = False
            is_auto_spam_active = False
            if auto_spam_task:
                auto_spam_task.cancel()
            if clock_task:
                clock_task.cancel()
            text, buttons = await get_menu(e.sender_id)
            await safe_edit(bot, e.chat_id, e.message_id, text, buttons=buttons)

        elif data == "back":
            text, buttons = await get_menu(e.sender_id)
            await safe_edit(bot, e.chat_id, e.message_id, text, buttons=buttons)

        elif data == "ping":
            start = time.time()
            try:
                await bot.get_me()
            except Exception:
                pass
            await e.edit("Ping: " + str(int((time.time()-start)*1000)) + "ms")

        elif data == "set_report_count":
            try:
                async with bot.conversation(e.chat_id, timeout=60) as conv:
                    await conv.send_message("How many times per session? (1-10)")
                    resp = await conv.get_response()
                    try:
                        new_count = int(resp.text.strip())
                        if new_count < 1:
                            new_count = 1
                        if new_count > 10:
                            new_count = 10
                        report_count_setting = new_count
                        save_report_count(new_count)
                        await conv.send_message("Set to x" + str(new_count))
                    except ValueError:
                        await conv.send_message("Invalid number!")
            except asyncio.TimeoutError:
                await e.respond("Timeout!")

        elif data == "leave_ch":
            if not GLOBAL_TARGET:
                await e.respond("Set target first!")
                return
            sessions = get_sessions()
            ok = 0
            fail = 0
            for s in sessions:
                res = await leave_worker(s, GLOBAL_TARGET)
                if res == "left":
                    ok += 1
                else:
                    fail += 1
            await e.respond("Left: " + str(ok) + " | Failed: " + str(fail))

        elif data in ("react_pos", "react_neg"):
            if not GLOBAL_TARGET:
                await e.respond("Set target first!")
                return
            emojies = ["1", "2", "3", "4"] if data == "react_pos" else ["5", "6", "7", "8"]
            sessions = get_sessions()
            ok = 0
            fail = 0
            for s in sessions:
                res = await reaction_worker(s, GLOBAL_TARGET, emojies)
                if res == "success":
                    ok += 1
                else:
                    fail += 1
            await e.respond("Reactions: " + str(ok) + " | Failed: " + str(fail))

        elif data == "clock_menu":
            if is_clock_active:
                is_clock_active = False
                if clock_task:
                    clock_task.cancel()
                text, buttons = await get_menu(e.sender_id)
                await safe_edit(bot, e.chat_id, e.message_id, text, buttons=buttons)
            else:
                sessions = get_sessions()
                if not sessions:
                    await e.respond("No sessions!")
                    return
                buttons = []
                for i, s in enumerate(sessions[:20]):
                    buttons.append([Button.inline(safe_session_name(s), ("clk_" + str(i)).encode())])
                buttons.append([Button.inline("Back", b"back")])
                await e.edit("Select session:", buttons=buttons)

        elif data.startswith("clk_"):
            idx = int(data.split('_')[1])
            sessions = get_sessions()
            if idx >= len(sessions):
                return
            if is_clock_active:
                is_clock_active = False
                if clock_task:
                    clock_task.cancel()
            session_path = sessions[idx]
            session_name = os.path.basename(session_path).replace('.session', '')
            client = create_stable_client(session_path)
            await client.connect()
            if await client.is_user_authorized():
                is_clock_active = True
                clock_task = asyncio.create_task(clock_task_func(client, session_name))
                await e.respond("Clock ON: " + safe_session_name(session_path))
            else:
                await e.respond("Not authorized!")

        elif data == "msg_menu":
            try:
                async with bot.conversation(e.chat_id, timeout=120) as conv:
                    await conv.send_message("Recipient (username/ID/phone):")
                    target_user = (await conv.get_response()).text.strip()
                    await conv.send_message("Text:")
                    msg_text = (await conv.get_response()).text.strip()
                    sessions = get_sessions()
                    ok = 0
                    fail = 0
                    for s in sessions:
                        res = await send_msg_worker(s, target_user, msg_text)
                        if res == "success":
                            ok += 1
                        else:
                            fail += 1
                    await conv.send_message("Sent: " + str(ok) + " | Failed: " + str(fail))
            except asyncio.TimeoutError:
                await e.respond("Timeout!")

        elif data == "proxy_main":
            buttons = [
                [Button.inline("View", b"view_proxies")],
                [Button.inline("Set", b"set_proxy")],
                [Button.inline("Remove", b"remove_proxy")],
                [Button.inline("Back", b"back")]
            ]
            await e.edit("PROXY MANAGEMENT", buttons=buttons)

        elif data == "view_proxies":
            proxies = load_proxies()
            if not proxies:
                await e.edit("No proxies!", buttons=[[Button.inline("Back", b"proxy_main")]])
                return
            text = "PROXY LIST\n\n"
            for sess, proxy in list(proxies.items())[:15]:
                if '@' in proxy:
                    proxy = proxy.split('@')[0] + "***"
                sess_display = sess.replace('.session', '')
                clean = sess_display.replace('+', '').replace('-', '').replace(' ', '')
                if clean.isdigit() and len(clean) >= 10:
                    sess_display = mask_phone(sess_display)
                text += "- " + sess_display + ": " + proxy[:50] + "...\n"
            await e.edit(text, buttons=[[Button.inline("Back", b"proxy_main")]])

        elif data == "set_proxy":
            sessions = get_sessions()
            if not sessions:
                await e.respond("No sessions!")
                return
            buttons = []
            for i, s in enumerate(sessions[:20]):
                buttons.append([Button.inline(safe_session_name(s), ("setproxy_" + str(i)).encode())])
            buttons.append([Button.inline("Back", b"proxy_main")])
            await e.edit("Select session:", buttons=buttons)

        elif data.startswith("setproxy_"):
            idx = int(data.split('_')[1])
            sessions = get_sessions()
            if idx >= len(sessions):
                return
            session_display = safe_session_name(sessions[idx])
            try:
                async with bot.conversation(e.chat_id, timeout=120) as conv:
                    await conv.send_message("Session: " + session_display + "\n\nSend proxy:")
                    proxy_input = (await conv.get_response()).text.strip()
                    proxies = load_proxies()
                    session_name = os.path.basename(sessions[idx])
                    if proxy_input.lower() == 'none':
                        proxies.pop(session_name, None)
                        save_proxies(proxies)
                        await conv.send_message("Proxy removed!")
                    else:
                        proxies[session_name] = proxy_input
                        save_proxies(proxies)
                        await conv.send_message("Proxy saved!")
            except asyncio.TimeoutError:
                await e.respond("Timeout!")

        elif data == "remove_proxy":
            sessions = get_sessions()
            if not sessions:
                await e.respond("No sessions!")
                return
            buttons = []
            for i, s in enumerate(sessions[:20]):
                buttons.append([Button.inline(safe_session_name(s), ("rmproxy_" + str(i)).encode())])
            buttons.append([Button.inline("Back", b"proxy_main")])
            await e.edit("Select session:", buttons=buttons)

        elif data.startswith("rmproxy_"):
            idx = int(data.split('_')[1])
            sessions = get_sessions()
            if idx >= len(sessions):
                return
            session_name = os.path.basename(sessions[idx])
            session_display = safe_session_name(sessions[idx])
            proxies = load_proxies()
            if session_name in proxies:
                del proxies[session_name]
                save_proxies(proxies)
                await e.respond("Removed: " + session_display)
            else:
                await e.respond("Not found!")

        elif data == "email_menu":
            buttons = [
                [Button.inline("View", b"view_emails")],
                [Button.inline("Add", b"add_email")],
                [Button.inline("Remove", b"remove_email")],
                [Button.inline("Clear", b"clear_emails")],
                [Button.inline("Start Attack", b"start_email_attack")],
                [Button.inline("Back", b"back")]
            ]
            await e.edit("EMAIL MANAGER", buttons=buttons)

        elif data == "view_emails":
            emails = load_emails()
            if not emails:
                await e.edit("No emails!", buttons=[[Button.inline("Back", b"email_menu")]])
                return
            text = "EMAILS (" + str(len(emails)) + "):\n\n"
            for i, em in enumerate(emails, 1):
                text += str(i) + ". " + em['email'] + "\n"
            await e.edit(text, buttons=[[Button.inline("Back", b"email_menu")]])

        elif data == "add_email":
            try:
                async with bot.conversation(e.chat_id, timeout=180) as conv:
                    await conv.send_message("Send email:")
                    email_addr = (await conv.get_response()).text.strip()
                    await conv.send_message("Send password:")
                    password = (await conv.get_response()).text.strip()
                    emails = load_emails()
                    emails.append({"email": email_addr, "password": password})
                    save_emails(emails)
                    await conv.send_message("Saved! Total: " + str(len(emails)))
            except asyncio.TimeoutError:
                await e.respond("Timeout!")

        elif data == "remove_email":
            emails = load_emails()
            if not emails:
                await e.edit("No emails!")
                return
            buttons = []
            for i, em in enumerate(emails):
                buttons.append([Button.inline("Remove " + em['email'][:40], ("rememail_" + str(i)).encode())])
            buttons.append([Button.inline("Back", b"email_menu")])
            await e.edit("Select:", buttons=buttons)

        elif data.startswith("rememail_"):
            idx = int(data.split('_')[1])
            emails = load_emails()
            if idx < len(emails):
                removed = emails.pop(idx)
                save_emails(emails)
                await e.respond("Removed: " + removed['email'])

        elif data == "clear_emails":
            save_emails([])
            await e.respond("Cleared!")

        elif data == "start_email_attack":
            if not GLOBAL_TARGET:
                await e.respond("Set target first!")
                return
            emails = load_emails()
            if not emails:
                await e.respond("No emails!")
                return
            try:
                async with bot.conversation(e.chat_id, timeout=180) as conv:
                    await conv.send_message("Send subject:")
                    subject = (await conv.get_response()).text.strip()
                    await conv.send_message("Send body:")
                    body = (await conv.get_response()).text.strip()
                    msg = await conv.send_message("Starting...")
                    asyncio.create_task(mass_email_attack(bot, e.chat_id, msg.id, subject, body, GLOBAL_TARGET))
            except asyncio.TimeoutError:
                await e.respond("Timeout!")

        elif data == "auto_spam_menu":
            if is_auto_spam_active:
                await e.edit("AUTO SPAM RUNNING", buttons=[
                    [Button.inline("STOP SPAM", b"stop_auto_spam")],
                    [Button.inline("Back", b"back")]
                ])
            else:
                sessions = get_sessions()
                if not sessions:
                    await e.respond("No sessions!")
                    return
                buttons = []
                for i, s in enumerate(sessions[:20]):
                    buttons.append([Button.inline(safe_session_name(s), ("as_" + str(i)).encode())])
                buttons.append([Button.inline("Back", b"back")])
                await e.edit("Select session:", buttons=buttons)

        elif data.startswith("as_"):
            idx = int(data.split('_')[1])
            sessions = get_sessions()
            if idx >= len(sessions):
                return
            session_path = sessions[idx]
            try:
                async with bot.conversation(e.chat_id, timeout=180) as conv:
                    await conv.send_message("Send group link:")
                    group = (await conv.get_response()).text.strip()
                    await conv.send_message("Send message:")
                    message = (await conv.get_response()).text.strip()
                    await conv.send_message("Interval (sec):")
                    try:
                        interval = int((await conv.get_response()).text.strip())
                    except ValueError:
                        interval = 60
                    patch_session_db(session_path)
                    client = create_stable_client(session_path, use_proxy=True)
                    await client.connect()
                    if await client.is_user_authorized():
                        is_auto_spam_active = True
                        auto_spam_task = asyncio.create_task(auto_spam_worker(client, group, message, interval))
                        await conv.send_message("Started! Interval: " + str(interval) + "s")
                    else:
                        await client.disconnect()
                        await conv.send_message("Not authorized!")
            except asyncio.TimeoutError:
                await e.respond("Timeout!")

        elif data == "stop_auto_spam":
            is_auto_spam_active = False
            if auto_spam_task:
                auto_spam_task.cancel()
            await e.respond("Stopped!")
            text, buttons = await get_menu(e.sender_id)
            await safe_edit(bot, e.chat_id, e.message_id, text, buttons=buttons)

        elif data == "sub_menu":
            await subscription_menu(bot, e.chat_id, e.sender_id)

        elif data == "sub_free":
            user_id = str(e.sender_id)
            existing = get_user_sub(e.sender_id)
            if existing and not existing.get('pending'):
                await e.answer("Already have subscription!", alert=True)
                return
            if has_used_free_trial(user_id):
                await e.answer("Already used free trial!", alert=True)
                return
            subscribers[user_id] = {
                'plan': 'free',
                'sessions': MAX_ACCOUNTS_PER_USER,
                'expiry': 'pending',
                'added': datetime.now().isoformat(),
                'pending': True
            }
            save_subscribers(subscribers)
            mark_free_trial_used(user_id)
            await e.respond(
                "Free Trial Requested!\n\n"
                "Add " + str(MAX_ACCOUNTS_PER_USER) + " accounts with /add\n"
                "Activates automatically after 5 accounts.\n\n"
                "Once per user."
            )

        elif data == "sub_buy" or data == "buy_premium":
            await buy_premium_menu(bot, e.chat_id, e.sender_id)

        elif data == "sub_status":
            sub = get_user_sub(e.sender_id)
            is_admin_user = is_admin(e.sender_id)
            if is_admin_user:
                role = "Owner" if is_owner(e.sender_id) else "Admin"
                await e.respond(role + " - Unlimited")
                return
            if sub:
                if sub.get('pending'):
                    await e.respond("Pending: " + str(len(get_user_accounts(e.sender_id))) + "/" + str(sub['sessions']))
                else:
                    expiry = datetime.fromisoformat(sub['expiry'])
                    days = (expiry - datetime.now()).days
                    await e.respond(SUB_PLANS[sub['plan']]['name'] + "\n" + str(len(get_user_accounts(e.sender_id))) + "/" + str(sub['sessions']) + "\nDays: " + str(days))
            else:
                pending = get_user_pending_payment(e.sender_id)
                if pending:
                    await e.respond("Payment Pending #" + str(pending['id']) + "\n" + pending['plan'] + " - " + pending['amount'])
                else:
                    await e.respond("No subscription!")

        elif data == "contact_admin":
            await e.respond("Contact: " + ADMIN_CONTACT)

        elif data.startswith("plan_"):
            plan_key = data[5:]
            if plan_key in SUB_PLANS and plan_key != "free":
                await payment_method_menu(bot, e.chat_id, plan_key)

        elif data.startswith("paymethod_card_"):
            plan_key = data[len("paymethod_card_"):]
            if plan_key in SUB_PLANS:
                existing = get_user_pending_payment(e.sender_id)
                if existing:
                    await e.answer("Pending #" + str(existing['id']), alert=True)
                    return
                plan = SUB_PLANS[plan_key]
                try:
                    user = await e.get_sender()
                    username = "@" + user.username if user.username else "ID:" + str(e.sender_id)
                except Exception:
                    username = "ID:" + str(e.sender_id)
                payment = add_payment(e.sender_id, username, plan_key, plan['price'], "card")
                admin_ids = load_admins()
                await e.respond(
                    "Payment Created\n\n"
                    "ID: #" + str(payment['id']) + "\n"
                    "Plan: " + plan['name'] + "\n"
                    "Amount: " + plan['price'] + "\n"
                    "Sessions: " + str(plan['sessions']) + "\n\n"
                    "Send to:\n"
                    "Card: 6037-XXXX-XXXX-XXXX\n"
                    "Owner: [Your Name]\n\n"
                    "Then submit receipt:",
                    buttons=[
                        [Button.inline("Submit Receipt", ("submit_receipt_" + str(payment['id'])).encode())],
                        [Button.inline("Cancel", ("cancel_payment_" + str(payment['id'])).encode())]
                    ]
                )
                for admin_id in admin_ids:
                    try:
                        await bot.send_message(
                            admin_id,
                            "NEW PAYMENT\n\n#" + str(payment['id']) + "\n"
                            "User: " + username + " (" + str(e.sender_id) + ")\n"
                            "Plan: " + plan['name'] + "\n"
                            "Amount: " + plan['price'] + "\n\n/admin"
                        )
                    except Exception:
                        pass

        elif data.startswith("submit_receipt_"):
            payment_id = int(data.split("_")[2])
            payment = get_payment(payment_id)
            if not payment or payment['user_id'] != str(e.sender_id):
                await e.answer("Not found!", alert=True)
                return
            try:
                async with bot.conversation(e.chat_id, timeout=300) as conv:
                    await conv.send_message("Send receipt (photo) for #" + str(payment_id) + ":")
                    resp = await conv.get_response()
                    if resp.photo or resp.document:
                        admin_ids = load_admins()
                        success = 0
                        for admin_id in admin_ids:
                            try:
                                await bot.forward_messages(admin_id, resp)
                                await bot.send_message(
                                    admin_id,
                                    "Receipt for #" + str(payment_id) + "\n" + payment['username'] + "\n" + payment['plan'] + " - " + payment['amount'] + "\n\n/admin"
                                )
                                success += 1
                            except Exception:
                                pass
                        if success > 0:
                            await conv.send_message("Sent to " + str(success) + " admin(s)!")
                        else:
                            await conv.send_message("Failed. Contact admin.")
                    else:
                        await conv.send_message("Send a photo.")
            except asyncio.TimeoutError:
                await e.respond("Timeout!")

        elif data.startswith("cancel_payment_"):
            payment_id = int(data.split("_")[2])
            payment = get_payment(payment_id)
            if not payment:
                await e.answer("Not found!", alert=True)
                return
            if payment['user_id'] != str(e.sender_id) and e.sender_id not in ADMINS:
                await e.answer("Access denied!", alert=True)
                return
            if payment['status'] != 'pending':
                await e.answer("Already " + payment['status'] + "!", alert=True)
                return
            payments.remove(payment)
            save_payments(payments)
            await e.respond("Cancelled #" + str(payment_id))
            text, buttons = await get_menu(e.sender_id)
            await safe_edit(bot, e.chat_id, e.message_id, text, buttons=buttons)

        elif data == "payments_panel":
            if not is_admin(e.sender_id):
                await e.answer("Access denied!", alert=True)
                return
            await show_payments_panel(bot, e.chat_id, e.message_id)

        elif data == "all_payments":
            if not is_admin(e.sender_id):
                await e.answer("Access denied!", alert=True)
                return
            text = "All Payments (" + str(len(payments)) + "):\n\n"
            for p in payments[-20:]:
                text += "#" + str(p['id']) + " | " + p['status'] + " | " + p['user_id'] + " | " + p['plan'] + "\n"
            await e.edit(text, buttons=[[Button.inline("Back", b"payments_panel")]])

        elif data.startswith("review_payment_"):
            if not is_admin(e.sender_id):
                await e.answer("Access denied!", alert=True)
                return
            payment_id = int(data.split("_")[2])
            payment = get_payment(payment_id)
            if not payment:
                await e.answer("Not found!", alert=True)
                return
            plan = SUB_PLANS.get(payment['plan'], {})
            text = "PAYMENT #" + str(payment['id']) + "\n\n"
            text += "User: " + payment['username'] + "\n"
            text += "User ID: " + payment['user_id'] + "\n"
            text += "Plan: " + plan.get('name', payment['plan']) + "\n"
            text += "Amount: " + payment['amount'] + "\n"
            text += "Status: " + payment['status']
            buttons = []
            if payment['status'] == 'pending':
                buttons.append([Button.inline("APPROVE", ("approve_payment_" + str(payment_id)).encode())])
                buttons.append([Button.inline("REJECT", ("reject_payment_" + str(payment_id)).encode())])
            buttons.append([Button.inline("Back", b"payments_panel")])
            await e.edit(text, buttons=buttons)

        elif data.startswith("approve_payment_"):
            if not is_admin(e.sender_id):
                await e.answer("Access denied!", alert=True)
                return
            payment_id = int(data.split("_")[2])
            success, payment = approve_payment(payment_id, e.sender_id)
            if success:
                await e.answer("Approved!", alert=True)
                try:
                    await bot.send_message(
                        int(payment['user_id']),
                        "PAYMENT APPROVED!\n\nPlan: " + SUB_PLANS[payment['plan']]['name'] + "\nSessions: " + str(SUB_PLANS[payment['plan']]['sessions']) + "\nDays: " + str(SUB_PLANS[payment['plan']]['days']) + "\n\nUse /start."
                    )
                except Exception:
                    pass
                await show_payments_panel(bot, e.chat_id, e.message_id)
            else:
                await e.answer("Already processed!", alert=True)

        elif data.startswith("reject_payment_"):
            if not is_admin(e.sender_id):
                await e.answer("Access denied!", alert=True)
                return
            payment_id = int(data.split("_")[2])
            success, payment = reject_payment(payment_id, e.sender_id, "Rejected")
            if success:
                await e.answer("Rejected!", alert=True)
                try:
                    await bot.send_message(int(payment['user_id']), "PAYMENT REJECTED\n\nContact " + ADMIN_CONTACT)
                except Exception:
                    pass
                await show_payments_panel(bot, e.chat_id, e.message_id)
            else:
                await e.answer("Already processed!", alert=True)

        elif data == "admin_menu":
            admins = load_admins()
            text = "ADMINS (" + str(len(admins)) + "/" + str(MAX_ADMINS) + ")\n\n"
            for i, a in enumerate(admins, 1):
                text += str(i) + ". " + str(a) + "\n"
            buttons = [
                [Button.inline("Add", b"admin_add")],
                [Button.inline("Remove", b"admin_remove")],
                [Button.inline("Back", b"back")]
            ]
            await e.edit(text, buttons=buttons)

        elif data == "admin_add":
            if not is_owner(e.sender_id):
                await e.answer("Only owner can add admins!", alert=True)
                return
            try:
                async with bot.conversation(e.chat_id, timeout=60) as conv:
                    await conv.send_message("User_id to add (" + str(len(load_admins())) + "/" + str(MAX_ADMINS) + "):")
                    resp = await conv.get_response()
                    try:
                        new_id = int(resp.text.strip())
                        success, msg = add_admin(new_id)
                        if success:
                            ADMINS = load_admins()
                        await conv.send_message(msg)
                    except ValueError:
                        await conv.send_message("Invalid ID!")
            except asyncio.TimeoutError:
                await e.respond("Timeout!")

        elif data == "admin_remove":
            if not is_owner(e.sender_id):
                await e.answer("Only owner can remove admins!", alert=True)
                return
            try:
                async with bot.conversation(e.chat_id, timeout=60) as conv:
                    await conv.send_message("User_id to remove:")
                    resp = await conv.get_response()
                    try:
                        del_id = int(resp.text.strip())
                        success, msg = remove_admin(del_id)
                        if success:
                            ADMINS = load_admins()
                        await conv.send_message(msg)
                    except ValueError:
                        await conv.send_message("Invalid ID!")
            except asyncio.TimeoutError:
                await e.respond("Timeout!")

    await bot.run_until_disconnected()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[!] Bot stopped")
        sys.exit(0)
