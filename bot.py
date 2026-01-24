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

# timezone for scheduled tasks (IANA name, e.g. 'UTC' or 'Europe/Rome')
TIMEZONE = os.getenv("TIMEZONE", "UTC")
TZ = ZoneInfo(TIMEZONE)

intents = discord.Intents.default()
intents.guilds = True
intents.message_content = True

client = discord.Client(intents=intents)

# carica tutti i messaggi in array
async def load_messages():
    """
    Carica tutti i messaggi dal canale SOURCE_CHANNEL_ID,
    compresi testo e attachment.
    """
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

        if msg.content.strip():
            cached_messages.append({
                "type": "text",
                "content": msg.content,
                "attachments": [],
                "jump_url": msg.jump_url
            })

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

            if valid_attachments:
                cached_messages.append({
                    "type": "attachment",
                    "jump_url": msg.jump_url,
                    "attachments": valid_attachments
                })

        if total_fetched % 100 == 0:
            print(f"Messaggi processati finora: {total_fetched}")
            await asyncio.sleep(0.5)

    print(f"Caricamento completato. Totale messaggi validi: {len(cached_messages)}")

# invio messaggio
@tasks.loop(time=time(hour=21, minute=31, second=0, tzinfo=TZ))
async def daily_post():
    if not cached_messages:
        print("No messages cached")
        return

    index = random.randrange(len(cached_messages))
    item = cached_messages.pop(index)

    target_channel = client.get_channel(TARGET_CHANNEL_ID)
    if target_channel is None:
        target_channel = await client.fetch_channel(TARGET_CHANNEL_ID)

    role_mention = f"<@&{ROLE_ID}>"
    source_link = f"\n\nMessaggio originale:\n{item['jump_url']}"

    if item["type"] == "text":
        await target_channel.send(
            content=f"{role_mention}\n{item['content']}{source_link}",
            allowed_mentions=AllowedMentions(roles=True)
        )

    elif item["type"] == "attachment":
        attachments = item["attachments"]
        total_size = sum(a["size"] for a in attachments)

        # upload possibile
        if total_size <= MAX_UPLOAD_SIZE:
            files = []

            async with aiohttp.ClientSession() as session:
                for a in attachments:
                    async with session.get(a["url"]) as resp:
                        if resp.status != 200:
                            print(f"Errore download {a['url']}")
                            continue

                        data = await resp.read()
                        files.append(
                            discord.File(
                                io.BytesIO(data),
                                filename=a["filename"]
                            )
                        )

            await target_channel.send(
                files=files,
                content=f"{role_mention}{source_link}",
                allowed_mentions=AllowedMentions(roles=True)
            )

        # troppo grandi → URL
        else:
            urls = "\n".join(a["url"] for a in attachments)
            await target_channel.send(
                content=f"{role_mention}\n{urls}{source_link}",
                allowed_mentions=AllowedMentions(roles=True)
            )

    print("Posted daily message")

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    await load_messages()
    daily_post.start()

client.run(TOKEN)

