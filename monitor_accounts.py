import asyncio
import traceback
from datetime import datetime
import zoneinfo
import os
import sys
from telethon import TelegramClient, events
from telethon.errors import RPCError
from accounts_list2 import accounts
import winsound  # built-in on Windows

# ==== SETTINGS ====
POLL_INTERVAL = 10  # seconds between PM checks
LOG_FILE = "monitor_log.txt"
MAX_CONNECT_ATTEMPTS = 3

# ==== TIMEZONE ====
PARIS = zoneinfo.ZoneInfo("Europe/Paris")

# ==== GLOBALS ====
user_id_whitelist = set()
clients_cache = {}
last_seen_private = {}
running = True

# Enable ANSI colors in Windows CMD
if os.name == "nt":
    import ctypes
    kernel32 = ctypes.windll.kernel32
    kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)

# ==== UTILS ====
def log_error(msg):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now(PARIS)} - {msg}\n")

def play_alert():
    """Play alert sound 3 times (~3 seconds total)."""
    try:
        for _ in range(3):
            winsound.Beep(1000, 1000)  # 1 second beep
    except Exception as e:
        log_error(f"Error playing sound: {e}")

async def start_client(acc_key):
    """Start Telegram client with retry."""
    acc = accounts[acc_key]
    attempt = 0
    while attempt < MAX_CONNECT_ATTEMPTS:
        try:
            client = TelegramClient(acc["session"], int(acc["api_id"]), acc["api_hash"])
            await client.start(phone=acc["phone"])
            return client
        except (asyncio.TimeoutError, RPCError):
            attempt += 1
            print(f"Attempt {attempt} at connecting {acc_key} failed.")
            await asyncio.sleep(2)
        except Exception as e:
            log_error(f"Unexpected error starting {acc_key}: {e}")
            break
    print(f"❌ Skipping {acc_key} after {MAX_CONNECT_ATTEMPTS} failed attempts.")
    return None

# ==== BUILD WHITELIST ====
async def build_whitelist():
    print("🔧 Building whitelist of your accounts...")
    for acc_key in accounts:
        client = await start_client(acc_key)
        if not client:
            continue
        try:
            me = await client.get_me()
            accounts[acc_key]["user_id"] = me.id
            user_id_whitelist.add(me.id)
            username = getattr(me, "username", None)
            print(f"  ✅ {acc_key} => user_id {me.id} ({username})")
        except Exception as e:
            print(f"  ❌ {acc_key} error: {e}")
        finally:
            await client.disconnect()
    print("✅ Whitelist built.\n")

# ==== PRIVATE MESSAGE CHECK ====
async def check_private_messages():
    """Check for incoming PMs from strangers."""
    while running:
        for acc_key in accounts:
            if acc_key not in clients_cache:
                client = await start_client(acc_key)
                if client:
                    clients_cache[acc_key] = client
                else:
                    continue
            client = clients_cache[acc_key]
            try:
                async for msg in client.iter_messages(None, limit=10):
                    if not msg.is_private:
                        continue
                    if msg.out:
                        continue
                    sender_id = msg.sender_id
                    if sender_id not in user_id_whitelist:
                        if last_seen_private.get(acc_key, 0) < (msg.id or 0):
                            sender = await msg.get_sender()
                            sender_name = f"{getattr(sender, 'first_name', '')} {getattr(sender, 'last_name', '')}".strip()
                            preview = msg.raw_text[:50].replace("\n", " ")
                            current_time = datetime.now(PARIS).strftime("%m-%d %H:%M")
                            print(f"\033[93m[PM ALERT] {current_time}\033[0m {acc_key} got message from stranger {sender_name} ({sender_id}) - Msg: {preview}")
                            play_alert()
                            last_seen_private[acc_key] = msg.id
            except (asyncio.TimeoutError, RPCError):
                continue
            except Exception as e:
                log_error(f"Error checking PMs for {acc_key}: {e}")
        await asyncio.sleep(POLL_INTERVAL)

# ==== GROUP MONITOR ====
async def start_group_monitor(main_acc_key):
    """Monitor groups for strangers."""
    client = await start_client(main_acc_key)
    if not client:
        print(f"❌ Cannot start group monitor for {main_acc_key} — no connection.")
        return
    clients_cache[main_acc_key] = client

    @client.on(events.NewMessage(incoming=True))
    async def handler(event):
        try:
            sender_id = event.sender_id
            if sender_id and sender_id not in user_id_whitelist:
                chat = await event.get_chat()
                chat_title = getattr(chat, "title", getattr(chat, "username", str(chat)))
                sender = await event.get_sender()
                sender_name = f"{getattr(sender, 'first_name', '')} {getattr(sender, 'last_name', '')}".strip()
                preview = event.raw_text[:50].replace("\n", " ")
                current_time = datetime.now(PARIS).strftime("%m-%d %H:%M")
                print(f"\033[91m[GROUP ALERT] {current_time}\033[0m {chat_title} ({getattr(chat, 'id', '?')}) - Stranger: {sender_name} ({sender_id}) - Msg: {preview}")
                play_alert()
        except Exception as e:
            log_error(f"Error in group handler: {e}")

    print(f"🎧 Starting group monitor with account: {main_acc_key}")
    await client.run_until_disconnected()

# ==== CLEANUP ====
async def cleanup():
    print("\n🔌 Disconnecting all clients...")
    for client in clients_cache.values():
        try:
            await client.disconnect()
        except Exception as e:
            log_error(f"Error disconnecting client: {e}")
    print("✅ All clients disconnected.")

# ==== MAIN ====
async def main():
    global running
    await build_whitelist()
    main_acc_key = "vip4b"
    pm_task = asyncio.create_task(check_private_messages())
    try:
        await start_group_monitor(main_acc_key)
    finally:
        running = False
        await cleanup()
        pm_task.cancel()

# ==== ENTRY ====
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Script interrupted by user")
    except Exception:
        log_error(f"Fatal error: {traceback.format_exc()}")
