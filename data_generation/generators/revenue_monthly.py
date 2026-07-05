"""
revenue_monthly テーブルのデータ生成

Messaging SaaS の月次売上集計。アカウントライフサイクルの「収益」フェーズ。
粒度: account_id × revenue_month × snapshot_date（snapshot 版管理あり）

  ※ テーブル名は "monthly" だが実体は「月次サマリの履歴」。命名と実体の齟齬は
    意図的。ADR (docs/decisions/) に記録すること:
    「revenue_monthly は名前に反し account_id × revenue_month × snapshot_date 粒度。
     理由は drift 追跡。確定版が必要なら latest snapshot でフィルタする。
     drift は上振れonly（late arrival起因）。下方修正は Phase 5-7 で追加候補。」

集計テーブル固有の汚れ（生ログの汚れは message_event.py に分離）:
  Q1 snapshot drift : 同一 account_id × month の値が snapshot により変わる（初回<確定）
  Q2 未締め         : 最新月は is_finalized=False の不完全データ
  Q3 ゼロ/欠損混同  : revenue=0 の行 と そもそも行が無い を混在
  加えて currency 混入（固定2アカウントをUSD）で currency 無視 SUM を試す余地

Text-to-SQL の狙い: latest snapshot 取り忘れによる全版 SUM の fan-out を踏ませる。
QUALIFY ROW_NUMBER() OVER (PARTITION BY account_id, revenue_month
ORDER BY snapshot_date DESC) = 1 相当を要求する。
"""
import random
from datetime import date
from pathlib import Path

import pandas as pd


# 固定シード（account_master=42, subscription=43, message_event=44 に続けて 45）
SEED = 45
random.seed(SEED)


# 対象月（追友/配信の期間 2025-11〜2026-04 に整合）
REVENUE_MONTHS = [
    date(2025, 11, 1), date(2025, 12, 1), date(2026, 1, 1),
    date(2026, 2, 1), date(2026, 3, 1), date(2026, 4, 1),
]

# 各月の snapshot 日（初回=当月末締め後、確定=数ヶ月後）。
# 最新月 2026-04 は1版のみ＝未締め。
SNAPSHOT_DATES = {
    date(2025, 11, 1): [date(2025, 12, 5), date(2026, 2, 5)],
    date(2025, 12, 1): [date(2026, 1, 5), date(2026, 3, 5)],
    date(2026, 1, 1):  [date(2026, 2, 5), date(2026, 4, 5)],
    date(2026, 2, 1):  [date(2026, 3, 5), date(2026, 5, 5)],
    date(2026, 3, 1):  [date(2026, 4, 5), date(2026, 5, 5)],
    date(2026, 4, 1):  [date(2026, 5, 5)],                    # 未締め（1版）
}
UNFINALIZED_MONTHS = {date(2026, 4, 1)}

# 固定2アカウント（index基準）を USD に。currency 無視 SUM を試す余地。
USD_BOT_INDICES = {6, 12}


def load_account_ids() -> list[str]:
    """account_master.csv から account_id 一覧を読み込む"""
    master_path = Path(__file__).parent.parent / "output" / "account_master.csv"
    df = pd.read_csv(master_path)
    return df["account_id"].tolist()


def base_revenue_for(account_id: str, month: date) -> int:
    """アカウントごと・月ごとのベース売上（JPY, 整数円）"""
    seed = hash((account_id, month.isoformat())) % 1000
    return int(50_000 + seed * 900)


def generate():
    """月次売上（snapshot版管理付き）を生成"""
    account_ids = load_account_ids()
    rows: list[dict] = []

    for idx, account_id in enumerate(account_ids):
        currency = "USD" if idx in USD_BOT_INDICES else "JPY"

        for month in REVENUE_MONTHS:
            snapshots = SNAPSHOT_DATES[month]
            base = base_revenue_for(account_id, month)

            # Q3 ゼロ/欠損混同: 15% は行ごと欠損、次の 10% は revenue=0
            roll = random.random()
            if roll < 0.15:
                continue
            is_zero = roll < 0.25

            for i, snap in enumerate(snapshots):
                is_first = (i == 0)
                if is_zero:
                    amount, message_count = 0, 0
                else:
                    # Q1 drift: 初回スナップショットは late arrival 取りこぼしで過少
                    if is_first and len(snapshots) > 1:
                        amount = int(base * random.uniform(0.88, 0.97))
                    else:
                        amount = base
                    message_count = max(1, int(amount / random.randint(300, 800)))

                is_finalized = month not in UNFINALIZED_MONTHS

                rows.append({
                    "account_id": account_id,
                    "revenue_month": month.isoformat(),
                    "snapshot_date": snap.isoformat(),
                    "revenue_amount": amount,
                    "currency": currency,
                    "message_count": message_count,
                    "is_finalized": is_finalized,
                })

    # P3 参照整合性を軽く崩す: master に無い account_id の行を1つ足す
    rows.append({
        "account_id": "U" + "f" * 32,
        "revenue_month": date(2026, 2, 1).isoformat(),
        "snapshot_date": date(2026, 5, 5).isoformat(),
        "revenue_amount": 120_000,
        "currency": "JPY",
        "message_count": 200,
        "is_finalized": True,
    })

    df = pd.DataFrame(rows, columns=[
        "account_id", "revenue_month", "snapshot_date",
        "revenue_amount", "currency", "message_count", "is_finalized",
    ])

    output_path = Path(__file__).parent.parent / "output" / "revenue_monthly.csv"
    df.to_csv(output_path, index=False)
    print(f"Generated {len(df)} records -> {output_path}")

    # サマリ
    multi = (df.groupby(["account_id", "revenue_month"]).size() > 1).sum()
    print(f"  - Q1 (bot,month) with multiple snapshots: {multi}")
    latest = (df.sort_values("snapshot_date")
                .groupby(["account_id", "revenue_month"])
                .agg(first_amt=("revenue_amount", "first"),
                     last_amt=("revenue_amount", "last")))
    print(f"  - Q1 drift (first < final): {(latest['first_amt'] < latest['last_amt']).sum()}")
    print(f"  - Q2 unfinalized rows: {(~df['is_finalized']).sum()}")
    print(f"  - Q3 zero-revenue rows: {(df['revenue_amount'] == 0).sum()}")
    print(f"  - currency mix: {df['currency'].value_counts().to_dict()}")

    return df


if __name__ == "__main__":
    generate()