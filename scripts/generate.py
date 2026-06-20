#!/usr/bin/env python3
"""
Daily English — AI 职场英语内容生成器

用法:
  python3 scripts/generate.py                                    # 自动选择主题
  python3 scripts/generate.py --topic "会议英语"                   # 指定主题
  python3 scripts/generate.py --list-scenarios                    # 列出可用主题

功能:
  调用 DeepSeek API 生成外企工作场景常用对话内容，保存为 Markdown 草稿。
"""

from __future__ import annotations

import json
import os
import random
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PROJECT_DIR = Path(__file__).resolve().parent.parent
DRAFT_DIR = PROJECT_DIR / "drafts"


def _load_env() -> dict[str, str]:
    result: dict[str, str] = {}
    # 先读 .env（真实密钥），再读 .env.example（仅补缺）
    for fname in (".env", ".env.example"):
        fpath = PROJECT_DIR / fname
        if not fpath.exists():
            continue
        for line in fpath.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                val = val[1:-1]
            # .env.example 不覆盖 .env 已有的值
            if fname == ".env.example" and key in result:
                continue
            result[key] = val
    for k in ("DEEPSEEK_API_KEY",):
        if os.environ.get(k):
            result[k] = os.environ[k]
    return result


ENV = _load_env()
DEEPSEEK_API_KEY = ENV.get("DEEPSEEK_API_KEY", "")

# ---------------------------------------------------------------------------
# 场景库
# ---------------------------------------------------------------------------

WORKPLACE_SCENARIOS: list[dict[str, str]] = [
    {"zh": "晨会 Standup", "en": "Daily Standup Meeting",
     "desc": "每日站会中如何简洁汇报进度、提出阻塞"},
    {"zh": "头脑风暴会议", "en": "Brainstorming Session",
     "desc": "头脑风暴中如何提出想法、回应他人建议"},
    {"zh": "项目复盘会", "en": "Project Retrospective",
     "desc": "复盘会中如何总结得失、提出改进"},
    {"zh": "跨部门协作会议", "en": "Cross-functional Meeting",
     "desc": "与不同部门同事高效沟通、对齐目标"},
    {"zh": "客户演示", "en": "Client Presentation",
     "desc": "向客户展示方案、回答提问的专业表达"},
    {"zh": "面试英语", "en": "Job Interview",
     "desc": "外企面试中的常见问题和地道回答"},
    {"zh": "给老板发邮件", "en": "Email to Your Manager",
     "desc": "写邮件向老板汇报进度、请求资源"},
    {"zh": "Slack/Teams 即时沟通", "en": "Instant Messaging at Work",
     "desc": "在办公沟通工具中的得体表达"},
    {"zh": "请假和休假申请", "en": "Requesting Time Off",
     "desc": "如何得体地请假、安排工作交接"},
    {"zh": "拒绝额外任务", "en": "Saying No to Extra Work",
     "desc": "委婉但不失专业地拒绝额外任务"},
    {"zh": "请求反馈", "en": "Asking for Feedback",
     "desc": "如何主动请求同事或上司给出反馈"},
    {"zh": "接受批评", "en": "Handling Criticism",
     "desc": "面对负面反馈时如何成熟应对"},
    {"zh": "办公室小聊", "en": "Office Small Talk",
     "desc": "茶水间、午餐时的闲聊话题和表达"},
    {"zh": "团队聚餐", "en": "Team Dinner",
     "desc": "聚餐时的聊天话题和礼貌用语"},
    {"zh": "公司年会", "en": "Company Annual Party",
     "desc": "年会上与人寒暄、表达感谢"},
    {"zh": "接待外国同事", "en": "Hosting International Colleagues",
     "desc": "接待海外同事时的日常对话"},
    {"zh": "电话沟通", "en": "Phone Calls",
     "desc": "工作电话中的标准话术"},
    {"zh": "请假邮件", "en": "Sick Leave Email",
     "desc": "请病假时怎么发邮件"},
    {"zh": "写周报", "en": "Weekly Report",
     "desc": "周报怎么写才清晰有条理"},
    {"zh": "1对1 与老板谈话", "en": "One-on-One with Manager",
     "desc": "一对一沟通中的技巧和表达"},
    {"zh": "晋升谈话", "en": "Promotion Conversation",
     "desc": "如何与老板讨论晋升和职业发展"},
    {"zh": "离职面谈", "en": "Exit Interview",
     "desc": "离职时如何体面地沟通"},
    {"zh": "Code Review 发言", "en": "Code Review Comments",
     "desc": "Code Review 中如何给出建设性意见"},
    {"zh": "技术方案讨论", "en": "Technical Design Discussion",
     "desc": "讨论技术方案时的专业表达"},
    {"zh": "生产事故处理", "en": "Incident Response",
     "desc": "线上故障时的紧急沟通话术"},
    # 轻松话题（3:1 比例，调节节奏）
    {"zh": "办公室闲聊", "en": "Water Cooler Chat",
     "desc": "茶水间、电梯里的日常闲聊话题和表达"},
    {"zh": "入职第一天", "en": "First Day Onboarding",
     "desc": "新公司第一天如何自我介绍、熟悉环境"},
    {"zh": "团队聚餐社交", "en": "Team Bonding Activities",
     "desc": "团建、聚餐等非正式场合的英语表达"},
    {"zh": "出差归来闲谈", "en": "Back from Business Trip",
     "desc": "出差回来跟同事聊见闻的地道说法"},
]


