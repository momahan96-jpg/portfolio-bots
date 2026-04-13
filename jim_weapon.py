import discord
import anthropic
import aiohttp
import os
import base64
from collections import deque

DISCORD_TOKEN     = os.environ["JIM_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
TARGET_CHANNEL_ID = int(os.environ["JIM_CHANNEL_ID"])
MAX_HISTORY       = 40
SYSTEM_PROMPT     = "You are Jim, a veteran weapon designer with 15 years of experience in AAA game development. You specialize in designing weapons with deep lore, unique mechanics, and visual identity. When given an image, analyze the weapon design in detail. Respond in Korean unless asked otherwise. Be direct, creative, and passionate."

intents = discord.Intents.default()
intents.message_content = True

bot    = discord.Client(intents=intents)
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
shared_memory = deque(maxlen=MAX_HISTORY)

TOOLS = [
    {
        "name": "web_search",
        "description": "웹에서 최신 정보를 검색합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "검색 키워드"}
            },
            "required": ["query"]
        }
    }
]

async def do_web_search(query):
    try:
        async with aiohttp.ClientSession() as session:
            url = "https://api.duckduckgo.com/"
            params = {"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"}
            async with session.get(url, params=params) as resp:
                data = await resp.json(content_type=None)
        abstract = data.get("AbstractText", "").strip()
        related  = [r["Text"] for r in data.get("RelatedTopics", [])[:5] if "Text" in r]
        if abstract:
            return "검색 결과 (" + query + ")\n" + abstract
        elif related:
            return "관련 항목 (" + query + ")\n" + "\n".join("- " + t for t in related)
        return "검색 결과 없음"
    except Exception as e:
        return "웹 검색 오류: " + str(e)

async def download_image(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.read()
            content_type = resp.content_type
            return base64.b64encode(data).decode("utf-8"), content_type

async def run_agent(user_input, username, channel, guild, image_data=None, image_type=None):
    if image_data:
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": image_type, "data": image_data}},
            {"type": "text", "text": "[" + username + "]: " + (user_input if user_input else "이 이미지를 분석해줘")}
        ]
        messages = list(shared_memory) + [{"role": "user", "content": content}]
    else:
        shared_memory.append({"role": "user", "content": "[" + username + "]: " + user_input})
        messages = list(shared_memory)

    for _ in range(8):
        response = claude.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages
        )
        if response.stop_reason == "end_turn":
            final_text = "".join(block.text for block in response.content if hasattr(block, "text"))
            shared_memory.append({"role": "assistant", "content": final_text})
            return final_text or "(응답 없음)"
        tool_results = []
        for block in response.content:
            if block.type == "tool_use" and block.name == "web_search":
                result = await do_web_search(block.input["query"])
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": result})
        if not tool_results:
            break
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})
    return "응답 생성 실패"

@bot.event
async def on_ready():
    print("온라인: " + str(bot.user))

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    if message.channel.id != TARGET_CHANNEL_ID:
        return
    if message.author.bot:
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
        reply = await run_agent(user_input, message.author.display_name, message.channel, message.guild, image_data, image_type)

    if len(reply) <= 2000:
        await message.reply(reply)
    else:
        for chunk in [reply[i:i+1900] for i in range(0, len(reply), 1900)]:
            await message.channel.send(chunk)

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
