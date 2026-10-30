"""sl_mcp の終わりの条件を、1つずつ判定する。

- 条件1〜6 は、.mcp.json と同じコマンドでサーバーを stdio で起動し、MCP のクライアントとして呼ぶ
- busy と maintenance は時刻や外のプロセスに左右されるので、server の関数を同じプロセスで直接呼ぶ
- 比べる相手（_metrics.yml、mf list、ADR-006）は、サーバーを通さずに読む

使い方：uv run --frozen --project agent/sl_mcp python agent/sl_mcp/check.py（リポジトリの直下で）
"""
import asyncio
import datetime
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import guards
import server

REPO = guards.REPO
FAILS = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def mf_direct(args):
    r = subprocess.run([str(guards.MF)] + args, cwd=guards.DBT, env=guards.mf_env(),
                       capture_output=True, text=True, timeout=300)
    return r.stdout + r.stderr


def adr006_revenue():
    text = (REPO / "docs/decisions/ADR-006-generated-data-version.md").read_text()
    m = re.search(r"^\| revenue_amount \| ([\d,]+)（JPY ([\d,]+) / USD ([\d,]+)）", text, re.M)
    return tuple(int(x.replace(",", "")) for x in m.groups())


async def over_stdio():
    conf = json.loads((REPO / ".mcp.json").read_text())["mcpServers"]["sl"]
    params = StdioServerParameters(command=conf["command"], args=conf["args"], cwd=str(REPO))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()

            async def call(tool, **kw):
                r = await s.call_tool(tool, arguments=kw)
                if r.isError:
                    return {"kind": "<isError>", "text": " ".join(c.text for c in r.content)}
                return r.structuredContent

            # 条件1：4つの道具が見える
            names = sorted(t.name for t in (await s.list_tools()).tools)
            check("1 道具がちょうど4つ", names == ["get_dimensions", "list_metrics", "query_metrics", "run_sql"],
                  str(names))

            # 条件2：list_metrics が _metrics.yml と mf list metrics の指標を全部返す
            r = await call("list_metrics")
            got = {m["name"]: m["description"] for m in r["metrics"]}
            yml = re.findall(r"^\s*- name:\s*(\S+)", (REPO / "dbt_project/models/mart/_metrics.yml").read_text(), re.M)
            mfl = re.findall(r"^• (\w+):", mf_direct(["list", "metrics"]), re.M)
            check("2 件数が _metrics.yml と同じ", len(got) == len(yml), f"server {len(got)} / yml {len(yml)}")
            check("2 件数が mf list metrics と同じ", len(got) == len(mfl), f"server {len(got)} / mf {len(mfl)}")
            check("2 名前の集合が同じ", set(got) == set(yml) == set(mfl), str(sorted(got)))
            man = {m["name"]: m.get("description") for m in json.loads(guards.MANIFEST.read_text())["metrics"]}
            check("2 説明が manifest の description とそのまま同じ", got == man)

            # 条件3：get_dimensions が mf list dimensions と同じ
            r = await call("get_dimensions", metric="revenue_amount")
            mfd = re.findall(r"^• (\S+)", mf_direct(["list", "dimensions", "--metrics", "revenue_amount"]), re.M)
            check("3 revenue_amount の切り口が mf list dimensions と同じ",
                  r["kind"] == "ok" and sorted(r["dimensions"]) == sorted(mfd), f"{len(r.get('dimensions', []))} 個 / mf {len(mfd)} 個")

            # 条件4：revenue_amount が ADR-006 の基準値と一致
            total, jpy, usd = adr006_revenue()
            r = await call("query_metrics", metrics=["revenue_amount"])
            check("4 revenue_amount の全体が ADR-006 と一致", r["kind"] == "ok" and r["rows"] == [[total]],
                  f"{r['kind']} {r.get('rows')} / ADR-006 {total}")
            r = await call("query_metrics", metrics=["revenue_amount"], group_by=["revenue_record__currency"])
            by = {row[0]: row[1] for row in r.get("rows", [])}
            check("4 通貨別が ADR-006 と一致", by == {"JPY": jpy, "USD": usd}, f"{by} / ADR-006 JPY {jpy} USD {usd}")

            # 条件5：空・語彙に無い・{{ }} 抜け・mf の書き方のエラーが、別の種類
            kinds = {}
            r = await call("query_metrics", metrics=["revenue_amount"], group_by=["revenue_record__currency"],
                           start_time="2026-10-01T00:00:00", end_time="2026-10-31T23:59:59",
                           order_by=["-revenue_amount"])  # run_002 の sl_D6_r1 で空になった問い合わせ
            kinds["empty"] = r["kind"]
            check("5 空の結果は empty", r["kind"] == "empty" and r["mf_query_ran"], r["kind"])
            r = await call("query_metrics", metrics=["open_rate"])
            kinds["unknown_name"] = r["kind"]
            check("5 語彙に無い指標は unknown_name で mf query を呼ばない",
                  r["kind"] == "unknown_name" and r["mf_query_ran"] is False, f"{r['kind']} {r.get('unknown')}")
            r = await call("query_metrics", metrics=["revenue_amount"], group_by=["revenue_record__plan"])
            check("5 語彙に無い切り口も unknown_name", r["kind"] == "unknown_name", f"{r['kind']} {r.get('unknown')}")
            r = await call("query_metrics", metrics=["revenue_amount"],
                           where=["Dimension('revenue_record__currency') = 'JPY'"])
            kinds["bad_where"] = r["kind"]
            check("5 {{ }} の無い where は bad_where で mf query を呼ばない",
                  r["kind"] == "bad_where" and r["mf_query_ran"] is False, r["kind"])
            r = await call("query_metrics", metrics=["revenue_amount"],
                           where=["{{ Dimension('revenue_record__revenue_month') }} = '2026-02'"])
            kinds["mf_error"] = r["kind"]
            check("5 mf の書き方のエラーは mf_error で、mf の文を返す",
                  r["kind"] == "mf_error" and "Conversion Error" in r.get("text", ""), r["kind"])
            check("5 4つの kind がすべて違う", len(set(kinds.values())) == 4, str(kinds))

            # 条件6：run_sql で書き込み・外のファイルが通らない
            r = await call("run_sql", sql="SELECT current_setting('enable_external_access') AS ext, "
                                          "current_setting('lock_configuration') AS locked;")
            check("6 外部アクセスが切れ、設定が固まっている",
                  r["kind"] == "ok" and r["results"][0]["rows"] == [{"ext": False, "locked": True}], str(r.get("results")))
            r = await call("run_sql", sql="SELECT count(*) AS n FROM main_mart.dim_account;")
            check("6 読む SQL は通る", r["kind"] == "ok", f"{r['kind']} {r.get('results') or r.get('text')}")
            r = await call("run_sql", sql="SELECT 1 AS x WHERE false;")
            check("6 0行は empty", r["kind"] == "empty", r["kind"])
            for label, sql in [
                ("CREATE TABLE", "CREATE TABLE sl_mcp_probe AS SELECT 1 AS x;"),
                ("外のファイルを読む", "SELECT * FROM read_csv('../data_generation/output.sha256');"),
                ("外へ書き出す", "COPY (SELECT 1) TO 'sl_mcp_probe.csv';"),
                ("ATTACH", "ATTACH 'sl_mcp_probe.duckdb';"),
                ("ドットコマンド", ".shell echo sl_mcp_probe"),
            ]:
                r = await call("run_sql", sql=sql)
                check(f"6 {label} は sql_error", r["kind"] == "sql_error", (r.get("text") or "")[:90])


