-- C1 売上の合計（通貨別）（answer_queries.sql の C1。先頭の temp view latest_revenue を CTE にした）
with latest_revenue as (
    select r.*
    from main_mart.fct_revenue r
    where r.snapshot_date = (
        select max(r2.snapshot_date)
        from main_mart.fct_revenue r2
        where r2.account_id = r.account_id and r2.revenue_month = r.revenue_month
    )
)
select currency, sum(revenue_amount) as revenue
from latest_revenue
group by currency
order by currency;
