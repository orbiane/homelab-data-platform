-- A3 流入経路ごとの登録数（answer_queries.sql の A3 のまま）
select route, count(event_id) as subscriptions
from main_mart.fct_subscription
group by route
order by subscriptions desc;
