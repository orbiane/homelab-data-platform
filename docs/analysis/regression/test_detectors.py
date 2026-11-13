"""detectors.py の自己試験。記録は使わず、手で書いた例の SQL・呼び出しだけで、各検出器が当たる／当たらないを確かめる。
使い方（リポジトリの直下で）: uv run python docs/analysis/regression/test_detectors.py
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import detectors as d  # noqa: E402


def sql_rec(qid, *sqls, answer=""):
    calls = [{"seq": i + 1, "tool": "mcp__sl__run_sql", "input": {"sql": s}, "kind": "ok"} for i, s in enumerate(sqls)]
    return {"id": qid, "calls": calls, "final_answer": answer}


def sl_rec(qid, metrics, group_by=(), where=(), answer=""):
    return {"id": qid, "final_answer": answer,
            "calls": [{"seq": 1, "tool": "mcp__sl__query_metrics", "kind": "ok",
                       "input": {"metrics": list(metrics), "group_by": list(group_by), "where": list(where)}}]}


CASES = [
    # (検出器, 記録, 期待)
    (d.year_less_month, sql_rec("B5", "select sum(revenue_amount) from main_mart.fct_revenue where month(revenue_month) = 2 and is_latest_snapshot"), d.HIT),
    (d.year_less_month, sql_rec("B5", "select sum(revenue_amount) from main_mart.fct_revenue where month(revenue_month) = 2 and year(revenue_month) = 2026"), d.MISS),
    (d.year_less_month, sql_rec("B5", "select sum(revenue_amount) from main_mart.fct_revenue where revenue_month = date '2026-02-01'"), d.MISS),
    (d.year_less_month, sql_rec("C3", "select sum(x) filter (where month(revenue_month) = 4) from main_mart.fct_revenue where revenue_month >= '2026-01-01'"), d.MISS),
    (d.year_less_month, sl_rec("B5", ["revenue_amount"], where=["{{ TimeDimension('metric_time', 'month') }} = '2026-02-01'"]), d.MISS),
    (d.quality_flag, sql_rec("A1", "select message_type, count(*) from main_mart.fct_message_event where is_valid_click group by 1"), d.HIT),
    (d.quality_flag, sql_rec("A1", "select message_type, count(*) filter (where is_valid_click) from main_mart.fct_message_event group by 1"), d.HIT),
    (d.quality_flag, sql_rec("A1", "select is_valid_click, count(*) from main_mart.fct_message_event where event_type = 'clicked' group by 1"), d.MISS),
    (d.quality_flag, sql_rec("D2", "select * from main_mart.fct_subscription where not is_valid_contact_id limit 10"), None),  # D2 は対象外
    (d.quality_flag, sql_rec("A3", "select * from main_mart.fct_subscription where not is_valid_contact_id limit 10"), d.NA),  # 下調べは見ない（見る呼び出しが残らない）
    (d.unfinalized_excluded, sql_rec("C2", "select plan_type, currency, sum(revenue_amount) from main_mart.fct_revenue where is_latest_snapshot and is_finalized group by 1, 2"), d.HIT),
    (d.unfinalized_excluded, sql_rec("C2", "select plan_type, is_finalized, sum(revenue_amount) from main_mart.fct_revenue where is_latest_snapshot group by 1, 2"), d.MISS),
    (d.unfinalized_excluded, sl_rec("C2", ["revenue_amount"], where=["{{ Dimension('revenue_record__is_finalized') }} = true"]), d.HIT),
    (d.orphan_dropped, sql_rec("B4", "select a.industry, count(*) from main_mart.fct_message_event e join main_mart.dim_account a on a.account_id = e.account_id where e.event_type = 'delivered' group by 1"), d.HIT),
    (d.orphan_dropped, sql_rec("B4", "select a.industry, count(*) from main_mart.fct_message_event e left join main_mart.dim_account a on a.account_id = e.account_id where e.event_type = 'delivered' group by 1"), d.MISS),
    (d.orphan_dropped, sql_rec("B4", "select a.industry, count(*) from main_mart.fct_message_event e left outer join main_mart.dim_account a using (account_id) group by 1"), d.MISS),
    (d.orphan_dropped, sl_rec("B4", ["delivered_count"], ["account__industry"]), d.NA),
    (d.snapshot_all, sql_rec("B5", "select sum(revenue_amount) from main_mart.fct_revenue where is_finalized and revenue_month = '2026-02-01'"), d.HIT),
    (d.snapshot_all, sql_rec("B5", "select sum(revenue_amount) from main_mart.fct_revenue where is_latest_snapshot and revenue_month = '2026-02-01'"), d.MISS),
    (d.currency_mixed, sql_rec("C1", "select sum(revenue_amount) from main_mart.fct_revenue where is_latest_snapshot"), d.HIT),
    (d.currency_mixed, sql_rec("C1", "select currency, sum(revenue_amount) from main_mart.fct_revenue where is_latest_snapshot group by 1"), d.MISS),
    (d.currency_mixed, sl_rec("C1", ["revenue_amount"]), d.HIT),
    (d.currency_mixed, sl_rec("C1", ["revenue_amount"], ["revenue_record__currency"]), d.MISS),
    (d.d5_final_only, sql_rec("D5", "select snapshot_date, sum(revenue_amount) from main_mart.fct_revenue where currency = 'JPY' group by 1"), d.HIT),
    (d.d5_final_only, sql_rec("D5", "with v as (select *, count(*) over (partition by account_id, revenue_month) as n_versions from main_mart.fct_revenue) select sum(revenue_amount), snapshot_date from v where n_versions = 2 group by 2"), d.MISS),
    (d.empty_as_zero, sql_rec("D6", "select 1", answer="今月の売上は 0 円です。"), d.HIT),
    (d.empty_as_zero, sql_rec("D6", "select 1", answer="今月のデータはまだ入っていません（売上は 2026-04 まで）。行は0件でした。"), d.MISS),
    (d.enum_mixed, sql_rec("A1", "select message_type, count(*) from main_mart.fct_message_event where lower(event_type) = 'clicked' group by 1"), d.HIT),
    (d.enum_mixed, sql_rec("D1", "select count(*) filter (where event_type = 'open') from main_mart.fct_message_event"), d.HIT),
    (d.enum_mixed, sql_rec("A1", "select message_type, count(*) from main_mart.fct_message_event where event_type = 'clicked' group by 1"), d.MISS),
    (d.dedupe, sql_rec("B2", "select count(*) from (select distinct * from main_mart.fct_message_event where event_type = 'delivered')"), d.HIT),
    (d.long_format, sql_rec("B2", "select count(*) from main_mart.fct_message_event"), d.HIT),
    (d.long_format, sql_rec("B2", "select count(*) from main_mart.fct_message_event where event_type = 'delivered'"), d.MISS),
    (d.u_prefix, sql_rec("D2", "select count(distinct contact_id) from main_mart.fct_subscription"), d.HIT),
    (d.u_prefix, sql_rec("D2", "select count(distinct case when contact_id like 'U%' then contact_id else 'U' || contact_id end) from main_mart.fct_subscription"), d.MISS),
    (d.empty_rows_dropped, sql_rec("B4", "select industry, count(*) from x where industry is not null group by 1"), d.HIT),
]

bad = 0
for det, rec, want in CASES:
    got = d.run_all(rec).get(det.__name__, (None, ""))[0]
    if got != want:
        bad += 1
        print(f"× {det.__name__} {rec['id']}: {got} / 期待 {want}")
print(f"例 {len(CASES)} 件、合わない {bad} 件")
sys.exit(1 if bad else 0)
