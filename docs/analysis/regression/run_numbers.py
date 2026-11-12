"""回帰の試験の数字の層（R1）。bank.json の各問を2通りで解き直し、期待値と比べる。

(a) agent/sl_mcp/server.py の query_metrics・list_metrics を import して呼ぶ（mf を直接呼ばない）
(b) sql/<ID>.sql を server の run_sql で流す（duckdb を直接呼ばない）

使い方（リポジトリの直下で）：
    uv run --frozen --project agent/sl_mcp python docs/analysis/regression/run_numbers.py [--out 結果のファイル]
server の依存（mcp）が無い Python で起動されたときは、上の形で自分を起動し直す。

終了コード：0 すべて合う（未決を除く）／1 外れが1件以上／2 道具が maintenance か busy を返した（試験にならない）
"""
import argparse
import json
import os
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[2]
SL_MCP = REPO / "agent" / "sl_mcp"

try:
    import mcp  # noqa: F401  server の依存があるかだけを見る
except ImportError:
    if os.environ.get("R1_REEXEC"):
        sys.exit("agent/sl_mcp の環境でも mcp が import できない")
    os.environ["R1_REEXEC"] = "1"
    os.chdir(REPO)
    argv = ["uv", "run", "--frozen", "--project", "agent/sl_mcp", "python", str(pathlib.Path(__file__).resolve())]
    os.execvp("uv", argv + sys.argv[1:])

sys.path.insert(0, str(SL_MCP))
import server  # noqa: E402

NOT_A_TEST = ("maintenance", "busy")


class NotATest(Exception):
    pass


def key_of(values):
    return "|".join("(空)" if v is None else str(v) for v in values)


NUMERIC_TEXT = re.compile(r"-?\d+(\.\d+)?")


def same(expected, actual, tol):
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        # DuckDB の -json は、整数の合計（HUGEINT）を文字列で返す（例 "87395105"）。数字だけの文字列は数として比べる
        if isinstance(actual, str) and NUMERIC_TEXT.fullmatch(actual):
            actual = float(actual) if "." in actual else int(actual)
        if not isinstance(actual, (int, float)) or isinstance(actual, bool):
            return False
        return abs(expected - actual) <= tol + 1e-12
    return expected == actual


def table_from_sl(reply):
    cols = reply.get("columns", [])
    return [dict(zip(cols, row)) for row in reply.get("rows", [])]


def table_from_sql(reply):
    results = reply.get("results", [])
    # 1つの SQL ファイルは1つの文。最後の文の結果を見る
    return results[-1]["rows"] if results else []


def derive(rows, spec):
    for row in rows:
        num, den = row.get(spec["num"]), row.get(spec["den"])
        row[spec["name"]] = round(num / den, spec.get("round", 6)) if num is not None and den else None
    return rows


def compare(expect, reply, rows, tol):
    """期待と返事を比べ、(合うか, 問題の文のリスト, 見た値) を返す。"""
    kind = reply.get("kind")
    if kind in NOT_A_TEST:
        raise NotATest(f"{kind}: {reply.get('message')}")
    problems = []
    if kind != expect["kind"]:
        if reply.get("rows"):
            detail = f"columns={reply.get('columns')} rows={reply['rows']}"
        else:
            detail = reply.get("unknown") or " ".join((reply.get("text") or "").split())[:160]
        problems.append(f"kind が {kind}（期待は {expect['kind']}） {detail}")
        return False, problems, {}
    if "absent_metrics" in expect:
        names = {m["name"] for m in reply.get("metrics", [])}
        found = sorted(names & set(expect["absent_metrics"]))
        if found:
            problems.append(f"無いはずの指標がある: {found}")
        return not problems, problems, {"metrics": sorted(names)}
    if "rows" not in expect:
        return True, problems, {}
    if "derive" in expect:
        rows = derive(rows, expect["derive"])
    keycols = expect.get("key", [])
    got = {}
    for row in rows:
        got[key_of([row.get(c) for c in keycols])] = row
    seen = {}
    for k, want in expect["rows"].items():
        row = got.get(k)
        if row is None:
            problems.append(f"行 {k!r} が無い")
            continue
        for col, val in want.items():
            actual = row.get(col)
            seen[f"{k}:{col}" if k else col] = actual
            if not same(val, actual, tol):
                problems.append(f"{k + ' ' if k else ''}{col} = {actual}（期待 {val}、幅 {tol}）")
    if expect.get("exact_keys"):
        extra = sorted(set(got) - set(expect["rows"]))
        if extra:
            problems.append(f"期待に無い行: {extra}")
    return not problems, problems, seen


def run_sl(call, tol):
    tool = call["tool"]
    if tool == "query_metrics":
        reply = server.query_metrics(**call["args"])
    elif tool == "list_metrics":
        reply = server.list_metrics()
    else:
        raise ValueError(f"知らない道具: {tool}")
    return compare(call["expect"], reply, table_from_sl(reply), tol)


def run_sql(spec, tol):
    sql = (HERE / spec["file"]).read_text()
    reply = server.run_sql(sql)
    return compare(spec["expect"], reply, table_from_sql(reply), tol)


def fmt_seen(seen):
    return ", ".join(f"{k}={v}" for k, v in seen.items())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", default=str(HERE / "bank.json"))
    ap.add_argument("--out", help="結果を Markdown でこのファイルにも書く")
    args = ap.parse_args()

    bank = json.loads(pathlib.Path(args.bank).read_text())["questions"]
    lines = ["| 問 | (a) SL | (b) SQL | 判定 | 見た値・外れの中身 |", "|---|---|---|---|---|"]
    counts = {"調べた問": 0, "合う": 0, "外れる": 0, "未決": 0}
    sides = {"a_ok": 0, "a_ng": 0, "b_ok": 0, "b_ng": 0}
    try:
        for q in bank:
            counts["調べた問"] += 1
            if q.get("status") != "有効":
                counts["未決"] += 1
                lines.append(f"| {q['id']} | — | — | 未決 | {q.get('status')} |")
                continue
            tol = q.get("tolerance", {}).get("abs", 0)
            a_ok, notes = True, []
            for call in q["sl"]:
                ok, problems, seen = run_sl(call, tol)
                label = call.get("label", call["tool"])
                a_ok &= ok
                notes.append(f"(a){label}: " + ("; ".join(problems) if problems else (fmt_seen(seen) or call["expect"]["kind"])))
            b_ok, problems, seen = run_sql(q["sql"], tol)
            notes.append("(b): " + ("; ".join(problems) if problems else fmt_seen(seen)))
            sides["a_ok" if a_ok else "a_ng"] += 1
            sides["b_ok" if b_ok else "b_ng"] += 1
            verdict = "合う" if a_ok and b_ok else "外れる"
            counts[verdict] += 1
            mark = lambda x: "合う" if x else "外れる"  # noqa: E731
            cell = " / ".join(notes).replace("|", "¦")
            lines.append(f"| {q['id']} | {mark(a_ok)} | {mark(b_ok)} | {verdict} | {cell} |")
    except NotATest as e:
        print(f"試験にならない（道具の返事）: {e}")
        sys.exit(2)

    lines.append("")
    lines.append("件数：" + "、".join(f"{k} {v}" for k, v in counts.items())
                 + f"（(a) 合う {sides['a_ok']}・外れる {sides['a_ng']}、(b) 合う {sides['b_ok']}・外れる {sides['b_ng']}）")
    text = "\n".join(lines)
    print(text)
    if args.out:
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("a") as f:
            f.write(text + "\n")
    sys.exit(1 if counts["外れる"] else 0)


if __name__ == "__main__":
    main()
