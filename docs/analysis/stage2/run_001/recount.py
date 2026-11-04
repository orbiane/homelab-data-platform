"""段階2 run_001：scores.md の数を、runs/ の記録から2通りに数え直して突き合わせる。

1. final_scores.tsv から（runs/*.json の78本と1本ずつ対応することを先に確かめる）
2. scores.md の「問ごと（r1 / r2 / r3）」の表の1本ずつの印から。軸3 はさらに、runs/ の道具の順番から規則で数え直す。
   印は、runs/ の○の本のクエリの WHERE 句から機械で拾った本と突き合わせる

合わない所があれば全部出して、終了コード 1 で終わる。
使い方（リポジトリの直下で）: python3 docs/analysis/stage2/run_001/recount.py
"""
import collections, csv, json, pathlib, re, sys

HERE = pathlib.Path(__file__).resolve().parent
GROUPS = ["sl_mcp", "sql_mcp"]
QIDS = ["A1", "A3", "B2", "B3", "B4", "B5", "C1", "C2", "C3", "D1", "D2", "D5", "D6"]
SL = {"list_metrics", "get_dimensions", "query_metrics"}
bad = []
checked = collections.Counter()


def same(what, got, want):
    checked[what.split("：")[0]] += 1
    if got != want:
        bad.append(f"{what}: 数え直し {got!r} / 期待 {want!r}")


def cell(c):
    """「○3 ×1」の形にする"""
    return " ".join(f"{k}{c[k]}" for k in ("○", "×", "答えなし") if c[k])


def section(md, title):
    """見出しから、次の見出し（高さを問わない）まで"""
    m = re.search(rf"^#+ {re.escape(title)}\s*$", md, re.M)
    if not m:
        bad.append(f"scores.md に見出しが無い：{title}")
        return ""
    rest = md[m.end():]
    n = re.search(r"^#+ ", rest, re.M)
    return rest[: n.start()] if n else rest


def table(text):
    rows = []
    for line in text.splitlines():
        if line.startswith("|") and not re.match(r"^\|[-|\s]+\|$", line):
            rows.append([c.strip() for c in line.strip().strip("|").split("|")])
    return rows[1:]   # 見出しの行を外す


# ---- 読み込みと、記録との対応 ----
recs = {}
for f in sorted((HERE / "runs").glob("*.json")):
    recs[f.stem] = json.loads(f.read_text())
keys = {(r["group"], r["id"], r["rep"]) for r in recs.values()}
same("記録：ファイルの数", len(recs), 78)
same("記録：組×問×回の数", len(keys), 78)
fin = {r["file"]: r for r in csv.DictReader(open(HERE / "final_scores.tsv"), delimiter="\t")}
same("記録：final_scores.tsv の本", sorted(fin), sorted(recs))
for s, r in fin.items():
    if s in recs:
        same(f"記録：{s} の組・問・回", (r["group"], r["id"], int(r["rep"])),
             (recs[s]["group"], recs[s]["id"], recs[s]["rep"]))
auto = {}
for line in (HERE / "auto_axis1.tsv").read_text().splitlines():
    if line.strip() and not line.startswith("#"):
        s, v, *_ = line.split("\t")
        auto[s] = v
draft = {r["file"]: r for r in csv.DictReader(open(HERE / "axis34_draft.tsv"), delimiter="\t")}
for s, r in fin.items():
    same(f"下書き：{s} の自動の軸1", r["auto_axis1"], auto.get(s))
    same(f"下書き：{s} の軸3 の下書き", r["axis3_draft"], draft[s]["axis3"])
    same(f"下書き：{s} の軸3 の確定（要確認→守った）", r["axis3"], {"要確認": "守った"}.get(r["axis3_draft"], r["axis3_draft"]))

md = (HERE / "scores.md").read_text()

# ---- 1通り目：final_scores.tsv から ----
c1 = {(g, q): collections.Counter(r["axis1"] for r in fin.values() if r["group"] == g and r["id"] == q)
      for g in GROUPS for q in QIDS}
tot1 = {g: sum((c1[(g, q)] for q in QIDS), collections.Counter()) for g in GROUPS}
summary = {row[0]: row[1:] for row in table(section(md, "集計：軸1（3回のうち）"))}
for q in QIDS:
    same(f"軸1 の集計（tsv）：{q}", summary.get(q), [cell(c1[(g, q)]) for g in GROUPS])
same("軸1 の集計（tsv）：計", summary.get("計"), [cell(tot1[g]) for g in GROUPS])
types = {"A": ["A1", "A3"], "B": ["B2", "B3", "B4", "B5"], "C": ["C1", "C2", "C3"], "D": ["D1", "D2", "D5", "D6"]}
trows = {row[0][0]: row for row in table(section(md, "型ごと")) if row[0][0] in "ABCD計"}
for t, qs in types.items():
    same(f"型ごと（tsv）：{t}", trows.get(t, [])[2:],
         [cell(sum((c1[(g, q)] for q in qs), collections.Counter())) for g in GROUPS])
