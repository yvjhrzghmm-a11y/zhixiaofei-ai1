import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, timedelta, datetime
import re

from database import (
    init_db,
    add_expense,
    get_expenses,
    delete_expense,
    export_expenses,
    import_expenses,
    clear_all_expenses
)

from ai import generate_consumption_advice as local_consumption_advice
from modules.ai_service import (
    is_ai_available,
    ai_parse_transactions,
    ai_generate_insight_structured,
    ai_answer_question,
    ai_purchase_decision
)

def render_ai_response(title, content, icon="🤖", color="#4C78A8"):
    """
    统一的 AI 回答卡片：有标题、有边框、有背景色，和普通内容明显区分。
    """
    st.markdown(
        f"""
<div style="
    display: flex;
    align-items: center;
    gap: 8px;
    background: {color};
    color: white;
    padding: 10px 16px;
    border-radius: 10px 10px 0 0;
    font-weight: 700;
    font-size: 15px;
    letter-spacing: 0.3px;
    margin-top: 12px;
">
    <span style="font-size: 18px;">{icon}</span>
    <span>{title}</span>
</div>
""",
        unsafe_allow_html=True
    )

    with st.container(border=True):
        st.markdown(content)

# =========================
# 页面设置
# =========================

st.set_page_config(
    page_title="知消费 AI",
    page_icon="💡",
    layout="wide"
)

init_db()
from datetime import datetime

if "qa_history" not in st.session_state:
    st.session_state.qa_history = []

if "decision_history" not in st.session_state:
    st.session_state.decision_history = []
if "monthly_budget" not in st.session_state:
    st.session_state.monthly_budget = 2000.0

if "saving_target" not in st.session_state:
    st.session_state.saving_target = 300
if "profile_grade" not in st.session_state:
    st.session_state.profile_grade = "大二"

if "profile_allowance" not in st.session_state:
    st.session_state.profile_allowance = 2000

if "profile_income" not in st.session_state:
    st.session_state.profile_income = "父母给生活费"

if "profile_part_time" not in st.session_state:
    st.session_state.profile_part_time = "没有兼职"

if "profile_status" not in st.session_state:
    st.session_state.profile_status = "正常上课"

if "profile_goal" not in st.session_state:
    st.session_state.profile_goal = "控制非必要消费，每月存 300"

if "qa_history" not in st.session_state:
    st.session_state.qa_history = []

if "decision_history" not in st.session_state:
    st.session_state.decision_history = []

# =========================
# 通用工具
# =========================

def load_expenses_df():
    records = get_expenses()
    if not records:
        return pd.DataFrame(columns=["id", "date", "amount", "category", "note"])

    df = pd.DataFrame(
        records,
        columns=["id", "date", "amount", "category", "note"]
    )

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)

    return df


def get_month_df(df, month_str=None):
    if month_str is None:
        month_str = date.today().strftime("%Y-%m")

    if df.empty:
        return df

    return df[df["date"].dt.strftime("%Y-%m") == month_str].copy()


def parse_natural_language(text):
    """本地规则版自然语言识别，作为 AI 兜底。"""
    amount_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:元|块|块钱)?", text)

    if not amount_match:
        return None

    amount = float(amount_match.group(1))

    if "退款" in text:
        amount = -amount

    category = "其他"

    if any(w in text for w in ["饭", "吃", "餐", "外卖", "食堂"]):
        category = "餐饮"
    elif any(w in text for w in ["奶茶", "咖啡", "饮料", "零食"]):
        category = "饮品零食"
    elif any(w in text for w in ["地铁", "公交", "打车", "出租", "交通"]):
        category = "交通"
    elif any(w in text for w in ["电影", "游戏", "娱乐", "唱歌"]):
        category = "娱乐"
    elif any(w in text for w in ["书", "教材", "课程", "学习"]):
        category = "学习"
    elif any(w in text for w in ["购物", "衣服", "鞋", "买"]):
        category = "购物"

    expense_date = date.today()
    if "昨天" in text:
        expense_date = date.today() - timedelta(days=1)

    return amount, category, expense_date, text


# =========================
# 模块一：我的消费
# =========================

