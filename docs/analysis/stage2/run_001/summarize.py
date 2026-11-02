"""段階2 run_001：回し終わった記録（runs/）から、下書きの表を作る。○×の最終判断はしない（判定は人がする）。

- 軸1：5-4 の run_002/auto_score.py を、変えずにそのまま呼ぶ（runs/ をそのまま渡す。記録の欄は auto_score の読み込みに合わせてある）
- 軸3・軸4：axis_draft.py をそのまま呼ぶ
- 書き出すもの（このフォルダ）：auto_axis1.tsv、axis34_draft.tsv、drafts.md（数の表と「要読み」の一覧）

使い方（リポジトリの直下で）: python3 docs/analysis/stage2/run_001/summarize.py
"""
import collections, datetime, json, pathlib, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[3]
RUNS = HERE / "runs"
AUTO = REPO / "docs/analysis/5-4/run_002/auto_score.py"
GROUPS = ["sl_mcp", "sql_mcp"]
QIDS = ["A1", "A3", "B2", "B3", "B4", "B5", "C1", "C2", "C3", "D1", "D2", "D5", "D6"]
TEXT_Q = {"C1", "C3", "D6"}   # 文で答える問（要読み）


def run(args):
    r = subprocess.run(args, cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"{args[1]} が失敗した:\n{r.stdout}\n{r.stderr}")
    return r.stdout


