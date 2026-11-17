# R2 検出器の当て：段階2 run_001（作りの段）

- 記録 78 本。人の判定 78 本。記録と人の判定の本の名前が同じか：True
- 見る呼び出しから外したもの：{'列や表を探すクエリ': 60}
- 数字の照合と、記録に残る自動の下書き（auto_axis1.tsv）の食い違い：0 本 []
- 人が×か印の本：14 本（×7、印7、答えなし0）

## 検出器ごと（件数の合計は本の数）

一致＝当たって、人も×か印で札がこの検出器に対応する。誤検出＝当たったが、人は○で印なし。別の札＝当たったが、人の×・印の札はこの検出器に対応しない。見落とし＝当たらなかったが、人の札がこの検出器に対応する。当たらず＝当たらず、人の札も対応しない。

| 検出器 | 当てる問 | 一致 | 誤検出 | 別の札 | 見落とし | 当たらず | 判定できない | 対象外 | 計 |
|---|---|---|---|---|---|---|---|---|---|
| 年を見ずに月で絞る（`year_less_month`） | B5・C3・D6 | 5 | 0 | 0 | 0 | 13 | 0 | 60 | 78 |
| 品質フラグで行を除く・数える（`quality_flag`） | A1・A3・B2・B3・D1 | 2 | 8 | 0 | 0 | 20 | 0 | 48 | 78 |
| 未確定の月を外す（`unfinalized_excluded`） | C1・C2・D6 | 3 | 0 | 0 | 0 | 15 | 0 | 60 | 78 |
| 孤児の行を内部結合で落とす（`orphan_dropped`） | B4・B5・C2 | 1 | 2 | 1 | 0 | 6 | 8 | 60 | 78 |
| snapshot を全部足す（`snapshot_all`） | B5・C1・C2 | 0 | 0 | 0 | 0 | 9 | 9 | 60 | 78 |
| 通貨を混ぜて足す（`currency_mixed`） | C1・C2・D5・D6 | 0 | 2 | 0 | 0 | 22 | 0 | 54 | 78 |
| 確定値にだけある行を差に入れる（D5）（`d5_final_only`） | D5 | 3 | 2 | 0 | 1 | 0 | 0 | 72 | 78 |
| 空の結果を 0 と読む（`empty_as_zero`） | C3・D6 | 0 | 0 | 0 | 0 | 12 | 0 | 66 | 78 |
| 不正な・存在しない event_type（`enum_mixed`） | A1・B2・B3・D1 | 1 | 8 | 0 | 0 | 6 | 9 | 54 | 78 |
| 定義の含める重複を除く（`dedupe`） | B2・B3 | 1 | 5 | 0 | 0 | 0 | 6 | 66 | 78 |
| 縦持ちの行をそのまま数える（`long_format`） | B2・B3・D1 | 0 | 0 | 0 | 0 | 12 | 6 | 60 | 78 |
| U プレフィックスをそろえずに数える（`u_prefix`） | D2 | 0 | 1 | 0 | 0 | 5 | 0 | 72 | 78 |
| 業種が空の行を捨てる（`empty_rows_dropped`） | B4 | 0 | 0 | 0 | 0 | 4 | 2 | 72 | 78 |

### 本の名前（一致・誤検出・別の札・見落とし・判定できない）

