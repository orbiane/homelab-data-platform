-- B3 クリック率（answer_queries.sql の B3 のまま。段階2の時点の数え方：clicked の行数 ÷ delivered の行数）
select round(
    count(*) filter (where event_type = 'clicked')::double
    / count(*) filter (where event_type = 'delivered'), 6) as ctr
from main_mart.fct_message_event;
