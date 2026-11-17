#!/usr/bin/env python3
"""NEXT.md の表と GitHub の PR から、自律ループが次に進める1件の ID を決める（L0、L1 で続きを足した）。

使い方:
  python3 agent/loop/pick.py [--next NEXT.md] [--prs-json FILE] [--logs DIR] [--status]
  python3 agent/loop/pick.py selftest

- 出力：選んだ ID を1行。選べるものが無ければ何も出さない（理由は stderr に）
- 決める規則は docs/agent/loop.md の 2（ADR-009 の決定6・決定8）。モデルには選ばせない。上から順に：
  1. 持ち主の決めの続き：開いたループの PR（auto/）に、最後のコミットより新しい「決め:」のコメント（1行目の先頭）がある
  2. レビューの直し：最新のレビュー（台本が出し、記録に残したもの）が今の先頭のコミットに「直しが要る」で、
     その PR での直しが2回未満。または、PR の本文の最初の行（HTML のコメントと空行を除く）が「途中」で、続きが3回未満
  3. 新しい行：表を上から見て、種類が loop、PR がまだ無い、依存がすべて済み、の最初の行
     開いているループの PR が3つ以上なら、3 は選ばない（1・2 は選ぶ）
  - 1・2 は、同じ引き金（決めのコメント・レビュー）のあとに、もう続きの回を始めていれば選ばない（空回りを止める）
  - 状態：その ID の作業ブランチ（auto/<ID>・owner/<ID>、後ろに `-` で始まる名前を付けたもの）の PR で決まる
    済み＝マージされた PR がある、進行中＝開いた PR がある、断られた＝閉じた PR だけがある
  - 依存の ALL は「ほかのすべての行が、済みか断られた」
- 1・2 で選んだときの ID は、ブランチ名の auto/ の後ろ（例：auto/L1-trial なら L1-trial）。表の行でなくてよい
- --prs-json：gh を呼ぶ代わりに JSON を読む（試しと記録用）。`gh pr list --json number,headRefName,state` の形に、
  開いた auto/ の PR だけ body・headRefOid・comments・commits を足したもの
- --logs：台本の記録（reviews.jsonl・runs.jsonl）の場所。既定 ~/homelab-loop/logs
"""
import datetime
import json
import pathlib
import re
import subprocess
import sys

MAX_OPEN_LOOP_PRS = 3
MAX_FIXES = 2          # レビューの直しは、同じ PR で2回まで
MAX_CONTINUES = 3      # 「途中」の続きは、同じ PR で3回まで
DONE, OPEN, REJECTED, NONE = "済み", "進行中", "断られた", "PRなし"
NEW, DECISION, FIX, CONTINUE = "新しい行", "決め", "直し", "途中"
VERDICTS = ("マージしてよい", "直しが要る", "持ち主の決めが要る")
# 台本（run.py）がレビューのコメントの1行目に付ける形。review.md の 3
REVIEW_LINE = re.compile(r"^レビュー: (" + "|".join(VERDICTS) + r")（([0-9a-f]{7,40})）$")
DECISION_PREFIXES = ("決め:", "決め：")  # 仮決め L1-3：全角のコロンも数える


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


def ts(s):
    """GitHub の `...Z` と、台本の記録の `+09:00` を、比べられる時刻にする。"""
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))


def first_line(text):
    return (text or "").lstrip("﻿").split("\n", 1)[0].rstrip("\r")


def is_script_review(comment, posted_urls):
    """台本が出したレビューのコメントなら (判定, 先頭のコミットの短い ID) を、そうでなければ None を返す。

    comment は gh の comments の1つ（{"url", "body", "createdAt"}）。posted_urls は、台本が
    gh pr comment で出したときに記録したコメントの URL の集合（~/homelab-loop/logs/reviews.jsonl）。
    """
    # 両方を求める（仮決め L1-4）。形だけだと、同じアカウントの誰でも同じ1行目を書ける（K9）。
    # 記録だけだと、出したあとに GitHub の画面で本文を書き換えられても気づけない
    if comment.get("url") not in posted_urls:
        return None
    m = REVIEW_LINE.match(first_line(comment.get("body")))
    return (m.group(1), m.group(2)) if m else None