- `year_less_month`：一致：sql_mcp_B5_r1、sql_mcp_B5_r2、sql_mcp_B5_r3、sql_mcp_C3_r2、sql_mcp_C3_r3
- `quality_flag`：一致：sl_mcp_D1_r1、sql_mcp_B3_r2／誤検出：sql_mcp_A1_r2、sql_mcp_A1_r3、sql_mcp_A3_r1、sql_mcp_A3_r2、sql_mcp_A3_r3、sql_mcp_B2_r1、sql_mcp_B3_r1、sql_mcp_B3_r3
- `unfinalized_excluded`：一致：sql_mcp_C2_r1、sql_mcp_C2_r2、sql_mcp_C2_r3
- `orphan_dropped`：一致：sql_mcp_C2_r1／誤検出：sql_mcp_B4_r1、sql_mcp_B4_r2／別の札：sql_mcp_C2_r3／判定できない：sl_mcp_B4_r1、sl_mcp_B4_r2、sl_mcp_B5_r1、sl_mcp_B5_r2、sl_mcp_B5_r3、sl_mcp_C2_r1、sl_mcp_C2_r2、sl_mcp_C2_r3
- `snapshot_all`：判定できない：sl_mcp_B5_r1、sl_mcp_B5_r2、sl_mcp_B5_r3、sl_mcp_C1_r1、sl_mcp_C1_r2、sl_mcp_C1_r3、sl_mcp_C2_r1、sl_mcp_C2_r2、sl_mcp_C2_r3
- `currency_mixed`：誤検出：sl_mcp_C2_r1、sl_mcp_C2_r3
- `d5_final_only`：一致：sl_mcp_D5_r2、sl_mcp_D5_r3、sql_mcp_D5_r1／誤検出：sql_mcp_D5_r2、sql_mcp_D5_r3／見落とし：sl_mcp_D5_r1
- `enum_mixed`：一致：sql_mcp_B3_r2／誤検出：sql_mcp_A1_r1、sql_mcp_A1_r2、sql_mcp_A1_r3、sql_mcp_B3_r1、sql_mcp_B3_r3、sql_mcp_D1_r1、sql_mcp_D1_r2、sql_mcp_D1_r3／判定できない：sl_mcp_A1_r1、sl_mcp_A1_r2、sl_mcp_A1_r3、sl_mcp_B2_r1、sl_mcp_B2_r2、sl_mcp_B2_r3、sl_mcp_B3_r1、sl_mcp_B3_r2、sl_mcp_B3_r3
- `dedupe`：一致：sql_mcp_B3_r2／誤検出：sql_mcp_B2_r1、sql_mcp_B2_r2、sql_mcp_B2_r3、sql_mcp_B3_r1、sql_mcp_B3_r3／判定できない：sl_mcp_B2_r1、sl_mcp_B2_r2、sl_mcp_B2_r3、sl_mcp_B3_r1、sl_mcp_B3_r2、sl_mcp_B3_r3
- `long_format`：判定できない：sl_mcp_B2_r1、sl_mcp_B2_r2、sl_mcp_B2_r3、sl_mcp_B3_r1、sl_mcp_B3_r2、sl_mcp_B3_r3
- `u_prefix`：誤検出：sql_mcp_D2_r2
- `empty_rows_dropped`：判定できない：sl_mcp_B4_r1、sl_mcp_B4_r2

## 見立てと人の判定（本ごとの突き合わせ。合計は本の数）

| 見立て ＼ 人 | ○ | 印 | × | 答えなし | 計 |
|---|---|---|---|---|---|
| ○ | 33 | 1 | 0 | 0 | 34 |
| 印 | 19 | 5 | 3 | 0 | 27 |
| × | 12 | 1 | 4 | 0 | 17 |
| 答えなし | 0 | 0 | 0 | 0 | 0 |
| 判定できない | 0 | 0 | 0 | 0 | 0 |
| 計 | 64 | 7 | 7 | 0 | 78 |

- 見立てが×か印で、人も×か印：13 本／見立てだけ：31 本 ['sl_mcp_C2_r1', 'sl_mcp_C2_r3', 'sl_mcp_C3_r1', 'sl_mcp_C3_r3', 'sl_mcp_D6_r1', 'sl_mcp_D6_r2', 'sl_mcp_D6_r3', 'sql_mcp_A1_r1', 'sql_mcp_A1_r2', 'sql_mcp_A1_r3', 'sql_mcp_A3_r1', 'sql_mcp_A3_r2', 'sql_mcp_A3_r3', 'sql_mcp_B2_r1', 'sql_mcp_B2_r2', 'sql_mcp_B2_r3', 'sql_mcp_B3_r1', 'sql_mcp_B3_r3', 'sql_mcp_B4_r1', 'sql_mcp_B4_r2', 'sql_mcp_B4_r3', 'sql_mcp_C3_r1', 'sql_mcp_D1_r1', 'sql_mcp_D1_r2', 'sql_mcp_D1_r3', 'sql_mcp_D2_r2', 'sql_mcp_D5_r2', 'sql_mcp_D5_r3', 'sql_mcp_D6_r1', 'sql_mcp_D6_r2', 'sql_mcp_D6_r3']／人だけ：1 本 ['sl_mcp_D5_r1']

