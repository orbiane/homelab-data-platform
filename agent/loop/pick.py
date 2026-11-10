#!/usr/bin/env python3
"""NEXT.md の表と GitHub の PR から、自律ループが次に進める1件の ID を決める（L0）。

使い方:
  python3 agent/loop/pick.py [--next NEXT.md] [--prs-json FILE] [--status]
  python3 agent/loop/pick.py selftest

- 出力：選んだ ID を1行。選べるものが無ければ何も出さない（理由は stderr に）
- 決める規則は docs/agent/loop.md の 2（ADR-009 の決定6）。モデルには選ばせない
  - 状態：その ID の作業ブランチ（auto/<ID>・owner/<ID>、後ろに `-` で始まる名前を付けたもの）の PR で決まる
    済み＝マージされた PR がある、進行中＝開いた PR がある、断られた＝閉じた PR だけがある
  - 表を上から見て、種類が loop、PR がまだ無い、依存がすべて済み、の最初の行
  - 依存の ALL は「ほかのすべての行が、済みか断られた」
  - 開いているループの PR（auto/ のブランチ）が3つ以上なら、何も選ばない
- --prs-json：gh を呼ぶ代わりに、`gh pr list --json number,headRefName,state` の形の JSON を読む（試しと記録用）
"""
import json
import pathlib
import re
import subprocess
import sys

MAX_OPEN_LOOP_PRS = 3
DONE, OPEN, REJECTED, NONE = "済み", "進行中", "断られた", "PRなし"


def parse_table(text):
    """「作業の一覧」の表から [(ID, 種類, [依存])] を、上から順に返す。"""
    rows, in_table = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            in_table = line.startswith("## 作業の一覧")
            continue
        if not in_table or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4 or cells[0] in ("ID", "") or set(cells[0]) <= set("-: "):
            continue
        kind = cells[2].strip("` ")
        dep = cells[3]
        deps = [] if dep in ("—", "-", "") else [d.strip() for d in dep.split(",") if d.strip()]
        rows.append((cells[0], kind, deps))
    return rows


def branch_id_re(task_id):
    return re.compile(r"^(?:auto|owner)/" + re.escape(task_id) + r"(?:-.*)?$")


def status_of(prs):
    """1つの ID の PR の並び（各 {"state": "OPEN"|"MERGED"|"CLOSED", ...}）から状態を返す。

    返す値は DONE（済み）・OPEN（進行中）・REJECTED（断られた）・NONE（PR なし）のどれか。
    マージされた PR があれば、開いた PR が残っていても済み（仮決め L0-4。続きの作業は別の行として起こすため、
    同じ ID の開いた PR は追加の直しとして扱い、後ろの行を待たせない）。
    """
    states = {p.get("state") for p in prs}
    if "MERGED" in states:
        return DONE
    if "OPEN" in states:
        return OPEN
    if "CLOSED" in states:
        return REJECTED
    return NONE


def statuses(rows, prs):
    out = {}
    for task_id, _, _ in rows:
        r = branch_id_re(task_id)
        out[task_id] = status_of([p for p in prs if r.match(p.get("headRefName", ""))])
    return out


def choose(rows, prs, max_open=MAX_OPEN_LOOP_PRS):
    """(選んだ ID か None, 理由) を返す。"""
    open_loop = [p for p in prs if p.get("state") == "OPEN" and p.get("headRefName", "").startswith("auto/")]
    if len(open_loop) >= max_open:
        return None, f"開いているループの PR が {len(open_loop)} 件（{max_open} 件以上）。持ち主のマージを待つ"
    st = statuses(rows, prs)
    for task_id, kind, deps in rows:
        if kind != "loop" or st[task_id] != NONE:
            continue
        if deps == ["ALL"]:
            ok = all(st[t] in (DONE, REJECTED) for t, _, _ in rows if t != task_id)
        else:
            ok = all(st.get(d) == DONE for d in deps)
        if ok:
            return task_id, f"{task_id} を選んだ（種類 loop、PR なし、依存 {deps or 'なし'} がすべて済み）"
    return None, "選べる行が無い（種類 loop で、PR が無く、依存がすべて済みの行が無い）"


def fetch_prs(cwd=None):
    r = subprocess.run(["gh", "pr", "list", "--state", "all", "--limit", "1000",
                        "--json", "number,headRefName,state"],
                       capture_output=True, text=True, cwd=cwd, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"gh pr list が失敗しました: {r.stderr.strip()}")
    return json.loads(r.stdout)