def body_status_line(body):
    """PR の本文の最初の行。先頭の HTML のコメント（複数行も）と空行を飛ばす（仮決め L1-2）。

    ループの PR の本文は報告のファイル（--body-file）で、1行目は公開リポジトリの注意書きのコメントになる。
    見出しの `#` は外して返す。「# 途中：…」も「途中：…」も「途中」で始まる行として読む。
    """
    text, in_comment = (body or "").lstrip("﻿"), False
    for line in text.splitlines():
        s = line.strip()
        if in_comment:
            if "-->" in s:
                in_comment = False
            continue
        if s.startswith("<!--"):
            in_comment = "-->" not in s
            continue
        if s:
            return s.lstrip("#").strip()
    return ""


def tried_since(runs, pr_number, mode, since):
    """その PR で、その種類の続きの回を、since（引き金の時刻）より後に始めた回数。"""
    return sum(1 for r in runs
               if r.get("pr") == pr_number and r.get("cont") == mode and ts(r["at"]) > since)


def continuation(pr, posted_urls, runs):
    """開いたループの PR 1つについて、続きの (種類, 理由, 渡す文) か None を返す。"""
    comments = sorted(pr.get("comments") or [], key=lambda c: ts(c["createdAt"]))
    commits = pr.get("commits") or []
    head = pr.get("headRefOid", "")
    last_commit = max((ts(c["committedDate"]) for c in commits), default=None)
    n = pr["number"]

    # 1. 持ち主の決め：1行目の先頭が「決め:」。台本が出したコメントは数えない。最後のコミットより新しいもの
    decisions = [c for c in comments
                 if first_line(c["body"]).startswith(DECISION_PREFIXES)
                 and c.get("url") not in posted_urls
                 and (last_commit is None or ts(c["createdAt"]) > last_commit)]
    if decisions:
        c = decisions[-1]
        if tried_since(runs, n, DECISION, ts(c["createdAt"])) == 0:
            return DECISION, f"PR #{n} に、最後のコミットより新しい決めのコメントがある", c["body"]

    # 2. レビューの直し：台本のレビューだけを見る
    reviews = [(c, *is_script_review(c, posted_urls)) for c in comments if is_script_review(c, posted_urls)]
    if reviews:
        c, verdict, sha = reviews[-1]
        fixes_done = sum(1 for _, v, s in reviews if v == "直しが要る" and not head.startswith(s))
        if verdict == "直しが要る" and head.startswith(sha):
            if fixes_done >= MAX_FIXES:
                return None  # 3回目の直しは要らない。持ち主の決めを待つ（loop.md）
            if tried_since(runs, n, FIX, ts(c["createdAt"])) == 0:
                return FIX, f"PR #{n} の最新のレビュー（{sha}）が直しが要る。直しは {fixes_done} 回済み", c["body"]

    # 2'. 途中の続き
    if body_status_line(pr.get("body")).startswith(CONTINUE):
        done = sum(1 for r in runs if r.get("pr") == n and r.get("cont") == CONTINUE)
        if done < MAX_CONTINUES and (last_commit is None
                                     or tried_since(runs, n, CONTINUE, last_commit) == 0):
            return CONTINUE, f"PR #{n} の本文が途中。続きは {done} 回済み", ""
    return None


