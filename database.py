import sqlite3
from pathlib import Path
import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "expenses.db"


def get_connection():
    return sqlite3.connect(DB_PATH)


def init_db():
    """创建消费记录表"""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                note TEXT
            )
        """)


def add_expense(date, amount, category, note):
    """添加消费记录"""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO expenses (date, amount, category, note)
            VALUES (?, ?, ?, ?)
            """,
            (date, amount, category, note)
        )


def get_expenses():
    """读取消费记录"""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT id, date, amount, category, note
            FROM expenses
            ORDER BY date DESC, id DESC
        """).fetchall()

    return rows


def delete_expense(expense_id):
    """删除单笔消费"""
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM expenses WHERE id = ?",
            (expense_id,)
        )


def export_expenses():
    """导出全部消费记录"""

    rows = get_expenses()

    df = pd.DataFrame(
        rows,
        columns=[
            "id",
            "date",
            "amount",
            "category",
            "note"
        ]
    )

    # 去掉内部 ID
    df = df.drop(columns=["id"])

    # 转换成用户能看懂的中文字段
    df = df.rename(columns={
        "date": "消费日期",
        "amount": "金额（元）",
        "category": "消费类别",
        "note": "消费备注"
    })

    return df


def clear_all_expenses():
    """删除全部消费记录"""

    with get_connection() as conn:
        conn.execute("DELETE FROM expenses")


def import_expenses(df):
    """从 CSV 数据导入消费记录"""

    # 将中文字段转换成数据库字段
    column_mapping = {
        "消费日期": "date",
        "金额（元）": "amount",
        "消费类别": "category",
        "消费备注": "note"
    }

    df = df.rename(columns=column_mapping)

    required_columns = [
        "date",
        "amount",
        "category",
        "note"
    ]

    # 检查文件格式
    if not all(
        column in df.columns
        for column in required_columns
    ):
        raise ValueError(
            "文件格式不正确，请使用“知消费 AI”导出的消费数据文件。"
        )

    # 只保留需要的数据
    df = df[required_columns].copy()

    # 金额转换
    df["amount"] = pd.to_numeric(
        df["amount"],
        errors="coerce"
    )

    # 删除无效数据
    df = df.dropna(
        subset=[
            "date",
            "amount",
            "category"
        ]
    )

    # 写入数据库
    with get_connection() as conn:

        for _, row in df.iterrows():

            conn.execute(
                """
                INSERT INTO expenses
                (date, amount, category, note)
                VALUES (?, ?, ?, ?)
                """,
                (
                    str(row["date"]),
                    float(row["amount"]),
                    str(row["category"]),
                    str(row["note"])
                    if pd.notna(row["note"])
                    else ""
                )
            )
def get_expense_count():
    """返回当前消费记录总数，用于判断数据是否足够分析。"""
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()
    return row[0] if row else 0


def get_expenses_by_month(year_month: str):
    """
    按月份筛选消费记录，例如 year_month="2026-10"。
    返回结构同 get_expenses()。
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, date, amount, category, note
            FROM expenses
            WHERE substr(date, 1, 7) = ?
            ORDER BY date DESC, id DESC
            """,
            (year_month,)
        ).fetchall()
    return rows