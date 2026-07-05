with source as (
    select * from {{ source('raw', 'revenue_monthly') }}
),

typed as (
    select
        account_id,
        cast(revenue_month as date) as revenue_month,
        cast(snapshot_date as date) as snapshot_date,
        cast(revenue_amount as bigint) as revenue_amount,
        currency,
        cast(message_count as bigint) as message_count,
        cast(is_finalized as boolean) as is_finalized,
        -- Q3: ゼロ売上に印（欠損は行が無いので区別可能）
        cast(revenue_amount as bigint) = 0 as is_zero_revenue
    from source
),

flagged as (
    select
        *,
        -- 同一 account_id × revenue_month の最新snapshotに印（latest抽出はmart側で使う）
        row_number() over (
            partition by account_id, revenue_month
            order by snapshot_date desc
        ) = 1 as is_latest_snapshot
    from typed
)

select * from flagged