def choose_next(rows, prs, posted_urls=frozenset(), runs=(), max_open=MAX_OPEN_LOOP_PRS):
    """続き（決め・直し・途中）を先に、無ければ新しい行を選ぶ。

    返す値：{"id", "mode", "why"}、続きなら "pr"・"branch"・"trigger"（渡す文）も。選べなければ id は None。
    """
    open_loop = sorted((p for p in prs if p.get("state") == "OPEN" and p.get("headRefName", "").startswith("auto/")),
                       key=lambda p: p["number"])
    found = {}
    for p in open_loop:
        c = continuation(p, posted_urls, runs)
        if c:
            found.setdefault(c[0], (p, c))
    for mode in (DECISION, FIX, CONTINUE):
        if mode in found:
            p, (_, why, trigger) = found[mode]
            branch = p["headRefName"]
            return {"id": branch[len("auto/"):], "mode": mode, "why": why,
                    "pr": p["number"], "branch": branch, "trigger": trigger}
    if len(open_loop) >= max_open:
        return {"id": None, "mode": NEW,
                "why": f"続きは無い。開いているループの PR が {len(open_loop)} 件（{max_open} 件以上）。持ち主のマージを待つ"}
    task_id, why = choose(rows, prs, max_open=10 ** 9)
    return {"id": task_id, "mode": NEW, "why": why}


def read_jsonl(path):
    out = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def load_records(logs):
    """(台本が出したレビューのコメントの URL の集合, 続きの回の start の記録) を返す。"""
    logs = pathlib.Path(logs)
    posted = {e["url"] for e in read_jsonl(logs / "reviews.jsonl")
              if e.get("kind") == "posted" and e.get("url")}
    runs = [e for e in read_jsonl(logs / "runs.jsonl") if e.get("kind") == "start" and e.get("cont")]
    return posted, runs


def fetch_prs(cwd=None, details=True):
    r = subprocess.run(["gh", "pr", "list", "--state", "all", "--limit", "1000",
                        "--json", "number,headRefName,state"],
                       capture_output=True, text=True, cwd=cwd, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"gh pr list が失敗しました: {r.stderr.strip()}")
    prs = json.loads(r.stdout)
    if details:
        for p in prs:
            if p.get("state") == "OPEN" and p.get("headRefName", "").startswith("auto/"):
                p.update(fetch_pr(p["number"], cwd))
    return prs


def fetch_pr(number, cwd=None):
    r = subprocess.run(["gh", "pr", "view", str(number), "--json",
                        "number,headRefName,headRefOid,state,body,comments,commits"],
                       capture_output=True, text=True, cwd=cwd, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"gh pr view {number} が失敗しました: {r.stderr.strip()}")
    d = json.loads(r.stdout)
    d["comments"] = [{"url": c.get("url"), "body": c.get("body", ""), "createdAt": c["createdAt"]}
                     for c in d.get("comments") or []]
    d["commits"] = [{"oid": c["oid"], "committedDate": c["committedDate"]} for c in d.get("commits") or []]
    return d


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
    bad += selftest_continuation(rows, pr)
    print(f"selftest：期待と違う {bad} 件")
    return 1 if bad else 0