| 本 | 人の軸1 | 人の印 | 人の札 | 数字の照合 | 当たった検出器 | 見立て |
|---|---|---|---|---|---|---|
| sl_mcp_A1_r1 | ○ |  |  | ○ |  | ○ |
| sl_mcp_A1_r2 | ○ |  |  | ○ |  | ○ |
| sl_mcp_A1_r3 | ○ |  |  | ○ |  | ○ |
| sl_mcp_A3_r1 | ○ |  |  | ○ |  | ○ |
| sl_mcp_A3_r2 | ○ |  |  | ○ |  | ○ |
| sl_mcp_A3_r3 | ○ |  |  | ○ |  | ○ |
| sl_mcp_B2_r1 | ○ |  |  | ○ |  | ○ |
| sl_mcp_B2_r2 | ○ |  |  | ○ |  | ○ |
| sl_mcp_B2_r3 | ○ |  |  | ○ |  | ○ |
| sl_mcp_B3_r1 | ○ |  |  | ○ |  | ○ |
| sl_mcp_B3_r2 | ○ |  |  | ○ |  | ○ |
| sl_mcp_B3_r3 | ○ |  |  | ○ |  | ○ |
| sl_mcp_B4_r1 | ○ |  |  | ○ |  | ○ |
| sl_mcp_B4_r2 | ○ |  |  | ○ |  | ○ |
| sl_mcp_B4_r3 | ○ |  |  | ○ |  | ○ |
| sl_mcp_B5_r1 | ○ |  |  | ○ |  | ○ |
| sl_mcp_B5_r2 | ○ |  |  | ○ |  | ○ |
| sl_mcp_B5_r3 | ○ |  |  | ○ |  | ○ |
| sl_mcp_C1_r1 | ○ |  |  | ○ |  | ○ |
| sl_mcp_C1_r2 | ○ |  |  | ○ |  | ○ |
| sl_mcp_C1_r3 | ○ |  |  | ○ |  | ○ |
| sl_mcp_C2_r1 | ○ |  |  | ○ | currency_mixed | 印 |
| sl_mcp_C2_r2 | ○ |  |  | ○ |  | ○ |
| sl_mcp_C2_r3 | ○ |  |  | ○ | currency_mixed | 印 |
| sl_mcp_C3_r1 | ○ |  |  | × |  | × |
| sl_mcp_C3_r2 | ○ |  |  | ○ |  | ○ |
| sl_mcp_C3_r3 | ○ |  |  | × |  | × |
| sl_mcp_D1_r1 | ○ | 品質フラグ |  | ○ | quality_flag | 印 |
| sl_mcp_D1_r2 | ○ |  |  | ○ |  | ○ |
| sl_mcp_D1_r3 | ○ |  |  | ○ |  | ○ |
| sl_mcp_D2_r1 | ○ |  |  | ○ |  | ○ |
| sl_mcp_D2_r2 | ○ |  |  | ○ |  | ○ |
| sl_mcp_D2_r3 | ○ |  |  | ○ |  | ○ |
| sl_mcp_D5_r1 | ○ | 版の取り方 |  | ○ |  | ○ |
| sl_mcp_D5_r2 | × |  | その他（確定値にだけある行を差に入れた） | × | d5_final_only | × |
| sl_mcp_D5_r3 | × |  | その他（確定値にだけある行を差に入れた） | ○ | d5_final_only | 印 |
| sl_mcp_D6_r1 | ○ |  |  | × |  | × |
| sl_mcp_D6_r2 | ○ |  |  | × |  | × |
| sl_mcp_D6_r3 | ○ |  |  | × |  | × |
| sql_mcp_A1_r1 | ○ |  |  | ○ | enum_mixed | 印 |
| sql_mcp_A1_r2 | ○ |  |  | ○ | quality_flag、enum_mixed | 印 |
| sql_mcp_A1_r3 | ○ |  |  | ○ | quality_flag、enum_mixed | 印 |
| sql_mcp_A3_r1 | ○ |  |  | ○ | quality_flag | 印 |
| sql_mcp_A3_r2 | ○ |  |  | ○ | quality_flag | 印 |
| sql_mcp_A3_r3 | ○ |  |  | ○ | quality_flag | 印 |
| sql_mcp_B2_r1 | ○ |  |  | ○ | quality_flag、dedupe | 印 |
| sql_mcp_B2_r2 | ○ |  |  | ○ | dedupe | 印 |
| sql_mcp_B2_r3 | ○ |  |  | ○ | dedupe | 印 |
| sql_mcp_B3_r1 | ○ |  |  | ○ | quality_flag、enum_mixed、dedupe | 印 |
| sql_mcp_B3_r2 | × |  | 品質フラグ・enum・重複 | ○ | quality_flag、enum_mixed、dedupe | 印 |
| sql_mcp_B3_r3 | ○ |  |  | ○ | quality_flag、enum_mixed、dedupe | 印 |
| sql_mcp_B4_r1 | ○ |  |  | × | orphan_dropped | × |
| sql_mcp_B4_r2 | ○ |  |  | × | orphan_dropped | × |
| sql_mcp_B4_r3 | ○ |  |  | × |  | × |
| sql_mcp_B5_r1 | ○ | 年 |  | ○ | year_less_month | 印 |
| sql_mcp_B5_r2 | ○ | 年 |  | ○ | year_less_month | 印 |
| sql_mcp_B5_r3 | ○ | 年 |  | ○ | year_less_month | 印 |
| sql_mcp_C1_r1 | ○ |  |  | ○ |  | ○ |
| sql_mcp_C1_r2 | ○ |  |  | ○ |  | ○ |
| sql_mcp_C1_r3 | ○ |  |  | ○ |  | ○ |
| sql_mcp_C2_r1 | × |  | 孤児・その他（確定の月だけ） | × | unfinalized_excluded、orphan_dropped | × |
| sql_mcp_C2_r2 | × |  | その他（確定の月だけ） | × | unfinalized_excluded | × |
| sql_mcp_C2_r3 | × |  | その他（確定の月だけ） | × | unfinalized_excluded、orphan_dropped | × |
| sql_mcp_C3_r1 | ○ |  |  | × |  | × |
| sql_mcp_C3_r2 | ○ | 年 |  | × | year_less_month | × |
| sql_mcp_C3_r3 | ○ | 年 |  | ○ | year_less_month | 印 |
| sql_mcp_D1_r1 | ○ |  |  | ○ | enum_mixed | 印 |
| sql_mcp_D1_r2 | ○ |  |  | ○ | enum_mixed | 印 |
| sql_mcp_D1_r3 | ○ |  |  | ○ | enum_mixed | 印 |
| sql_mcp_D2_r1 | ○ |  |  | ○ |  | ○ |
| sql_mcp_D2_r2 | ○ |  |  | ○ | u_prefix | 印 |
| sql_mcp_D2_r3 | ○ |  |  | ○ |  | ○ |
| sql_mcp_D5_r1 | × |  | その他（確定値にだけある行を差に入れた） | ○ | d5_final_only | 印 |
| sql_mcp_D5_r2 | ○ |  |  | ○ | d5_final_only | 印 |
| sql_mcp_D5_r3 | ○ |  |  | ○ | d5_final_only | 印 |
| sql_mcp_D6_r1 | ○ |  |  | × |  | × |
| sql_mcp_D6_r2 | ○ |  |  | × |  | × |
| sql_mcp_D6_r3 | ○ |  |  | × |  | × |

