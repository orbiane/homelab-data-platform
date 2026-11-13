-- B3 クリック率（R1 で新しく書いた。answer_queries.sql の B3 ではない）
-- 数え方は docs/business/2026-11-06-ctr-opened.md：clicked の行数 ÷ opened の行数。表記の揺れ（open、CLICK など）は数えない
-- 段階2の時点の SQL（clicked ÷ delivered）は、answer_queries.sql の B3 と、このファイルの git の履歴にある
select round(
    count(*) filter (where event_type = 'clicked')::double
    / count(*) filter (where event_type = 'opened'), 6) as ctr_per_open
from main_mart.fct_message_event;