def render_my_expenses():
    st.header("📒 我的消费")

    df = load_expenses_df()
    df_month = get_month_df(df)
    monthly_budget = st.session_state.get("monthly_budget", 2000.0)

    total = df_month["amount"].sum() if not df_month.empty else 0.0
    count = len(df_month)
    remaining = monthly_budget - total
    usage_rate = total / monthly_budget if monthly_budget > 0 else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("💰 本月消费", f"¥{total:.2f}")
    c2.metric("💵 剩余预算", f"¥{remaining:.2f}")
    c3.metric("📊 预算使用率", f"{usage_rate * 100:.1f}%")
    c4.metric("🧾 消费笔数", f"{count} 笔")

    st.divider()

    # ---- 智能记录 ----
    st.subheader("🤖 AI 智能记录（当前为本地识别，后续接入大模型）")

    user_text = st.text_input(
        "直接告诉我你花了什么",
        placeholder="例如：今天午饭18元，昨天买奶茶16元",
        key="nl_input"
    )

    if user_text:
        if is_ai_available():
            with st.spinner("AI 正在识别…"):
                transactions = ai_parse_transactions(user_text)
        else:
            parsed = parse_natural_language(user_text)
            transactions = []
            if parsed:
                amount, category, expense_date, note = parsed
                transactions.append({
                    "date": expense_date.isoformat(),
                    "amount": amount,
                    "category": category,
                    "description": note,
                    "need_confirm": False
                })

        if not transactions:
            st.warning("没有识别到有效消费，例如：今天午饭18元")
        else:
            st.success(f"识别到 {len(transactions)} 笔消费，请确认：")

            edited = []
            for i, t in enumerate(transactions):
                with st.expander(
                    f"记录 {i+1}：{t['description'] or t['category']}",
                    expanded=True
                ):
                    c1, c2, c3 = st.columns(3)

                    new_date = c1.date_input(
                        "日期",
                        value=pd.to_datetime(t["date"]).date(),
                        key=f"nl_date_{i}"
                    )

                    new_amount = c2.number_input(
                        "金额",
                        value=float(t["amount"]),
                        step=1.0,
                        key=f"nl_amount_{i}"
                    )

                    categories = [
                        "餐饮", "饮品零食", "交通", "购物",
                        "娱乐", "社交", "学习", "日用品", "其他"
                    ]

                    new_category = c3.selectbox(
                        "类别",
                        categories,
                        index=categories.index(t["category"])
                        if t["category"] in categories else 8,
                        key=f"nl_category_{i}"
                    )

                    new_desc = st.text_input(
                        "备注",
                        value=t["description"],
                        key=f"nl_desc_{i}"
                    )

                    edited.append({
                        "date": new_date.isoformat(),
                        "amount": new_amount,
                        "category": new_category,
                        "description": new_desc
                    })

            if st.button("💾 确认保存全部", key="save_all_nl"):
                for t in edited:
                    add_expense(
                        t["date"],
                        t["amount"],
                        t["category"],
                        t["description"]
                    )
                st.success(f"已保存 {len(edited)} 笔消费！")
                st.rerun()

    st.divider()

    # ---- 手动记录 ----
    st.subheader("📝 手动记录一笔消费")

    with st.form("manual_expense_form"):
        expense_date = st.date_input("消费日期", value=date.today())
        manual_amount = st.number_input("消费金额（元）", min_value=0.0, step=1.0)
        manual_category = st.selectbox(
            "消费类别",
            ["餐饮", "饮品零食", "交通", "购物", "娱乐", "社交", "学习", "日用品", "其他"]
        )
        note = st.text_input("备注", placeholder="例如：午饭、奶茶、购买教材")
        submitted = st.form_submit_button("添加消费")

        if submitted:
            if manual_amount <= 0:
                st.error("消费金额必须大于 0 元。")
            else:
                add_expense(
                    expense_date.isoformat(),
                    manual_amount,
                    manual_category,
                    note
                )
                st.success("消费记录添加成功！")
                st.rerun()

    st.divider()

    # ---- 消费记录 ----
    st.subheader("📋 我的消费记录")

    if not df.empty:
        display_df = df.copy()
        display_df["日期"] = display_df["date"].dt.date
        display_df = display_df.rename(
            columns={"amount": "金额", "category": "类别", "note": "备注"}
        )

        st.dataframe(
            display_df[["日期", "金额", "类别", "备注"]],
            use_container_width=True,
            hide_index=True
        )

        st.subheader("🗑️ 删除消费记录")

        options = {
            f'ID {row["id"]} | {row["date"].date()} | {row["category"]} | ¥{row["amount"]:.2f}':
            row["id"]
            for _, row in df.iterrows()
        }

        selected = st.selectbox(
            "选择需要删除的记录",
            list(options.keys()),
            key="delete_select"
        )

        if st.button("删除选中记录", key="delete_one"):
            delete_expense(options[selected])
            st.success("记录已删除。")
            st.rerun()
    else:
        st.info("目前还没有消费记录。")

    st.divider()

    # ---- 数据管理 ----
    st.subheader("🔒 我的数据")
    st.caption(
        "你的消费数据默认保存在本地 SQLite，不需要注册账号。"
        "你可以随时导出、恢复或删除自己的数据。"
    )

    st.markdown("### 📤 导出我的数据")
    df_export = export_expenses()
    csv_data = df_export.to_csv(index=False, encoding="utf-8-sig")

    st.download_button(
        label="📤 导出我的消费数据",
        data=csv_data,
        file_name="我的消费数据.csv",
        mime="text/csv",
        key="download_csv"
    )

    st.markdown("### 📥 导入历史数据")
    uploaded_file = st.file_uploader(
        "选择之前导出的消费数据 CSV 文件",
        type=["csv"],
        key="upload_csv"
    )

    if uploaded_file is not None:
        try:
            df_import = pd.read_csv(uploaded_file, encoding="utf-8-sig")
            st.write("检测到以下数据：")
            st.dataframe(df_import, use_container_width=True)

            if st.button("📥 确认导入这些数据", key="confirm_import"):
                import_expenses(df_import)
                st.success(f"成功导入 {len(df_import)} 条消费记录！")
                st.rerun()
        except Exception as e:
            st.error(f"导入失败：{e}")

    st.markdown("### 🗑️ 删除我的数据")
    st.warning(
        "删除后，所有消费记录都会从本地数据库中清除。"
        "如果需要保留数据，请先导出备份。"
    )

    if st.button("🗑️ 删除全部消费数据", type="secondary", key="delete_all_btn"):
        st.session_state["confirm_delete"] = True

    if st.session_state.get("confirm_delete", False):
        st.error("⚠️ 确定要删除全部消费数据吗？此操作无法撤销。")
        c1, c2 = st.columns(2)

        with c1:
            if st.button("确定删除", type="primary", key="confirm_delete_yes"):
                clear_all_expenses()
                st.session_state["confirm_delete"] = False
                st.success("所有消费数据已删除。")
                st.rerun()

        with c2:
            if st.button("取消", key="confirm_delete_no"):
                st.session_state["confirm_delete"] = False
                st.rerun()