## 当たった根拠（どの呼び出しのどこか）

- sl_mcp_C2_r1 `currency_mixed`：#4 query_metrics: metrics ['revenue_amount'] group_by ['revenue_record__revenue_month', 'revenue_record__is_finalized'] where []
- sl_mcp_C2_r3 `currency_mixed`：#4 query_metrics: metrics ['revenue_amount'] group_by ['revenue_record__revenue_month', 'revenue_record__is_finalized'] where []
- sl_mcp_D1_r1 `quality_flag`：#4 run_sql: where で絞った（is_valid_event_type）: is_valid_event_type
- sl_mcp_D5_r2 `d5_final_only`：#8 run_sql: select revenue_month, snapshot_date, currency, is_finalized, is_latest_snapshot, count(*) n, sum(revenue_amount) amt from main_mart.fct_revenue group by all ord…
- sl_mcp_D5_r3 `d5_final_only`：#6 run_sql: with s as (select revenue_month, currency, snapshot_date, sum(revenue_amount) amt, count(*) n, bool_and(is_finalized) fin from main_mart.fct_revenue group by 1,…
- sql_mcp_A1_r1 `enum_mixed`：#4 run_sql: lower(event_type
- sql_mcp_A1_r2 `quality_flag`：#5 run_sql: filter で数えた（is_valid_click）: event_type='clicked' and is_valid_click
- sql_mcp_A1_r2 `enum_mixed`：#4 run_sql: lower(event_type
- sql_mcp_A1_r3 `quality_flag`：#4 run_sql: where で絞った（is_valid_click）: event_type in ('clicked','click') or is_valid_click=false
- sql_mcp_A1_r3 `enum_mixed`：#4 run_sql: event_type in ('clicked','CLICK')（正規でない値 ['CLICK']）
- sql_mcp_A3_r1 `quality_flag`：#4 run_sql: 数えた: when is_valid_contact_id then 1 else 0 end) valid_c
- sql_mcp_A3_r2 `quality_flag`：#3 run_sql: 数えた: when not is_valid_contact_id then 1 else 0 end) invalid_cid
- sql_mcp_A3_r3 `quality_flag`：#3 run_sql: 数えた: when is_valid_contact_id then 1 else 0 end) valid_c
- sql_mcp_B2_r1 `quality_flag`：#4 run_sql: 数えた: when is_valid_contact_id then 0 else 1 end) badcontact from main_mart.fct_message_event group by all order by n desc
- sql_mcp_B2_r1 `dedupe`：#4 run_sql: count(distinct event_id)
- sql_mcp_B2_r2 `dedupe`：#4 run_sql: count(distinct event_id)
- sql_mcp_B2_r3 `dedupe`：#4 run_sql: count(distinct event_id)
- sql_mcp_B3_r1 `quality_flag`：#4 run_sql: filter で数えた（is_valid_click）: event_type='clicked' and is_valid_click
- sql_mcp_B3_r1 `enum_mixed`：#4 run_sql: lower(event_type
- sql_mcp_B3_r1 `dedupe`：#4 run_sql: count(distinct event_id)
- sql_mcp_B3_r2 `quality_flag`：#5 run_sql: where で絞った（is_valid_click）: event_type='clicked' and not is_valid_click
- sql_mcp_B3_r2 `enum_mixed`：#5 run_sql: lower(event_type
- sql_mcp_B3_r2 `dedupe`：#4 run_sql: count(distinct event_id)
- sql_mcp_B3_r3 `quality_flag`：#5 run_sql: filter で数えた（is_valid_click）: event_type='clicked' and is_valid_click
- sql_mcp_B3_r3 `enum_mixed`：#4 run_sql: lower(event_type
- sql_mcp_B3_r3 `dedupe`：#3 run_sql: count(distinct event_id)
- sql_mcp_B4_r1 `orphan_dropped`：#4 run_sql: where in (select account_id from main_mart.dim_account
- sql_mcp_B4_r2 `orphan_dropped`：#4 run_sql: where a.account_id is not null
- sql_mcp_B5_r1 `year_less_month`：#3 run_sql: where month(revenue_month)=2
- sql_mcp_B5_r2 `year_less_month`：#3 run_sql: where month(revenue_month)=2
- sql_mcp_B5_r3 `year_less_month`：#3 run_sql: where month(revenue_month)=2
- sql_mcp_C2_r1 `unfinalized_excluded`：#5 run_sql: where a.account_id is null; select coalesce(a.plan_type,'(未登録)') plan_type, r.currency, r.is_finalized, count(distinct r.account_id) accts, count(distinct r.rev…
- sql_mcp_C2_r1 `orphan_dropped`：#5 run_sql: dim_account を左にした left join: from main_mart.dim_account a left join main_mart.fct_revenue
- sql_mcp_C2_r2 `unfinalized_excluded`：#5 run_sql: where a.account_id is null; select coalesce(a.plan_type,'(マスタ未登録)') plan, r.currency, count(distinct r.account_id) accts, sum(case when r.is_finalized then r.re…
- sql_mcp_C2_r3 `unfinalized_excluded`：#4 run_sql: where a.account_id is null; select r.account_id, a.plan_type, r.revenue_month, r.revenue_amount, r.is_finalized from main_mart.fct_revenue r left join main_mart…
- sql_mcp_C2_r3 `orphan_dropped`：#4 run_sql: dim_account を左にした left join: from main_mart.dim_account a left join main_mart.fct_revenue
- sql_mcp_C3_r2 `year_less_month`：#3 run_sql: where month(revenue_month)=4
- sql_mcp_C3_r3 `year_less_month`：#4 run_sql: where month(revenue_month)=4
- sql_mcp_D1_r1 `enum_mixed`：#5 run_sql: event_type='open'（正規でない値 ['open']）
- sql_mcp_D1_r2 `enum_mixed`：#4 run_sql: event_type in ('opened','open')（正規でない値 ['open']）
- sql_mcp_D1_r3 `enum_mixed`：#5 run_sql: event_type in ('opened','open')（正規でない値 ['open']）
- sql_mcp_D2_r2 `u_prefix`：#4 run_sql: select contact_id, is_valid_contact_id, count(*) from main_mart.fct_subscription group by all order by 3 desc, 1 limit 15; select left(contact_id,1) p, length(c…
- sql_mcp_D5_r1 `d5_final_only`：#4 run_sql: select revenue_month, currency, snapshot_date, is_finalized, is_latest_snapshot, count(*) n, sum(revenue_amount) amt from main_mart.fct_revenue group by all ord…
- sql_mcp_D5_r2 `d5_final_only`：#4 run_sql: select revenue_month, currency, snapshot_date, is_finalized, is_latest_snapshot, count(*) n, sum(revenue_amount) amt from main_mart.fct_revenue group by all ord…
- sql_mcp_D5_r3 `d5_final_only`：#4 run_sql: with r as (select *, row_number() over (partition by account_id, revenue_month, currency order by snapshot_date) rn_first, row_number() over (partition by accou…

## D5 の答えに出た罠の数（判定には使っていない。別の欄）

- sl_mcp_D5_r1：2026-02 の最初の見積もり 5,091,741
- sl_mcp_D5_r2：5か月の差 +2,852,863
- sl_mcp_D5_r3：2026-02 の差 +504,859、5か月の差 +2,852,863
- sql_mcp_D5_r1：2026-02 の差 +504,859、5か月の差 +2,852,863
- sql_mcp_D5_r2：2026-02 の差 +504,859
- sql_mcp_D5_r3：無し

確かめで合わない所：0 件
