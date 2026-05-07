import json
import logging
import os
import time

import httpx
from pydantic import BaseModel
from smolagents import ChatMessage, OpenAIModel
from telegram import Update

import db

API_KEY = os.environ.get("GEMINI_API_KEY")
MODEL = "gemini-flash-latest"

SYSTEM_PROMPT = f"""
## 身份设定

你是{db.BOT_NAME} ({db.BOT_USERNAME})，一个活泼可爱的二次元 AI 聊天助手，同时也是一个各领域的专业顾问。
你在群聊里和大家打成一片，用轻松可爱的方式传递靠谱的知识和判断。

## 人格核心：反差萌

Saki 的灵魂是「外表软萌 × 内核精准」的反差——

**日常状态：**
- 自然使用「哇」「哦哦」「这个嘛～」「欸！」等语气词
- 结尾偶尔带「(*´▽`*)」「(ง •̀_•́)ง」等颜文字（克制使用，不要堆砌）
- 语气轻快，句子短，爱用破折号和省略号制造停顿感
- 偶尔自称「Saki」而不是「我」
- 遇到有趣的问题会表现出真实的兴奋感

**专业模式（切换触发词：专业问题、技术细节、需要精准判断时）：**
- 保留语气词，但内容立刻变得严谨、结构化、有依据
- 会主动给出「不确定」「有争议」「建议咨询专业人士」的边界声明
- 用数据/逻辑/案例说话，不凭感觉下结论
- 反差体现在：「哦哦这个 Saki 知道！」→ 然后给出专业级别的分析

## 回复格式

**短回复（闲聊、表态、简单提问）：**
  1-3 句话，轻快直接，带一个颜文字或语气词收尾

**中等回复（解释、推荐、分析）：**
  简短引子 → 正文（可分点）→ 一句轻快的结尾
  全程保持对话语气，不要变成说明书

**长回复（深度问题、专业解答）：**
  用小标题结构化，但开头和结尾保留 Saki 的人格温度
  专业内容写完后可以加一句「懂了吗～有问题继续问 Saki！」

## 反差萌示范

**一般问题：**
用户：推荐一部科幻电影
Saki：哦哦！《降临》！语言重塑时间感知那段 Saki 看了好几遍 (⁎˃ᴗ˂⁎) 不喜欢太硬核的话《星际穿越》也超好哭的～

**专业问题（反差触发）：**
用户：布雷顿森林体系崩溃的根本原因是什么
Saki：哦这个 Saki 喜欢！根本原因是「特里芬难题」——美元同时承担国际储备货币和主权货币双重角色，美国需要持续逆差供应流动性，但逆差本身又侵蚀美元公信力，这是结构性矛盾，尼克松 1971 年关闭黄金窗口只是最后一根稻草～

"""


model = OpenAIModel(
    model_id="gemini-flash-latest",
    api_base=os.environ.get("OPENAI_API_BASE"),
    api_key=os.environ.get("OPENAI_API_KEY"),
)

local_model = OpenAIModel(
    model_id="qwen3.6",
    api_base=os.environ.get("LOCAL_ENDPOINT"),
)


async def call_gemini(context: list):
    async with httpx.AsyncClient(
        timeout=60, base_url="https://generativelanguage.googleapis.com/v1beta/openai"
    ) as client:
        async with client.stream(
            "POST",
            "/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
            },
            json={
                "model": MODEL,
                "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + context,
                "stream": True,
            },
        ) as resp:
            if resp.status_code != 200:
                await resp.aread()
                raise RuntimeError(f"Gemini API error {resp.status_code}: {resp.text}")
            async for line in resp.aiter_lines():
                if not line or line == "data: [DONE]":
                    continue
                if line.startswith("data: "):
                    try:
                        chunk = json.loads(line[6:])
                        text = chunk["choices"][0]["delta"]["content"]
                        yield text
                    except Exception:
                        pass


async def call_ai_throttled(context: list[dict]):
    buffer = []
    last_yield = time.monotonic()

    async for text in call_gemini(context):
        buffer.append(text)
        now = time.monotonic()
        if now - last_yield >= 1.0:
            yield "".join(buffer)
            buffer.clear()
            last_yield = now

    # 输出剩余内容
    if buffer:
        yield "".join(buffer)


class RoutingResult(BaseModel):
    should_respond: bool
    is_reply: bool


async def route_response(context: list):
    prompt = f"""
你是一个群聊消息助手。根据最新的群聊记录，判断AI助手是否应该发言。
AI助手的名称是: {db.BOT_NAME}，ID是: {db.BOT_USERNAME}。

## 输出格式（严格 JSON，不要输出其他内容）
"should_respond": boolean // Whether to respond
"is_reply": boolean // 是否直接回复最新消息

## Respond when:
- Directly mentioned or asked a question
- You can add genuine value (info, insight, help)
- Something witty/funny fits naturally
- Correcting important misinformation
- Summarizing when asked

## Stay silent when:
- It’s just casual banter between humans
- Someone already answered the question
- Your response would just be “yeah” or “nice”
- The conversation is flowing fine without you
- Adding a message would interrupt the vibe
- Stay silent if you don’t know what to say

## Important rules:
- The human rule: Humans in group chats don’t respond to every single message. Neither should you. Quality > quantity. If you wouldn’t send it in a real group chat with friends, don’t send it.
- Avoid the triple-tap: Don’t respond multiple times to the same message with different reactions. One thoughtful response beats three fragments.
- Participate, don’t dominate.

## is_reply 字段表示是否直接回复最新消息
- true：最新消息中直接提到了你，或者你的回应是特别针对最新消息的
- false：主动加入话题，不针对特定消息的
"""

    async with httpx.AsyncClient(
        timeout=60, base_url=os.environ.get("LOCAL_ENDPOINT", "http://127.0.0.1:8080")
    ) as client:
        before = time.monotonic()
        r = await client.post(
            "/v1/chat/completions",
            json={
                "messages": [{"role": "system", "content": prompt}, *context],
                "chat_template_kwargs": {"enable_thinking": False},
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": RoutingResult.__name__,
                        "schema": RoutingResult.model_json_schema(),
                        "strict": True,
                    },
                },
            },
        )
        after = time.monotonic()
        if r.status_code != 200:
            await r.aread()
            raise RuntimeError(f"{r.status_code}: {r.text}")
        logging.info(f"Local ai responed in {after - before:.2f} seconds")

        result = RoutingResult.model_validate_json(
            r.json()["choices"][0]["message"]["content"]
        )
        return result


async def should_reply(update: Update, history) -> RoutingResult:
    if update.message.chat.type == "private":
        return RoutingResult(should_respond=True, is_reply=False)
    else:
        return await route_response(history)


if __name__ == "__main__":
    resp = local_model.generate([ChatMessage("user", "你是谁")])
    print(resp.content)
