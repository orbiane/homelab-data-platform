-- D5 最初の見積もりと確定値の差（answer_queries.sql の D5 のまま）
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