# ---------------------------------------------------------------------------
# DeepSeek API
# ---------------------------------------------------------------------------

DEEPSEEK_BASE = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"


def _call_deepseek(
    messages: list[dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 4096,
    timeout: int = 120,
) -> str | None:
    if not DEEPSEEK_API_KEY:
        return None
    url = f"{DEEPSEEK_BASE}/chat/completions"
    body = json.dumps({
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }).encode("utf-8")
    req = Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {DEEPSEEK_API_KEY}")
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if "choices" in data and len(data["choices"]) > 0:
            return data["choices"][0]["message"]["content"]
        print(f"  ⚠️ DeepSeek 返回异常: {data.get('error', data)}")
        return None
    except (HTTPError, URLError, json.JSONDecodeError, OSError) as e:
        print(f"  ❌ DeepSeek API 调用失败: {e}")
        return None

# ---------------------------------------------------------------------------
# 提示词
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """你是 Daily English 的内容创作者，在微信公众号上写外企工作场景英语内容。

## 核心原则：写得像人，不像 AI
你的读者是正在外企或想去外企的中国人。他们刷到你的文章时，应该感觉像刷到一个有经验的同事在分享亲身经历，而不是翻开了一本语法书。

**绝对不要做的事：**
- 不要用固定模版结构（不要每篇都写"场景介绍→核心词汇→对话→解析→小贴士→练习"）
- 不要用 emoji 做章节编号（不要写 📌 🗣️ 💬 📝 🌟 💪）
- 不要写"核心词汇"这种像教科书的标题
- 不要写成说明文档风格

**应该做的事：**
- 每篇文章结构都不一样。有时候重点讲一个故事，有时候侧重几个关键表达，有时候分享一个翻车经历
- 开头写一个具体的场景或小故事，让读者立刻产生共鸣
- 中间自然地引出 2-3 个最实用的英文表达，不要列清单
- 结尾给一个简单可做的行动建议
- 段落要短小精悍：手机上每段不超过 3-4 行，长段落必须拆分。对话单独用引用块或短段落呈现
- 最后增加三个板块：常用单词、常用句型、小练习（见下方新增板块说明），让内容更有深度和实用性
- 总篇幅 800-1200 字，比之前更充实

## 语气参考
- 像你朋友在咖啡厅跟你聊天："上周我开会就翻车了..."
- 语言口语化：多用"其实"、"说白了"、"你会发现"、"说实话"这种自然衔接
- 适当自嘲：承认自己曾经也犯过错
- 英文部分要地道，但不追求难词，用外企真正在用的
- 中文不要翻译腔，用中国人日常说话的方式写

## 内容结构建议（仅供参考，每篇灵活调整）

你可以自由组合这些元素，但不必全用：

### 开头（必写，4-6句话）
一个具体的场景画面，要有"现场感"。包括：
- 时间/地点/环境细节（比如"下午两点，会议室空调开得很足"）
- 人物的动作或语气（比如"她犹豫了一下才开口"、"他苦笑了一下"）
- 读者的心理活动或微妙氛围（比如"你心里咯噔一下"）
让读者 3 秒内产生"这说的就是我"的代入感。例如：
"早上 9:25，你刚倒完咖啡坐下来，PM 就在群里发了一条 'Standup in 5 mins'。你心里咯噔一下——昨天代码还没跑通，今天要怎么说？"

### 中间（主体）
自然地展开以下内容，不要用标题分隔：

- **关键词/表达**：挑 2-3 个最实用的表达，每个要挖深三层：
  1. 字面含义 —— 这句话/这个词最直接的意思和用法
  2. 语气潜台词 —— 在什么场景说、说出来是什么感觉、对方会怎么理解、跟中文类似表达的区别
  3. 进阶用法 —— 相关衍生表达、常见搭配、容易被忽略的细节
  每个表达展开 3-5 句分析，不要只写一句话就过。不要写 7-8 个，读者记不住
- **场景对话**：写一段 4-6 轮的简短对话，最好有戏剧冲突或常见困惑。可以穿插在讲解中
- **常见误区**：这个场景下中国人容易说错的表达，或者文化差异导致的误解
- **个人经验**：可以编一些"我朋友/前同事"的经历，增加真实感

### 结尾（必写，2-4句话）
- 一句简单的练习建议
- 一句互动引导（不要生硬）

### 📖 今天学到的词（新增板块，必写）
标题用「📖 今天学到的词」，整理 3-5 个本课最有用的常用单词。
每个单词格式：
- 单词（标注词性）
- 中文释义
- 一个地道例句（结合外企真实工作场景，自然嵌入）

### 🔧 今天能用的句子（新增板块，必写）
标题用「🔧 今天能用的句子」，整理 2-3 个本课最实用的句型/连接词/常用语。
每个句型格式：
- 句型/表达
- 中文说明
- 一个地道例句

### ✍️ 小练习（新增板块，必写）
标题用「✍️ 小练习」，1-2 句话。结合读者的实际工作场景布置一个小任务，让读者在留言区写一两句话。
例如："你最近一次跟老板 1:1 是什么时候？试着用今天学的 move on 写一句话发在留言区吧。"

## 输出格式
- 用 # 加英文标题开头，例如 "# Morning Standup Meeting"
- 正文用自然的分段，偶尔用 ## 区分大段
- 英文关键词用 **加粗** 标出
- 三个新增板块（📖 今天学到的词 / 🔧 今天能用的句子 / ✍️ 小练习）用 ## 分隔，标题用 ###"""


def build_prompt(scenario: dict[str, str]) -> list[dict[str, str]]:
    user_msg = (
        f"请为微信公众号写一篇\"{scenario['zh']}\"场景的英语学习文章。\n\n"
        f"场景说明：{scenario['desc']}\n\n"
        f"写作要求：\n"
        f"1. 写得像真人，不要像 AI 生成的模版内容\n"
        f"2. 开头用一个小故事或具体画面抓住读者，让人有代入感\n"
        f"3. 正文自然地融入 2-3 个最实用的英文表达，不要列清单\n"
        f"4. 穿插一个简短的真实对话场景（4-6 轮）\n"
        f"5. 英文地道，是外企真实在用的说法\n"
        f"6. 中文用口语化方式写，像朋友在聊天\n"
        f"7. 总字数 800-1200 字，内容更充实，但依然精炼"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]

# ---------------------------------------------------------------------------
# 后处理
# ---------------------------------------------------------------------------

def _extract_title(md_text: str) -> str:
    for line in md_text.split("\n"):
        m = re.match(r"^#\s+(.+)$", line.strip())
        if m:
            return m.group(1).strip()
    return ""


def _generate_filename(title: str) -> str:
    today = datetime.now(timezone(timedelta(hours=8)))
    date_prefix = today.strftime("%Y-%m-%d")
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff_-]", "_", title.lower()).strip("_")
    slug = slug[:50]
    return f"{date_prefix}-{slug}.md"


