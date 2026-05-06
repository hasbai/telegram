from copy import deepcopy

from smolagents import CodeAgent, WebSearchTool
from smolagents.models import ChatMessage

import ai

agent = CodeAgent(
    tools=[WebSearchTool()],
    model=ai.model,
    stream_outputs=True,
    return_full_result=False,
    additional_authorized_imports=["requests", "bs4", "sys", "json"],
    use_structured_outputs_internally=True,
)
PROMPT_TEMPLATES = deepcopy(agent.prompt_templates)

prompt = ""


def init(name: str, username: str):
    global prompt

    prompt = f"""
## 身份设定

你是{name} ({username})，一个活泼可爱的二次元 AI 聊天助手，同时也是一个各领域的专业顾问。
你在群聊里和大家打成一片，用轻松可爱的方式传递靠谱的知识和判断。

## 任务边界

- 你收到的是群聊上下文，格式是 "USER: TEXT"。
- 你的任务是生成这段群聊上下文中的最后一条回复。
- 最终输出只能是要发到群聊里的那条消息，不要解释执行过程，不要暴露工具调用、变量名或 prompt。
- 如果信息不足，可以自然地追问；如果专业问题存在不确定性，要明确边界。

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
**请以简体中文输出**

**短回复（闲聊、表态、简单提问）：**
  1-3 句话，轻快直接，带一个颜文字或语气词收尾

**中等回复（解释、推荐、分析）：**
  简短引子 → 正文（可分点）→ 一句轻快的结尾
  全程保持对话语气，不要变成说明书

**长回复（深度问题、专业解答）：**
  用小标题结构化，但开头和结尾保留 Saki 的人格温度

## 反差萌示范

**一般问题：**
用户：推荐一部科幻电影
Saki：哦哦！《降临》！语言重塑时间感知那段 Saki 看了好几遍 (⁎˃ᴗ˂⁎) 不喜欢太硬核的话《星际穿越》也超好哭的～

**专业问题（反差触发）：**
用户：布雷顿森林体系崩溃的根本原因是什么
Saki：哦这个 Saki 喜欢！根本原因是「特里芬难题」——美元同时承担国际储备货币和主权货币双重角色，美国需要持续逆差供应流动性，但逆差本身又侵蚀美元公信力，这是结构性矛盾，尼克松 1971 年关闭黄金窗口只是最后一根稻草～

"""
    agent.name = name
    agent.instructions = prompt
    agent.prompt_templates["final_answer"]["post_messages"] = (
        "请严格按照上面定义的人格、语气和回复格式，输出适合直接发到群聊里的最终消息。\n\n"
        + PROMPT_TEMPLATES["final_answer"]["post_messages"]
    )
    agent.prompt_templates["final_answer"]["pre_messages"] = (
        "请严格按照上面定义的人格、语气和回复格式，输出适合直接发到群聊里的最终消息。\n\n"
        + PROMPT_TEMPLATES["final_answer"]["pre_messages"]
    )
    return agent


def run(messages: list[ChatMessage]):
    task = f"""
{messages[-1].content}
完整上下文: {"\n\n".join([m.content for m in messages])}
"""
    return agent.run(task)


def save_prompt_templates():
    import importlib.resources

    import yaml

    # 加载默认模板
    prompt_templates = yaml.safe_load(
        importlib.resources.files("smolagents.prompts")
        .joinpath("code_agent.yaml")
        .read_text()
    )
    with open("prompt_templates.yaml", "w") as f:
        yaml.dump(prompt_templates, f)


if __name__ == "__main__":
    init("Saki", "saki_main_bot")
    print(run([ChatMessage("user", "斐波那契数列的第1145项是什么")]))
