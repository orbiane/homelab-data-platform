-- C2 契約プラン別の売上（通貨別）（answer_queries.sql の C2。先頭の temp view latest_revenue を CTE にした）
with latest_revenue as (
    select r.*
    from main_mart.fct_revenue r
    where r.snapshot_date = (
        select max(r2.snapshot_date)
        from main_mart.fct_revenue r2
        where r2.account_id = r.account_id and r2.revenue_month = r.revenue_month
    )
)
select a.plan_type, l.currency, sum(l.revenue_amount) as revenue
from latest_revenue l
left join main_mart.dim_account a on a.account_id = l.account_id
group by a.plan_type, l.currency
order by a.plan_type nulls last, l.currency;
