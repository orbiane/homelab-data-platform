"""
subscription_log テーブルのデータ生成

Messaging SaaS への友だち追加イベントの生ログ。アカウントライフサイクルの起点（獲得）。
"""
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd


# 固定シード（account_master.py と別シードにして独立性確保）
SEED = 43
random.seed(SEED)
np.random.seed(SEED)


# 獲得経路（実務では QR コードと検索が大半）
ROUTES = ["qr_code", "search", "ad", "link_share", "other"]
ROUTE_WEIGHTS = [0.40, 0.30, 0.15, 0.10, 0.05]

# route ごとの referrer 候補（流入元の詳細）
REFERRERS = {
    "qr_code": ["store_front", "receipt", "poster", "business_card", "event_booth"],
    "search": ["line_app_search", "official_directory"],
    "ad": ["line_ads", "yahoo_ads", "google_ads", "facebook_ads"],
    "link_share": ["sns_share", "email_share", "messaging_app"],
    "other": ["unknown", "import_bulk"],
}

# データ生成期間（過去6ヶ月）
END_DATE = datetime(2026, 4, 15)
START_DATE = END_DATE - timedelta(days=180)

# 総レコード数
TOTAL_RECORDS = 2000


def generate_contact_id(introduce_format_glitch: bool = False) -> str:
    """ユーザーID生成。意図的に形式揺れを混ぜる"""
    hex_part = "".join(random.choices("0123456789abcdef", k=32))
    if introduce_format_glitch:
        # 一部レコードで U プレフィックスを欠落させる（上流データの典型的揺れ）
        return hex_part
    return "U" + hex_part


def load_account_ids() -> list[str]:
    """account_master.csv から account_id 一覧を読み込む"""
    master_path = Path(__file__).parent.parent / "output" / "account_master.csv"
    df = pd.read_csv(master_path)
    return df["account_id"].tolist()


def generate():
    """約2,000件の友だち追加ログを生成"""
    account_ids = load_account_ids()

    # account_id の獲得数分布を pareto 風に偏らせる
    # 上位3アカウントに獲得が集中（実務の人気アカウント vs 低活動アカウント の差を再現）
    n_bots = len(account_ids)
    weights = np.array([10.0] * 3 + [2.0] * 5 + [0.5] * (n_bots - 8))
    weights = weights / weights.sum()

    records = []
    period_seconds = int((END_DATE - START_DATE).total_seconds())

    for _ in range(TOTAL_RECORDS):
        account_id = np.random.choice(account_ids, p=weights)

        # added_at を期間内のランダムな時刻に
        offset_seconds = random.randint(0, period_seconds)
        added_at = START_DATE + timedelta(seconds=offset_seconds)

        # dt の決定（基本は added_at と同日、5%だけ意図的にズラす）
        if random.random() < 0.05:
            # 深夜帯イベントが翌日のdtに分類されたパターンを再現
            dt = (added_at + timedelta(days=1)).date()
        else:
            dt = added_at.date()

        # contact_id の形式揺れ（10%の確率で U プレフィックス欠落）
        format_glitch = random.random() < 0.10
        contact_id = generate_contact_id(introduce_format_glitch=format_glitch)

        route = np.random.choice(ROUTES, p=ROUTE_WEIGHTS)
        referrer = random.choice(REFERRERS[route])

        record = {
            "event_id": str(uuid.uuid4()),
            "account_id": account_id,
            "contact_id": contact_id,
            "added_at": added_at,
            "dt": dt,
            "route": route,
            "referrer": referrer,
        }
        records.append(record)

    # 重複レコードの仕込み：
    # 既存レコードから30件を選んで複製。同じ (account_id, contact_id) が複数存在する状態を作る
    # 再追加（ブロック後の再フォロー）か重複登録かは staging 層での判断課題
    duplicates = random.sample(records, 30)
    for dup in duplicates:
        # event_id だけ新しくして残りはそのまま
        new_dup = dup.copy()
        new_dup["event_id"] = str(uuid.uuid4())
        # added_at は少しズラす（数日後の再追加風）
        new_dup["added_at"] = dup["added_at"] + timedelta(days=random.randint(1, 30))
        new_dup["dt"] = new_dup["added_at"].date()
        records.append(new_dup)

    # 極端な added_at の仕込み：
    # 5件だけ、未来日付や超古い日付を混ぜる（時間の品質問題）
    for _ in range(3):
        # 未来日付
        rec = random.choice(records).copy()
        rec["event_id"] = str(uuid.uuid4())
        rec["added_at"] = datetime(2030, 1, 1) + timedelta(days=random.randint(0, 365))
        rec["dt"] = rec["added_at"].date()
        records.append(rec)
    for _ in range(2):
        # 超古い日付（アカウント開設前のイベント）
        rec = random.choice(records).copy()
        rec["event_id"] = str(uuid.uuid4())
        rec["added_at"] = datetime(2010, 1, 1) + timedelta(days=random.randint(0, 365))
        rec["dt"] = rec["added_at"].date()
        records.append(rec)

    # シャッフル（時系列順を崩す。実務の生ログに近い状態に）
    random.shuffle(records)

    df = pd.DataFrame(records)

    output_path = Path(__file__).parent.parent / "output" / "subscription_log.csv"
    df.to_csv(output_path, index=False)
    print(f"Generated {len(df)} records -> {output_path}")

    # サマリ出力
    print(f"  - Unique account_ids: {df['account_id'].nunique()}")
    print(f"  - Route distribution:")
    for route, count in df["route"].value_counts().items():
        print(f"      {route}: {count}")
    print(f"  - User MID format glitches (no U prefix): "
          f"{(~df['contact_id'].str.startswith('U')).sum()}")

    return df


if __name__ == "__main__":
    generate()