def in_process():
    # busy：使い捨ての DuckDB ファイルを、別のプロセスに書き込みで開かせたまま、run_sql を呼ぶ
    tmp = Path(tempfile.mkdtemp(prefix="sl_mcp_busy_"))
    db = tmp / "lock.duckdb"
    subprocess.run([str(guards.DUCKDB), str(db), "-c", "CREATE TABLE t AS SELECT 1 AS x;"], check=True)
    holder = subprocess.Popen([str(guards.DUCKDB), str(db)], stdin=subprocess.PIPE,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
    holder.stdin.write("SELECT 1;\n")
    holder.stdin.flush()
    time.sleep(1.5)
    saved = guards.WAREHOUSE
    try:
        guards.WAREHOUSE = db
        r = server.run_sql("SELECT x FROM t;")
    finally:
        guards.WAREHOUSE = saved
        holder.stdin.close()
        holder.wait(timeout=10)
    check("6 外のプロセスが書き込みで開いていると busy", r["kind"] == "busy", (r.get("text") or "")[:120])
    guards.WAREHOUSE = db
    try:
        r = server.run_sql("SELECT x FROM t;")
    finally:
        guards.WAREHOUSE = saved
    check("6 放したあとは ok", r["kind"] == "ok", str(r.get("results")))

    # 条件7：時間帯
    jst = guards.JST
    for hm, want in [((2, 49), False), ((2, 50), True), ((3, 14), True), ((3, 15), False)]:
        t = datetime.datetime(2026, 10, 30, *hm, tzinfo=jst)
        check(f"7 {hm[0]:02d}:{hm[1]:02d} は {'断る' if want else '通す'}", guards.in_maintenance(t) is want)
    saved_fn = guards.in_maintenance
    try:
        guards.in_maintenance = lambda now=None: True
        replies = [server.list_metrics(), server.get_dimensions("revenue_amount"),
                   server.query_metrics(["revenue_amount"]), server.run_sql("SELECT 1;")]
    finally:
        guards.in_maintenance = saved_fn
    check("7 時間帯には4つの道具とも maintenance と理由を返す",
          all(r["kind"] == "maintenance" and "dbt build" in r["message"] for r in replies),
          str([r["kind"] for r in replies]))


if __name__ == "__main__":
    before = sha256(guards.WAREHOUSE)
    asyncio.run(over_stdio())
    in_process()
    after = sha256(guards.WAREHOUSE)
    check("6 warehouse.duckdb の sha256 が試す前と同じ", before == after, f"{before[:12]} → {after[:12]}")
    print(f"\n{len(FAILS)} 件 FAIL" if FAILS else "\nすべて PASS")
    sys.exit(1 if FAILS else 0)
