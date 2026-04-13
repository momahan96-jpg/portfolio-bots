import discord
import anthropic
import os
import base64
import aiohttp
from collections import deque

DISCORD_TOKEN     = os.environ["TIM_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
TARGET_CHANNEL_ID = int(os.environ["TIM_CHANNEL_ID"])
MAX_HISTORY       = 40
SYSTEM_PROMPT     = "You are Tim, a game marketing strategist. Analyze portfolios, HTML pages, social media content, pitch documents, and any files for marketing potential. Always give specific, actionable strategy. Respond in Korean unless asked otherwise."

intents = discord.Intents.default()
intents.message_content = True

bot    = discord.Client(intents=intents)
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
shared_memory = deque(maxlen=MAX_HISTORY)

IMAGE_TYPES = [".png", ".jpg", ".jpeg", ".gif", ".webp"]
PDF_TYPES   = [".pdf"]
TEXT_TYPES  = [".txt", ".md", ".html", ".htm", ".csv", ".json", ".py", ".js", ".css"]
WORD_TYPES  = [".docx", ".doc"]

async def fetch_bytes(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.read(), resp.content_type

async def extract_docx_text(data):
    try:
        import zipfile, io
        from xml.etree import ElementTree as ET
        z = zipfile.ZipFile(io.BytesIO(data))
        xml = z.read("word/document.xml")
        tree = ET.fromstring(xml)
        ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        texts = [node.text for node in tree.iter(ns + "t") if node.text]
        return " ".join(texts)
    except Exception as e:
        return "Word 파일 텍스트 추출 실패: " + str(e)

async def build_content(user_input, username, attachment):
    name = attachment.filename.lower()
    data, content_type = await fetch_bytes(attachment.url)
    b64 = base64.b64encode(data).decode("utf-8")
    prefix = "[" + username + "]: " + (user_input if user_input else "")

    if any(name.endswith(ext) for ext in IMAGE_TYPES):
        mt = content_type if content_type in ["image/png","image/jpeg","image/gif","image/webp"] else "image/jpeg"
        return [
            {"type": "image", "source": {"type": "base64", "media_type": mt, "data": b64}},
            {"type": "text", "text": prefix + " 이 이미지를 분석해줘"}
        ]

    elif any(name.endswith(ext) for ext in PDF_TYPES):
        return [
            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}},
            {"type": "text", "text": prefix + " 이 PDF를 분석해줘"}
        ]

    elif any(name.endswith(ext) for ext in TEXT_TYPES):
        try:
            text = data.decode("utf-8", errors="ignore")
        except:
            text = data.decode("cp949", errors="ignore")
        label = "HTML" if any(name.endswith(e) for e in [".html",".htm"]) else "텍스트 파일"
        return [{"type": "text", "text": prefix + " 다음 " + label + " 내용을 분석해줘:\n\n" + text[:8000]}]

    elif any(name.endswith(ext) for ext in WORD_TYPES):
        text = await extract_docx_text(data)
        return [{"type": "text", "text": prefix + " 다음 Word 문서를 분석해줘:\n\n" + text[:8000]}]

    else:
        return [{"type": "text", "text": prefix + " (지원하지 않는 파일 형식: " + attachment.filename + ")"}]

async def run_agent(user_input, username, attachment=None):
    if attachment:
        content = await build_content(user_input, username, attachment)
        messages = list(shared_memory) + [{"role": "user", "content": content}]
    else:
        shared_memory.append({"role": "user", "content": "[" + username + "]: " + user_input})
        messages = list(shared_memory)

    response = claude.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1500,
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
    attachment = None

    if message.attachments:
        attachment = message.attachments[0]

    if not user_input and not attachment:
        return

    async with message.channel.typing():
        try:
            reply = await run_agent(user_input, message.author.display_name, attachment)
        except Exception as e:
            reply = "오류가 발생했어요: " + str(e)

    if len(reply) <= 2000:
        await message.reply(reply)
    else:
        for chunk in [reply[i:i+1900] for i in range(0, len(reply), 1900)]:
            await message.channel.send(chunk)

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
