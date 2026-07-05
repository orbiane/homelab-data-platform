with stg as (
    select * from {{ ref('stg_account_master') }}
)

select
    account_id,
    account_seq,
    handle,
    account_name,
    industry,
    plan_type,
    region,
    status,
    created_at,
    as_of_date
from stg
