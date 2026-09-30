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
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from telethon import TelegramClient, events, functions, types, Button
from telethon.errors import FloodWaitError, RPCError, SessionPasswordNeededError
from aiohttp import web
import aiohttp

# ---------------------- TIMEZONE IRAN ----------------------
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

# ---------------------- PHONE MASK ----------------------
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

# ---------------------- LOGGING ----------------------
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.FileHandler('bot_log.txt'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ---------------------- CONFIG ----------------------
API_ID = 25342127
API_HASH = '0b75a27b1ab66bd482b6d93a0989d34f'
BOT_TOKEN = '8428206780:AAFX28ITNNv3GIUaaslSJzxVAXbUPs2CDjo'
ADMIN_CONTACT = '@AMIRALIxTAN'

GLOBAL_TARGET = None
is_attacking = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_DIR = os.path.join(BASE_DIR, 'sessions')
PROXIES_FILE = os.path.join(BASE_DIR, 'proxies.json')
ADMINS_FILE = os.path.join(BASE_DIR, 'admins.json')
EMAILS_FILE = os.path.join(BASE_DIR, 'emails.json')
SUBSCRIBERS_FILE = os.path.join(BASE_DIR, 'subscribers.json')
FREE_TRIAL_FILE = os.path.join(BASE_DIR, 'free_trial_used.json')
PAYMENTS_FILE = os.path.join(BASE_DIR, 'payments.json')

os.makedirs(SESSION_DIR, exist_ok=True)

session_locks = {}
_session_cache = {'sessions': [], 'last_scan': 0, 'lock': asyncio.Lock()}

is_clock_active = False
clock_task = None
is_auto_spam_active = False
auto_spam_task = None

DAILY_REPORT_LIMIT = 40
MIN_DELAY = 1.0
MAX_DELAY = 2.5
FLOOD_EXTRA_SLEEP = 3
CONCURRENT_LIMIT = 5
daily_report_counter = {}
MAX_ADMINS = 10

WORKER_SEMAPHORE = asyncio.Semaphore(CONCURRENT_LIMIT)

REPORTS = {
    "scam": ["This channel is completely fake and scamming users"],
    "porn": ["This channel is publishing illegal pornographic media"],
    "violence": ["This channel promotes extreme violence and hatred"],
    "child": ["This channel shares child abuse and illegal content"],
    "copyright": ["This channel steals copyrighted content illegally"],
    "fake": [
        "This channel is FAKE and impersonating an official entity",
        "Fake channel engaged in identity fraud",
        "This channel is completely fake and impersonating real organization",
    ]
}

ALL_REPORT_REASONS = {
    "child": (types.InputReportReasonChildAbuse(), "Child abuse"),
    "violence": (types.InputReportReasonViolence(), "Violence"),
    "spam": (types.InputReportReasonSpam(), "Spam"),
    "porn": (types.InputReportReasonPornography(), "Pornography"),
    "copyright": (types.InputReportReasonCopyright(), "Copyright"),
    "fake": (types.InputReportReasonFake(), "Fake Impersonation"),
    "personal": (types.InputReportReasonPersonalDetails(), "Personal data"),
    "drugs": (types.InputReportReasonIllegalDrugs(), "Illegal drugs"),
    "other": (types.InputReportReasonOther(), "Other violations"),
}

SUB_PLANS = {
    "free": {"sessions": 5, "days": 30, "name": "Free Trial (30 Days)", "price": "Free", "price_toman": 0},
    "1month": {"sessions": 50, "days": 30, "name": "1 Month", "price": "100k Toman", "price_toman": 100000},
    "3month": {"sessions": 100, "days": 90, "name": "3 Months", "price": "200k Toman", "price_toman": 200000},
    "6month": {"sessions": 150, "days": 180, "name": "6 Months", "price": "350k Toman", "price_toman": 350000},
    "1year": {"sessions": 200, "days": 365, "name": "1 Year", "price": "500k Toman", "price_toman": 500000},
}

# ---------------------- SUBSCRIBERS ----------------------
def load_subscribers():
    if os.path.exists(SUBSCRIBERS_FILE):
        try:
            with open(SUBSCRIBERS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Load subscribers error: {e}")
    return {}

def save_subscribers(data):
    try:
        with open(SUBSCRIBERS_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logger.error(f"Save subscribers error: {e}")

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
            logger.info(f"Subscription expired: {user_id}")
        except Exception as e:
            logger.error(f"get_user_sub error: {e}")
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

# ---------------------- FREE TRIAL TRACKING ----------------------
def load_free_trials():
    if os.path.exists(FREE_TRIAL_FILE):
        try:
            with open(FREE_TRIAL_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_free_trials(data):
    try:
        with open(FREE_TRIAL_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logger.error(f"Save free trials error: {e}")

free_trials = load_free_trials()

def has_used_free_trial(user_id):
    return str(user_id) in free_trials

def mark_free_trial_used(user_id):
    free_trials[str(user_id)] = now_tehran().isoformat()
    save_free_trials(free_trials)

# ---------------------- PAYMENTS ----------------------
def load_payments():
    if os.path.exists(PAYMENTS_FILE):
        try:
            with open(PAYMENTS_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_payments(data):
    try:
        with open(PAYMENTS_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logger.error(f"Save payments error: {e}")

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

# ---------------------- ADMIN ----------------------
def load_admins():
    if os.path.exists(ADMINS_FILE):
        try:
            with open(ADMINS_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    default = [7733193342, 8127994507]
    save_admins(default)
    return default

def save_admins(admins):
    try:
        with open(ADMINS_FILE, 'w') as f:
            json.dump(admins, f)
    except Exception as e:
        logger.error(f"Save admins error: {e}")

def add_admin(user_id):
    admins = load_admins()
    user_id = int(user_id)
    if user_id in admins:
        return False, "Already admin!"
    if len(admins) >= MAX_ADMINS:
        return False, f"Admin limit reached! Max {MAX_ADMINS} admins."
    admins.append(user_id)
    save_admins(admins)
    return True, f"Admin {user_id} added! ({len(admins)}/{MAX_ADMINS})"

def remove_admin(user_id):
    admins = load_admins()
    user_id = int(user_id)
    if user_id not in admins:
        return False, "Not an admin!"
    admins.remove(user_id)
    save_admins(admins)
    return True, f"Admin {user_id} removed! ({len(admins)}/{MAX_ADMINS})"

ADMINS = load_admins()

# ---------------------- PROXY ----------------------
def parse_mtproto_proxy(proxy_input):
    if not proxy_input or proxy_input.lower() == "none":
        return None
    proxy_input = proxy_input.strip()
    server, port, secret = None, None, None
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
    if os.path.exists(PROXIES_FILE):
        try:
            with open(PROXIES_FILE, 'r') as f:
                return json.loads(f.read().strip() or "{}")
        except Exception:
            return {}
    return {}

def save_proxies(proxies):
    try:
        with open(PROXIES_FILE, 'w') as f:
            json.dump(proxies, f, indent=4)
    except Exception as e:
        logger.error(f"Save proxies error: {e}")

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
                full_path = os.path.join(SESSION_DIR, f)
                try:
                    if os.path.getsize(full_path) > 1024:
                        sessions.append(full_path)
                except OSError:
                    continue
        except Exception as e:
            logger.error(f"Scan sessions error: {e}")
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

# ---------------------- WORKERS ----------------------
async def report_worker(session_path, target_clean, reason, message):
    patch_session_db(session_path)
    session_name = os.path.basename(session_path)
    if daily_report_counter.get(session_name, 0) >= DAILY_REPORT_LIMIT:
        return 0
    async with WORKER_SEMAPHORE:
        lock = get_session_lock(session_name)
        async with lock:
            client = create_stable_client(session_path, use_proxy=True)
            try:
                await client.connect()
                if not await client.is_user_authorized():
                    return -1
                target_entity = await client.get_input_entity(target_clean)
                await asyncio.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
                await client(functions.account.ReportPeerRequest(
                    peer=target_entity, reason=reason, message=message
                ))
                daily_report_counter[session_name] = daily_report_counter.get(session_name, 0) + 1
                return 1
            except FloodWaitError as e:
                await asyncio.sleep(min(e.seconds + FLOOD_EXTRA_SLEEP, 60))
                return 0
            except Exception:
                return -1
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

async def group_report_worker(session_path, group_link, selected_reasons):
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
                if group_link.startswith('https://t.me/'):
                    entity = await client.get_entity(group_link)
                else:
                    clean = group_link.replace('@', '').strip()
                    entity = await client.get_entity(clean)
                ok = 0
                for reason, msg in selected_reasons:
                    if daily_report_counter.get(session_name, 0) >= DAILY_REPORT_LIMIT:
                        break
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
                return f"reported_{ok}" if ok > 0 else "failed"
            except Exception as e:
                logger.error(f"Group report error: {e}")
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
                    message=f"{reason_msg} - User profile report"
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

# ---------------------- ATTACK RUNNERS ----------------------
async def run_attack(bot, chat_id, message_id, mode, target):
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
    ok, fail = 0, 0
    total = len(sessions)
    tasks = [report_worker(s, target.replace('@', '').strip(), reason, random.choice(texts)) for s in sessions]
    for idx, coro in enumerate(asyncio.as_completed(tasks), 1):
        if not is_attacking:
            break
        res = await coro
        if res == 1:
            ok += 1
        else:
            fail += 1
        if idx % 5 == 0 or idx == total:
            await safe_edit(bot, chat_id, message_id,
                f"Attack [{mode.upper()}]\n{idx}/{total}\nSuccess: {ok}\nFailed: {fail}")
    is_attacking = False
    await safe_edit(bot, chat_id, message_id, f"Done\n\nSuccess: {ok}\nFailed: {fail}")

async def run_join_group(bot, chat_id, message_id, target):
    global is_attacking
    is_attacking = True
    sessions = await get_sessions_async()
    if not sessions:
        await safe_edit(bot, chat_id, message_id, "No sessions!")
        is_attacking = False
        return
    ok, fail, already, limited = 0, 0, 0, 0
    failed_accounts = []
    tasks = [join_worker(s, target) for s in sessions]
    session_paths = list(sessions)
    total = len(sessions)
    for idx, coro in enumerate(asyncio.as_completed(tasks), 1):
        if not is_attacking:
            break
        res = await coro
        sname = safe_session_name(session_paths[idx-1]) if idx-1 < len(session_paths) else "?"
        if res == "joined":
            ok += 1
        elif res == "already":
            already += 1
        elif res == "limited":
            limited += 1
            failed_accounts.append(f"{sname}: Too many")
        else:
            fail += 1
            failed_accounts.append(f"{sname}: Failed")
        status = f"join\n\n{idx}/{total}\nJoined: {ok}\nFailed: {fail}\nAlready: {already}\nLimited: {limited}"
        if failed_accounts:
            status += "\n\n" + "\n".join(f"- {f}" for f in failed_accounts[-3:])
        await safe_edit(bot, chat_id, message_id, status)
    is_attacking = False
    final = f"join COMPLETE\n\nJoined: {ok}\nFailed: {fail}"
    await safe_edit(bot, chat_id, message_id, final)

async def run_group_report(bot, chat_id, message_id, target, selected_reasons):
    global is_attacking
    is_attacking = True
    sessions = await get_sessions_async()
    if not sessions:
        await safe_edit(bot, chat_id, message_id, "No sessions!")
        is_attacking = False
        return
    ok, fail, limited = 0, 0, 0
    total_reports = 0
    total = len(sessions)
    tasks = [group_report_worker(s, target, selected_reasons) for s in sessions]
    for idx, coro in enumerate(asyncio.as_completed(tasks), 1):
        if not is_attacking:
            break
        res = await coro
        if res.startswith("reported"):
            ok += 1
            total_reports += int(res.split("_")[1])
        elif res == "limited":
            limited += 1
        else:
            fail += 1
        if idx % 3 == 0 or idx == total:
            await safe_edit(bot, chat_id, message_id,
                f"GROUP REPORT\n\n{idx}/{total}\nSuccess: {ok}\nFailed: {fail}\nTotal: {total_reports}")
    is_attacking = False
    await safe_edit(bot, chat_id, message_id,
        f"GROUP REPORT DONE\n\nSuccess: {ok}\nFailed: {fail}\nTotal: {total_reports}")

async def run_bot_report(bot, chat_id, message_id, bot_username):
    global is_attacking
    is_attacking = True
    sessions = await get_sessions_async()
    if not sessions:
        await safe_edit(bot, chat_id, message_id, "No sessions!")
        is_attacking = False
        return
    ok, fail = 0, 0
    total = len(sessions)
    tasks = [bot_report_worker(s, bot_username) for s in sessions]
    for idx, coro in enumerate(asyncio.as_completed(tasks), 1):
        if not is_attacking:
            break
        res = await coro
        if res == "reported":
            ok += 1
        else:
            fail += 1
        if idx % 5 == 0 or idx == total:
            await safe_edit(bot, chat_id, message_id,
                f"BOT REPORT\n\n{idx}/{total}\nSuccess: {ok}\nFailed: {fail}")
    is_attacking = False
    await safe_edit(bot, chat_id, message_id,
        f"BOT REPORT DONE\n\nSuccess: {ok}\nFailed: {fail}")

async def run_profile_report(bot, chat_id, message_id, user_username, reason_key="fake"):
    global is_attacking
    is_attacking = True
    sessions = await get_sessions_async()
    if not sessions:
        await safe_edit(bot, chat_id, message_id, "No sessions!")
        is_attacking = False
        return
    ok, fail = 0, 0
    total = len(sessions)
    tasks = [profile_report_worker(s, user_username, reason_key) for s in sessions]
    for idx, coro in enumerate(asyncio.as_completed(tasks), 1):
        if not is_attacking:
            break
        res = await coro
        if res == "reported":
            ok += 1
        else:
            fail += 1
        if idx % 5 == 0 or idx == total:
            await safe_edit(bot, chat_id, message_id,
                f"PROFILE REPORT\n\n{idx}/{total}\nSuccess: {ok}\nFailed: {fail}")
    is_attacking = False
    await safe_edit(bot, chat_id, message_id,
        f"PROFILE REPORT DONE\n\nSuccess: {ok}\nFailed: {fail}")

# ---------------------- CLOCK ----------------------
async def clock_task_func(client):
    global is_clock_active
    last = ""
    try:
        while is_clock_active:
            try:
                now = format_tehran_time()
                if now != last:
                    await client(functions.account.UpdateProfileRequest(
                        first_name=f"SIGMATOR {now}", last_name=""
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

# ---------------------- AUTO SPAM ----------------------
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

# ---------------------- HELPERS ----------------------
async def safe_edit(bot, chat_id, message_id, text, buttons=None):
    try:
        if buttons:
            await bot.edit_message(chat_id, message_id, text, buttons=buttons)
        else:
            await bot.edit_message(chat_id, message_id, text)
    except Exception:
        pass

# ---------------------- EMAIL ----------------------
def load_emails():
    if os.path.exists(EMAILS_FILE):
        try:
            with open(EMAILS_FILE, 'r') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
    return []

def save_emails(emails):
    try:
        with open(EMAILS_FILE, 'w') as f:
            json.dump(emails, f, indent=4)
    except Exception as e:
        logger.error(f"Save emails error: {e}")

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

async def mass_email_attack(bot, chat_id, message_id, subject, body, target_channel):
    emails = load_emails()
    if not emails:
        await safe_edit(bot, chat_id, message_id, "No emails!")
        return
    success, fail = 0, 0
    for idx, em in enumerate(emails, 1):
        await safe_edit(bot, chat_id, message_id,
            f"Email {idx}/{len(emails)}\nSuccess: {success}\nFailed: {fail}")
        msg = MIMEMultipart()
        msg['From'] = em['email']
        msg['To'] = "abuse@telegram.org"
        msg['Subject'] = subject
        msg.attach(MIMEText(f"Report: {target_channel}\nFrom: {em['email']}\n{body}\n---\nSIGMATOR", 'plain'))
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
    await safe_edit(bot, chat_id, message_id, f"Done\n\nSuccess: {success}\nFailed: {fail}")

# ---------------------- KEEP ALIVE ----------------------
RAILWAY_URL = os.environ.get('RAILWAY_PUBLIC_DOMAIN', '')
if RAILWAY_URL and not RAILWAY_URL.startswith('http'):
    RAILWAY_URL = f"https://{RAILWAY_URL}"

async def health_check(request):
    return web.Response(text="OK", status=200)

async def keep_alive_pinger():
    if not RAILWAY_URL:
        logger.info("[Keep-Alive] No RAILWAY_PUBLIC_DOMAIN set")
        return
    await asyncio.sleep(30)
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{RAILWAY_URL}/health", timeout=10) as resp:
                    logger.info(f"[Keep-Alive] Ping: {resp.status}")
        except Exception as e:
            logger.error(f"[Keep-Alive] Failed: {e}")
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
    logger.info(f"[Web] Server on port {port}")
    while True:
        await asyncio.sleep(3600)

# ---------------------- MENU ----------------------
async def get_menu(user_id=None):
    global is_clock_active, is_auto_spam_active

    is_admin_user = user_id in ADMINS if user_id else False
    sub = get_user_sub(user_id) if user_id and not is_admin_user else None
    has_sub = sub is not None and not sub.get('pending', False)

    if user_id and not is_admin_user and not has_sub:
        if sub and sub.get('pending'):
            current = len(get_sessions())
            limit = sub['sessions']
            text = f"""SIGMATOR BOT

PENDING ACTIVATION

Add {limit} accounts to activate your 30-day subscription.
Progress: {current}/{limit}

Use /add to add accounts.
Contact: {ADMIN_CONTACT}"""
            buttons = [[Button.inline("Check Progress", b"sub_status")]]
        elif has_used_free_trial(user_id):
            pending = get_user_pending_payment(user_id)
            if pending:
                text = f"""PAYMENT PENDING

Plan: {SUB_PLANS[pending['plan']]['name']}
Amount: {pending['amount']}
Payment ID: #{pending['id']}

Contact: {ADMIN_CONTACT}"""
                buttons = [
                    [Button.inline("My Status", b"sub_status")],
                    [Button.inline("Cancel", f"cancel_payment_{pending['id']}".encode())]
                ]
            else:
                text = f"""SIGMATOR BOT

FREE TRIAL EXPIRED

Purchase a premium plan to continue.

Plans:
1 Month - 100k Toman
3 Months - 200k Toman
6 Months - 350k Toman
1 Year - 500k Toman

Contact: {ADMIN_CONTACT}"""
                buttons = [
                    [Button.inline("Buy Premium", b"buy_premium")],
                    [Button.inline("My Status", b"sub_status")]
                ]
        else:
            text = f"""SIGMATOR BOT

ACCESS DENIED

Free Trial - 30 Days (5 accounts)
Only available ONCE per user

Premium:
1 Month - 100k Toman
3 Months - 200k Toman
6 Months - 350k Toman
1 Year - 500k Toman

Commands:
/subscribe | /add | /status | /pay | /myid"""
            buttons = [
                [Button.inline("Start Free Trial", b"sub_free")],
                [Button.inline("Buy Premium", b"buy_premium")],
                [Button.inline("My Status", b"sub_status")]
            ]
        return text, buttons

    target_display = GLOBAL_TARGET if GLOBAL_TARGET else "Not set"
    tehran_time = format_tehran_time()

    if is_admin_user:
        sub_line = "Admin"
    elif sub and not sub.get('pending'):
        try:
            expiry = datetime.fromisoformat(sub['expiry'])
            days_left = (expiry - datetime.now()).days
            sub_line = f"{SUB_PLANS[sub['plan']]['name']} ({days_left}d)"
        except Exception:
            sub_line = "Active"
    else:
        sub_line = "None"

    text = f"""SIGMATOR BOT
--------------------
Time: {tehran_time}
Plan: {sub_line}
Target: {target_display}
Sessions: {len(get_sessions())}
Proxies: {len(load_proxies())}
Emails: {len(load_emails())}
Clock: {'ON' if is_clock_active else 'OFF'}
Spam: {'ON' if is_auto_spam_active else 'OFF'}
Status: {'RUNNING' if is_attacking else 'IDLE'}
--------------------"""

    buttons = [
        [Button.inline("SET TARGET", b"set")],
        [Button.inline("SCAM", b"a_scam"), Button.inline("PORN", b"a_porn")],
        [Button.inline("VIOLENCE", b"a_violence"), Button.inline("CHILD", b"a_child")],
        [Button.inline("COPYRIGHT", b"a_copyright"), Button.inline("FAKE", b"a_fake")],
        [Button.inline("JOIN", b"join_group"), Button.inline("GROUP REPORT", b"group_report_menu")],
        [Button.inline("BOT REPORT", b"bot_report_menu")],
        [Button.inline("PROFILE REPORT", b"profile_report_menu")],
        [Button.inline("SEND MSG", b"msg_menu")],
        [Button.inline("LEAVE", b"leave_ch"), Button.inline("REACT +", b"react_pos")],
        [Button.inline("REACT -", b"react_neg")],
        [Button.inline("PROXY", b"proxy_main"), Button.inline("EMAIL", b"email_menu")],
        [Button.inline(f"CLOCK {'ON' if is_clock_active else 'OFF'}", b"clock_menu")],
        [Button.inline(f"AUTO SPAM ({'ON' if is_auto_spam_active else 'OFF'})", b"auto_spam_menu")],
        [Button.inline("MONITOR", b"monit")],
        [Button.inline("PING", b"ping"), Button.inline("STOP ALL", b"stop")],
    ]

    if user_id and (is_admin_user or has_sub):
        buttons.append([Button.inline("MY SUBSCRIPTION", b"sub_menu")])

    if is_admin_user:
        buttons.append([Button.inline("ADMINS", b"admin_menu")])
        buttons.append([Button.inline("PAYMENTS", b"payments_panel")])

    return text, buttons

# ---------------------- SUBSCRIPTION MENU ----------------------
async def subscription_menu(bot, chat_id, user_id):
    sub = get_user_sub(user_id)
    is_admin_user = user_id in ADMINS

    if is_admin_user:
        text = f"ADMIN ACCOUNT\n\nUnlimited access.\nContact: {ADMIN_CONTACT}"
        buttons = [[Button.inline("Back", b"back")]]
    elif sub and not sub.get('pending'):
        expiry = datetime.fromisoformat(sub['expiry'])
        days_left = (expiry - datetime.now()).days
        text = f"""YOUR SUBSCRIPTION

Plan: {SUB_PLANS[sub['plan']]['name']}
Sessions: {len(get_sessions())}/{sub['sessions']}
Days Left: {days_left} days
Expires: {expiry.strftime('%Y-%m-%d')}"""
        buttons = [
            [Button.inline("Refresh", b"sub_status")],
            [Button.inline("Renew", b"buy_premium")],
            [Button.inline("Back", b"back")]
        ]
    elif sub and sub.get('pending'):
        current = len(get_sessions())
        limit = sub['sessions']
        text = f"""PENDING ACTIVATION

Add {limit} accounts to activate.
Progress: {current}/{limit}

Use /add."""
        buttons = [
            [Button.inline("Refresh", b"sub_status")],
            [Button.inline("Back", b"back")]
        ]
    else:
        pending = get_user_pending_payment(user_id)
        if pending:
            text = f"""PAYMENT PENDING

ID: #{pending['id']}
Plan: {SUB_PLANS[pending['plan']]['name']}
Amount: {pending['amount']}

Waiting for admin.
Contact: {ADMIN_CONTACT}"""
            buttons = [
                [Button.inline("Refresh", b"sub_status")],
                [Button.inline("Cancel", f"cancel_payment_{pending['id']}".encode())],
                [Button.inline("Back", b"back")]
            ]
        else:
            text = f"""SUBSCRIPTION PLANS

Free Trial (30 days, 5 accounts) - FREE
Premium:
1 Month - 100k Toman
3 Months - 200k Toman
6 Months - 350k Toman
1 Year - 500k Toman

Contact: {ADMIN_CONTACT}"""
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
    text = f"""PREMIUM PLANS

1 Month  - 50 accounts  - 100,000 Toman
3 Months - 100 accounts - 200,000 Toman
6 Months - 150 accounts - 350,000 Toman
1 Year   - 200 accounts - 500,000 Toman

Payment: Card-to-Card

Contact: {ADMIN_CONTACT}"""
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
    text = f"""PAYMENT: {plan['name']}

Amount: {plan['price']}
Sessions: {plan['sessions']}
Duration: {plan['days']} days

Choose method:"""
    buttons = [
        [Button.inline("Card-to-Card", f"paymethod_card_{plan_key}".encode())],
        [Button.inline("Contact Admin", b"contact_admin")],
        [Button.inline("Back", b"buy_premium")]
    ]
    try:
        await bot.send_message(chat_id, text, buttons=buttons)
    except Exception:
        pass

# ---------------------- SESSION BUILDER ----------------------
async def session_builder(bot, chat_id, user_id):
    sub = get_user_sub(user_id)
    is_admin_user = user_id in ADMINS

    if not is_admin_user and not sub:
        await bot.send_message(chat_id, f"No subscription!\nUse /subscribe\nContact: {ADMIN_CONTACT}")
        return

    if not is_admin_user:
        current = len(get_sessions())
        if current >= sub['sessions']:
            await bot.send_message(chat_id, f"Limit reached! {current}/{sub['sessions']}\nContact: {ADMIN_CONTACT}")
            return

    try:
        async with bot.conversation(chat_id, timeout=300) as conv:
            await conv.send_message("Send phone number:\nExample: +989123456789")
            resp = await conv.get_response()
            phone = resp.text.strip()
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
                    f"Code sent to {mask_phone(phone)}\n\n"
                    f"Enter the 5-digit code (BE FAST - expires in 2 min):"
                )
                resp = await conv.get_response()
                code = resp.text.strip()

                try:
                    await client.sign_in(phone, code, phone_code_hash=send_code.phone_code_hash)
                except SessionPasswordNeededError:
                    await conv.send_message("2FA Enabled! Enter password:")
                    resp = await conv.get_response()
                    password = resp.text.strip()
                    await client.sign_in(password=password)
                except Exception as sign_err:
                    if "expired" in str(sign_err).lower():
                        await conv.send_message("Code expired! Requesting new code...")
                        send_code = await client.send_code_request(phone)
                        await conv.send_message("New code sent! Enter quickly:")
                        resp = await conv.get_response()
                        code = resp.text.strip()
                        await client.sign_in(phone, code, phone_code_hash=send_code.phone_code_hash)
                    else:
                        raise sign_err

                me = await client.get_me()
                _session_cache['last_scan'] = 0
                new_count = len(get_sessions())
                limit = sub['sessions'] if sub else "Unlimited"

                msg = f"Account Added!\n\nName: {me.first_name}\nPhone: {mask_phone(phone)}\nProgress: {new_count}/{limit}"

                if sub and sub.get('pending') and new_count >= sub['sessions']:
                    add_subscription(user_id, "free")
                    msg += "\n\nFree Trial Activated!\n30-day access enabled.\n\nUse /start."

                await conv.send_message(msg)
            except Exception as e:
                logger.error(f"Session builder error: {e}")
                await conv.send_message(f"Error: {str(e)[:100]}")
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
        logger.error(f"Session builder outer error: {e}")

# ---------------------- CHECK EXPIRED ----------------------
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
                    await bot.send_message(
                        int(uid),
                        f"Subscription Expired!\n\n"
                        f"Your subscription has expired.\n"
                        f"Purchase a new plan to continue.\n\n"
                        f"Contact: {ADMIN_CONTACT}"
                    )
                except Exception:
                    pass

            if expired:
                save_subscribers(subscribers)
                logger.info(f"Expired subs removed: {len(expired)}")
        except Exception as e:
            logger.error(f"Check expired error: {e}")
        await asyncio.sleep(3600)

# ---------------------- REPORT REASON MENU ----------------------
async def show_report_reason_menu(e):
    buttons = []
    items = list(ALL_REPORT_REASONS.items())
    row = []
    for key, (_, label) in items:
        row.append(Button.inline(label, f"gr_{key}".encode()))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([Button.inline("ALL 9 REASONS", b"gr_all")])
    buttons.append([Button.inline("Back", b"back")])
    await e.edit("SELECT REPORT REASON:", buttons=buttons)

# ---------------------- PAYMENTS PANEL ----------------------
async def show_payments_panel(bot, chat_id, message_id=None):
    pending_payments = [p for p in payments if p['status'] == 'pending']

    if not pending_payments:
        text = "PAYMENTS PANEL\n\nNo pending payments."
        buttons = [[Button.inline("All Payments", b"all_payments")], [Button.inline("Back", b"back")]]
        if message_id:
            await safe_edit(bot, chat_id, message_id, text, buttons=buttons)
        else:
            await bot.send_message(chat_id, text, buttons=buttons)
        return

    text = f"PAYMENTS PANEL\n\nPending: {len(pending_payments)}\n\n"
    for p in pending_payments[-10:]:
        text += f"#{p['id']} | {p['username']} | {p['plan']} | {p['amount']}\n"

    buttons = []
    for p in pending_payments[-5:]:
        buttons.append([Button.inline(f"Review #{p['id']}", f"review_payment_{p['id']}".encode())])
    buttons.append([Button.inline("All Payments", b"all_payments")])
    buttons.append([Button.inline("Back", b"back")])

    if message_id:
        await safe_edit(bot, chat_id, message_id, text, buttons=buttons)
    else:
        await bot.send_message(chat_id, text, buttons=buttons)

# ---------------------- MAIN ----------------------
async def main():
    global GLOBAL_TARGET, is_attacking, is_clock_active, ADMINS, clock_task
    global is_auto_spam_active, auto_spam_task

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
    logger.info(f"[+] Admins: {ADMINS}")

    asyncio.create_task(check_expired(bot))
    asyncio.create_task(run_web_server())
    asyncio.create_task(keep_alive_pinger())

    @bot.on(events.NewMessage(pattern='/start'))
    async def start_cmd(e):
        try:
            text, buttons = await get_menu(e.sender_id)
            await e.respond(text, buttons=buttons)
        except Exception as ex:
            logger.error(f"Start cmd error: {ex}")

    @bot.on(events.NewMessage(pattern='/subscribe'))
    async def sub_cmd(e):
        await subscription_menu(bot, e.chat_id, e.sender_id)

    @bot.on(events.NewMessage(pattern='/add'))
    async def add_cmd(e):
        await session_builder(bot, e.chat_id, e.sender_id)

    @bot.on(events.NewMessage(pattern='/status'))
    async def status_cmd(e):
        sub = get_user_sub(e.sender_id)
        is_admin_user = e.sender_id in ADMINS
        if is_admin_user:
            await e.respond("Admin - Unlimited access")
            return
        if sub:
            if sub.get('pending'):
                await e.respond(f"Pending: {len(get_sessions())}/{sub['sessions']} accounts")
            else:
                expiry = datetime.fromisoformat(sub['expiry'])
                days = (expiry - datetime.now()).days
                await e.respond(f"{SUB_PLANS[sub['plan']]['name']}\nSessions: {len(get_sessions())}/{sub['sessions']}\nDays: {days}")
        else:
            pending = get_user_pending_payment(e.sender_id)
            if pending:
                await e.respond(f"Payment Pending #{pending['id']}\nPlan: {pending['plan']}\nAmount: {pending['amount']}")
            else:
                await e.respond("No active subscription!\nUse /subscribe")

    @bot.on(events.NewMessage(pattern='/myid'))
    async def myid_cmd(e):
        await e.respond(f"Your User ID: `{e.sender_id}`")

    @bot.on(events.NewMessage(pattern='/pay'))
    async def pay_cmd(e):
        await buy_premium_menu(bot, e.chat_id, e.sender_id)

    @bot.on(events.NewMessage(pattern='/admin'))
    async def admin_cmd(e):
        if e.sender_id not in ADMINS:
            await e.respond("Access denied!")
            return
        await show_payments_panel(bot, e.chat_id)

    @bot.on(events.CallbackQuery)
    async def callback(e):
        global GLOBAL_TARGET, is_attacking, is_clock_active, ADMINS, clock_task
        global is_auto_spam_active, auto_spam_task

        is_admin_user = e.sender_id in ADMINS
        sub = get_user_sub(e.sender_id) if not is_admin_user else None
        has_sub = sub is not None and not sub.get('pending', False)

        data = e.data.decode()

        if not is_admin_user and not has_sub:
            allowed = ["sub_free", "sub_buy", "sub_status", "buy_premium", "contact_admin", "back"]
            allowed_prefixes = ["plan_", "paymethod_", "cancel_payment_", "submit_receipt_"]
            is_allowed = data in allowed or any(data.startswith(p) for p in allowed_prefixes)
            if not is_allowed:
                await e.answer("You need an active subscription!", alert=True)
                return

        await e.answer()

        # ATTACK
        if data.startswith("a_"):
            if not GLOBAL_TARGET:
                await e.respond("Set target first!")
                return
            mode = data.split('_')[1]
            msg = await e.respond(f"Starting {mode} attack...")
            asyncio.create_task(run_attack(bot, e.chat_id, msg.id, mode, GLOBAL_TARGET))

        elif data == "join_group":
            if not GLOBAL_TARGET:
                await e.respond("Set target first!")
                return
            msg = await e.respond("join starting...")
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
            msg = await e.respond(f"Reporting ALL {len(reasons)} reasons...")
            asyncio.create_task(run_group_report(bot, e.chat_id, msg.id, GLOBAL_TARGET, reasons))

        elif data.startswith("gr_"):
            key = data[3:]
            if key in ALL_REPORT_REASONS:
                if not GLOBAL_TARGET:
                    await e.respond("Set target first!")
                    return
                reason, msg_text = ALL_REPORT_REASONS[key]
                msg = await e.respond(f"Reporting: {msg_text}...")
                asyncio.create_task(run_group_report(bot, e.chat_id, msg.id, GLOBAL_TARGET, [(reason, msg_text)]))

        elif data == "gr_back":
            await show_report_reason_menu(e)

        elif data == "bot_report_menu":
            try:
                async with bot.conversation(e.chat_id, timeout=120) as conv:
                    await conv.send_message("Send bot username:")
                    resp = await conv.get_response()
                    bot_username = resp.text.strip()
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
                row.append(Button.inline(label, f"pr_{key}".encode()))
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
                        await conv.send_message("Send target username:")
                        resp = await conv.get_response()
                        user_username = resp.text.strip()
                        if user_username:
                            msg = await conv.send_message("Reporting...")
                            asyncio.create_task(run_profile_report(bot, e.chat_id, msg.id, user_username, key))
                except asyncio.TimeoutError:
                    await e.respond("Timeout!")

        elif data == "set":
            try:
                async with bot.conversation(e.chat_id, timeout=120) as conv:
                    await conv.send_message("Send target:")
                    resp = await conv.get_response()
                    new_target = resp.text.strip()
                    if new_target:
                        GLOBAL_TARGET = new_target
                        await conv.send_message(f"Target set: {GLOBAL_TARGET}")
                        text, buttons = await get_menu(e.sender_id)
                        await conv.send_message(text, buttons=buttons)
            except asyncio.TimeoutError:
                await e.respond("Timeout!")

        elif data == "monit":
            sessions = get_sessions()
            text = f"Sessions ({len(sessions)}):\n\n"
            for i, s in enumerate(sessions[:30], 1):
                text += f"{i}. {safe_session_name(s)}\n"
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
            await e.edit(f"Ping: {int((time.time()-start)*1000)}ms")

        elif data == "leave_ch":
            if not GLOBAL_TARGET:
                await e.respond("Set target first!")
                return
            sessions = get_sessions()
            ok, fail = 0, 0
            for s in sessions:
                res = await leave_worker(s, GLOBAL_TARGET)
                if res == "left":
                    ok += 1
                else:
                    fail += 1
            await e.respond(f"Left: {ok} | Failed: {fail}")

        elif data in ("react_pos", "react_neg"):
            if not GLOBAL_TARGET:
                await e.respond("Set target first!")
                return
            emojies = ["👍", "🔥", "❤️", "🥰"] if data == "react_pos" else ["👎", "💩", "🤮", "🤡"]
            sessions = get_sessions()
            ok, fail = 0, 0
            for s in sessions:
                res = await reaction_worker(s, GLOBAL_TARGET, emojies)
                if res == "success":
                    ok += 1
                else:
                    fail += 1
            await e.respond(f"Reactions: {ok} | Failed: {fail}")

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
                    buttons.append([Button.inline(safe_session_name(s), f"clk_{i}")])
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
            client = create_stable_client(session_path)
            await client.connect()
            if await client.is_user_authorized():
                is_clock_active = True
                clock_task = asyncio.create_task(clock_task_func(client))
                await e.respond(f"Clock ON: {safe_session_name(session_path)}")
            else:
                await e.respond("Not authorized!")

        elif data == "msg_menu":
            try:
                async with bot.conversation(e.chat_id, timeout=120) as conv:
                    await conv.send_message("Send recipient:")
                    target_user = (await conv.get_response()).text.strip()
                    await conv.send_message("Send text:")
                    msg_text = (await conv.get_response()).text.strip()
                    sessions = get_sessions()
                    ok, fail = 0, 0
                    for s in sessions:
                        res = await send_msg_worker(s, target_user, msg_text)
                        if res == "success":
                            ok += 1
                        else:
                            fail += 1
                    await conv.send_message(f"Sent: {ok} | Failed: {fail}")
            except asyncio.TimeoutError:
                await e.respond("Timeout!")

        elif data == "proxy_main":
            buttons = [
                [Button.inline("View Proxies", b"view_proxies")],
                [Button.inline("Set Proxy", b"set_proxy")],
                [Button.inline("Remove Proxy", b"remove_proxy")],
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
                text += f"- {sess_display}: {proxy[:50]}...\n"
            await e.edit(text, buttons=[[Button.inline("Back", b"proxy_main")]])

        elif data == "set_proxy":
            sessions = get_sessions()
            if not sessions:
                await e.respond("No sessions!")
                return
            buttons = []
            for i, s in enumerate(sessions[:20]):
                buttons.append([Button.inline(safe_session_name(s), f"setproxy_{i}")])
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
                    await conv.send_message(f"Session: {session_display}\n\nSend proxy:")
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
                buttons.append([Button.inline(safe_session_name(s), f"rmproxy_{i}")])
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
                await e.respond(f"Removed: {session_display}")
            else:
                await e.respond("Not found!")

        elif data == "email_menu":
            buttons = [
                [Button.inline("View Emails", b"view_emails")],
                [Button.inline("Add Email", b"add_email")],
                [Button.inline("Remove Email", b"remove_email")],
                [Button.inline("Clear All", b"clear_emails")],
                [Button.inline("Start Attack", b"start_email_attack")],
                [Button.inline("Back", b"back")]
            ]
            await e.edit("EMAIL MANAGER", buttons=buttons)

        elif data == "view_emails":
            emails = load_emails()
            if not emails:
                await e.edit("No emails!", buttons=[[Button.inline("Back", b"email_menu")]])
                return
            text = f"EMAILS ({len(emails)}):\n\n"
            for i, em in enumerate(emails, 1):
                text += f"{i}. {em['email']}\n"
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
                    await conv.send_message(f"Saved! Total: {len(emails)}")
            except asyncio.TimeoutError:
                await e.respond("Timeout!")

        elif data == "remove_email":
            emails = load_emails()
            if not emails:
                await e.edit("No emails!")
                return
            buttons = []
            for i, em in enumerate(emails):
                buttons.append([Button.inline(f"Remove: {em['email'][:40]}", f"rememail_{i}")])
            buttons.append([Button.inline("Back", b"email_menu")])
            await e.edit("Select:", buttons=buttons)

        elif data.startswith("rememail_"):
            idx = int(data.split('_')[1])
            emails = load_emails()
            if idx < len(emails):
                removed = emails.pop(idx)
                save_emails(emails)
                await e.respond(f"Removed: {removed['email']}")

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
                    buttons.append([Button.inline(safe_session_name(s), f"as_{i}")])
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
                    await conv.send_message("Interval (seconds):")
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
                        await conv.send_message(f"Started!\nInterval: {interval}s")
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
                await e.answer("You already have an active subscription!", alert=True)
                return
            if has_used_free_trial(user_id):
                await e.answer("You already used your free trial!\nBuy premium.", alert=True)
                return
            subscribers[user_id] = {
                'plan': 'free',
                'sessions': 5,
                'expiry': 'pending',
                'added': datetime.now().isoformat(),
                'pending': True
            }
            save_subscribers(subscribers)
            mark_free_trial_used(user_id)
            await e.respond(
                "Free Trial Requested!\n\n"
                "Add 5 accounts using /add to activate.\n"
                "Trial activates automatically after 5 accounts.\n\n"
                "Note: Free trial is available ONCE per user.\n\n"
                "Use /add to start."
            )

        elif data == "sub_buy" or data == "buy_premium":
            await buy_premium_menu(bot, e.chat_id, e.sender_id)

        elif data == "sub_status":
            sub = get_user_sub(e.sender_id)
            is_admin_user = e.sender_id in ADMINS
            if is_admin_user:
                await e.respond("Admin - Unlimited")
                return
            if sub:
                if sub.get('pending'):
                    await e.respond(f"Pending: {len(get_sessions())}/{sub['sessions']} accounts")
                else:
                    expiry = datetime.fromisoformat(sub['expiry'])
                    days = (expiry - datetime.now()).days
                    await e.respond(f"{SUB_PLANS[sub['plan']]['name']}\nSessions: {len(get_sessions())}/{sub['sessions']}\nDays: {days}")
            else:
                pending = get_user_pending_payment(e.sender_id)
                if pending:
                    await e.respond(f"Payment Pending #{pending['id']}\n{pending['plan']} - {pending['amount']}")
                else:
                    await e.respond("No active subscription!")

        elif data == "contact_admin":
            await e.respond(f"Contact: {ADMIN_CONTACT}")

        elif data.startswith("plan_"):
            plan_key = data[5:]
            if plan_key in SUB_PLANS and plan_key != "free":
                await payment_method_menu(bot, e.chat_id, plan_key)

        elif data.startswith("paymethod_card_"):
            plan_key = data[len("paymethod_card_"):]
            if plan_key in SUB_PLANS:
                existing = get_user_pending_payment(e.sender_id)
                if existing:
                    await e.answer(f"You have pending payment #{existing['id']}", alert=True)
                    return
                plan = SUB_PLANS[plan_key]
                try:
                    user = await e.get_sender()
                    username = f"@{user.username}" if user.username else f"ID:{e.sender_id}"
                except Exception:
                    username = f"ID:{e.sender_id}"
                payment = add_payment(e.sender_id, username, plan_key, plan['price'], "card")
                admin_ids = load_admins()
                await e.respond(
                    f"Payment Created\n\n"
                    f"ID: #{payment['id']}\n"
                    f"Plan: {plan['name']}\n"
                    f"Amount: {plan['price']}\n"
                    f"Sessions: {plan['sessions']}\n\n"
                    f"Send payment to:\n"
                    f"Card: 6037-XXXX-XXXX-XXXX\n"
                    f"Owner: [Your Name]\n\n"
                    f"After payment, submit receipt:",
                    buttons=[
                        [Button.inline("Submit Receipt", f"submit_receipt_{payment['id']}".encode())],
                        [Button.inline("Cancel", f"cancel_payment_{payment['id']}".encode())]
                    ]
                )
                for admin_id in admin_ids:
                    try:
                        await bot.send_message(
                            admin_id,
                            f"NEW PAYMENT\n\n#{payment['id']}\n"
                            f"User: {username} ({e.sender_id})\n"
                            f"Plan: {plan['name']}\n"
                            f"Amount: {plan['price']}\n\n"
                            f"/admin"
                        )
                    except Exception:
                        pass

        elif data.startswith("submit_receipt_"):
            payment_id = int(data.split("_")[2])
            payment = get_payment(payment_id)
            if not payment or payment['user_id'] != str(e.sender_id):
                await e.answer("Payment not found!", alert=True)
                return
            try:
                async with bot.conversation(e.chat_id, timeout=300) as conv:
                    await conv.send_message(f"Send receipt (photo) for #{payment_id}:")
                    resp = await conv.get_response()
                    if resp.photo or resp.document:
                        admin_ids = load_admins()
                        success = 0
                        for admin_id in admin_ids:
                            try:
                                await bot.forward_messages(admin_id, resp)
                                await bot.send_message(
                                    admin_id,
                                    f"Receipt for #{payment_id}\n"
                                    f"User: {payment['username']}\n"
                                    f"Plan: {payment['plan']}\n"
                                    f"Amount: {payment['amount']}\n\n"
                                    f"/admin"
                                )
                                success += 1
                            except Exception:
                                pass
                        if success > 0:
                            await conv.send_message(f"Receipt sent to {success} admin(s)!\nYou will be notified.")
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
                await e.answer(f"Already {payment['status']}!", alert=True)
                return
            payments.remove(payment)
            save_payments(payments)
            await e.respond(f"Payment #{payment_id} cancelled.")
            text, buttons = await get_menu(e.sender_id)
            await safe_edit(bot, e.chat_id, e.message_id, text, buttons=buttons)

        elif data == "payments_panel":
            if e.sender_id not in ADMINS:
                await e.answer("Access denied!", alert=True)
                return
            await show_payments_panel(bot, e.chat_id, e.message_id)

        elif data == "all_payments":
            if e.sender_id not in ADMINS:
                await e.answer("Access denied!", alert=True)
                return
            text = f"ALL PAYMENTS ({len(payments)}):\n\n"
            for p in payments[-20:]:
                text += f"#{p['id']} | {p['status']} | {p['user_id']} | {p['plan']} | {p['amount']}\n"
            await e.edit(text, buttons=[[Button.inline("Back", b"payments_panel")]])

        elif data.startswith("review_payment_"):
            if e.sender_id not in ADMINS:
                await e.answer("Access denied!", alert=True)
                return
            payment_id = int(data.split("_")[2])
            payment = get_payment(payment_id)
            if not payment:
                await e.answer("Not found!", alert=True)
                return
            plan = SUB_PLANS.get(payment['plan'], {})
            text = f"""PAYMENT #{payment['id']}

User: {payment['username']}
User ID: {payment['user_id']}
Plan: {plan.get('name', payment['plan'])}
Amount: {payment['amount']}
Sessions: {plan.get('sessions', '?')}
Days: {plan.get('days', '?')}
Status: {payment['status']}
Created: {payment['created'][:19]}"""
            buttons = []
            if payment['status'] == 'pending':
                buttons.append([Button.inline("APPROVE", f"approve_payment_{payment_id}".encode())])
                buttons.append([Button.inline("REJECT", f"reject_payment_{payment_id}".encode())])
            buttons.append([Button.inline("Back", b"payments_panel")])
            await e.edit(text, buttons=buttons)

        elif data.startswith("approve_payment_"):
            if e.sender_id not in ADMINS:
                await e.answer("Access denied!", alert=True)
                return
            payment_id = int(data.split("_")[2])
            success, payment = approve_payment(payment_id, e.sender_id)
            if success:
                await e.answer("Approved!", alert=True)
                try:
                    await bot.send_message(
                        int(payment['user_id']),
                        f"PAYMENT APPROVED!\n\n"
                        f"Plan: {SUB_PLANS[payment['plan']]['name']}\n"
                        f"Sessions: {SUB_PLANS[payment['plan']]['sessions']}\n"
                        f"Days: {SUB_PLANS[payment['plan']]['days']}\n\n"
                        f"Use /start."
                    )
                except Exception:
                    pass
                await show_payments_panel(bot, e.chat_id, e.message_id)
            else:
                await e.answer("Already processed!", alert=True)

        elif data.startswith("reject_payment_"):
            if e.sender_id not in ADMINS:
                await e.answer("Access denied!", alert=True)
                return
            payment_id = int(data.split("_")[2])
            success, payment = reject_payment(payment_id, e.sender_id, "Rejected")
            if success:
                await e.answer("Rejected!", alert=True)
                try:
                    await bot.send_message(
                        int(payment['user_id']),
                        f"PAYMENT REJECTED\n\n"
                        f"Contact {ADMIN_CONTACT}"
                    )
                except Exception:
                    pass
                await show_payments_panel(bot, e.chat_id, e.message_id)
            else:
                await e.answer("Already processed!", alert=True)

        elif data == "admin_menu":
            admins = load_admins()
            text = f"ADMINS ({len(admins)}/{MAX_ADMINS})\n\n"
            for i, a in enumerate(admins, 1):
                text += f"{i}. {a}\n"
            buttons = [
                [Button.inline("Add Admin", b"admin_add")],
                [Button.inline("Remove Admin", b"admin_remove")],
                [Button.inline("Back", b"back")]
            ]
            await e.edit(text, buttons=buttons)

        elif data == "admin_add":
            try:
                async with bot.conversation(e.chat_id, timeout=60) as conv:
                    await conv.send_message(f"Send user_id to add ({len(load_admins())}/{MAX_ADMINS}):")
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
            try:
                async with bot.conversation(e.chat_id, timeout=60) as conv:
                    await conv.send_message("Send user_id to remove:")
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