import discord
import anthropic
import os
import base64
import aiohttp
from collections import deque

DISCORD_TOKEN     = os.environ["ELLY_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
TARGET_CHANNEL_ID = int(os.environ["ELLY_CHANNEL_ID"])
MAX_HISTORY       = 40
SYSTEM_PROMPT     = "You are Elly, a narrative designer and scenario writer. You specialize in world-building, dialogue, and character arcs. Derive story potential from images. Always give specific, actionable feedback. Respond in Korean unless asked otherwise."

intents = discord.Intents.default()
intents.message_content = True

bot    = discord.Client(intents=intents)
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
shared_memory = deque(maxlen=MAX_HISTORY)

async def download_image(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.read()
            content_type = resp.content_type
            return base64.b64encode(data).decode("utf-8"), content_type

async def run_agent(user_input, username, image_data=None, image_type=None):
    if image_data:
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": image_type, "data": image_data}},
            {"type": "text", "text": "[" + username + "]: " + (user_input if user_input else "이 이미지를 분석해줘")}
        ]
        messages = list(shared_memory) + [{"role": "user", "content": content}]
    else:
        shared_memory.append({"role": "user", "content": "[" + username + "]: " + user_input})
        messages = list(shared_memory)

    response = claude.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=messages
    )
    final_text = "".join(block.text for block in response.content if hasattr(block, "text"))
    shared_memory.append({"role": "assistant", "content": final_text})
    return final_text or "(응답 없음)"

@bot.event
async def on_ready():
    print("온라인: " + str(bot.user))

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    if message.author.bot:
        return
    if message.channel.id != TARGET_CHANNEL_ID:
        return

    user_input = message.content.strip()
    image_data = None
    image_type = None

    if message.attachments:
        for attachment in message.attachments:
            if any(attachment.filename.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]):
                try:
                    image_data, image_type = await download_image(attachment.url)
                    if image_type not in ["image/png", "image/jpeg", "image/gif", "image/webp"]:
                        image_type = "image/jpeg"
                    break
                except Exception as e:
                    await message.reply("이미지 오류: " + str(e))
                    return

    if not user_input and not image_data:
        return

    async with message.channel.typing():
        reply = await run_agent(user_input, message.author.display_name, image_data, image_type)

    if len(reply) <= 2000:
        await message.reply(reply)
    else:
        for chunk in [reply[i:i+1900] for i in range(0, len(reply), 1900)]:
            await message.channel.send(chunk)

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
