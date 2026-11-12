-- B4 業種ごとの配信数（answer_queries.sql の B4 のまま）
select a.industry,
       count(*) as delivered,
       count(*) filter (where a.account_id is null) as of_which_orphan
from main_mart.fct_message_event e
left join main_mart.dim_account a on a.account_id = e.account_id
where e.event_type = 'delivered'
group by a.industry
order by delivered desc;
