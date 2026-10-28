-- 5-4 質問セットの参考値クエリ
-- 実行: cd dbt_project && duckdb -readonly warehouse.duckdb < ../docs/analysis/5-4/reference_queries.sql
-- 前提: data_generation/output.sha256 と一致する CSV（ADR-006）
-- 値はすべて参考値。正解値は questions.md で人間が確定する
-- 「罠を踏む」= T2S がやりがちな集計、「踏まない」= 合意済みの定義どおりの集計

-- A1 メッセージの種類ごとのクリック数
select message_type, count(*) as clicked
from main_mart.fct_message_event
where event_type = 'clicked'
group by 1 order by 1;

-- A3 流入経路ごとの登録数（route）。referrer 版は罠を踏む集計
select route, count(*) as subscriptions
from main_mart.fct_subscription
group by 1 order by 2 desc;

select referrer, count(*) as subscriptions
from main_mart.fct_subscription
group by 1 order by 2 desc;

-- B2 配信数
select
    count(*) filter (where event_type = 'delivered') as delivered_rows,          -- 踏まない
    count(*) as all_rows,                                                       -- 踏む: 全行
    count(distinct message_id) as messages,                                     -- 踏む: 配信本数
    (select sum(message_count) from main_mart.fct_revenue) as billed_all_snap,   -- 踏む: 請求ベース・全 snapshot
    (select sum(message_count) from main_mart.fct_revenue where is_latest_snapshot) as billed_latest
from main_mart.fct_message_event;

-- B2 補足: 完全重複の行数（定義はこれを含める）
select count(*) - count(distinct (message_id, contact_id, event_type, event_timestamp)) as exact_dup_rows
from main_mart.fct_message_event;

-- B3 クリック率
select
    round(count(*) filter (where event_type = 'clicked')
        / count(*) filter (where event_type = 'delivered'), 6) as ctr,                        -- 踏まない
    round(count(*) filter (where event_type = 'clicked') / count(*), 6) as clicks_over_all_rows, -- 踏む
    round(count(*) filter (where event_type in ('clicked', 'CLICK'))
        / count(*) filter (where event_type in ('delivered', 'deliverd')), 6) as incl_bad_enum, -- 踏む
    round(count(distinct (message_id, contact_id)) filter (where event_type = 'clicked')
        / count(distinct (message_id, contact_id)) filter (where event_type = 'delivered'), 6) as dedup -- 踏む
from main_mart.fct_message_event;

-- B4 業種ごとの配信数（左結合で孤児を残す）。of_which_orphan が内部結合で落ちる行数
select
    d.industry,
    count(*) as delivered,
    count(*) filter (where d.account_id is null) as of_which_orphan
from main_mart.fct_message_event f
left join main_mart.dim_account d using (account_id)
where f.event_type = 'delivered'
group by 1 order by 2 desc;

-- B4 補足: 業種が空のアカウント
select account_seq, industry from main_mart.dim_account where industry is null;

-- B5 2月の確定した売上（円）
select
    sum(revenue_amount) filter (where is_latest_snapshot) as latest,   -- 踏まない（決めごと3）
    sum(revenue_amount) as all_snap,                                   -- 踏む: is_finalized で絞っても多重計上
    sum(revenue_amount) filter (where is_latest_snapshot
        and account_id in (select account_id from main_mart.dim_account)) as latest_inner_join
from main_mart.fct_revenue
where revenue_month = date '2026-02-01' and is_finalized and currency = 'JPY';

-- C1 売上の合計
select
    currency,
    sum(revenue_amount) filter (where is_latest_snapshot) as latest,
    sum(revenue_amount) as all_snap
from main_mart.fct_revenue
group by rollup (currency) order by 1;

-- C2 契約プラン別の売上（通貨別と混在合計）
select
    d.plan_type,
    r.currency,
    sum(r.revenue_amount) filter (where r.is_latest_snapshot) as latest,
    sum(r.revenue_amount) as all_snap
from main_mart.fct_revenue r
left join main_mart.dim_account d using (account_id)
group by rollup (d.plan_type, r.currency) order by 1, 2;

-- C3 4月の確定した売上（円）。4月は未締めで、確定の行は 0 件
select
    count(*) filter (where is_finalized) as finalized_rows,
    sum(revenue_amount) filter (where is_latest_snapshot) as provisional_latest,
    sum(revenue_amount) filter (where is_latest_snapshot and is_finalized) as finalized_latest
from main_mart.fct_revenue
where revenue_month = date '2026-04-01' and currency = 'JPY';

-- D1 開封率（SL の語彙に無い）
select
    round(count(*) filter (where event_type = 'opened')
        / count(*) filter (where event_type = 'delivered'), 4) as open_rate,
    round(count(*) filter (where event_type in ('opened', 'open'))
        / count(*) filter (where event_type in ('delivered', 'deliverd')), 4) as incl_bad_enum
from main_mart.fct_message_event;

-- D2 登録した人数（重複なし。SL の語彙に無い）
select
    count(*) as events,
    count(distinct contact_id) as contacts,
    count(*) filter (where not is_valid_timestamp) as bad_timestamp_rows
from main_mart.fct_subscription;

-- D5 最初の見積もりと確定値の差（円、2版ある組だけ）
with snaps as (
    select
        *,
        row_number() over (partition by account_id, revenue_month order by snapshot_date) as rn,
        count(*) over (partition by account_id, revenue_month) as n_snap
    from main_mart.fct_revenue
    where currency = 'JPY'
)
select
    revenue_month,
    sum(revenue_amount) filter (where rn = 1) as first_snap,
    sum(revenue_amount) filter (where is_latest_snapshot) as final_snap,
    sum(revenue_amount) filter (where is_latest_snapshot)
        - sum(revenue_amount) filter (where rn = 1) as diff,
    count(*) filter (where rn = 1) as pairs
from snaps
where n_snap > 1
group by 1 order by 1;

-- D6 今月（2026-10）の売上。データは 2026-04 まで
select
    (select max(revenue_month) from main_mart.fct_revenue) as max_month,
    count(*) as rows_2026_10
from main_mart.fct_revenue
where revenue_month = date '2026-10-01';

select currency, sum(revenue_amount) as latest_month_latest   -- 踏む: 最新月を「今月」とみなす
from main_mart.fct_revenue
where revenue_month = date '2026-04-01' and is_latest_snapshot
group by rollup (currency) order by 1;
