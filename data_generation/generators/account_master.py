"""
account_master テーブルのデータ生成

Messaging SaaS の主体テーブル。全ての分析の主語となるアカウントマスタ。
"""
import random
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from faker import Faker


# 固定シードで再現性を確保
SEED = 42
random.seed(SEED)
fake = Faker("ja_JP")
Faker.seed(SEED)


# 業種マスタ（20アカウントに割り当てる候補）
INDUSTRIES = [
    "retail",
    "food_and_beverage",
    "beauty",
    "education",
    "finance",
    "healthcare",
    "real_estate",
    "entertainment",
]

# プラン種別（意図的に表記を揺らす）
# 同じ意味でも、上流データでは表記が揺れているケースを再現
PLAN_TYPES = ["free", "light", "standard", "STANDARD", "Standard"]

# 地域
REGIONS = ["東京", "大阪", "名古屋", "福岡", "札幌", "仙台"]

# ステータス
STATUSES = ["active", "active", "active", "active", "suspended", "closed"]
# activeを多めにして、現実の分布に近づける


def generate_account_id() -> str:
    """Messaging SaaS由来の上流ID。Uから始まる32文字のhex風"""
    return "U" + "".join(random.choices("0123456789abcdef", k=32))


def generate_account_seq(index: int) -> str:
    """内部ID。DWHが発番する連番風"""
    return f"acct_{index:06d}"


def generate_handle(account_name: str) -> str:
    """表示用の短い識別子。account_name から簡易生成"""
    base = "".join(c for c in account_name.lower() if c.isalnum())[:10]
    suffix = random.randint(100, 999)
    return f"{base}-{suffix}"


def generate():
    """20個のアカウントマスタレコードを生成してCSV出力"""
    records = []
    # 各アカウントの作成時期は過去1〜2年の範囲でばらける
    now = datetime(2026, 4, 15)

    for i in range(20):
        account_name = fake.company()
        days_ago = random.randint(30, 730)  # 1ヶ月〜2年前
        created_at = now - timedelta(days=days_ago)

        # 一部レコード（15%）の industry を NULL にする
        # 業種不明のアカウントが現実には存在する
        industry = None if random.random() < 0.15 else random.choice(INDUSTRIES)

        # プラン種別は意図的に表記が揺れる（上流の典型的汚れ）
        plan_type = random.choice(PLAN_TYPES)

        status = random.choice(STATUSES)

        # 整合性問題の仕込み：
        # status が closed でも、as_of_date が最近のレコードを混ぜる
        # 本来は closed なら as_of_date はクローズ時点で固定されるべき
        as_of_date = now.date()

        record = {
            "account_id": generate_account_id(),
            "account_seq": generate_account_seq(i + 1),
            "handle": generate_handle(account_name),
            "account_name": account_name,
            "industry": industry,
            "plan_type": plan_type,
            "region": random.choice(REGIONS),
            "created_at": created_at,
            "status": status,
            "as_of_date": as_of_date,
        }
        records.append(record)

    df = pd.DataFrame(records)

    # 出力
    output_path = Path(__file__).parent.parent / "output" / "account_master.csv"
    df.to_csv(output_path, index=False)
    print(f"Generated {len(df)} records -> {output_path}")

    return df


if __name__ == "__main__":
    generate()