def selftest_continuation(rows, pr):
    """L1：続き（決め・直し・途中）の選び方。"""
    base = [pr(1, "owner/L0-loop-setup", "MERGED"), pr(2, "auto/M2", "MERGED")]
    H1, H2, H3 = "a" * 40, "b" * 40, "c" * 40
    U = "https://github.com/o/r/pull/{}#issuecomment-{}"

    def loop_pr(n, ref, head, commits, comments=(), body="<!-- 注意書き -->\n# M1 の報告"):
        return {"number": n, "headRefName": ref, "state": "OPEN", "headRefOid": head, "body": body,
                "commits": [{"oid": o, "committedDate": d} for o, d in commits],
                "comments": [{"url": U.format(n, i), "body": b, "createdAt": d} for i, (b, d) in enumerate(comments)]}

    def review(verdict, head):
        return f"レビュー: {verdict}（{head[:7]}）\n\n- 機械の確かめ：…"

    c1 = [(H1, "2026-11-15T01:00:00Z")]
    c2 = [(H1, "2026-11-15T01:00:00Z"), (H2, "2026-11-15T03:00:00Z")]
    c3 = c2 + [(H3, "2026-11-15T05:00:00Z")]
    posted_all = {U.format(n, i) for n in (3, 4) for i in range(5)}
    start = "2026-11-15T{}:00:00+09:00"  # 台本の記録は JST

    cases = [
        # (名前, PR, 記録した URL, 続きの記録, 期待する (ID, 種類))
        ("決め：最後のコミットより新しい「決め:」があれば、その PR の続き",
         [loop_pr(3, "auto/M1", H1, c1, [("決め: 推す案Aでよい", "2026-11-15T02:00:00Z")])], set(), [], ("M1", DECISION)),
        ("決め：全角のコロンも数える（仮決め L1-3）",
         [loop_pr(3, "auto/M1", H1, c1, [("決め：Aでよい", "2026-11-15T02:00:00Z")])], set(), [], ("M1", DECISION)),
        ("決め：最後のコミットより古い決めは数えない（もう続きを進めた）",
         [loop_pr(3, "auto/M1", H2, c2, [("決め: Aでよい", "2026-11-15T02:00:00Z")])], set(), [], ("R1", NEW)),
        ("決め：1行目の先頭でなければ数えない",
         [loop_pr(3, "auto/M1", H1, c1, [("了解。\n決め: Aでよい", "2026-11-15T02:00:00Z")])], set(), [], ("R1", NEW)),
        ("決め：レビューのコメントの中の「決め:」は数えない",
         [loop_pr(3, "auto/M1", H1, c1, [(review("マージしてよい", H1) + "\n決め: 勝手に決めた", "2026-11-15T02:00:00Z")])],
         posted_all, [], ("R1", NEW)),
        ("決め：同じ決めのあとに続きの回をもう始めていれば、選ばない（空回りを止める）",
         [loop_pr(3, "auto/M1", H1, c1, [("決め: Aでよい", "2026-11-15T02:00:00Z")])], set(),
         [{"at": start.format(12), "pr": 3, "cont": DECISION}], ("R1", NEW)),
        ("直し：最新のレビューが今の先頭に「直しが要る」なら直す",
         [loop_pr(3, "auto/M1", H1, c1, [(review("直しが要る", H1), "2026-11-15T02:00:00Z")])], posted_all, [],
         ("M1", FIX)),
        ("直し：2回目の直し（1回済み）も選ぶ",
         [loop_pr(3, "auto/M1", H2, c2, [(review("直しが要る", H1), "2026-11-15T02:00:00Z"),
                                          (review("直しが要る", H2), "2026-11-15T04:00:00Z")])], posted_all, [],
         ("M1", FIX)),
        ("直し：2回済んだら、3回目は選ばない（持ち主の決めを待つ）",
         [loop_pr(3, "auto/M1", H3, c3, [(review("直しが要る", H1), "2026-11-15T02:00:00Z"),
                                          (review("直しが要る", H2), "2026-11-15T04:00:00Z"),
                                          (review("直しが要る", H3), "2026-11-15T06:00:00Z")])], posted_all, [],
         ("R1", NEW)),
        ("直し：レビューが古い先頭のコミットのもの（もう直した）なら選ばない",
         [loop_pr(3, "auto/M1", H2, c2, [(review("直しが要る", H1), "2026-11-15T02:00:00Z")])], posted_all, [],
         ("R1", NEW)),
        ("直し：形が同じでも、台本が記録していないコメントは数えない",
         [loop_pr(3, "auto/M1", H1, c1, [(review("直しが要る", H1), "2026-11-15T02:00:00Z")])], set(), [],
         ("R1", NEW)),
        ("直し：記録にあっても、1行目の形が違えば数えない",
         [loop_pr(3, "auto/M1", H1, c1, [("レビュー：直しが要る\n", "2026-11-15T02:00:00Z")])], posted_all, [],
         ("R1", NEW)),
        ("直し：マージしてよい なら選ばない",
         [loop_pr(3, "auto/M1", H1, c1, [(review("マージしてよい", H1), "2026-11-15T02:00:00Z")])], posted_all, [],
         ("R1", NEW)),
        ("決めが直しより先：別の PR に直しがあっても、決めの PR を選ぶ",
         [loop_pr(3, "auto/M1", H1, c1, [(review("直しが要る", H1), "2026-11-15T02:00:00Z")]),
          loop_pr(4, "auto/R1", H1, c1, [("決め: Bにする", "2026-11-15T02:00:00Z")])], {U.format(3, 0)}, [],
         ("R1", DECISION)),
        ("途中：本文の最初の行（注意書きのコメントを除く）が「途中」なら続ける",
         [loop_pr(3, "auto/M1", H1, c1, body="<!-- 注意書き\n2行目 -->\n\n# 途中：M1 の報告")], set(), [], ("M1", CONTINUE)),
        ("途中：3回続けたら選ばない",
         [loop_pr(3, "auto/M1", H1, c1, body="途中：M1")], set(),
         [{"at": start.format(h), "pr": 3, "cont": CONTINUE} for h in ("08", "09", "10")], ("R1", NEW)),
        ("途中：続きの回のあとにコミットが無ければ、もう選ばない",
         [loop_pr(3, "auto/M1", H1, c1, body="途中：M1")], set(), [{"at": start.format(11), "pr": 3, "cont": CONTINUE}],
         ("R1", NEW)),
        ("試しの PR：表の行でなくても、auto/L1-trial の決めの続きは L1-trial",
         [loop_pr(5, "auto/L1-trial", H1, c1, [(review("マージしてよい", H1), "2026-11-15T02:00:00Z"),
                                                ("決め: 試し", "2026-11-15T03:00:00Z")])], posted_all, [],
         ("L1-trial", DECISION)),
        ("開いたループの PR が3つでも、続きは選ぶ",
         [loop_pr(3, "auto/M1", H1, c1), loop_pr(4, "auto/R1", H1, c1, [("決め: Bにする", "2026-11-15T02:00:00Z")]),
          loop_pr(6, "auto/R2", H1, c1)], set(), [], ("R1", DECISION)),
        ("開いたループの PR が3つで、続きが無ければ何も選ばない",
         [loop_pr(3, "auto/M1", H1, c1), loop_pr(4, "auto/R1", H1, c1), loop_pr(6, "auto/R2", H1, c1)], set(), [],
         (None, NEW)),
    ]
    bad = 0
    for name, prs, posted, runs, expect in cases:
        got = choose_next(rows, base + prs, posted, runs)
        ok = (got["id"], got["mode"]) == expect
        bad += 0 if ok else 1
        print(f"{'OK ' if ok else 'NG '} {name}: 期待={expect} 実際={(got['id'], got['mode'])} | {got['why']}")
    return bad


def main(argv):
    if argv[1:2] == ["selftest"]:
        return selftest()
    next_path = pathlib.Path(__file__).resolve().parents[2] / "NEXT.md"
    prs_json = None
    logs = pathlib.Path.home() / "homelab-loop" / "logs"
    show_status = "--status" in argv
    if "--next" in argv:
        next_path = pathlib.Path(argv[argv.index("--next") + 1])
    if "--prs-json" in argv:
        prs_json = pathlib.Path(argv[argv.index("--prs-json") + 1])
    if "--logs" in argv:
        logs = pathlib.Path(argv[argv.index("--logs") + 1])
    rows = parse_table(next_path.read_text(encoding="utf-8"))
    prs = json.loads(prs_json.read_text(encoding="utf-8")) if prs_json else fetch_prs(next_path.parent)
    if show_status:
        st = statuses(rows, prs)
        for task_id, kind, deps in rows:
            sys.stderr.write(f"  {task_id:4} {kind:9} 依存={','.join(deps) or '—':10} 状態={st[task_id]}\n")
    posted, runs = load_records(logs)
    got = choose_next(rows, prs, posted, runs)
    sys.stderr.write(f"pick: [{got['mode']}] {got['why']}\n")
    if got["id"]:
        print(got["id"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