# =========================
# 模块二：消费分析
# =========================

def render_analysis():
    st.header("📊 消费分析")

    df = load_expenses_df()

    if df.empty:
        st.info("还没有消费数据，请先记录消费。")
        return

    df_month = get_month_df(df)
    monthly_budget = st.session_state.get("monthly_budget", 2000.0)
    today = date.today()

    period = st.selectbox(
        "选择周期",
        ["本月", "近7天", "近30天", "全部"],
        key="period_select"
    )

    if period == "本月":
        filtered = df_month
    elif period == "近7天":
        start = today - timedelta(days=6)
        filtered = df[(df["date"].dt.date >= start) & (df["date"].dt.date <= today)]
    elif period == "近30天":
        start = today - timedelta(days=29)
        filtered = df[(df["date"].dt.date >= start) & (df["date"].dt.date <= today)]
    else:
        filtered = df

    if filtered.empty:
        st.info("该周期内没有消费记录。")
        return

    total = filtered["amount"].sum()
    count = len(filtered)
    st.metric("周期总支出", f"¥{total:.2f}", f"{count} 笔")

    # ---- 趋势图（补全日期 + 滑动平均） ----
    st.subheader("📈 消费趋势")

    daily = (
        filtered
        .groupby(filtered["date"].dt.date)["amount"]
        .sum()
        .reset_index()
    )
    daily.columns = ["日期", "消费金额"]

    if not daily.empty:
        min_date = daily["日期"].min()
        max_date = daily["日期"].max()

        all_dates = pd.date_range(start=min_date, end=max_date, freq="D").date
        daily_full = pd.DataFrame({"日期": all_dates})
        daily_full = daily_full.merge(daily, on="日期", how="left").fillna(0)
        daily_full["7日滑动平均"] = (
            daily_full["消费金额"].rolling(7, min_periods=1).mean()
        )

        fig = go.Figure()
        fig.add_bar(
            x=daily_full["日期"],
            y=daily_full["消费金额"],
            name="每日消费",
            marker_color="#4C78A8"
        )
        fig.add_trace(
            go.Scatter(
                x=daily_full["日期"],
                y=daily_full["7日滑动平均"],
                mode="lines+markers",
                name="7日滑动平均",
                line=dict(color="#F58518", width=3)
            )
        )
        fig.update_layout(
            xaxis_title="日期",
            yaxis_title="消费金额（元）",
            hovermode="x unified"
        )
        st.plotly_chart(fig, use_container_width=True)

    # ---- 结构图 ----
    st.subheader("🥧 消费结构")

    category_total = (
        filtered
        .groupby("category")["amount"]
        .sum()
        .reset_index()
        .sort_values("amount", ascending=False)
    )
    category_total.columns = ["消费类别", "消费金额"]

    fig_pie = px.pie(
        category_total,
        names="消费类别",
        values="消费金额",
        hole=0.4
    )
    fig_pie.update_traces(textposition="inside", textinfo="percent+label")
    st.plotly_chart(fig_pie, use_container_width=True)

    # ---- 预算进度 ----
    st.subheader("💰 预算进度")

    month_total = df_month["amount"].sum() if not df_month.empty else 0.0
    usage_rate = month_total / monthly_budget if monthly_budget > 0 else 0

    st.progress(min(usage_rate, 1.0))

    c1, c2, c3 = st.columns(3)
    c1.metric("本月已消费", f"¥{month_total:.2f}")
    c2.metric("剩余预算", f"¥{monthly_budget - month_total:.2f}")
    c3.metric("预算使用率", f"{usage_rate * 100:.1f}%")

    if usage_rate >= 1:
        st.error("⚠️ 本月消费已经超过预算。")
    elif usage_rate >= 0.8:
        st.warning("⚠️ 本月预算使用已超过 80%，请注意消费。")
    else:
        st.success("✅ 当前消费仍在预算范围内。")

    # ---- 趋势预测 ----
    st.subheader("📈 本月消费趋势预测")

    if not df_month.empty:
        current_expense = df_month["amount"].sum()
        days_passed = today.day
        daily_avg = current_expense / days_passed if days_passed > 0 else 0
        days_in_month = pd.Period(today, freq="M").days_in_month
        predicted = daily_avg * days_in_month

        c1, c2, c3 = st.columns(3)
        c1.metric("日均消费", f"¥{daily_avg:.2f}")
        c2.metric("预计月消费", f"¥{predicted:.2f}")
        c3.metric("当前预算", f"¥{monthly_budget:.2f}")

        if predicted > monthly_budget:
            st.warning(
                f"⚠️ 按目前消费速度，本月预计消费 ¥{predicted:.2f}，可能超过预算。"
            )
        else:
            st.success(
                f"✅ 按目前消费速度，预计本月消费 ¥{predicted:.2f}，暂时不会超过预算。"
            )
    else:
        st.info("本月暂时没有消费记录。")