def selftest():
    table = "\n".join([
        "## 作業の一覧（上から順に優先）", "",
        "| ID | 作業 | 種類 | 依存 | 指示書 |", "|---|---|---|---|---|",
        "| L0 | 据え付け | `attended` | — | x |",
        "| M2 | 小さな作業 | `loop` | L0 | x |",
        "| M1 | 小さな作業 | `loop` | L0 | x |",
        "| R1 | 回帰1 | `loop` | L0 | x |",
        "| R2 | 回帰2 | `loop` | R1 | x |",
        "| R3a | 条件 | `loop` | R2 | x |",
        "| Q9 | 決めごと | `owner` | — | x |",
        "| Z1 | 記録 | `loop` | ALL | x |", "",
        "## 小さな作業", "| ID | これは表ではない | `loop` | — | x |",
    ])
    rows = parse_table(table)

    def pr(n, ref, state):
        return {"number": n, "headRefName": ref, "state": state}

    cases = [
        # (名前, PR の並び, 期待する ID)
        ("表の読み取り：8行、小さな作業の節は読まない", None, None),
        ("L0 が済んでいない：L0 に依存する行は選ばない（attended の L0 も選ばない）", [], None),
        ("L0 が進行中（開いた PR）：まだ選ばない", [pr(1, "owner/L0-loop-setup", "OPEN")], None),
        ("L0 が済み：上から最初の M2", [pr(1, "owner/L0-loop-setup", "MERGED")], "M2"),
        ("M2 が進行中：次の M1", [pr(1, "owner/L0-loop-setup", "MERGED"), pr(2, "auto/M2", "OPEN")], "M1"),
        ("M2 が断られた（閉じた PR だけ）：やり直さず M1",
         [pr(1, "owner/L0-loop-setup", "MERGED"), pr(2, "auto/M2", "CLOSED")], "M1"),
        ("M2 が済み、M1 は後ろに名前を付けたブランチで進行中：R1",
         [pr(1, "owner/L0-loop-setup", "MERGED"), pr(2, "auto/M2", "MERGED"), pr(3, "auto/M1-claude-md", "OPEN")], "R1"),
        ("依存が足りない：R1 が進行中なら R2 は選ばず、選べるものは無い",
         [pr(1, "owner/L0-loop-setup", "MERGED"), pr(2, "auto/M2", "MERGED"), pr(3, "auto/M1", "MERGED"),
          pr(4, "auto/R1", "OPEN")], None),
        ("R1 が済み：R2",
         [pr(1, "owner/L0-loop-setup", "MERGED"), pr(2, "auto/M2", "MERGED"), pr(3, "auto/M1", "MERGED"),
          pr(4, "auto/R1", "MERGED")], "R2"),
        ("開いたループの PR が3つ：何も選ばない",
         [pr(1, "owner/L0-loop-setup", "MERGED"), pr(2, "auto/M2", "OPEN"), pr(3, "auto/M1", "OPEN"),
          pr(4, "auto/R1", "OPEN")], None),
        ("開いた PR が3つでも、owner/ のブランチは数えない",
         [pr(1, "owner/L0-loop-setup", "MERGED"), pr(2, "auto/M2", "OPEN"), pr(3, "auto/M1", "OPEN"),
          pr(4, "owner/X1", "OPEN")], "R1"),
        ("ID の取り違え：auto/R3ab は R3a の PR ではない",
         [pr(1, "owner/L0-loop-setup", "MERGED"), pr(2, "auto/M2", "MERGED"), pr(3, "auto/M1", "MERGED"),
          pr(4, "auto/R1", "MERGED"), pr(5, "auto/R2", "MERGED"), pr(6, "auto/R3ab", "OPEN")], "R3a"),
        ("ALL：ほかがすべて済みか断られた（owner の Q9 も）なら Z1",
         [pr(1, "owner/L0-loop-setup", "MERGED"), pr(2, "auto/M2", "MERGED"), pr(3, "auto/M1", "CLOSED"),
          pr(4, "auto/R1", "MERGED"), pr(5, "auto/R2", "MERGED"), pr(6, "auto/R3a", "MERGED"),
          pr(7, "owner/Q9", "MERGED")], "Z1"),
        ("ALL：owner の Q9 が残っていれば Z1 は選ばない",
         [pr(1, "owner/L0-loop-setup", "MERGED"), pr(2, "auto/M2", "MERGED"), pr(3, "auto/M1", "CLOSED"),
          pr(4, "auto/R1", "MERGED"), pr(5, "auto/R2", "MERGED"), pr(6, "auto/R3a", "MERGED")], None),
    ]
    bad = 0
    for name, prs, expect in cases:
        if prs is None:
            got = [r[0] for r in rows]
            ok = got == ["L0", "M2", "M1", "R1", "R2", "R3a", "Q9", "Z1"] and rows[-1][2] == ["ALL"]
            print(f"{'OK ' if ok else 'NG '} {name}: {got}")
        else:
            got, why = choose(rows, prs)
            ok = got == expect
            print(f"{'OK ' if ok else 'NG '} {name}: 期待={expect} 実際={got} | {why}")
        bad += 0 if ok else 1
    # 状態の決め方そのもの
    for prs, expect in [
        ([], NONE),
        ([{"state": "MERGED"}], DONE),
        ([{"state": "OPEN"}], OPEN),
        ([{"state": "CLOSED"}], REJECTED),
        ([{"state": "CLOSED"}, {"state": "OPEN"}], OPEN),
        ([{"state": "CLOSED"}, {"state": "MERGED"}], DONE),
        ([{"state": "MERGED"}, {"state": "OPEN"}], DONE),  # 仮決め L0-4
    ]:
        got = status_of(prs)
        ok = got == expect
        bad += 0 if ok else 1
        print(f"{'OK ' if ok else 'NG '} 状態 {[p['state'] for p in prs]}: 期待={expect} 実際={got}")
    print(f"selftest：期待と違う {bad} 件")
    return 1 if bad else 0


def main(argv):
    if argv[1:2] == ["selftest"]:
        return selftest()
    next_path = pathlib.Path(__file__).resolve().parents[2] / "NEXT.md"
    prs_json = None
    show_status = "--status" in argv
    if "--next" in argv:
        next_path = pathlib.Path(argv[argv.index("--next") + 1])
    if "--prs-json" in argv:
        prs_json = pathlib.Path(argv[argv.index("--prs-json") + 1])
    rows = parse_table(next_path.read_text(encoding="utf-8"))
    prs = json.loads(prs_json.read_text(encoding="utf-8")) if prs_json else fetch_prs(next_path.parent)
    if show_status:
        st = statuses(rows, prs)
        for task_id, kind, deps in rows:
            sys.stderr.write(f"  {task_id:4} {kind:9} 依存={','.join(deps) or '—':10} 状態={st[task_id]}\n")
    chosen, why = choose(rows, prs)
    sys.stderr.write(f"pick: {why}\n")
    if chosen:
        print(chosen)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
