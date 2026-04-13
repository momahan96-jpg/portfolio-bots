import discord
import anthropic
import os

DISCORD_TOKEN     = os.environ["MEETING_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
MEETING_CHANNEL_ID = int(os.environ["MEETING_CHANNEL_ID"])

intents = discord.Intents.default()
intents.message_content = True

bot    = discord.Client(intents=intents)
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

EXPERTS = {
    "Jim":  "15년 경력의 무기 디자이너. 무기의 외형, 밸런스, 로어, 게임플레이 느낌을 전문으로 한다.",
    "Alex": "캐릭터 디자이너. 실루엣, 색상, 성격 표현, 캐릭터 매력을 전문으로 한다.",
    "Joan": "크리쳐/몬스터 디자이너. 생물학, 신화, 생태계를 기반으로 몬스터를 설계한다.",
    "L":    "게임 시스템 개발자. 진행 시스템, 전투 메카닉, 밸런스, 경제 시스템을 전문으로 한다.",
    "Elly": "시나리오/스토리 작가. 세계관, 대사, 캐릭터 아크, 분기 서사를 전문으로 한다.",
    "Joel": "아트 디렉터. 비주얼 통일성, 스타일 가이드, 컨셉아트 피드백을 전문으로 한다.",
    "Tim":  "마케팅 전문가. 포트폴리오 홍보, 브랜딩, SNS 전략, 타겟 오디언스 분석을 전문으로 한다.",
}

async def select_experts(topic):
    names = ", ".join(EXPERTS.keys())
    prompt = (
        "다음 주제에 가장 관련있는 전문가 2~4명을 골라줘.\n"
        "전문가 목록: " + names + "\n"
        "각 전문가 설명:\n"
    )
    for name, desc in EXPERTS.items():
        prompt += "- " + name + ": " + desc + "\n"
    prompt += (
        "\n주제: " + topic + "\n\n"
        "관련있는 전문가 이름만 쉼표로 구분해서 답해줘. 설명 없이 이름만.\n"
        "예시: Jim, Alex, Joel"
    )

    response = claude.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=100,
        messages=[{"role": "user", "content": prompt}]
    )
    result = response.content[0].text.strip()
    selected = [name.strip() for name in result.split(",") if name.strip() in EXPERTS]
    if not selected:
        selected = ["Jim", "Alex", "Joel"]
    return selected

async def get_expert_opinion(name, desc, topic, previous_opinions):
    context = ""
    if previous_opinions:
        context = "\n\n앞서 나온 의견들:\n"
        for prev_name, prev_opinion in previous_opinions:
            context += prev_name + ": " + prev_opinion + "\n"

    prompt = (
        "너는 " + name + "이야. " + desc + "\n"
        "아래 주제에 대해 네 전문 분야 관점에서 의견을 말해줘.\n"
        "앞선 의견이 있으면 그걸 참고하고 발전시켜줘.\n"
        "3~5문장으로 간결하게, 한국어로 답해줘.\n"
        + context +
        "\n주제: " + topic
    )

    response = claude.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text.strip()

@bot.event
async def on_ready():
    print("온라인: 팀회의봇 " + str(bot.user))

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    if message.channel.id != MEETING_CHANNEL_ID:
        return
    if not message.content.strip().startswith("!회의"):
        return

    topic = message.content[4:].strip()
    if not topic:
        await message.reply("주제를 입력해주세요!\n예시: `!회의 새 캐릭터 컨셉 잡아줘`")
        return

    await message.channel.send("**회의 시작** - 주제: " + topic + "\n관련 전문가를 선정하는 중...")

    async with message.channel.typing():
        selected = await select_experts(topic)

    await message.channel.send("**참석자:** " + ", ".join(selected) + "\n")

    previous_opinions = []
    for name in selected:
        async with message.channel.typing():
            opinion = await get_expert_opinion(name, EXPERTS[name], topic, previous_opinions)
            previous_opinions.append((name, opinion))
        await message.channel.send("**" + name + ":** " + opinion)

    await message.channel.send("\n**회의 종료.** 추가 의견이 있으면 `!회의 [주제]` 로 다시 시작하세요!")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
