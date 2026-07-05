with stg as (
    select * from {{ ref('stg_message_event') }}
)

select
    event_id,
    dt,
    message_id,
    account_id,
    contact_id,
    message_type,
    event_type,
    event_timestamp,
    click_url,
    is_valid_event_type,
    is_valid_click,
    is_late_arrival,
    is_valid_mid
from stg
