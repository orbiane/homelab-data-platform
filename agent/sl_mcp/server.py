"""mf query と読むだけの SQL を、決まった欄の MCP の道具として出すサーバー（stdio）。

道具の説明文には使い方だけを書く。データの罠の注意は書かない（理由は README.md）。
"""
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

import guards

mcp = FastMCP("sl")

ORDER = ("数字の問いには、まず SL の道具（list_metrics → get_dimensions → query_metrics）を使い、"
         "SL で答えられないときだけ run_sql を使う。")
NO_ANSWER = "kind が ok と empty 以外なら、答えは得られていない。数字を作らず、答えられなかったと伝える。"
NULL_VALUE = ("値の欄がすべて空だった。条件に合う行が0件だったのか、行はあるが値が欠けていたのかは、"
              "この返事からは分からない。")

MESSAGES = {
    "ok": "結果の行がある。",
    "empty": "条件に合う行が0件だった。",
    "null_value": NULL_VALUE,
    "unknown_name": "登録されていない指標か切り口の名前がある。mf query は呼んでいない。",
    "bad_where": "where に {{ }} が無い。mf query は呼んでいない。",
    "mf_error": "mf がエラーを返した。text は mf の文。",
    "sql_error": "SQL がエラーになった。text は DuckDB の文。",
    "busy": "ほかのプロセスが DB を開いていて、開けなかった。text はエラーの文。",
    "maintenance": guards.MAINTENANCE_MESSAGE,
}


def reply(kind, **fields):
    return {"kind": kind, "message": MESSAGES[kind], **fields}


def mf_failure(out, **fields):
    return reply("busy" if guards.is_busy(out) else "mf_error", text=out, **fields)


@mcp.tool(description=(
    "登録済みの指標の名前と説明を返す。" + ORDER + "\n"
    "返す kind：ok / maintenance。" + NO_ANSWER
))
def list_metrics() -> dict[str, Any]:
    if guards.in_maintenance():
        return reply("maintenance")
    return reply("ok", metrics=guards.metrics_from_manifest())


@mcp.tool(description=(
    "指定した指標で使える切り口（ディメンション）の名前を返す。"
    "query_metrics の group_by・where・order_by には、ここに出た名前だけが使える。"
    "時間の切り口は、group_by では metric_time__month のように粒度を付けて書ける。" + ORDER + "\n"
    "返す kind：ok / unknown_name / mf_error / busy / maintenance。" + NO_ANSWER
))
def get_dimensions(metric: str) -> dict[str, Any]:
    if guards.in_maintenance():
        return reply("maintenance")
    known = {m["name"] for m in guards.metrics_from_manifest()}
    if metric not in known:
        return reply("unknown_name", unknown=[metric])
    dims, out = guards.list_dimensions([metric])
    if dims is None:
        return mf_failure(out)
    return reply("ok", metric=metric, dimensions=dims)


