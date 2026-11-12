-- D2 登録した人数（answer_queries.sql の D2 のまま）
select count(distinct case when contact_id like 'U%' then contact_id else 'U' || contact_id end) as contacts,
       count(distinct contact_id) as contacts_raw,
       count(*) as subscription_events
from main_mart.fct_subscription;