def main():
    recs = {f.stem: json.loads(f.read_text()) for f in sorted(RUNS.glob("*.json"))}

    auto_out = run([sys.executable, str(AUTO), str(RUNS)])
    (HERE / "auto_axis1.tsv").write_text(auto_out)
    axis1 = {}
    for line in auto_out.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        stem, verdict, *rest = line.split("\t")
        axis1[stem] = (verdict, (rest[0] if rest else "").strip())

    a34_out = run([sys.executable, str(HERE / "axis_draft.py"), str(RUNS)])
    (HERE / "axis34_draft.tsv").write_text(a34_out)
    a34 = {}
    for line in a34_out.splitlines()[1:]:
        f = line.split("\t")
        a34[f[0]] = {"axis3": f[2], "axis3_reason": f[3], "axis4": f[4], "axis4_reasons": f[5], "missing": f[6]}

    L = ["# 段階2 run_001 の下書き（機械で作った数。○×の最終判断はしていない）", ""]
    L.append(f"- 作った日時：{datetime.datetime.now().astimezone().isoformat(timespec='seconds')}")
    L.append(f"- 記録：`runs/` の {len(recs)} 本。軸1 は `auto_axis1.tsv`（5-4 の `run_002/auto_score.py` をそのまま呼んだ出力）、"
             "軸3・軸4 は `axis34_draft.tsv`（`axis_draft.py` の出力）")
    L.append(f"- auto_score の1行目：`{auto_out.splitlines()[0]}`")
    L.append("")

    # 軸1：組ごと・問ごと
    L += ["## 軸1 の自動の下書き（3回のうちの数）", "", "| 問 | " + " | ".join(GROUPS) + " |", "|---|" + "---|" * len(GROUPS)]
    totals = {g: collections.Counter() for g in GROUPS}
    for q in QIDS:
        cells = []
        for g in GROUPS:
            c = collections.Counter(axis1.get(f"{g}_{q}_r{r}", ("記録なし", ""))[0] for r in (1, 2, 3))
            totals[g].update(c)
            cells.append(" ".join(f"{k}{c[k]}" for k in ("○", "×", "答えなし", "記録なし") if c[k]))
        L.append(f"| {q} | " + " | ".join(cells) + " |")
    L.append("| 計 | " + " | ".join(" ".join(f"{k}{totals[g][k]}" for k in ("○", "×", "答えなし", "記録なし") if totals[g][k])
                                    for g in GROUPS) + " |")
    L.append("")

    # 軸3：sl_mcp の内訳
    L += ["## 軸3 道具の順番の下書き（sl_mcp だけ）", ""]
    c3 = collections.Counter(v["axis3"] for k, v in a34.items() if k.startswith("sl_mcp_"))
    L += ["| 判定 | 本数 |", "|---|---|"] + [f"| {k} | {n} |" for k, n in c3.most_common()]
    r3 = collections.Counter((v["axis3"], v["axis3_reason"]) for k, v in a34.items() if k.startswith("sl_mcp_"))
    L += ["", "| 判定 | 理由 | 本数 |", "|---|---|---|"] + [f"| {a} | {r} | {n} |" for (a, r), n in sorted(r3.items())]
    L += ["", "問ごと（r1 / r2 / r3）：", "", "| 問 | 軸3 |", "|---|---|"]
    for q in QIDS:
        L.append(f"| {q} | " + " / ".join(a34.get(f"sl_mcp_{q}_r{r}", {}).get("axis3", "記録なし") for r in (1, 2, 3)) + " |")
    L.append("")

    # 軸4：要確認の数
    L += ["## 軸4 札の読み方の下書き（要確認の数）", "", "| 組 | 要確認 | 問題なし |", "|---|---|---|"]
    for g in GROUPS:
        c4 = collections.Counter(v["axis4"] for k, v in a34.items() if k.startswith(g + "_"))
        L.append(f"| {g} | {c4['要確認']} | {c4['問題なし']} |")
    reasons = collections.Counter()
    for k, v in a34.items():
        for r in filter(None, v["axis4_reasons"].split(" / ")):
            if r != "—":
                reasons[(k.rsplit("_", 2)[0], r)] += 1
    L += ["", "| 組 | 理由 | 本数 |", "|---|---|---|"] + [f"| {g} | {r} | {n} |" for (g, r), n in sorted(reasons.items())]
    L.append("")

    # problems・時間・費用
    probs = {k: r["problems"] for k, r in recs.items() if r.get("problems")}
    starts = [r["started_at"] for r in recs.values()]
    ends = [r["ended_at"] for r in recs.values()]
    span = (datetime.datetime.fromisoformat(max(ends)) - datetime.datetime.fromisoformat(min(starts))) if recs else None
    dur = [r.get("duration_ms") or 0 for r in recs.values()]
    cost = {g: sum(r.get("total_cost_usd") or 0 for r in recs.values() if r["group"] == g) for g in GROUPS}
    L += ["## problems・時間・費用", ""]
    L.append(f"- problems が空でない記録：{len(probs)} 本" + (f"（{', '.join(probs)}）" if probs else ""))
    L.append(f"- 最初の開始 {min(starts) if recs else '—'} → 最後の終了 {max(ends) if recs else '—'}（経過 {span}）")
    L.append(f"- 1本の時間（duration_ms）：合計 {sum(dur)/1000:.0f} 秒、平均 {sum(dur)/len(dur)/1000:.1f} 秒、"
             f"最短 {min(dur)/1000:.1f} 秒、最長 {max(dur)/1000:.1f} 秒" if dur else "- 1本の時間：—")
    L.append(f"- total_cost_usd の合計（見積もり。請求額ではない）：{sum(cost.values()):.4f}（"
             + "、".join(f"{g} {v:.4f}" for g, v in cost.items()) + "）")
    turns = collections.Counter(r.get("result_subtype") for r in recs.values())
    L.append(f"- 終わり方（result の subtype）：{dict(turns)}")
    L.append("")

    # 要読み
    L += ["## 要読み（人が全文を読んで決める本）", "",
          "文で答える問（C1・C3・D6）と、クエリ（query_metrics・run_sql）を呼ばずに答えた本。", "",
          "| 記録 | 理由 | 軸1 の自動の下書き |", "|---|---|---|"]
    for k, r in recs.items():
        why = []
        if r["id"] in TEXT_Q:
            why.append("文で答える問")
        if r.get("no_query"):
            why.append("クエリを呼ばずに答えた")
        if why:
            L.append(f"| {k} | {'・'.join(why)} | {axis1.get(k, ('—', ''))[0]} |")
    (HERE / "drafts.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
