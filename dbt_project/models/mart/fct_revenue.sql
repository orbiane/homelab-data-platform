with stg as (
    select * from {{ ref('stg_revenue_monthly') }}
)

select
    account_id,
    revenue_month,
    snapshot_date,
    revenue_amount,
    currency,
    message_count,
    is_finalized,
    is_zero_revenue,
    is_latest_snapshot
from stg
