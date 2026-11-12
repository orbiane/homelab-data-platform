-- D6 今月（2026-10）の売上（answer_queries.sql の D6 のまま）
select (select count(*) from main_mart.fct_revenue where revenue_month = date '2026-10-01') as rows_2026_10,
       (select max(revenue_month) from main_mart.fct_revenue) as last_month;