@mcp.tool(description=(
    "指標を集計する（mf query を、サーバーが欄から組み立てて実行する）。" + ORDER + "\n"
    "欄：metrics（指標の名前のリスト）、group_by（切り口のリスト）、start_time / end_time"
    "（iso8601 の日時で期間を絞る。両端を含む）、where（絞り込みのリスト。複数は AND）、"
    "order_by（並べ替え。- を付けると降順。例 -metric_time）、limit（行数の上限）。\n"
    "where の書き方：\"{{ Dimension('order_id__revenue') }} > 100\" のように Dimension() で囲む。"
    "時間は {{ TimeDimension('metric_time', 'day') }} のように粒度を付けて書ける。\n"
    "返す kind：ok（結果の行がある）／empty（条件に合う行が0件だった）／"
    "null_value（" + NULL_VALUE + "）／"
    "unknown_name（登録されていない指標か切り口の名前がある。mf は呼んでいない）／"
    "bad_where（where に {{ }} が無い。mf は呼んでいない）／mf_error（mf がエラーを返した。文はそのまま）／"
    "busy（ほかのプロセスが DB を開いていて開けなかった）／maintenance（毎晩の dbt build の時間帯なので断った）。"
    + NO_ANSWER
))
def query_metrics(
    metrics: Annotated[list[str], Field(min_length=1)],
    group_by: list[str] | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    where: list[str] | None = None,
    order_by: list[str] | None = None,
    limit: Annotated[int | None, Field(ge=1, le=guards.MAX_ROWS)] = None,
) -> dict[str, Any]:
    group_by, where, order_by = group_by or [], where or [], order_by or []
    if guards.in_maintenance():
        return reply("maintenance", mf_query_ran=False)

    known = {m["name"] for m in guards.metrics_from_manifest()}
    unknown = [m for m in metrics if m not in known]
    if unknown:
        return reply("unknown_name", unknown=unknown, mf_query_ran=False)

    no_braces = [w for w in where if not guards.where_has_braces(w)]
    if no_braces:
        return reply("bad_where", bad_where=no_braces, mf_query_ran=False)

    dims, out = guards.list_dimensions(metrics)
    if dims is None:
        return mf_failure(out, mf_query_ran=False)
    dimset = set(dims)
    suffixes = guards.time_dimension_suffixes()

    def known_dim(name):
        base = guards.strip_grain(name)
        return base in dimset and (base == name or guards.is_time_dimension(base, suffixes))

    unknown = [g for g in group_by if not known_dim(g)]
    for w in where:
        for fn, name in guards.names_in_where(w):
            if fn not in ("Dimension", "TimeDimension") or not known_dim(name):
                unknown.append(f"{fn}('{name}')")
    for o in order_by:
        name = o[1:] if o.startswith("-") else o
        if name not in metrics and name not in group_by and not known_dim(name):
            unknown.append(o)
    if unknown:
        return reply("unknown_name", unknown=unknown, mf_query_ran=False)

    args = ["query", "--metrics", ",".join(metrics)]
    if group_by:
        args += ["--group-by", ",".join(group_by)]
    if start_time:
        args += ["--start-time", start_time]
    if end_time:
        args += ["--end-time", end_time]
    for w in where:
        args += ["--where", w]
    if order_by:
        args += ["--order", ",".join(order_by)]
    if limit is not None:
        args += ["--limit", str(limit)]

    code, out = guards.run_mf(args)
    fields = {"mf_query_ran": True, "mf_args": args}
    if guards.is_busy(out):
        return reply("busy", text=out, **fields)
    if code != 0 or "ERROR" in out:
        return reply("mf_error", text=out, **fields)
    if guards.MF_EMPTY_MARK in out:
        return reply("empty", columns=[], rows=[], text=out, **fields)
    columns, rows = guards.parse_mf_table(out)
    if not columns:
        return reply("mf_error", text=out, **fields)
    value_idx = [i for i, c in enumerate(columns) if c in metrics]
    if guards.all_null([[row[i] for i in value_idx] for row in rows]):
        return reply("null_value", columns=columns, rows=rows, text=out, **fields)
    return reply("ok", columns=columns, rows=rows, text=out, **fields)


@mcp.tool(description=(
    "warehouse.duckdb（DuckDB）に SQL を投げて、結果を返す。読み取り専用で開く。" + ORDER + "\n"
    "結果は文ごとに results に入る。1つの文で返す行は " + str(guards.MAX_ROWS) + " 行まで。\n"
    "返す kind：ok（結果の行がある）／empty（結果の行が0件だった）／"
    "null_value（" + NULL_VALUE + "）／sql_error（SQL がエラーになった。文はそのまま）／"
    "busy（ほかのプロセスが DB を開いていて開けなかった）／maintenance（毎晩の dbt build の時間帯なので断った）。"
    + NO_ANSWER
))
def run_sql(sql: str) -> dict[str, Any]:
    if guards.in_maintenance():
        return reply("maintenance")
    code, stdout, stderr = guards.run_duckdb(sql)
    err = guards.hide_home(stderr.strip())
    if guards.is_busy(stderr):
        return reply("busy", text=err)
    if code != 0 or "Error" in stderr:
        return reply("sql_error", text=err)
    results = []
    for rows in guards.parse_duckdb_json(stdout):
        results.append({"row_count": len(rows), "truncated": len(rows) > guards.MAX_ROWS,
                        "rows": rows[:guards.MAX_ROWS]})
    if all(r["row_count"] == 0 for r in results):
        return reply("empty", results=results)
    if guards.all_null([list(row.values()) for r in results for row in r["rows"]]):
        return reply("null_value", results=results)
    return reply("ok", results=results)


if __name__ == "__main__":
    mcp.run()