# =========================
# 模块三：AI 洞察
# =========================

def render_ai_insight():
    st.header("🧠 AI 消费洞察")
    st.write("根据你的消费数据，生成个性化消费分析。")

    df = load_expenses_df()

    if df.empty:
        st.warning("目前还没有消费记录，请先记录一些消费。")
        return

    df_month = get_month_df(df)

    if df_month.empty:
        st.info("本月还没有消费记录，暂时无法生成分析。")
        return

    monthly_budget = st.session_state.get("monthly_budget", 2000.0)
    saving_target = st.session_state.get("saving_target", 300)
    today = date.today()

    total = df_month["amount"].sum()
    count = len(df_month)
    daily_avg = total / today.day if today.day > 0 else 0
    predicted = daily_avg * pd.Period(today, freq="M").days_in_month

    category_total = (
        df_month
        .groupby("category")["amount"]
        .sum()
        .sort_values(ascending=False)
    )

    top_category = category_total.index[0] if not category_total.empty else "无"
    top_amount = category_total.iloc[0] if not category_total.empty else 0
    top_ratio = top_amount / total if total > 0 else 0
    small_count = len(df_month[df_month["amount"] <= 30])
    budget_rate = total / monthly_budget if monthly_budget > 0 else 0

    # 取本月金额最高的 5 笔消费，让 AI 看到"具体花了什么"
    top_expenses = (
        df_month
        .sort_values("amount", ascending=False)
        .head(5)[["category", "amount", "note"]]
        .to_dict(orient="records")
    )
    top_expenses = (
        df_month
        .sort_values("amount", ascending=False)
        .head(5)[["category", "amount", "note"]]
        .to_dict(orient="records")
    )

    summary_data = {
        "period": today.strftime("%Y-%m"),
        "total": round(total, 2),
        "count": count,
        "categories": {
            k: round(float(v), 2) for k, v in category_total.items()
        },
        "top_category": top_category,
        "top_ratio": round(top_ratio, 3),
        "daily_average": round(daily_avg, 2),
        "predicted": round(predicted, 2),
        "budget": monthly_budget,
        "budget_rate": round(budget_rate, 3),
        "small_count": small_count,
        "user_profile": st.session_state.user_profile,
        "top_expenses": top_expenses
    }

    if st.button("✨ 生成我的消费洞察", key="gen_insight"):

        if not is_ai_available():
            st.warning("未配置 AI，暂时无法生成智能洞察。")
        else:
            with st.spinner("AI 正在分析你的消费数据…"):
                structured = ai_generate_insight_structured(summary_data)

            if not structured:
                st.error("AI 分析失败，请稍后重试。")
            else:
                st.subheader("💰 消费健康指数")
                score = int(structured.get("score", 0))
                st.progress(min(score / 100, 1.0))
                st.write(f"当前评分：**{score}/100**")

                st.markdown("### 📌 评分依据")
                for r in structured.get("score_reasons", []):
                    st.write("• " + r)

                st.subheader("🧠 AI消费画像")
                st.info(
                    f"**{structured.get('personality', '')}**\n\n"
                    f"{structured.get('personality_desc', '')}"
                )

                st.subheader("🔍 AI发现")
                st.write(structured.get("discovery", "暂无"))

                st.subheader("💡 AI优化建议")
                for s in structured.get("suggestions", []):
                    st.write("- " + s)

    st.divider()

    st.subheader("💬 AI 消费问答")
    st.caption("基于你的个人消费数据，AI 会直接回答。")

    question = st.text_input("输入你的问题", key="ai_question")

    if st.button("✨ 提问", key="ask_ai_btn") and question:
        if not is_ai_available():
            st.warning("未配置 AI，暂时无法回答。")
        else:
            with st.spinner("AI 正在分析你的问题…"):
                answer = ai_answer_question(question, summary_data)

            st.session_state.qa_history.insert(0, {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "question": question,
                "answer": answer
            })

    # 显示最新一次回答
    if st.session_state.qa_history:
        latest = st.session_state.qa_history[0]
        render_ai_response(
            "AI 回答",
            latest["answer"],
            icon="💬",
            color="#7B5EA7"
        )

    # 历史记录
    if st.session_state.qa_history:
        with st.expander(
            f"📚 历史提问记录（{len(st.session_state.qa_history)} 条）",
            expanded=False
        ):
            for i, item in enumerate(st.session_state.qa_history):
                st.markdown(f"**🕒 {item['time']}**")
                st.markdown(f"🙋 **你问：** {item['question']}")
                st.markdown(f"🤖 **AI：**\n\n{item['answer']}")
                if i < len(st.session_state.qa_history) - 1:
                    st.divider()

            if st.button("🗑️ 清空提问历史", key="clear_qa_history"):
                st.session_state.qa_history = []
                st.rerun()

