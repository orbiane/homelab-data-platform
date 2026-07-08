{{ config(severity='warn') }}

-- P4検知：同一 message × user で opened が delivered より前に発生している行を拾う。
-- イベントログの順序保証のなさ（クロックずれ等）を可視化する。
-- 1行でも返ればWARN。

with delivered as (
    select
        message_id,
        contact_id,
        event_timestamp as delivered_at
    from {{ ref('fct_message_event') }}
    where event_type = 'delivered'
),

opened as (
    select
        message_id,
        contact_id,
        event_timestamp as opened_at
    from {{ ref('fct_message_event') }}
    where event_type = 'opened'
)

select
    o.message_id,
    o.contact_id,
    d.delivered_at,
    o.opened_at
from opened o
join delivered d
    on o.message_id = d.message_id
    and o.contact_id = d.contact_id
where o.opened_at < d.delivered_at
