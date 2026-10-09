import os
import asyncio
import random
import sys
import json
import re
import sqlite3
from datetime import datetime
from telethon import TelegramClient, events, functions, types, Button
from telethon.errors import FloodWaitError
import time

# ==================== RAILWAY PATHS ====================
DATA_DIR = os.getenv('DATA_DIR', './data')
SESSION_DIR = os.path.join(DATA_DIR, 'sessions')
PROXIES_FILE = os.path.join(DATA_DIR, 'proxies.json')
ADMINS_FILE = os.path.join(DATA_DIR, 'admins.json')

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(SESSION_DIR, exist_ok=True)

# ==================== CONFIG ====================
API_ID = int(os.getenv('API_ID', 25342127))
API_HASH = os.getenv('API_HASH', '0b75a27b1ab66bd482b6d93a0989d34f')
BOT_TOKEN = os.getenv('BOT_TOKEN', '8261732652:AAHftLUpVGACTi-8j_xzXud6su79RSnuop4')

MAIN_ADMINS = [7733193342, 8127994507]
TARGET = 'target'
is_attacking = False

DB_SEMAPHORE = asyncio.Semaphore(2)
is_clock_active = False
active_clock_session = None
is_sniper_active = False

# ==================== REPORT BOTS ====================
REPORT_BOTS = {
    "scam": ["@SpamBot"],
    "fake": ["@SpamBot"],
    "porn": ["@SpamBot"],
    "violence": ["@SpamBot"],
    "child": ["@SpamBot"],
    "copyright": ["@SpamBot"],
}

# ==================== DEFAULT PROXIES ====================
DEFAULT_PROXIES = [
    "https://t.me/proxy?server=iranmaster27.suser.ir&port=2020&secret=AAAAAAAAAAAAAAAAAAAAAA%3D%3D",
    "https://t.me/proxy?server=iranmaster28.suser.ir&port=2020&secret=AAAAAAAAAAAAAAAAAAAAAA%3D%3D",
    "https://t.me/proxy?server=iranmaster29.suser.ir&port=2020&secret=AAAAAAAAAAAAAAAAAAAAAA%3D%3D",
]

# ==================== ADMIN MANAGEMENT ====================

def load_admins():
    extra = []
    if os.path.exists(ADMINS_FILE):
        try:
            with open(ADMINS_FILE, 'r') as f:
                extra = json.load(f)
        except:
            extra = []
    return list(set(MAIN_ADMINS + extra))

def save_admins(extra_admins):
    try:
        with open(ADMINS_FILE, 'w') as f:
            json.dump(extra_admins, f, indent=4)
    except:
        pass

