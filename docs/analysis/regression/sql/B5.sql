-- B5 2月の確定した売上（円）（answer_queries.sql の B5。先頭の temp view latest_revenue を CTE にした）
with latest_revenue as (
    select r.*
    from main_mart.fct_revenue r
    where r.snapshot_date = (
        select max(r2.snapshot_date)
        from main_mart.fct_revenue r2
        where r2.account_id = r.account_id and r2.revenue_month = r.revenue_month
    )
)
select sum(l.revenue_amount) as revenue_jpy,
       sum(l.revenue_amount) filter (where a.account_id is null) as of_which_orphan
from latest_revenue l
left join main_mart.dim_account a on a.account_id = l.account_id
where l.revenue_month = date '2026-02-01'
  and l.is_finalized
  and l.currency = 'JPY';