# =========================
# 模块四：AI 决策
# =========================

def render_ai_decision():
    st.header("🛒 AI 决策")
    st.write(
        "知消费不会只判断你现在买不买得起，"
        "还会考虑购买后是否影响本月剩余生活。"
    )

    df = load_expenses_df()

    if df.empty:
        st.warning("暂无消费数据，请先记录一些消费。")
        return

    df_month = get_month_df(df)

    if df_month.empty:
        st.info("本月暂无消费记录，暂时无法分析。")
        return

    monthly_budget = st.session_state.get("monthly_budget", 2000.0)
    today = date.today()
    total = df_month["amount"].sum()
    remaining_budget = monthly_budget - total

    # ===== 购买决策 =====
    st.subheader("🛍️ 购买决策模拟")

    product_name = st.text_input(
        "想购买什么？",
        placeholder="例如：无线耳机",
        key="product_name"
    )

    product_price = st.number_input(
        "商品价格（元）",
        min_value=0.0,
        value=699.0,
        step=10.0,
        key="product_price"
    )

    necessity = st.selectbox(
        "消费性质",
        ["必要消费", "改善生活", "非必要消费"],
        key="necessity"
    )

    if st.button("✨ 分析购买建议", key="analyze_purchase"):
        basic_categories = ["餐饮", "交通", "日用品"]
        basic_df = df_month[df_month["category"].isin(basic_categories)]
        basic_total = basic_df["amount"].sum()

        days_passed = today.day
        days_left = pd.Period(today, freq="M").days_in_month - days_passed

        daily_basic = basic_total / days_passed if days_passed > 0 else 0
        future_basic = daily_basic * days_left
        safety_buffer = max(future_basic * 0.2, 100)
        remaining_safe = remaining_budget - future_basic - safety_buffer
        after_purchase = remaining_safe - product_price
        top_expenses = (
            df_month
            .sort_values("amount", ascending=False)
            .head(5)[["category", "amount", "note"]]
            .to_dict(orient="records")
        )

        calc_data = {
            "month_total": round(total, 2),
            "budget": monthly_budget,
            "remaining_budget": round(remaining_budget, 2),
            "days_passed": days_passed,
            "days_left": days_left,
            "future_basic_cost": round(future_basic, 2),
            "safety_buffer": round(safety_buffer, 2),
            "remaining_safe": round(remaining_safe, 2),
            "after_purchase": round(after_purchase, 2),
            "user_profile": st.session_state.user_profile,
            "top_expenses": top_expenses
        }

        st.markdown("---")
        st.subheader("🧠 决策数据")

        c1, c2, c3 = st.columns(3)
        c1.metric("当前剩余预算", f"¥{remaining_budget:.2f}")
        c2.metric("未来预计生活成本", f"¥{future_basic:.2f}")
        c3.metric("安全缓冲", f"¥{safety_buffer:.2f}")

        st.markdown(
            f"""
- 真正可自由支配金额：**¥{max(remaining_safe, 0):.2f}**
- 购买后剩余：**¥{after_purchase:.2f}**
- 距离月底还有：**{days_left} 天**
"""
        )

        st.subheader("🎯 AI 建议")

        if is_ai_available():
            with st.spinner("AI 正在分析购买影响…"):
                advice = ai_purchase_decision(
                    product_name=product_name,
                    product_price=product_price,
                    necessity=necessity,
                    calc_data=calc_data
                )

            st.session_state.decision_history.insert(0, {
                "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "product_name": product_name or "未命名商品",
                "price": product_price,
                "necessity": necessity,
                "advice": advice
            })

            render_ai_response(
                "AI 购买建议",
                advice,
                icon="🛒",
                color="#E08A3C"
            )
        else:
            st.warning("未配置 AI，暂时无法给出智能建议。")
            if after_purchase < 0:
                st.error("⚠️ 不建议现在购买，会影响后续生活保障。")
            else:
                st.success("✅ 购买后仍在安全范围内，可以考虑。")

    st.divider()

    # ===== 节省目标模拟 =====
    st.subheader("🎯 节省目标模拟")

    saving_target = st.number_input(
        "你希望下个月节省多少钱？",
        min_value=0,
        step=50,
        key="saving_target_decision"
    )

    if st.button("生成节省方案", key="gen_saving_plan"):
        category_total = (
            df_month
            .groupby("category")["amount"]
            .sum()
            .sort_values(ascending=False)
        )

        possible_save = 0
        saving_plan = []

        for category, amount in category_total.items():
            if category in ["饮品零食", "娱乐", "购物", "社交"]:
                save_amount = amount * 0.3
                possible_save += save_amount
                saving_plan.append((category, save_amount))

        st.markdown("### 📌 优化方案")

        if saving_plan:
            for category, save_amount in saving_plan:
                st.write(f"减少 **{category}**，预计节省：¥{save_amount:.2f}")

            if possible_save >= saving_target:
                st.success(
                    f"✅ 根据你的消费结构，预计可以节省约 ¥{possible_save:.2f}，"
                    f"可以达到你的目标 ¥{saving_target}"
                )
            else:
                st.warning(
                    f"⚠️ 当前消费结构预计只能节省约 ¥{possible_save:.2f}，"
                    f"距离目标 ¥{saving_target} 还需要进一步调整。"
                )
        else:
            st.info("当前没有明显可优化的消费类别。")

    # ===== 历史决策记录 =====
    if st.session_state.decision_history:
        st.divider()
        with st.expander(
            f"📚 历史决策记录（{len(st.session_state.decision_history)} 条）",
            expanded=False
        ):
            for i, item in enumerate(st.session_state.decision_history):
                st.markdown(f"**🕒 {item['time']}**")
                st.markdown(
                    f"🛍️ **商品：** {item['product_name']}　"
                    f"**价格：** ¥{item['price']:.2f}　"
                    f"**性质：** {item['necessity']}"
                )
                st.markdown(f"🤖 **AI 建议：**\n\n{item['advice']}")
                if i < len(st.session_state.decision_history) - 1:
                    st.divider()

            if st.button("🗑️ 清空决策历史", key="clear_decision_history"):
                st.session_state.decision_history = []
                st.rerun()