same("型ごと（tsv）：計", trows.get("計", [])[2:], [cell(tot1[g]) for g in GROUPS])

abc = {}
for g in GROUPS:
    rs = [r for r in fin.values() if r["group"] == g and r["id"][0] in "ABC"]
    abc[g] = [str(sum(r["axis1"] == "○" for r in rs)), str(sum(r["axis1"] == "○" and not r["mark"] for r in rs)),
              str(sum(r["axis1"] == "○" and bool(r["mark"]) for r in rs)), str(sum(r["axis1"] == "×" for r in rs))]
abc_md = {row[0]: row[1:] for row in table(section(md, "A〜C 型の27本"))}
for g in GROUPS:
    same(f"A〜C（tsv）：{g}", abc_md.get(g), abc[g])
line = section(md, "判定の線への当てはめ")
same("判定の線（tsv）：条件1の数", f"sql_mcp {abc['sql_mcp'][1]}、sl_mcp {abc['sl_mcp'][1]}" in line, True)
same("判定の線（tsv）：条件2の数", f"| 満たさない | {abc['sql_mcp'][2]}本。" in line, True)
same("判定の線（tsv）：条件1は sql_mcp の印の無い○ ≥ sl_mcp か", int(abc["sql_mcp"][1]) >= int(abc["sl_mcp"][1]),
     "| 1. sql_mcp の印の無い○が sl_mcp 以上 | 満たした" in line)
same("判定の線（tsv）：条件2は印のある○が0本か", abc["sql_mcp"][2] == "0",
     "| 2. sql_mcp の「値は合ったが数え方が違う」○が0本 | 満たした" in line)

a3 = collections.Counter(r["axis3"] for r in fin.values() if r["group"] == "sl_mcp")
a3_md = {row[0]: row[1] for row in table(section(md, "軸3（sl_mcp の39本）"))}
same("軸3（tsv）", {k: int(v) for k, v in a3_md.items()}, dict(a3))
a4_md = {row[0]: row[1:] for row in table(section(md, "軸4（2組の78本）")) if row[0] in GROUPS}
for g in GROUPS:
    c = collections.Counter(r["axis4"] for r in fin.values() if r["group"] == g)
    same(f"軸4（tsv）：{g}", a4_md.get(g), [str(c["問題なし"]), str(c["出せない数がある"])])

diff = sorted(s for s, r in fin.items() if r["auto_axis1"] != r["axis1"])
diff_md = table(section(md, "自動の下書きと食い違った本（16本）"))
same("食い違い（tsv）：本", sorted(row[0] for row in diff_md), diff)
same("食い違い（tsv）：見出しの本数", f"（{len(diff)}本）", "（16本）")
for row in diff_md:
    if row[0] in fin:
        same(f"食い違い（tsv）：{row[0]} の自動と確定", row[1:3], [fin[row[0]]["auto_axis1"], fin[row[0]]["axis1"]])
        same(f"食い違い（tsv）：{row[0]} の規則", row[3] in fin[row[0]]["rule"], True)

cmp_rows = {row[0]: row for row in table(section(md, "5-4 run_002 との並び（軸1、3回のうち○の数）"))}
for q in QIDS:
    same(f"5-4 との並び（tsv）：{q} の段階2", cmp_rows.get(q, [""] * 5)[3:5], [str(c1[(g, q)]["○"]) for g in GROUPS])
same("5-4 との並び（tsv）：A〜C の○", cmp_rows.get("A〜C 型の○（27本のうち）", [""] * 5)[3:5], [abc[g][0] for g in GROUPS])
same("5-4 との並び（tsv）：印のある○", cmp_rows.get("うち印のある○", [""] * 5)[3:5], [abc[g][2] for g in GROUPS])
same("5-4 との並び（tsv）：印の無い○", cmp_rows.get("うち印の無い○", [""] * 5)[3:5], [abc[g][1] for g in GROUPS])
same("5-4 との並び（tsv）：D の○", cmp_rows.get("D 型の○（12本のうち）", [""] * 5)[3:5],
     [str(sum(c1[(g, q)]["○"] for q in types["D"])) for g in GROUPS])
# 5-4 の列は、5-4 の scores.md から写したものと同じか
md54 = (HERE.parents[1] / "5-4/run_002/scores.md").read_text()
s54 = {row[0]: row[1:] for row in table(section(md54, "集計：3回のうち軸1 が○の回数"))}
for q in QIDS:
    want = [re.sub(r"/3", "", s54[q][2]), re.sub(r"/3", "", s54[q][1])]   # sl, t2s_desc
    same(f"5-4 との並び：{q} の 5-4", cmp_rows.get(q, [""] * 5)[1:3], want)

