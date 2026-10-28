with stg as (
    select * from {{ ref('stg_subscription') }}
)

select
    event_id,
    account_id,
    contact_id,
    is_valid_contact_id,
    added_at,
    dt,
    route,
    referrer,
    is_valid_timestamp
from stg
