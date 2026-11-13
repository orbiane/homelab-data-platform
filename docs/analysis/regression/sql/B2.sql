-- B2 配信数（answer_queries.sql の B2 のまま）
select count(*) as delivered
from main_mart.fct_message_event
where event_type = 'delivered';
