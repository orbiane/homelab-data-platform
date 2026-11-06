# 段階3 定義の腐敗：記録

## 1. 入れたもの（2026-11-05）

- 決定メモ：`docs/business/2026-11-05-ctr.md`（クリック率を「クリック数 ÷ 開封数」で見る、という会社の決めごと）
- SL の定義（`_metrics.yml`・`_semantic_models.yml`）は、段階3の腐敗の注入として、**わざと直していない**。決めごとは変わったが、定義は古いまま残っている

## 2. 今の ctr の定義

- `dbt_project/models/mart/_metrics.yml` の 23〜29 行目：`ctr`（type: ratio、description「クリック率 = クリック数 ÷ 配信数」）
  - 分子：`numerator: clicked_count`（28 行目）
  - 分母：`denominator: delivered_count`（29 行目）
- measure の expr（`dbt_project/models/mart/_semantic_models.yml`）
  - `delivered_count`（68〜71 行目）：`case when event_type = 'delivered' then 1 else 0 end`、agg: sum
  - `clicked_count`（72〜75 行目）：`case when event_type = 'clicked' then 1 else 0 end`、agg: sum
  - `opened_count`（76〜79 行目）：`case when event_type = 'opened' then 1 else 0 end`、agg: sum

## 3. 変える前の数字（MCP の道具 sl）

データの版の照合（`cd data_generation/output && shasum -a 256 -c ../output.sha256`）：4本とも OK。

### query_metrics

呼び出し：`metrics=["ctr", "delivered_count", "clicked_count"]`（ほかの欄なし）

```
{"kind":"ok","columns":["ctr","delivered_count","clicked_count"],"rows":[[0.134196,8428,1131]],
 "mf_args":["query","--metrics","ctr,delivered_count,clicked_count"]}
```

ctr 0.134196 は、ADR-006 の基準値 0.134196 と小数6桁で一致した。

### run_sql

measure の expr と同じ数え方（品質フラグで除外しない）。

```sql
select
  sum(case when event_type = 'delivered' then 1 else 0 end) as delivered,
  sum(case when event_type = 'opened' then 1 else 0 end) as opened,
  sum(case when event_type = 'clicked' then 1 else 0 end) as clicked,
  round(sum(case when event_type = 'clicked' then 1 else 0 end)::double
        / sum(case when event_type = 'delivered' then 1 else 0 end), 6) as clicked_per_delivered,
  round(sum(case when event_type = 'clicked' then 1 else 0 end)::double
        / sum(case when event_type = 'opened' then 1 else 0 end), 6) as clicked_per_opened
from main_mart.fct_message_event
```

（1回目は `from fct_message_event` と書いて sql_error「Table with name fct_message_event does not exist! Did you mean "main_mart.fct_message_event"?」になった。スキーマを付けて出し直した。）

```
{"kind":"ok","results":[{"row_count":1,"truncated":false,"rows":[{"delivered":"8428","opened":"3835","clicked":"1131",
 "clicked_per_delivered":0.134196,"clicked_per_opened":0.294915}]}]}
```

### 突き合わせ

| | query_metrics | run_sql |
|---|---|---|
| delivered | 8428 | 8428 |
| clicked | 1131 | 1131 |
| clicked ÷ delivered | 0.134196（ctr） | 0.134196 |

## 4. 新しい数え方の見込み値

- clicked ÷ opened = 1131 ÷ 3835 = **0.294915**（上の run_sql の `clicked_per_opened`）
- SQL は上の run_sql と同じ（分母は `opened_count` の expr と同じ `case when event_type = 'opened' then 1 else 0 end`）
- これは、今ある opened_count の数え方に合わせた仮置き。新しい定義の数え方は、直す段で人が決める

## 5. dbt test（dbt_project/ で1回）

`dbt test`（exit=0）：`Done. PASS=4 WARN=3 ERROR=0 SKIP=0 NO-OP=0 TOTAL=7`

| テスト | 結果 |
|---|---|
| accepted_values_fct_revenue_currency__JPY__USD | PASS |
| assert_opened_after_delivered | WARN 392 |
| not_null_dim_account_account_id | PASS |
| relationships_fct_message_event_account_id（dim_account へ） | WARN 189 |
| relationships_fct_revenue_account_id（dim_account へ） | WARN 1 |
| relationships_fct_subscription_account_id（dim_account へ） | PASS |
| unique_dim_account_account_id | PASS |

WARN は仕込んだ汚れの検知（順序矛盾・message_event の孤児 189 行・revenue の孤児 1 行）。

## 6. 直す（2026-11-06）

- ADR-007 の R3 を、人の判断（2026-11-06 14:32）で「止める」から「毎回人に聞く（ask）」に変えた
- 決定メモ：`docs/business/2026-11-06-ctr-opened.md`（Claude Code が書き、人が承認した）
- 定義の変更：`ctr`（クリック数 ÷ 配信数）を消し、`ctr_per_open`（クリック数 ÷ 開封数）と `opened_count` を足した
