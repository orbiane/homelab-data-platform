-- 5-4 質問セットの正解クエリ（questions.md の「正解（確定）」の出どころ）
-- 実行: cd dbt_project && duckdb -readonly warehouse.duckdb < ../docs/analysis/5-4/answer_queries.sql
-- 前提: data_generation/output.sha256 と一致する CSV（ADR-006）
-- reference_queries.sql とは別に書いた検算。最新 snapshot は is_latest_snapshot に頼らず max(snapshot_date) で選ぶ
-- 定義は _semantic_models.yml の measure と、questions.md の評価の決めごとに従う

-- 共通: アカウント×月ごとの最新 snapshot の行
create temp view latest_revenue as
select r.*
from main_mart.fct_revenue r
where r.snapshot_date = (
    select max(r2.snapshot_date)
    from main_mart.fct_revenue r2
    where r2.account_id = r.account_id and r2.revenue_month = r.revenue_month
);

-- 検算: 自分で選んだ最新 snapshot と is_latest_snapshot が食い違う行（0 なら一致）
select count(*) as mismatch_vs_flag
from main_mart.fct_revenue r
left join latest_revenue l using (account_id, revenue_month, snapshot_date)
where (l.account_id is not null) <> r.is_latest_snapshot;

-- A1 メッセージの種類ごとのクリック数（event_type = 'clicked' だけ。CLICK は数えない）
select message_type, count(*) as clicked
from main_mart.fct_message_event
where event_type = 'clicked'
group by message_type
order by message_type;

-- A3 流入経路ごとの登録数（route 別。重複も含めた全イベント）
select route, count(event_id) as subscriptions
from main_mart.fct_subscription
group by route
order by subscriptions desc;

-- B2 配信数（event_type = 'delivered' の行数。完全重複も含める）
select count(*) as delivered
from main_mart.fct_message_event
where event_type = 'delivered';

-- B3 クリック率（clicked の行数 ÷ delivered の行数）
select round(
    count(*) filter (where event_type = 'clicked')::double
    / count(*) filter (where event_type = 'delivered'), 6) as ctr
from main_mart.fct_message_event;

-- B4 業種ごとの配信数（左結合で孤児を残す。業種が空の行の内訳も出す）
select a.industry,
       count(*) as delivered,
       count(*) filter (where a.account_id is null) as of_which_orphan
from main_mart.fct_message_event e
left join main_mart.dim_account a on a.account_id = e.account_id
where e.event_type = 'delivered'
group by a.industry
order by delivered desc;

-- B5 2月の確定した売上（円）（最新 snapshot、確定、JPY。孤児を含む）
select sum(l.revenue_amount) as revenue_jpy,
       sum(l.revenue_amount) filter (where a.account_id is null) as of_which_orphan
from latest_revenue l
left join main_mart.dim_account a on a.account_id = l.account_id
where l.revenue_month = date '2026-02-01'
  and l.is_finalized
  and l.currency = 'JPY';

-- C1 売上の合計（最新 snapshot、未確定の月を含む。通貨別）
select currency, sum(revenue_amount) as revenue
from latest_revenue
group by currency
order by currency;

-- C2 契約プラン別の売上（左結合で孤児を残す。通貨別）
select a.plan_type, l.currency, sum(l.revenue_amount) as revenue
from latest_revenue l
left join main_mart.dim_account a on a.account_id = l.account_id
group by a.plan_type, l.currency
order by a.plan_type nulls last, l.currency;

-- C3 4月の確定した売上（円）（確定の行があるかと、暫定値を並べて出す）
select count(*) filter (where is_finalized) as finalized_rows,
       count(*) as all_rows,
       sum(revenue_amount) as provisional_jpy
from latest_revenue
where revenue_month = date '2026-04-01'
  and currency = 'JPY';

-- D1 開封率（T2S 側の正解。opened の行数 ÷ delivered の行数）
select round(
    count(*) filter (where event_type = 'opened')::double
    / count(*) filter (where event_type = 'delivered'), 6) as open_rate
from main_mart.fct_message_event;

-- D2 登録した人数（重複なし。U プレフィックスの欠落をそろえてから数える）
select count(distinct case when contact_id like 'U%' then contact_id else 'U' || contact_id end) as contacts,
       count(distinct contact_id) as contacts_raw,
       count(*) as subscription_events
from main_mart.fct_subscription;

-- D5 最初の見積もりと確定値の差（円、2版ある組だけ。月ごと）
with versions as (
    select account_id, revenue_month, revenue_amount, snapshot_date,
           row_number() over (partition by account_id, revenue_month order by snapshot_date) as first_rank,
           row_number() over (partition by account_id, revenue_month order by snapshot_date desc) as last_rank,
           count(*) over (partition by account_id, revenue_month) as n_versions
    from main_mart.fct_revenue
    where currency = 'JPY'
)
select revenue_month,
       count(*) filter (where first_rank = 1) as pairs,
       sum(revenue_amount) filter (where first_rank = 1) as first_estimate,
       sum(revenue_amount) filter (where last_rank = 1) as final_value,
       sum(revenue_amount) filter (where last_rank = 1) - sum(revenue_amount) filter (where first_rank = 1) as diff
from versions
where n_versions = 2
group by revenue_month
order by revenue_month;

-- D6 今月（2026-10）の売上（行が無いことと、データの最終月を出す。current_date は使わない）
select (select count(*) from main_mart.fct_revenue where revenue_month = date '2026-10-01') as rows_2026_10,
       (select max(revenue_month) from main_mart.fct_revenue) as last_month;
