import os
import json
import re
from datetime import date, timedelta

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

API_KEY = os.getenv("LLM_API_KEY")
BASE_URL = os.getenv("LLM_BASE_URL")
MODEL = os.getenv("LLM_MODEL")

client = None
if API_KEY:
    client = OpenAI(
        api_key=API_KEY,
        base_url=BASE_URL
    )


def is_ai_available():
    return client is not None


def _call_llm(system_prompt, user_prompt, temperature=0.3, json_mode=True):
    if client is None:
        raise RuntimeError("未配置 LLM_API_KEY，无法调用大模型。")

    kwargs = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": temperature,
    }

    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    response = client.chat.completions.create(**kwargs)

    return response.choices[0].message.content


def _extract_json(text):
    if not text:
        return None

    text = text.strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass

    return None


# =========================
# 1. 自然语言消费识别
# =========================

def ai_parse_transactions(user_text):
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    system_prompt = """
你是一个消费记录结构化助手。用户会用自然语言描述他的消费。
你的任务是把它们拆成一条条结构化消费记录。

严格要求：
1. 只提取用户明确说出的消费，不要编造。
2. 如果用户说的是"打算"、"计划"、"想买"，那不是已发生的消费，不要返回。
3. 如果日期不明确，默认为今天。
4. 如果金额不明确，标记 amount 为 null，并加 "need_confirm": true。
5. 如果出现退款，金额记为负数。
6. 消费类别只能从以下选择：餐饮、饮品零食、交通、购物、娱乐、社交、学习、日用品、其他。
7. 必须返回纯 JSON，格式如下：

{
  "transactions": [
    {
      "date": "YYYY-MM-DD",
      "amount": 18.0,
      "category": "餐饮",
      "description": "午饭",
      "need_confirm": false
    }
  ]
}
"""

    user_prompt = f"""
今天是 {today}，昨天是 {yesterday}。

用户输入：
{user_text}
"""

    try:
        raw = _call_llm(system_prompt, user_prompt)
        data = _extract_json(raw)
        if not data:
            return []

        transactions = data.get("transactions", [])
        result = []

        for item in transactions:
            amount = item.get("amount")
            if amount is None:
                continue

            result.append({
                "date": item.get("date") or today,
                "amount": float(amount),
                "category": item.get("category") or "其他",
                "description": item.get("description") or "",
                "need_confirm": item.get("need_confirm", False)
            })

        return result

    except Exception as e:
        print("AI解析失败：", e)
        return []


# =========================
# 2. AI 消费洞察（结构化）
# =========================

def ai_generate_insight_structured(summary_data):
    system_prompt = """
你是一个面向大学生的消费分析助手。
你会收到三部分信息：
1. summary_data：本月消费汇总（数字）
2. user_profile：用户个人画像（年级、生活费、来源、兼职情况、当前状态、目标）
3. top_expenses：本月金额最高的几笔消费，带备注

你的任务是结合这三部分做分析，不要只盯数字。

严格要求：
1. 只能使用给定数据，不能编造数字。
2. 必须结合 user_profile 解释数字。例如：
   - 大二、靠父母给生活费、没有兼职、娱乐占比高 → 要提醒控制
   - 大四、实习期、有兼职收入、交通费高 → 可能是通勤，属合理
   - 考试周、期末复习、外卖增加 → 属正常，不必苛责
3. 分析时尽量引用 top_expenses 里的具体消费（例如"其中 480 元是游戏充值"），让建议落地。
4. 建议要具体、可执行。不要说"控制消费"、"合理规划"这种空话，要说"把游戏充值设为每月 200 元上限"这种。
5. 语气像朋友，不要说教。
6. 输出严格 JSON，格式如下：

{
  "score": 0-100 的整数,
  "score_reasons": ["结合画像的具体理由1", "理由2", "理由3"],
  "personality": "消费画像，结合画像描述",
  "personality_desc": "2-3 句，必须引用画像信息",
  "discovery": "2-3 句，结合 top_expenses 里的具体消费和当前状态",
  "suggestions": ["结合画像的建议1", "建议2", "建议3"]
}

7. 只返回 JSON，不要输出其他任何内容。
"""

    user_prompt = f"""
用户消费汇总数据：

{json.dumps(summary_data, ensure_ascii=False, indent=2)}

请结合用户画像和具体消费，生成分析。
"""

    try:
        raw = _call_llm(system_prompt, user_prompt, temperature=0.4)
        data = _extract_json(raw)
        if not data:
            return None
        return data
    except Exception as e:
        print("AI结构化分析失败：", e)
        return None


# =========================
# 3. AI 消费问答
# =========================

def ai_answer_question(question, summary_data):
    system_prompt = """
你是一个基于用户个人消费数据回答问题的助手。

你会收到：
1. 用户的消费汇总数据（数字）
2. 用户的个人画像（年级、生活费、来源、兼职情况、当前状态、目标）
3. 用户本月金额最高的几笔消费，带备注

要求：
1. 回答问题时，要结合用户画像和当前状态。例如：
   - "我现在考试周" → 外卖增加可能正常
   - "我大四实习" → 交通、正装、咖啡等支出是合理的
2. 如果问的是"为什么"，尽量从 top_expenses 的备注里找线索。
3. 如果问题所需的数据不在汇总里，明确说"当前数据不足以回答这个问题"，不要编造。
4. 回答要简短、自然，用中文 Markdown 格式。
5. 不要输出 JSON，不要输出代码块，直接输出人看的文字。
6. 不要用"亲"、"建议您"这种客服语气，像朋友说话。
"""

    user_prompt = f"""
用户问题：
{question}

用户数据：
{json.dumps(summary_data, ensure_ascii=False, indent=2)}

请基于这些数据回答。
"""

    try:
        raw = _call_llm(
            system_prompt,
            user_prompt,
            temperature=0.4,
            json_mode=False
        )
        return raw
    except Exception as e:
        return f"AI 回答失败：{e}"


# =========================
# 4. AI 购买决策
# =========================

def ai_purchase_decision(product_name, product_price, necessity, calc_data):
    system_prompt = """
你是一个面向大学生的消费决策助手。
用户正在考虑是否购买一件商品，Python 已经根据他的真实消费数据算好了预算情况。
你还会收到用户的个人画像和最近的大额消费，用来判断这笔购买是否合适。

严格要求：
1. 只能使用给定的计算结果，不能编造数字。
2. 不要说教，不要用"亲"、"建议您"这类客服语气。
3. 直接输出中文 Markdown，不要输出 JSON。
4. 要结合用户画像。例如：
   - 大四实习，买正装 → 可能合理
   - 大二无兼职，买高价数码 → 需要谨慎
5. 结构如下：

### 结论

一句话结论（可以买 / 谨慎考虑 / 不建议现在买）。

### 理由

- 理由1，引用具体数字
- 理由2，引用具体数字
- 理由3，结合画像

### 替代方案

- 方案1
- 方案2

### 最后

一句话说明这只是参考，最终决定权在用户。
"""

    user_prompt = f"""
用户想购买：{product_name or "未命名商品"}
价格：¥{product_price}
消费性质：{necessity}

Python 根据他的真实消费数据计算的结果：
{json.dumps(calc_data, ensure_ascii=False, indent=2)}

请给出购买建议。
"""

    try:
        raw = _call_llm(
            system_prompt,
            user_prompt,
            temperature=0.5,
            json_mode=False
        )
        return raw
    except Exception as e:
        return f"AI 决策分析失败：{e}"