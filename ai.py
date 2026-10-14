def generate_consumption_advice(
    total,
    budget,
    category_data,
    saving_goal
):

    if category_data is None or len(category_data) == 0:
        top_category = "暂无"
        top_amount = 0.0
    else:
        top_category = category_data.index[0]
        top_amount = float(category_data.iloc[0])

    remaining = budget - total

    if remaining < 0:
        risk = "高风险"
        advice = "当前消费已经超过预算，建议立即减少非必要消费。"

    elif remaining < budget * 0.2:
        risk = "中风险"
        advice = "当前预算剩余较少，建议控制娱乐和冲动消费。"

    else:
        risk = "低风险"
        advice = "当前消费状态较稳定，可以继续保持。"

    if top_category in [
        "娱乐",
        "购物",
        "饮品零食",
        "社交"
    ]:
        personality = "享受型消费者"
    else:
        personality = "理性规划型消费者"

    report = f"""
## 🧠 AI消费分析报告（本地规则版）

### 消费画像
你的消费类型：**{personality}**

---

### 当前状态
- 本月消费：¥{total:.2f}
- 剩余预算：¥{remaining:.2f}
- 消费风险等级：**{risk}**

---

### 消费重点分析
- 主要消费类别：**{top_category}**
- 金额：¥{top_amount:.2f}

---

### 🎯 目标分析
你的存钱目标：¥{saving_goal}

---

### 💡 建议
{advice}

建议你下一阶段：
1. 关注「{top_category}」支出变化
2. 每周检查一次消费记录
3. 根据目标调整非必要消费
"""

    return report