import os
import asyncio
import uuid
import requests
import discord
from discord import app_commands

HF_API = "https://huggingface.co/spaces/kakspex/NEW_BOT_LOLZ"

TOKEN = os.environ["DISCORD_TOKEN"]

pending_tasks = {}
task_lock = asyncio.Lock()

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

async def queue_task(prompt):
    async with task_lock:
        r = requests.post(f"{HF_API}/generate", json={"prompt":prompt})
        data = r.json()
        return data["task_id"]

async def wait_for_result(task_id):
    done = False
    output = ""
    while not done:
        await asyncio.sleep(1)
        r2 = requests.get(f"{HF_API}/result/{task_id}")
        data = r2.json()
        if data["status"] == "completed":
            done = True
            output = data["output"]
    return output

@tree.command(name="ai")
async def ai_command(interaction, prompt: str):
    await interaction.response.send_message("Processing")
    task_id = await queue_task(prompt)
    result = await wait_for_result(task_id)
    await interaction.edit_original_response(content=result)

@tree.command(name="queue")
async def queue_command(interaction, prompt: str):
    task_id = str(uuid.uuid4())
    pending_tasks[task_id] = prompt
    await interaction.response.send_message("Task added: " + task_id)

@tree.command(name="runqueue")
async def runqueue(interaction):
    await interaction.response.send_message("Running queue")
    keys = list(pending_tasks.keys())
    for task_id in keys:
        prompt = pending_tasks[task_id]
        real_task = await queue_task(prompt)
        result = await wait_for_result(real_task)
        await interaction.followup.send("Task " + task_id + ": " + result)
        del pending_tasks[task_id]

@tree.command(name="ping")
async def ping(interaction):
    await interaction.response.send_message("Pong")

@client.event
async def on_ready():
    await tree.sync()

async def start():
    await client.start(TOKEN)

asyncio.run(start())
