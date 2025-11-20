import os
import asyncio
import aiohttp
import discord
from discord import app_commands

HF_API = os.environ.get("HF_API", "https://kakspex-dc-ai.hf.space")
TOKEN = os.environ.get("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN missing")

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

http_session = None

async def request_generate(prompt):
    p = prompt.strip()[:2000]
    try:
        async with asyncio.timeout(10):
            async with http_session.post(f"{HF_API}/generate", json={"prompt": p, "max_length": 64}) as r:
                try:
                    j = await r.json()
                except:
                    return None
                return j.get("task_id")
    except:
        return None

async def request_result(task_id):
    try:
        async with asyncio.timeout(10):
            async with http_session.get(f"{HF_API}/result/{task_id}") as r:
                try:
                    j = await r.json()
                except:
                    return {"status": "error"}
                return j
    except:
        return {"status": "error"}

async def wait_result(interaction, task_id):
    start = asyncio.get_running_loop().time()
    last = ""
    while True:
        await asyncio.sleep(0.8)
        if asyncio.get_running_loop().time() - start > 120:
            return "timeout"
        j = await request_result(task_id)
        s = j.get("status")
        if s == "notfound":
            return "notfound"
        if s == "completed":
            return j.get("output", "")
        partial = j.get("partial", "")
        if partial and partial != last:
            last = partial
            d = partial[:1900] if len(partial) >= 1900 else partial
            try:
                await interaction.edit_original_response(content=d)
            except:
                pass

@tree.command(name="ai")
async def ai_command(interaction, prompt: str):
    await interaction.response.defer()
    tid = await request_generate(prompt)
    if not tid:
        await interaction.edit_original_response(content="request error")
        return
    r = await wait_result(interaction, tid)
    if not r or r in ("timeout", "notfound", "error"):
        await interaction.edit_original_response(content="request error")
        return
    if len(r) > 2000:
        r = r[:1990] + "..."
    await interaction.edit_original_response(content=r)

@tree.command(name="print")
async def ping(interaction):
    await interaction.response.send_message("Hello World!")

@client.event
async def on_ready():
    await tree.sync()

async def start():
    global http_session
    http_session = aiohttp.ClientSession()
    try:
        await client.start(TOKEN)
    finally:
        await http_session.close()

if __name__ == "__main__":
    asyncio.run(start())
