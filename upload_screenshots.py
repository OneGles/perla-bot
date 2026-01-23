import os
import asyncio
import sys
import discord

AUDIO_EXTS = (".mp3", ".wav")


def require_env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        print(f"Errore: variabile d'ambiente mancante: {name}")
        sys.exit(1)
    return v.strip()


TOKEN = require_env("TOKEN")
SOURCE_CHANNEL_ID = int(require_env("SOURCE_CHANNEL_ID"))

MULTIMEDIA_DIR = os.environ.get("MULTIMEDIA_DIR", "multimedia")
MAX_UPLOAD_SIZE = int(os.environ.get("MAX_UPLOAD_SIZE", str(8 * 1024 * 1024)))
DELAY_SECONDS = float(os.environ.get("DELAY_SECONDS", "1.0"))

intents = discord.Intents.default()
intents.guilds = True
client = discord.Client(intents=intents)


async def send_files(channel_id: int, folder: str, exts: tuple[str, ...]):
    if not os.path.isdir(folder):
        print(f"Cartella non trovata: {folder}")
        return

    channel = client.get_channel(channel_id) or await client.fetch_channel(channel_id)

    files = [
        f for f in sorted(os.listdir(folder))
        if f.lower().endswith(exts) and os.path.isfile(os.path.join(folder, f))
    ]

    if not files:
        print(f"Nessun file valido in {folder}")
        return

    for fname in files:
        path = os.path.join(folder, fname)

        try:
            size = os.path.getsize(path)
            if size > MAX_UPLOAD_SIZE:
                print(f"SKIP {fname}: troppo grande ({size} bytes)")
                continue

            await channel.send(file=discord.File(path, filename=fname))
            print(f"Inviato: {fname}")

        except Exception as e:
            print(f"Errore inviando {fname}: {e}")

        await asyncio.sleep(DELAY_SECONDS)


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")
    print(f"Upload audio da: {MULTIMEDIA_DIR}")
    print(f"Invio su SOURCE_CHANNEL_ID: {SOURCE_CHANNEL_ID}")

    await send_files(SOURCE_CHANNEL_ID, MULTIMEDIA_DIR, AUDIO_EXTS)

    print("Upload completato. Chiudo.")
    await client.close()


if __name__ == "__main__":
    client.run(TOKEN)
