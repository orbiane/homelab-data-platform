{{ config(materialized='table') }}

-- セマンティックレイヤーが要求する日付軸。
-- データの無い日を 0 として表現するために必要。
select
    cast(range as date) as date_day
from range(
    date '2024-01-01',
    date '2028-01-01',
    interval 1 day
)
