"""AENIMUS Discord bridge v0.1.0 — allowlisted inbound control and head-agent output."""
import os
import httpx, discord

TOKEN=os.environ["DISCORD_BOT_TOKEN"]
API=os.getenv("AENIMUS_API_URL","http://studio:8787/api").rstrip("/")
PREFIX=os.getenv("AENIMUS_DISCORD_COMMAND_PREFIX","!aenimus")
CHANNEL=int(os.environ["AENIMUS_DISCORD_CHANNEL_ID"])
ALLOWED={int(x) for x in os.getenv("AENIMUS_DISCORD_ALLOWED_USER_IDS","").split(",") if x.strip()}
intents=discord.Intents.default(); intents.message_content=True
client=discord.Client(intents=intents)

async def request(method,path,**kwargs):
    async with httpx.AsyncClient(timeout=180) as c:
        r=await c.request(method,API+path,**kwargs); r.raise_for_status(); return r.json()

@client.event
async def on_ready():
    print(f"AENIMUS Discord bridge v0.1.0 connected as {client.user}")

@client.event
async def on_message(message):
    if message.author.bot or message.channel.id!=CHANNEL or not message.content.startswith(PREFIX): return
    if ALLOWED and message.author.id not in ALLOWED:
        await message.reply("AENIMUS: sender is not authorized."); return
    prompt=message.content[len(PREFIX):].strip()
    if not prompt: await message.reply(f"Usage: `{PREFIX} your instruction`"); return
    sessions=await request("GET","/sessions")
    if not sessions: await message.reply("No active AENIMUS operation exists."); return
    session=sessions[0]
    await message.add_reaction("⚙️")
    result=await request("POST",f"/sessions/{session['id']}/chat",json={"content":prompt})
    # The final pipeline item is the designated head/final output.
    final=result["messages"][-1]["content"] if result.get("messages") else "No final output."
    for start in range(0,len(final),1900): await message.reply(final[start:start+1900])

client.run(TOKEN)