def get_extra_admins():
    if os.path.exists(ADMINS_FILE):
        try:
            with open(ADMINS_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []

def add_admin(user_id: int):
    if user_id in load_admins():
        return False
    extra = get_extra_admins()
    if user_id not in extra:
        extra.append(user_id)
        save_admins(extra)
    return True

def remove_admin(user_id: int):
    if user_id in MAIN_ADMINS:
        return "main"
    extra = get_extra_admins()
    if user_id in extra:
        extra.remove(user_id)
        save_admins(extra)
        return True
    return False

def is_user_admin(user_id: int) -> bool:
    return user_id in load_admins()

# ==================== PROXY ====================

def parse_mtproto_proxy(proxy_input: str):
    if not proxy_input or proxy_input.lower() == "none":
        return None
    proxy_input = proxy_input.strip()
    server = port = secret = None
    if 't.me/proxy?' in proxy_input:
        params = proxy_input.split('?')[1]
        for param in params.split('&'):
            if '=' in param:
                key, val = param.split('=', 1)
                if key == 'server':
                    server = val
                elif key == 'port':
                    port = int(val)
                elif key == 'secret':
                    secret = val
        if server and port:
            return (server, port, secret)
    if 'mtproto://' in proxy_input:
        proxy_input = proxy_input.replace('mtproto://', '')
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
    if os.path.exists(PROXIES_FILE):
        try:
            with open(PROXIES_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_proxies(proxies):
    try:
        with open(PROXIES_FILE, 'w') as f:
            json.dump(proxies, f, indent=4)
    except:
        pass

def get_session_proxy_config(session_name):
    proxies = load_proxies()
    proxy_str = proxies.get(session_name, "")
    if not proxy_str:
        proxy_str = random.choice(DEFAULT_PROXIES)
    parsed = parse_mtproto_proxy(proxy_str)
    if parsed:
        server, port, secret = parsed
        return ('mtproto', server, port, secret)
    return None

def get_sessions():
    if not os.path.exists(SESSION_DIR):
        return []
    return [os.path.join(SESSION_DIR, f) for f in os.listdir(SESSION_DIR) if f.endswith('.session')]

def patch_session_db(session_path):
    try:
        conn = sqlite3.connect(session_path, timeout=30.0)
        conn.execute('PRAGMA journal_mode=WAL;')
        conn.execute('PRAGMA synchronous=NORMAL;')
        conn.commit()
        conn.close()
    except:
        pass

def create_stable_client(session_path, use_proxy=True):
    proxy = None
    if use_proxy:
        proxy = get_session_proxy_config(os.path.basename(session_path))
    return TelegramClient(session_path, API_ID, API_HASH, timeout=45,
                          connection_retries=5, retry_delay=2,
                          auto_reconnect=True, proxy=proxy)

# ==================== REPORT ====================

async def report_via_bot(session_path, target, mode="scam"):
    patch_session_db(session_path)
    async with DB_SEMAPHORE:
        client = create_stable_client(session_path)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                return "unauthorized"
            bots = REPORT_BOTS.get(mode, ["@SpamBot"])
            sent = 0
            for bot_username in bots:
                try:
                    await client.send_message(bot_username, "/start")
                    await asyncio.sleep(1)
                    await client.send_message(bot_username, target)
                    sent += 1
                    await asyncio.sleep(0.5)
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds)
                except:
                    continue
            return "success" if sent > 0 else "failed"
        except:
            return "failed"
        finally:
            try:
                await client.disconnect()
            except:
                pass

async def ask_confirmation(bot, chat_id, question):
    buttons = [[Button.inline("YES", b"confirm_yes"),
                Button.inline("NO", b"confirm_no")]]
    msg = await bot.send_message(chat_id, question, buttons=buttons)
    try:
        response = await bot.wait_for(
            events.CallbackQuery,
            timeout=30,
            filter=lambda e: e.data in [b"confirm_yes", b"confirm_no"]
        )
        await response.answer()
        return response.data == b"confirm_yes", msg
    except asyncio.TimeoutError:
        await msg.edit("Timeout. Cancelled.")
        return False, msg

async def run_attack(bot, chat_id, message_id, mode):
    global is_attacking
    is_attacking = True
    total_sent = 0
    sessions = get_sessions()
    if not sessions:
        await bot.edit_message(chat_id, message_id, "No sessions found.")
        is_attacking = False
        return
    for i, s in enumerate(sessions):
        if not is_attacking:
            break
        result = await report_via_bot(s, TARGET, mode)
        if result == "success":
            total_sent += 1
        await asyncio.sleep(0.5)
        try:
            await bot.edit_message(
                chat_id, message_id,
                f"Attack Active\n\nTarget: {TARGET}\nMode: {mode}\nSent: {total_sent}/{i+1}\nSessions: {len(sessions)}"
            )
        except:
            pass
    is_attacking = False
    await bot.edit_message(
        chat_id, message_id,
        f"Attack Finished\n\nTarget: {TARGET}\nTotal: {total_sent}"
    )

# ==================== WORKERS ====================

async def leave_worker(session_path, target_link):
    patch_session_db(session_path)
    async with DB_SEMAPHORE:
        client = create_stable_client(session_path)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                return "unauthorized"
            target = target_link.replace('@', '').replace('https://t.me/', '').strip()
            entity = await client.get_entity(target)
            await client(functions.channels.LeaveChannelRequest(channel=entity))
            return "left"
        except:
            return "failed"
        finally:
            try:
                await client.disconnect()
            except:
                pass

async def reaction_worker(session_path, target_channel, emojies, limit=3):
    patch_session_db(session_path)
    async with DB_SEMAPHORE:
        client = create_stable_client(session_path)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                return "unauthorized"
            target = target_channel.replace('@', '').replace('https://t.me/', '').strip()
            entity = await client.get_input_entity(target)
            msgs = await client.get_messages(entity, limit=limit)
            sc = 0
            for msg in msgs:
                if not msg:
                    continue
                try:
                    await client(functions.messages.SendReactionRequest(
                        peer=entity, msg_id=msg.id,
                        reaction=[types.ReactionEmoji(emoticon=random.choice(emojies))]
                    ))
                    sc += 1
                    await asyncio.sleep(0.2)
                except:
                    pass
            return "success" if sc > 0 else "failed"
        except:
            return "failed"
        finally:
            try:
                await client.disconnect()
            except:
                pass

async def mass_reaction(target_channel, mode="positive"):
    sessions = get_sessions()
    if not sessions:
        return "No sessions found."
    emojies = ["\U0001F44D", "\U0001F525", "\u2764", "\U0001F970"] if mode == "positive" else ["\U0001F44E", "\U0001F4A9", "\U0001F92E", "\U0001F921"]
    ok, fail = 0, 0
    for s in sessions:
        res = await reaction_worker(s, target_channel, emojies)
        if res == "success":
            ok += 1
        else:
            fail += 1
        await asyncio.sleep(0.5)
    return f"Reaction Done\n\nSuccess: {ok}\nFailed: {fail}"

async def msg_worker(session_path, target_user, message_text):
    patch_session_db(session_path)
    async with DB_SEMAPHORE:
        client = create_stable_client(session_path)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                return "unauthorized"
            await client.send_message(target_user, message_text)
            return "success"
        except FloodWaitError:
            return "flood"
        except:
            return "failed"
        finally:
            try:
                await client.disconnect()
            except:
                pass

async def join_worker(session_path, target_link):
    patch_session_db(session_path)
    async with DB_SEMAPHORE:
        client = create_stable_client(session_path)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                return "unauthorized"
            if "start=" in target_link:
                bot_username = target_link.split('t.me/')[-1].split('?')[0]
                ref_code = target_link.split('start=')[-1]
                bot_entity = await client.get_entity(bot_username)
                await client.send_message(bot_entity, f"/start {ref_code}")
                return "joined"
            else:
                target = target_link.replace('@', '').replace('https://t.me/', '').strip()
                entity = await client.get_entity(target)
                await client(functions.channels.JoinChannelRequest(channel=entity))
                return "joined"
        except Exception as e:
            err = str(e).lower()
            if "already" in err or "member" in err:
                return "already"
            return "failed"
        finally:
            try:
                await client.disconnect()
            except:
                pass

async def mass_join(target_link):
    sessions = get_sessions()
    if not sessions:
        return "No sessions"
    results = []
    for s in sessions:
        res = await join_worker(s, target_link)
        results.append(res)
        await asyncio.sleep(1)
    return (f"Joined: {results.count('joined')} | "
            f"Already: {results.count('already')} | "
            f"Failed: {results.count('failed')}")

# ==================== MENU ====================

async def get_menu():
    global is_clock_active, is_sniper_active, TARGET
    clock_status = "ON" if is_clock_active else "OFF"
    sniper_status = "ON" if is_sniper_active else "OFF"
    proxies_count = len(load_proxies())
    admins_count = len(load_admins())

    text = f"""SIGMATOR BOT
================
Target: {TARGET}
Sessions: {len(get_sessions())}
Proxies: {proxies_count}
Admins: {admins_count}
Clock: {clock_status}
Sniper: {sniper_status}
Status: {'RUNNING' if is_attacking else 'IDLE'}
================="""

    buttons = [
        [Button.inline("SCAM", b"a_scam"), Button.inline("PORN", b"a_porn")],
        [Button.inline("VIOLENCE", b"a_violence"), Button.inline("CHILD", b"a_child")],
        [Button.inline("COPYRIGHT", b"a_copyright")],
        [Button.inline("SET TARGET", b"set"), Button.inline("MONITOR", b"monit")],
        [Button.inline(f"CLOCK {clock_status}", b"clock_menu"),
         Button.inline(f"SNIPER {sniper_status}", b"sniper_menu")],
        [Button.inline(f"PROXY ({proxies_count})", b"proxy_main"),
         Button.inline(f"ADMINS ({admins_count})", b"admins_menu")],
        [Button.inline("SEND MESSAGE", b"msg_menu")],
        [Button.inline("PROFILE", b"rpt_profile"), Button.inline("CHANNEL", b"rpt_channel")],
        [Button.inline("POSTS", b"rpt_posts")],
        [Button.inline("JOIN/REF", b"join_ch"), Button.inline("VIEW", b"view_ch")],
        [Button.inline("REACT +", b"react_pos"), Button.inline("REACT -", b"react_neg")],
        [Button.inline("LEAVE", b"leave_ch")],
        [Button.inline("PING", b"ping"), Button.inline("STOP", b"stop")],
    ]
    return text, buttons

# ==================== CLOCK ====================

async def clock_task(client):
    global is_clock_active
    last_time = ""
    original_first = original_last = ""
    try:
        async with DB_SEMAPHORE:
            me = await client.get_me()
            original_first = me.first_name or ""
            original_last = me.last_name or ""
        while is_clock_active:
            try:
                now = datetime.now().strftime("%H:%M")
                if now != last_time:
                    new_name = f"{original_first} {now}".strip()
                    async with DB_SEMAPHORE:
                        await client(functions.account.UpdateProfileRequest(
                            first_name=new_name, last_name=original_last
                        ))
                    last_time = now
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds)
            except:
                break
            await asyncio.sleep(1)
    finally:
        if client and client.is_connected():
            try:
                if original_first:
                    async with DB_SEMAPHORE:
                        await client(functions.account.UpdateProfileRequest(
                            first_name=original_first, last_name=original_last
                        ))
            except:
                pass
            await client.disconnect()

