-- D1 開封率（answer_queries.sql の D1 のまま。opened の行数 ÷ delivered の行数）
select round(
    count(*) filter (where event_type = 'opened')::double
    / count(*) filter (where event_type = 'delivered'), 6) as open_rate
from main_mart.fct_message_event;
