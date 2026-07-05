with source as (
    select * from {{ source('raw', 'subscription_log') }}
),

cleaned as (
    select
        event_id,
        account_id,
        contact_id,
        -- U欠落を除去せずフラグで可視化（5-7演習の素材を残す）
        contact_id like 'U%' as is_valid_mid,
        cast(added_at as timestamp) as added_at,
        cast(dt as date) as dt,
        route,
        referrer,
        -- 異常タイムスタンプもフラグで印付け（除去はしない）
        cast(added_at as timestamp)
            between timestamp '2015-01-01' and timestamp '2027-12-31'
            as is_valid_timestamp
    from source
)

select * from cleaned
