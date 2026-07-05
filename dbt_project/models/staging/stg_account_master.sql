with source as (
    select * from {{ source('raw', 'account_master') }}
),

renamed as (
    select
        account_id,
        account_seq,
        handle,
        account_name,
        industry,
        lower(plan_type) as plan_type,
        region,
        cast(created_at as timestamp) as created_at,
        status,
        cast(as_of_date as date) as as_of_date
    from source
)

select * from renamed
