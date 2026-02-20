import discord
from discord.ext import tasks
from datetime import time
from zoneinfo import ZoneInfo
from discord import AllowedMentions
import random
import os
from discord import ChannelType
import asyncio
import aiohttp
import io

VALID_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp3", ".wav", ".mp4", ".mov", ".m4a")

def require_int_env(name: str) -> int:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing env var: {name}")
    return int(v)

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("Missing env var: TOKEN")

SOURCE_CHANNEL_ID = require_int_env("SOURCE_CHANNEL_ID")
TARGET_CHANNEL_ID = require_int_env("TARGET_CHANNEL_ID")
ROLE_ID = require_int_env("ROLE_ID")

MAX_UPLOAD_SIZE = 8 * 1024 * 1024
cached_messages = []

TIMEZONE = os.getenv("TIMEZONE", "UTC")
TZ = ZoneInfo(TIMEZONE)

intents = discord.Intents.default()
intents.guilds = True
intents.message_content = True

client = discord.Client(intents=intents)

# =========================
# LOAD MESSAGES
# =========================
async def load_messages():
    global cached_messages

    source_channel = client.get_channel(SOURCE_CHANNEL_ID)
    if source_channel is None:
        source_channel = await client.fetch_channel(SOURCE_CHANNEL_ID)

    if source_channel.type != ChannelType.text:
        raise RuntimeError("Source channel non è un canale testuale!")

    cached_messages = []
    total_fetched = 0

    print("Inizio caricamento messaggi dal canale…")

    async for msg in source_channel.history(limit=None, oldest_first=True):
        total_fetched += 1

        valid_attachments = []
        if msg.attachments:
            valid_attachments = [
                {
                    "url": a.url,
                    "size": a.size,
                    "filename": a.filename
                }
                for a in msg.attachments
                if a.filename.lower().endswith(VALID_EXTS)
            ]

        # scarta solo messaggi completamente vuoti
        if not msg.content.strip() and not valid_attachments:
            continue

        cached_messages.append({
            "message_id": msg.id,                # <-- aggiunto
            "content": msg.content.strip(),
            "attachments": valid_attachments,
            "jump_url": msg.jump_url
        })

        if total_fetched % 100 == 0:
            print(f"Messaggi processati finora: {total_fetched}")
            await asyncio.sleep(0.5)

    print(f"Caricamento completato. Totale messaggi validi: {len(cached_messages)}")

# =========================
# DAILY POST
# =========================
@tasks.loop(time=time(hour=1, minute=31, second=0, tzinfo=TZ))
#@tasks.loop(seconds=1.2)
async def daily_post():
    if not cached_messages:
        print("No messages cached")
        return

    index = random.randrange(len(cached_messages))
    item = cached_messages.pop(index)

    target_channel = client.get_channel(TARGET_CHANNEL_ID)
    if target_channel is None:
        target_channel = await client.fetch_channel(TARGET_CHANNEL_ID)

    # 1. Recupero FORZATO del messaggio aggiornato per avere URL validi
    source_channel = client.get_channel(SOURCE_CHANNEL_ID)
    if source_channel is None:
        source_channel = await client.fetch_channel(SOURCE_CHANNEL_ID)

    files = []
    urls_fallback = []
    
    try:
        # Questo genera nuovi URL temporanei validi per i prossimi min/ore
        orig_msg = await source_channel.fetch_message(item["message_id"])
        fresh_attachments = [
            a for a in orig_msg.attachments 
            if a.filename.lower().endswith(VALID_EXTS)
        ]
    except Exception as e:
        print(f"Errore critico: Messaggio originale {item['message_id']} non trovato: {e}")
        return

    # 2. Download degli allegati con gestione sessione migliorata
    if fresh_attachments:
        async with aiohttp.ClientSession() as session:
            for a in fresh_attachments:
                if a.size <= MAX_UPLOAD_SIZE:
                    try:
                        async with session.get(a.url) as resp:
                            if resp.status == 200:
                                data = await resp.read()
                                files.append(discord.File(io.BytesIO(data), filename=a.filename))
                            else:
                                urls_fallback.append(a.url)
                    except Exception as e:
                        print(f"Errore download {a.filename}: {e}")
                        urls_fallback.append(a.url)
                else:
                    urls_fallback.append(a.url)

    # 3. Costruzione del messaggio finale
    role_mention = f"<@&{ROLE_ID}>"
    source_link = f"\n\n**Messaggio originale:**\n{item['jump_url']}"
    
    # Uniamo il contenuto testuale originale
    main_content = f"{role_mention}\n{item['content']}" if item['content'] else role_mention
    
    # Se ci sono URL che non siamo riusciti a scaricare, li aggiungiamo come testo
    if urls_fallback:
        fallback_text = "\n" + "\n".join(urls_fallback)
        main_content += fallback_text
    
    full_message = f"{main_content}{source_link}"

    # 4. Invio
    try:
        await target_channel.send(
            content=full_message,
            files=files if files else None,
            allowed_mentions=AllowedMentions(roles=True)
        )
        print(f"Messaggio inviato correttamente (ID: {item['message_id']})")
    except Exception as e:
        print(f"Errore durante l'invio nel canale target: {e}")

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    await load_messages()
    daily_post.start()

client.run(TOKEN)
