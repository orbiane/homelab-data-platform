-- C3 4月の確定した売上（円）（answer_queries.sql の C3。先頭の temp view latest_revenue を CTE にした）
with latest_revenue as (
    select r.*
    from main_mart.fct_revenue r
    where r.snapshot_date = (
        select max(r2.snapshot_date)
        from main_mart.fct_revenue r2
        where r2.account_id = r.account_id and r2.revenue_month = r.revenue_month
    )
)
select count(*) filter (where is_finalized) as finalized_rows,
       count(*) as all_rows,
       sum(revenue_amount) as provisional_jpy
from latest_revenue
where revenue_month = date '2026-04-01'
  and currency = 'JPY';
