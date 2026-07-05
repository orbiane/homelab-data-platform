"""
message_event テーブルのデータ生成

Messaging SaaS のメッセージ配信イベント生ログ。アカウントライフサイクルの「運用」フェーズ。
粒度: message_id × contact_id × event_type で1行（縦持ち）。
dt（処理日/パーティションキー）と event_timestamp（発生時刻）を分離設計。

仕込む品質問題（6種、生ログ固有の汚れ）:
  P1 遅延到着     : event_timestamp が dt より数日前
  P2 完全重複     : 同一 message_id × contact_id × event_type × event_timestamp が複数行
  P3 孤児レコード : master に無い account_id / 独立生成の contact_id（追友ログと非JOIN）
  P4 順序矛盾     : opened が delivered より前 / delivered 無しの opened
  P5 enum健全性   : event_type に未知値・typo・null
  P6 click_url整合: clicked なのに null / clicked 以外なのに url

集計テーブル固有の汚れ（drift 等）は revenue_monthly.py に分離。
"""
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd


# 固定シード（account_master=42, subscription=43 に続けて 44。独立性確保）
SEED = 44
random.seed(SEED)
np.random.seed(SEED)


# データ生成期間（追友ログ END_DATE=2026-04-15 と整合。配信は追友より後）
END_DATE = datetime(2026, 4, 15)
START_DATE = END_DATE - timedelta(days=150)

N_MESSAGES = 120                    # 配信数（message 単位）
RECIPIENTS_PER_MSG = (30, 120)      # 1 配信あたり受信ユーザー数レンジ

MESSAGE_TYPES = ["text", "image", "imagemap", "flex", "video"]
EVENT_TYPES = ["delivered", "opened", "clicked", "blocked", "failed"]
# P5: enum を汚す未知値・typo・null
BAD_EVENT_TYPES = ["deliverd", "open", "CLICK", "unsubscribe", None]

CLICK_URLS = [
    "https://example-saas.jp/campaign/spring",
    "https://example-saas.jp/coupon/500off",
    "https://example-saas.jp/lp/newmenu",
    "https://example-saas.jp/survey",
]


def load_account_ids() -> list[str]:
    """account_master.csv から account_id 一覧を読み込む"""
    master_path = Path(__file__).parent.parent / "output" / "account_master.csv"
    df = pd.read_csv(master_path)
    return df["account_id"].tolist()


def generate_contact_id(introduce_format_glitch: bool = False) -> str:
    """ユーザーID生成。追友ログと同じ流儀で U プレフィックスを10%欠落させる"""
    hex_part = "".join(random.choices("0123456789abcdef", k=32))
    if introduce_format_glitch:
        return hex_part
    return "U" + hex_part


def _ts_within_day(d) -> datetime:
    """処理日 d の 0-24時にランダムな時刻（正常系）"""
    base = datetime(d.year, d.month, d.day)
    return base + timedelta(seconds=random.randint(0, 24 * 3600 - 1))


def _row(dt, message_id, account_id, contact_id, message_type, event_type, event_ts, click_url) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "dt": dt,
        "message_id": message_id,
        "account_id": account_id,
        "contact_id": contact_id,
        "message_type": message_type,
        "event_type": event_type,
        "event_timestamp": event_ts,
        "click_url": click_url,
    }


