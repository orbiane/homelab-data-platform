-- A1 メッセージの種類ごとのクリック数（answer_queries.sql の A1 のまま）
select message_type, count(*) as clicked
from main_mart.fct_message_event
where event_type = 'clicked'
group by message_type
order by message_type;