def _extract_digest(md_text: str, max_len: int = 150) -> str:
    lines = []
    started = False
    for line in md_text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("# "):
            continue
        if not started and not stripped:
            continue
        started = True
        clean = re.sub(r"[#*`\[\]()>|]", "", stripped)
        if clean:
            lines.append(clean)
    plain = " ".join(lines)
    if len(plain) <= max_len:
        return plain
    return plain[:max_len].rsplit("。", 1)[0] + "。"

# ---------------------------------------------------------------------------
# 场景选择
# ---------------------------------------------------------------------------

def _pick_scenario(used_file: Path | None = None) -> dict[str, str]:
    used: set[int] = set()
    if used_file and used_file.exists():
        try:
            data = json.loads(used_file.read_text(encoding="utf-8"))
            used = set(data.get("used_indices", []))
        except (json.JSONDecodeError, OSError):
            used = set()
    available = [i for i in range(len(WORKPLACE_SCENARIOS)) if i not in used]
    if not available:
        used.clear()
        available = list(range(len(WORKPLACE_SCENARIOS)))
    pick = random.choice(available)
    used.add(pick)
    if used_file:
        used_file.parent.mkdir(parents=True, exist_ok=True)
        used_file.write_text(
            json.dumps({"used_indices": sorted(used)}, ensure_ascii=False),
            encoding="utf-8",
        )
    return WORKPLACE_SCENARIOS[pick]

# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Mock 模式（离线测试用）
# ---------------------------------------------------------------------------