# ---- 2通り目：scores.md の1本ずつの表から ----
per = table(section(md, "問ごと（r1 / r2 / r3）"))
c2, each = {}, {}
marks2, a3_2, a4_2 = collections.Counter(), {}, collections.Counter()
q = None
for row in per:
    q = row[0] or q
    g = row[1]
    marks = row[2].split()
    c2[(g, q)] = collections.Counter(marks)
    each[(g, q)] = marks
    for seg in row[3].split("。"):
        m = re.match(r"\s*((?:r\d・?)+)：(.*)", seg)
        if m and "【印】" in m.group(2):
            marks2[g] += len(re.findall(r"r\d", m.group(1))) if q[0] in "ABC" else 0
    if g == "sl_mcp":
        for i, v in enumerate(row[4].split(), 1):
            a3_2[f"sl_mcp_{q}_r{i}"] = {"守": "守った", "破": "破った"}[v]
    a4_2[g] += row[5].split().count("出")
for g in GROUPS:
    for qq in QIDS:
        same(f"軸1（1本ずつの表）：{g} {qq}", cell(c2.get((g, qq), collections.Counter())), summary.get(qq, ["", ""])[GROUPS.index(g)])
        same(f"軸1（1本ずつの表と tsv）：{g} {qq} の本ごと", each.get((g, qq)),
             [fin[f"{g}_{qq}_r{i}"]["axis1"] for i in (1, 2, 3)])
    same(f"A〜C の印のある○（1本ずつの表）：{g}", str(marks2[g]), abc_md.get(g, ["", "", ""])[2])
    same(f"軸4（1本ずつの表）：{g}", str(a4_2[g]), a4_md.get(g, ["", ""])[1])

# 軸3：runs/ の道具の順番から、規則で数え直す
for s, rec in recs.items():
    if rec["group"] != "sl_mcp":
        continue
    seq = [(c["tool"].split("__")[-1], c.get("kind")) for c in rec["calls"]]
    broke = False
    for i, (t, k) in enumerate(seq):
        if t != "run_sql":
            continue
        if not any(tt in SL for tt, _ in seq[:i]):
            broke = True   # SL の道具より先に run_sql
        if any(tt == "query_metrics" and kk == "ok" for tt, kk in seq[:i]):
            broke = True   # ok の query_metrics のあとに run_sql
    same(f"軸3（道具の順番）：{s}", "破った" if broke else "守った", a3_2.get(s))
    same(f"軸3（道具の順番と tsv）：{s}", "破った" if broke else "守った", fin[s]["axis3"])

# 印：○の本のクエリの WHERE 句から機械で拾う
WHERE = re.compile(r"(?<!filter \()(?<!filter\()\bwhere\b(.*?)(?=\bgroup\b|\border\b|\blimit\b|\)|;|$)", re.I | re.S)
PAT = re.compile(r"is_valid_\w+|month\(|extract\(month", re.I)
picked = set()
for s, rec in recs.items():
    if fin[s]["axis1"] != "○":
        continue
    for c in rec["calls"]:
        t, inp = c["tool"].split("__")[-1], c.get("input") or {}
        qs = [inp.get("sql", "")] if t == "run_sql" else (inp.get("where") or []) if t == "query_metrics" else []
        if any(PAT.search(w.group(1)) for qtext in qs for w in WHERE.finditer(qtext)):
            picked.add(s)
mark_sec = section(md, "印（値は合ったが、数え方が定義と違う○）")
side = re.search(r"印の無い本：(\d+)本(.*?)sl_mcp_D5_r1 の印", mark_sec, re.S)
side_runs = set()
if side:
    for m in re.finditer(r"(s(?:ql_)?l?_?mcp_[A-D]\d)_r(\d)((?:・r\d)*)", side.group(2)):
        for rep in [m.group(2)] + re.findall(r"r(\d)", m.group(3)):
            side_runs.add(f"{m.group(1)}_r{rep}")
    same("印（機械）：印の無い本の数", len(side_runs), int(side.group(1)))
marked = {s for s, r in fin.items() if r["mark"] in ("年", "品質フラグ")}
same("印（機械）：拾った本", sorted(picked), sorted(marked | side_runs))
same("印（機械）：拾った本の数", f"拾ったのは{len(picked)}本" in mark_sec, True)

print("確かめた数（種類ごと）：")
for k, n in checked.items():
    print(f"  {k}: {n}")
print(f"合計 {sum(checked.values())} 件、合わない所 {len(bad)} 件")
for b in bad:
    print("  ×", b)
sys.exit(1 if bad else 0)