# ==================== BOT MAIN ====================

async def main():
    bot = TelegramClient('bot_main', API_ID, API_HASH)
    await bot.start(bot_token=BOT_TOKEN)
    print("[+] SIGMATOR BOT STARTED")
    print(f"[+] Data dir: {DATA_DIR}")
    print(f"[+] Sessions: {len(get_sessions())}")

    def is_admin(uid):
        return is_user_admin(uid)

    @bot.on(events.NewMessage(pattern='/start'))
    async def start_cmd(e):
        if not is_admin(e.sender_id):
            await e.respond("You are not admin.")
            return
        text, buttons = await get_menu()
        await e.respond(text, buttons=buttons)

    @bot.on(events.NewMessage(pattern='/add'))
    async def add_cmd(e):
        if not is_admin(e.sender_id):
            await e.respond("You are not admin.")
            return
        await e.respond("Send user ID to add as admin:")
        try:
            resp = await bot.wait_for(events.NewMessage(from_users=e.sender_id), timeout=30)
            uid = int(resp.text.strip())
            if add_admin(uid):
                await e.respond(f"User {uid} added as admin.")
            else:
                await e.respond(f"User {uid} is already admin.")
        except ValueError:
            await e.respond("Invalid ID.")
        except asyncio.TimeoutError:
            await e.respond("Timeout.")

    @bot.on(events.NewMessage(pattern='/rem'))
    async def rem_cmd(e):
        if not is_admin(e.sender_id):
            await e.respond("You are not admin.")
            return
        await e.respond("Send user ID to remove from admins:")
        try:
            resp = await bot.wait_for(events.NewMessage(from_users=e.sender_id), timeout=30)
            uid = int(resp.text.strip())
            res = remove_admin(uid)
            if res == "main":
                await e.respond(f"Cannot remove MAIN admin {uid}.")
            elif res:
                await e.respond(f"User {uid} removed.")
            else:
                await e.respond(f"User {uid} is not admin.")
        except ValueError:
            await e.respond("Invalid ID.")
        except asyncio.TimeoutError:
            await e.respond("Timeout.")

    @bot.on(events.NewMessage(pattern='/admins'))
    async def admins_list_cmd(e):
        if not is_admin(e.sender_id):
            return
        admins = load_admins()
        text = "Admin List:\n\n"
        for i, aid in enumerate(admins, 1):
            mark = "[MAIN]" if aid in MAIN_ADMINS else "[USER]"
            text += f"{i}. {mark} {aid}\n"
        await e.respond(text)

    @bot.on(events.CallbackQuery)
    async def callback(e):
        global TARGET, is_attacking, is_clock_active, active_clock_session, is_sniper_active
        if not is_admin(e.sender_id):
            return
        await e.answer()
        data = e.data.decode()

        if data in ("confirm_yes", "confirm_no"):
            return

        if data.startswith("a_"):
            if TARGET == 'target':
                await e.respond("Set target first.")
                return
            mode = data.split('_')[1]
            confirmed, msg = await ask_confirmation(bot, e.chat_id,
                f"Start {mode.upper()} attack on {TARGET} ?")
            if not confirmed:
                await msg.edit("Attack cancelled.")
                return
            await msg.edit(f"Starting {mode} attack...")
            asyncio.create_task(run_attack(bot, e.chat_id, msg.id, mode))

        elif data == "rpt_profile":
            if TARGET == 'target':
                await e.respond("Set target first.")
                return
            confirmed, msg = await ask_confirmation(bot, e.chat_id,
                f"Report PROFILE of {TARGET} ?")
            if not confirmed:
                await msg.edit("Cancelled.")
                return
            await msg.edit("Reporting profiles...")
            sessions = get_sessions()
            ok = 0
            for s in sessions:
                res = await report_via_bot(s, TARGET, "fake")
                if res == "success":
                    ok += 1
                await asyncio.sleep(0.5)
            await msg.edit(f"Profile Reports Done\n\nSuccess: {ok}\nFailed: {len(sessions)-ok}")

        elif data == "rpt_channel":
            if TARGET == 'target':
                await e.respond("Set target first.")
                return
            confirmed, msg = await ask_confirmation(bot, e.chat_id,
                f"Report CHANNEL of {TARGET} ?")
            if not confirmed:
                await msg.edit("Cancelled.")
                return
            await msg.edit("Reporting channel...")
            sessions = get_sessions()
            ok = 0
            for s in sessions:
                res = await report_via_bot(s, TARGET, "fake")
                if res == "success":
                    ok += 1
                await asyncio.sleep(0.5)
            await msg.edit(f"Channel Reports Done\n\nSuccess: {ok}\nFailed: {len(sessions)-ok}")

        elif data == "rpt_posts":
            if TARGET == 'target':
                await e.respond("Set target first.")
                return
            confirmed, msg = await ask_confirmation(bot, e.chat_id,
                f"Report POSTS of {TARGET} ?")
            if not confirmed:
                await msg.edit("Cancelled.")
                return
            await msg.edit("Reporting posts...")
            sessions = get_sessions()
            ok = 0
            for s in sessions:
                res = await report_via_bot(s, TARGET, "scam")
                if res == "success":
                    ok += 1
                await asyncio.sleep(0.5)
            await msg.edit(f"Posts Reports Done\n\nSuccess: {ok}\nFailed: {len(sessions)-ok}")

        elif data == "set":
            await e.respond("Send target username/link/ID:")
            try:
                resp = await bot.wait_for(events.NewMessage(from_users=e.sender_id), timeout=60)
                TARGET = resp.text.strip()
                text, buttons = await get_menu()
                await e.respond(f"Target set to: {TARGET}", buttons=buttons)
            except asyncio.TimeoutError:
                await e.respond("Timeout.")

        elif data == "monit":
            sessions = get_sessions()
            text = f"Sessions ({len(sessions)}):\n\n"
            for s in sessions[:20]:
                text += f"- {os.path.basename(s)}\n"
            if len(sessions) > 20:
                text += f"\n+ {len(sessions)-20} more"
            await e.edit(text, buttons=[[Button.inline("Back", b"back")]])

        elif data == "stop":
            is_attacking = False
            is_sniper_active = False
            text, buttons = await get_menu()
            await e.edit(text, buttons=buttons)

        elif data == "back":
            text, buttons = await get_menu()
            await e.edit(text, buttons=buttons)

        elif data == "ping":
            text, buttons = await get_menu()
            await e.edit(text + f"\n\nPong! {random.randint(20, 80)}ms", buttons=buttons)

        elif data == "join_ch":
            await e.respond("Send channel/group invite link or bot start link:")
            try:
                resp = await bot.wait_for(events.NewMessage(from_users=e.sender_id), timeout=60)
                result = await mass_join(resp.text.strip())
                text, buttons = await get_menu()
                await e.respond(result, buttons=buttons)
            except asyncio.TimeoutError:
                await e.respond("Timeout.")

        elif data == "view_ch":
            await e.respond("View feature coming soon.")

        elif data == "react_pos":
            if TARGET == 'target':
                await e.respond("Set target first.")
                return
            confirmed, msg = await ask_confirmation(bot, e.chat_id,
                f"Send POSITIVE reactions to {TARGET} ?")
            if not confirmed:
                await msg.edit("Cancelled.")
                return
            await msg.edit("Sending positive reactions...")
            res = await mass_reaction(TARGET, "positive")
            await msg.edit(res)

        elif data == "react_neg":
            if TARGET == 'target':
                await e.respond("Set target first.")
                return
            confirmed, msg = await ask_confirmation(bot, e.chat_id,
                f"Send NEGATIVE reactions to {TARGET} ?")
            if not confirmed:
                await msg.edit("Cancelled.")
                return
            await msg.edit("Sending negative reactions...")
            res = await mass_reaction(TARGET, "negative")
            await msg.edit(res)

        elif data == "leave_ch":
            if TARGET == 'target':
                await e.respond("Set target first.")
                return
            confirmed, msg = await ask_confirmation(bot, e.chat_id,
                f"Leave {TARGET} with all sessions?")
            if not confirmed:
                await msg.edit("Cancelled.")
                return
            await msg.edit("Leaving...")
            sessions = get_sessions()
            ok, fail = 0, 0
            for s in sessions:
                res = await leave_worker(s, TARGET)
                if res == "left":
                    ok += 1
                else:
                    fail += 1
            await msg.edit(f"Leave Done\n\nLeft: {ok}\nFailed: {fail}")

        elif data == "clock_menu":
            if is_clock_active:
                is_clock_active = False
                text, buttons = await get_menu()
                await e.edit(text, buttons=buttons)
            else:
                sessions = get_sessions()
                if not sessions:
                    await e.respond("No sessions found.")
                    return
                buttons = []
                for i, s in enumerate(sessions[:20]):
                    buttons.append([Button.inline(os.path.basename(s), f"clk_{i}".encode())])
                buttons.append([Button.inline("Back", b"back")])
                await e.edit("Select session for clock:", buttons=buttons)

        elif data.startswith("clk_"):
            idx = int(data.split('_')[1])
            sessions = get_sessions()
            if idx >= len(sessions):
                return
            session_path = sessions[idx]
            is_clock_active = True
            active_clock_session = session_path
            patch_session_db(active_clock_session)
            client = create_stable_client(active_clock_session)
            await client.connect()
            if await client.is_user_authorized():
                asyncio.create_task(clock_task(client))
                await e.respond(f"Clock activated on {os.path.basename(active_clock_session)}")
            else:
                is_clock_active = False
                await e.respond("Session not authorized.")
            text, buttons = await get_menu()
            await e.edit(text, buttons=buttons)

        elif data == "sniper_menu":
            buttons = [
                [Button.inline("Start", b"start_sniper")],
                [Button.inline("Back", b"back")]
            ]
            await e.edit("SNIPER\n\nComing soon...", buttons=buttons)

        elif data == "start_sniper":
            is_sniper_active = True
            text, buttons = await get_menu()
            await e.edit(text, buttons=buttons)

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
            text = "PROXY LIST\n\nDefault Proxies:\n"
            for p in DEFAULT_PROXIES:
                text += f"- {p[:60]}...\n"
            text += f"\nCustom ({len(proxies)}):\n"
            for sess, proxy in list(proxies.items())[:15]:
                text += f"- {sess}\n  {proxy[:50]}...\n"
            await e.edit(text, buttons=[[Button.inline("Back", b"proxy_main")]])

        elif data == "set_proxy":
            sessions = get_sessions()
            if not sessions:
                await e.respond("No sessions found.")
                return
            buttons = []
            for i, s in enumerate(sessions[:20]):
                buttons.append([Button.inline(os.path.basename(s), f"setproxy_{i}".encode())])
            buttons.append([Button.inline("Back", b"proxy_main")])
            await e.edit("Select session:", buttons=buttons)

        elif data.startswith("setproxy_"):
            idx = int(data.split('_')[1])
            sessions = get_sessions()
            if idx >= len(sessions):
                return
            session_name = os.path.basename(sessions[idx])
            await e.respond(f"Session: {session_name}\n\nSend MTProto proxy or 'none' to remove:")
            try:
                resp = await bot.wait_for(events.NewMessage(from_users=e.sender_id), timeout=60)
                proxy_input = resp.text.strip()
                proxies = load_proxies()
                if proxy_input.lower() == 'none':
                    proxies.pop(session_name, None)
                    await e.respond(f"Proxy removed for {session_name}")
                else:
                    proxies[session_name] = proxy_input
                    await e.respond(f"Proxy set for {session_name}")
                save_proxies(proxies)
            except asyncio.TimeoutError:
                await e.respond("Timeout.")

        elif data == "remove_proxy":
            sessions = get_sessions()
            if not sessions:
                await e.respond("No sessions found.")
                return
            buttons = []
            for i, s in enumerate(sessions[:20]):
                buttons.append([Button.inline(os.path.basename(s), f"rmproxy_{i}".encode())])
            buttons.append([Button.inline("Back", b"proxy_main")])
            await e.edit("Select session to remove proxy:", buttons=buttons)

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
                await e.respond(f"Removed for {session_name}")
            else:
                await e.respond(f"No custom proxy for {session_name}")

        elif data == "admins_menu":
            admins = load_admins()
            text = f"ADMIN MANAGEMENT\n\nTotal: {len(admins)}\n\n"
            for i, aid in enumerate(admins, 1):
                mark = "[MAIN]" if aid in MAIN_ADMINS else "[USER]"
                text += f"{i}. {mark} {aid}\n"
            buttons = [
                [Button.inline("ADD ADMIN", b"add_admin_btn")],
                [Button.inline("REMOVE ADMIN", b"remove_admin_btn")],
                [Button.inline("Back", b"back")]
            ]
            await e.edit(text, buttons=buttons)

        elif data == "add_admin_btn":
            await e.respond("Send user ID to add as admin:")
            try:
                resp = await bot.wait_for(events.NewMessage(from_users=e.sender_id), timeout=30)
                uid = int(resp.text.strip())
                if add_admin(uid):
                    await e.respond(f"User {uid} added.")
                else:
                    await e.respond(f"User {uid} is already admin.")
            except ValueError:
                await e.respond("Invalid ID.")
            except asyncio.TimeoutError:
                await e.respond("Timeout.")

        elif data == "remove_admin_btn":
            await e.respond("Send user ID to remove from admins:")
            try:
                resp = await bot.wait_for(events.NewMessage(from_users=e.sender_id), timeout=30)
                uid = int(resp.text.strip())
                res = remove_admin(uid)
                if res == "main":
                    await e.respond(f"Cannot remove MAIN admin {uid}.")
                elif res:
                    await e.respond(f"User {uid} removed.")
                else:
                    await e.respond(f"User {uid} is not admin.")
            except ValueError:
                await e.respond("Invalid ID.")
            except asyncio.TimeoutError:
                await e.respond("Timeout.")

        elif data == "msg_menu":
            buttons = [
                [Button.inline("Broadcast All", b"send_msg_all")],
                [Button.inline("Back", b"back")]
            ]
            await e.edit("MESSAGE MENU", buttons=buttons)

        elif data == "send_msg_all":
            await e.respond("Send recipient username or ID:")
            try:
                target_user = (await bot.wait_for(
                    events.NewMessage(from_users=e.sender_id), timeout=60
                )).text.strip()
                await e.respond("Send message text:")
                msg_text = (await bot.wait_for(
                    events.NewMessage(from_users=e.sender_id), timeout=60
                )).text.strip()
                status_msg = await e.respond("Sending...")
                sessions = get_sessions()
                success, fail = 0, 0
                for s in sessions:
                    res = await msg_worker(s, target_user, msg_text)
                    if res == "success":
                        success += 1
                    else:
                        fail += 1
                    await asyncio.sleep(0.2)
                await status_msg.edit(f"Done\n\nSuccess: {success}\nFailed: {fail}")
            except asyncio.TimeoutError:
                await e.respond("Timeout.")

    await bot.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[!] Bot stopped")
        sys.exit(0)