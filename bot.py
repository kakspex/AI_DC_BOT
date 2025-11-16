import os
import asyncio
import uuid
import aiohttp
import discord
from discord import app_commands

curl -v https://kakspex-dc-ai.hf.space/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"test"}'


HF_API = os.environ.get("HF_API", "https://kakspex-dc-ai.hf.space")
TOKEN = os.environ.get("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN missing")

pending_tasks = {}
task_lock = asyncio.Lock()

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

http_session = None

async def queue_task(prompt):
    p = prompt.strip()
    if len(p) > 4000:
        p = p[:4000]
    try:
        async with asyncio.timeout(45):
            async with http_session.post(f"{HF_API}/generate", json={"prompt": p, "max_length": 128}) as r:
                if r.status not in (200, 202):
                    try:
                        j = await r.json()
                        return j.get("task_id")
                    except:
                        text = await r.text()
                        print("generate-error-status", r.status, text)
                        return None
                j = await r.json()
                return j.get("task_id")
    except Exception as e:
        print("generate-exception", str(e))
        return None

async def fetch_result(task_id):
    try:
        async with asyncio.timeout(8):
            async with http_session.get(f"{HF_API}/result/{task_id}") as r:
                if r.status == 404:
                    return {"status": "notfound"}
                j = await r.json()
                return j
    except:
        return {"status": "error"}

async def wait_with_progress(interaction, task_id, total_timeout=120):
    start = asyncio.get_running_loop().time()
    last_sent = ""
    try:
        while True:
            await asyncio.sleep(0.8)
            if asyncio.get_running_loop().time() - start > total_timeout:
                return "timeout"
            j = await fetch_result(task_id)
            if j.get("status") == "notfound":
                await interaction.edit_original_response(content="task not found")
                return "task not found"
            if j.get("status") == "completed":
                out = j.get("output", "")
                return out
            partial = j.get("partial", "") or ""
            if partial and partial != last_sent:
                last_sent = partial
                display = partial if len(partial) < 1900 else partial[:1890] + "..."
                try:
                    await interaction.edit_original_response(content=display)
                except:
                    pass
    except:
        return "error"

@tree.command(name="ai")
async def ai_command(interaction, prompt: str):
    await interaction.response.defer()
    try:
        tid = await queue_task(prompt)
        if not tid:
            await interaction.edit_original_response(content="request error")
            return
        result = await wait_with_progress(interaction, tid, total_timeout=120)
        if not result:
            await interaction.edit_original_response(content="no output")
            return
        if len(result) > 2000:
            await interaction.edit_original_response(content=result[:1990] + "...")
            return
        await interaction.edit_original_response(content=result)
    except:
        await interaction.edit_original_response(content="error")

@tree.command(name="queue")
async def queue_command(interaction, prompt: str):
    async with task_lock:
        tid = str(uuid.uuid4())
        pending_tasks[tid] = prompt.strip()[:4000]
    await interaction.response.send_message("Task added: " + tid)

@tree.command(name="runqueue")
async def runqueue(interaction):
    await interaction.response.send_message("Running queue")
    async with task_lock:
        keys = list(pending_tasks.keys())
    for tid in keys:
        async with task_lock:
            p = pending_tasks.get(tid)
        try:
            real_task = await queue_task(p)
            if not real_task:
                await interaction.followup.send("Task " + tid + ": request error")
                async with task_lock:
                    if tid in pending_tasks:
                        del pending_tasks[tid]
                continue
            msg = await wait_with_progress(interaction, real_task, total_timeout=120)
            if not msg or msg in ("timeout", "error"):
                msg = msg if msg else "no output"
            if len(msg) > 1900:
                msg = msg[:1890] + "..."
            await interaction.followup.send("Task " + tid + ": " + msg)
        except:
            await interaction.followup.send("Task " + tid + ": error")
        async with task_lock:
            if tid in pending_tasks:
                del pending_tasks[tid]

@tree.command(name="ping")
async def ping(interaction):
    await interaction.response.send_message("Pong")

@client.event
async def on_ready():
    await tree.sync()

async def start():
    global http_session
    timeout = aiohttp.ClientTimeout(total=None)
    http_session = aiohttp.ClientSession(timeout=timeout)
    try:
        await client.start(TOKEN)
    finally:
        await http_session.close()

if __name__ == "__main__":
    asyncio.run(start())