def _generate_mock_content(scenario: dict[str, str]) -> str:
    """不调用 API，生成一个示例内容用于测试排版。"""
    import datetime
    from xml.sax.saxutils import escape
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    return f"""# {escape(scenario['en'])}

## 📌 场景介绍

在{scenario['desc']}的场景中，地道表达会让沟通更顺畅。

## 🗣️ 核心词汇

1. **deadline** — ˈded.laɪn — 截止日期
   > "We need to meet the deadline."

2. **follow up** — 跟进
   > "I'll follow up with the team."

3. **alignment** — 对齐（目标和方向）
   > "We need alignment on this."

4. **action items** — 待办事项
   > "Let's review the action items."

5. **escalate** — 升级（向更高层汇报）
   > "We may need to escalate this issue."

## 💬 对话示例

**Alice**: Morning everyone! Let's get started with the standup. Bob, how's the progress on the API integration?
**Bob**: Good morning! I've wrapped up the authentication module, so it's ready for QA. The documentation is still in progress though.
**Alice**: Got it. Could you share the timeline for the docs?
**Bob**: Sure, I should have it done by EOD tomorrow.
**Alice**: That works. Now, Carol, any blockers on your end?
**Carol**: We're waiting on the design team for the new mockups. I pinged them on Slack but no response yet.
**Alice**: I'll follow up with the design lead after this meeting.

## 📝 用法解析

- **"Could you share the timeline?"** — 比 "Tell me the timeline" 更礼貌，外企常用
- **"I pinged them"** — ping = 发消息提醒，Slack/Teams 时代的常见说法
- **"EOD tomorrow"** — End Of Day tomorrow，外企日程常用缩写

## 🌟 文化小贴士

晨会（Standup）的外企惯例是"三问"：昨天做了什么、今天计划做什么、有什么阻塞。保持发言在 1-2 分钟内，避免现场解决问题，会后私下讨论。

## 💪 今日练习

试着用英文回答今天的 standup 三问，并录下来听自己的表达。

---
*本文为测试示例内容。正式内容由 AI 生成。*
"""


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Daily English — 内容生成器")
    parser.add_argument("--topic", "-t", default="", help="指定场景名称（模糊匹配）")
    parser.add_argument("--list-scenarios", action="store_true", help="列出所有可用场景")
    parser.add_argument("--output", "-o", default="", help="输出路径")
    parser.add_argument("--mock", action="store_true",
                        help="模拟模式：不调用 API，生成示例内容用于测试排版")
    parser.add_argument("--api-timeout", type=int, default=120, help="API 超时秒数")

    args = parser.parse_args()

    if args.list_scenarios:
        print(f"\n📋 可用场景（共 {len(WORKPLACE_SCENARIOS)} 个）:\n")
        for i, sc in enumerate(WORKPLACE_SCENARIOS, 1):
            print(f"  {i:2d}. {sc['zh']:12s} → {sc['en']:30s} ({sc['desc']})")
        return

    if not DEEPSEEK_API_KEY:
        if not args.mock:
            print("❌ 未找到 DEEPSEEK_API_KEY。请在 .env 中配置。")
            print("   获取地址: https://platform.deepseek.com/api_keys")
            sys.exit(1)
        else:
            print("  ℹ️ Mock 模式：跳过 DeepSeek API 调用")

    used_file = PROJECT_DIR / ".scenarios_state.json"
    DRAFT_DIR.mkdir(parents=True, exist_ok=True)

    if args.topic:
        keyword = args.topic.lower()
        matched = [
            sc for sc in WORKPLACE_SCENARIOS
            if keyword in sc["zh"].lower() or keyword in sc["en"].lower()
        ]
        if not matched:
            print(f"❌ 未找到匹配场景: {args.topic}")
            print("   使用 --list-scenarios 查看所有场景")
            sys.exit(1)
        scenario = matched[0]
        if len(matched) > 1:
            print(f"  ℹ️ 找到多个匹配，使用第一个: {scenario['zh']}")
    else:
        scenario = _pick_scenario(used_file)

    print(f"\n📝 正在生成内容...")
    print(f"   场景: {scenario['zh']} ({scenario['en']})")

    if args.mock:
        content = _generate_mock_content(scenario)
    else:
        messages = build_prompt(scenario)
        content = _call_deepseek(messages, timeout=args.api_timeout)

    if not content:
        print("\n❌ 内容生成失败。请检查 API Key 和网络。")
        sys.exit(1)

    title = _extract_title(content)
    if not title:
        title = scenario["en"]
        content = f"# {title}\n\n{content}"

    filename = args.output or _generate_filename(title)
    output_path = Path(filename)
    if not output_path.is_absolute():
        output_path = DRAFT_DIR / output_path.name

    output_path.write_text(content, encoding="utf-8")
    print(f"\n✅ 内容已生成!")
    print(f"   文件: {output_path}")
    print(f"   标题: {title}")

    digest = _extract_digest(content)
    print(f"   摘要: {digest[:80]}...")
    print(f"\n🚀 下一步: 用 publish.py 发布")
    print(f"   python3 scripts/publish.py \"{output_path}\"")


if __name__ == "__main__":
    main()