def generate():
    """メッセージ配信イベントの縦持ちログを生成"""
    account_ids = load_account_ids()
    n_bots = len(account_ids)

    # 追友ログと同じく上位アカウントに配信を偏らせる（pareto 風）。
    # 追友が上位3アカウントに集中しているので、配信も整合させる。
    weights = np.array([10.0] * 3 + [2.0] * 5 + [0.5] * (n_bots - 8))
    weights = weights / weights.sum()

    # P3: master に無い account_id（孤児）を少数用意
    orphan_account_ids = ["U" + "".join(random.choices("0123456789abcdef", k=32)) for _ in range(2)]

    period_seconds = int((END_DATE - START_DATE).total_seconds())
    rows: list[dict] = []

    for msg_idx in range(1, N_MESSAGES + 1):
        message_id = f"msg_{msg_idx:05d}"

        # 配信元。3% を孤児 account_id に。
        if random.random() < 0.03:
            account_id = random.choice(orphan_account_ids)
        else:
            account_id = np.random.choice(account_ids, p=weights)

        message_type = random.choice(MESSAGE_TYPES)

        # dt を期間内で決定
        offset = random.randint(0, period_seconds)
        dt = (START_DATE + timedelta(seconds=offset)).date()

        # 受信者。1配信内は非復元（意図しない重複を避ける）。
        n_recip = random.randint(*RECIPIENTS_PER_MSG)
        recipients = []
        for _ in range(n_recip):
            glitch = random.random() < 0.10          # 追友と同率で U 欠落
            recipients.append(generate_contact_id(introduce_format_glitch=glitch))
        # 同一配信内の contact_id 重複を除去（非復元化）
        recipients = list(dict.fromkeys(recipients))

        for contact_id in recipients:
            base_ts = _ts_within_day(dt)

            # --- delivered ---
            has_delivered = random.random() > 0.05
            delivered_ts = base_ts
            if has_delivered:
                d_ts = delivered_ts
                if random.random() < 0.02:                       # P1 遅延到着
                    d_ts = d_ts - timedelta(days=random.randint(1, 4))
                rows.append(_row(dt, message_id, account_id, contact_id, message_type,
                                 "delivered", d_ts, None))
                if random.random() < 0.01:                       # P2 完全重複
                    rows.append(_row(dt, message_id, account_id, contact_id, message_type,
                                     "delivered", d_ts, None))

            # --- opened ---
            open_prob = 0.45 if has_delivered else 0.30
            opened = random.random() < open_prob
            opened_ts = None
            if opened:
                if has_delivered and random.random() < 0.10:     # P4 順序矛盾
                    opened_ts = delivered_ts - timedelta(seconds=random.randint(1, 600))
                else:
                    opened_ts = delivered_ts + timedelta(seconds=random.randint(1, 7200))
                if random.random() < 0.01:                       # P1
                    opened_ts = opened_ts - timedelta(days=random.randint(1, 3))
                rows.append(_row(dt, message_id, account_id, contact_id, message_type,
                                 "opened", opened_ts, None))

            # --- clicked ---
            click_base = opened_ts if opened else delivered_ts
            clicked = random.random() < (0.25 if opened else 0.03)
            if clicked:
                clicked_ts = click_base + timedelta(seconds=random.randint(1, 3600))
                url = None if random.random() < 0.08 else random.choice(CLICK_URLS)  # P6
                rows.append(_row(dt, message_id, account_id, contact_id, message_type,
                                 "clicked", clicked_ts, url))

            # --- blocked ---
            if random.random() < 0.02:
                blocked_ts = delivered_ts + timedelta(seconds=random.randint(60, 86400))
                rows.append(_row(dt, message_id, account_id, contact_id, message_type,
                                 "blocked", blocked_ts, None))

            # --- failed ---
            if not has_delivered and random.random() < 0.4:
                rows.append(_row(dt, message_id, account_id, contact_id, message_type,
                                 "failed", base_ts, None))

    # P5: 不正 event_type 行を新規注入（既存行の整合を壊さない）
    n_bad = int(len(rows) * 0.01)
    for _ in range(n_bad):
        account_id = np.random.choice(account_ids, p=weights)
        dt = (START_DATE + timedelta(seconds=random.randint(0, period_seconds))).date()
        ts = _ts_within_day(dt)
        url = random.choice(CLICK_URLS) if random.random() < 0.3 else None
        rows.append(_row(dt, f"msg_{random.randint(1, N_MESSAGES):05d}", account_id,
                         generate_contact_id(), random.choice(MESSAGE_TYPES),
                         random.choice(BAD_EVENT_TYPES), ts, url))

    # P6 逆パターン: delivered なのに click_url が入る行を少量注入
    n_leak = int(len(rows) * 0.005)
    for _ in range(n_leak):
        account_id = np.random.choice(account_ids, p=weights)
        dt = (START_DATE + timedelta(seconds=random.randint(0, period_seconds))).date()
        ts = _ts_within_day(dt)
        rows.append(_row(dt, f"msg_{random.randint(1, N_MESSAGES):05d}", account_id,
                         generate_contact_id(), random.choice(MESSAGE_TYPES),
                         "delivered", ts, random.choice(CLICK_URLS)))

    random.shuffle(rows)
    df = pd.DataFrame(rows, columns=[
        "event_id", "dt", "message_id", "account_id", "contact_id",
        "message_type", "event_type", "event_timestamp", "click_url",
    ])

    output_path = Path(__file__).parent.parent / "output" / "message_event.csv"
    df.to_csv(output_path, index=False)
    print(f"Generated {len(df)} records -> {output_path}")

    # サマリ
    print(f"  - Unique account_ids: {df['account_id'].nunique()}")
    print(f"  - P3 orphan_account_id rows: {df['account_id'].isin(orphan_account_ids).sum()}")
    print(f"  - P5 bad/null event_type: {(~df['event_type'].isin(EVENT_TYPES)).sum()}")
    dup_keys = ["message_id", "contact_id", "event_type", "event_timestamp"]
    print(f"  - P2 exact duplicates: {df.duplicated(dup_keys).sum()}")
    p6_leak = ((df['event_type'] != 'clicked') & df['click_url'].notna()).sum()
    p6_missing = ((df['event_type'] == 'clicked') & df['click_url'].isna()).sum()
    print(f"  - P6 url_leak={p6_leak}, url_missing_on_click={p6_missing}")
    print(f"  - contact_id format glitches (no U): "
          f"{(~df['contact_id'].str.startswith('U')).sum()}")

    return df


if __name__ == "__main__":
    generate()