# =========================
# 页面标题与介绍
# =========================

st.title("💡 知消费 AI")
st.caption("你的大学生智能消费分析与预算决策助手")

st.markdown("## 为什么需要它")
st.markdown("大学生记账难，通常不是因为懒，而是因为：")
st.markdown("- 手动记账太麻烦，坚持不下来")
st.markdown("- 记完了也只看到一串数字，不知道问题在哪")
st.markdown("- 想买贵一点的东西时，只能凭感觉判断\"买不买得起\"")

st.markdown("## 知消费做了什么")
st.markdown("| 功能 | 具体做的事 |")
st.markdown("|---|---|")
st.markdown("| 智能记录 | 自然语言输入，自动识别日期、金额、类别 |")
st.markdown("| 消费洞察 | 结合个人画像，分析消费结构，给出可执行的调整建议 |")
st.markdown("| 购买决策 | 结合剩余预算和未来生活成本，判断这笔消费是否合适 |")

st.divider()


# =========================
# 侧边栏
# =========================

with st.sidebar:
    st.header("⚙️ 设置")

    st.number_input(
        "本月预算（元）",
        min_value=0.0,
        step=100.0,
        key="monthly_budget"
    )

    st.number_input(
        "下月节省目标（元）",
        min_value=0,
        step=50,
        key="saving_target"
    )

    st.divider()
    st.subheader("👤 个人画像")
    st.caption("填写后 AI 分析会结合你的实际情况。")

    st.selectbox(
        "年级",
        ["大一", "大二", "大三", "大四", "研究生"],
        key="profile_grade"
    )

    st.number_input(
        "月生活费（元）",
        min_value=0,
        step=100,
        key="profile_allowance"
    )

    st.selectbox(
        "生活费来源",
        ["父母给生活费", "奖学金/助学金", "兼职/实习", "父母+兼职"],
        key="profile_income"
    )

    st.selectbox(
        "兼职情况",
        ["没有兼职", "有兼职，每月几百", "有兼职，每月上千"],
        key="profile_part_time"
    )

    st.selectbox(
        "当前状态",
        ["正常上课", "考试周", "期末复习", "实习期", "假期"],
        key="profile_status"
    )

    st.text_input(
        "当前主要目标",
        key="profile_goal"
    )

    # 每次渲染都从 session_state 同步到 user_profile
    st.session_state.user_profile = {
        "grade": st.session_state.profile_grade,
        "monthly_allowance": st.session_state.profile_allowance,
        "income_source": st.session_state.profile_income,
        "has_part_time": st.session_state.profile_part_time,
        "current_status": st.session_state.profile_status,
        "main_goal": st.session_state.profile_goal
    }

    st.divider()

    st.caption("🔒 数据默认保存在本地 SQLite，不会自动上传。")

    if is_ai_available():
        st.success("🤖 AI 已连接（智谱 GLM）")
    else:
        st.warning("🤖 AI 未配置（在 .env 里填写 LLM_API_KEY）")

# =========================
# 四个 Tab
# =========================

tab1, tab2, tab3, tab4 = st.tabs(
    [
        "📒 我的消费",
        "📊 消费分析",
        "🧠 AI洞察",
        "🛒 AI决策"
    ]
)

with tab1:
    render_my_expenses()

with tab2:
    render_analysis()

with tab3:
    render_ai_insight()

with tab4:
    render_ai_decision()