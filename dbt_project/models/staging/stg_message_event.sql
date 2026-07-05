with source as (
    select * from {{ source('raw', 'message_event') }}
),

cleaned as (
    select
        event_id,
        cast(dt as date) as dt,
        message_id,
        account_id,
        contact_id,
        message_type,
        event_type,
        cast(event_timestamp as timestamp) as event_timestamp,
        click_url,

        -- P5: event_type が正規5値か
        event_type in ('delivered', 'opened', 'clicked', 'blocked', 'failed')
            as is_valid_event_type,

        -- P6: clicked のときだけ url があるのが正
        case
            when event_type = 'clicked' and click_url is not null then true
            when event_type != 'clicked' and click_url is null then true
            else false
        end as is_valid_click,

        -- P1: event_timestamp が処理日 dt より前 = 遅延到着
        cast(event_timestamp as timestamp) < cast(dt as timestamp)
            as is_late_arrival,

        -- contact_id の U欠落（他テーブルと同じ流儀）
        contact_id like 'U%' as is_valid_mid
    from source
)

select * from cleaned
