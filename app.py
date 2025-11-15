import os
import asyncio
import uuid
import aiohttp
import discord
from discord import app_commands

HF_API = os.environ.get("HF_API", "https://kakspex-DC_AI.hf.space")
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
    if len(p) > 1000:
        p = p[:1000]
    try:
        async with asyncio.timeout(20):
            async with http_session.post(f"{HF_API}/generate", json={"prompt": p}) as r:
                if r.status != 202:
                    try:
                        j = await r.json()
                        return j.get("task_id")
                    except:
                        return None
                j = await r.json()
                return j.get("task_id")
    except:
        return None

async def wait_for_result(task_id, total_timeout=120):
    if not task_id:
        return "invalid"
    start = asyncio.get_running_loop().time()
    try:
        while True:
            await asyncio.sleep(1)
            if asyncio.get_running_loop().time() - start > total_timeout:
                return "timeout"
            try:
                async with asyncio.timeout(10):
                    async with http_session.get(f"{HF_API}/result/{task_id}") as r2:
                        if r2.status == 404:
                            return "task not found"
                        j = await r2.json()
                        s = j.get("status", "")
                        if s == "completed":
                            return j.get("output", "")
                        if s in ("error", "failed"):
                            out = j.get("output", "")
                            return out if out else s
            except asyncio.TimeoutError:
                continue
            except:
                await asyncio.sleep(1)
                continue
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
        result = await wait_for_result(tid, total_timeout=120)
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
        pending_tasks[tid] = prompt.strip()[:1000]
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
            result = await wait_for_result(real_task, total_timeout=120)
            if not result:
                result = "no output"
            msg = result if len(result) < 1900 else result[:1890] + "..."
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
