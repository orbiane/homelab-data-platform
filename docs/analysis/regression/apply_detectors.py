"""R2：検出器（detectors.py）を記録に当て、人が確定した判定と突き合わせる。

  段階2（作りの段）：docs/analysis/stage2/run_001/runs/*.json の78本。人の判定は final_scores.tsv
  5-4（試しの段）  ：docs/analysis/5-4/run_002/runs/*.json の117本。人の判定は human_54.tsv（5-4 の scores.md から写した）

本ごとに：検出器の判定、数字の照合（5-4 の auto_score.py の judge をそのまま呼ぶ。期待値は段階2の時点＝questions.md）、
それらから出した軸1 の見立てと印の見立て、人の判定。
検出器ごとに：一致／誤検出／別の札／見落とし／当たらず／判定できない／対象外 の件数と本の名前（合計は本の数）。

使い方（リポジトリの直下で）:
  uv run python docs/analysis/regression/apply_detectors.py stage2 [--out results/<名前>.md]
  uv run python docs/analysis/regression/apply_detectors.py 54 [--out results/<名前>.md]
合わない確かめがあれば終了コード 1。
"""
import collections
import csv
import importlib.util
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ANALYSIS = HERE.parent
sys.path.insert(0, str(HERE))
import detectors as d  # noqa: E402

spec = importlib.util.spec_from_file_location("auto_score", ANALYSIS / "5-4/run_002/auto_score.py")
auto_score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auto_score)

QIDS = ["A1", "A3", "B2", "B3", "B4", "B5", "C1", "C2", "C3", "D1", "D2", "D5", "D6"]
CATS = ["一致", "誤検出", "別の札", "見落とし", "当たらず", "判定できない", "対象外"]
lines, bad = [], []


def say(s=""):
    lines.append(s)


def number_check(rec):
    """auto_score.judge をそのまま呼ぶ。A3 の referrer 別の数は、warehouse を読まないと分からないので、
    route 別の数が揃わなければ「判定できない」にする（referrer の数は渡さない。空のリストを渡すと、空の集合は
    どの集合の部分集合でもあるので、A3 が必ず○になる。それを避けるため、当たらない数 [-1] を渡す）"""
    v, _ = auto_score.judge(rec, [-1])
    if rec["id"] == "A3" and v == "×":
        return "判定できない"
    return v


def view(num, hits):
    if num == "答えなし":
        return "答えなし"
    if num == "×":
        return "×"
    if num == "○":
        return "印" if hits else "○"
    return "判定できない"


def load_stage2():
    base = ANALYSIS / "stage2/run_001"
    recs = {f.stem: json.loads(f.read_text()) for f in sorted((base / "runs").glob("*.json"))}
    human = {}
    for r in csv.DictReader(open(base / "final_scores.tsv"), delimiter="\t"):
        human[r["file"]] = {"axis1": r["axis1"], "mark": r["mark"], "tags": r["tags"], "group": r["group"]}
    auto = {}
    for line in (base / "auto_axis1.tsv").read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            s, v, *_ = line.split("\t")
            auto[s] = v
    return recs, human, auto


def load_54():
    base = ANALYSIS / "5-4/run_002"
    recs = {f.stem: json.loads(f.read_text()) for f in sorted((base / "runs").glob("*.json"))}
    human = {}
    for r in csv.DictReader(open(HERE / "human_54.tsv"), delimiter="\t"):
        human[r["file"]] = {"axis1": r["axis1"], "mark": r["mark"], "tags": r["tags"], "group": r["group"]}
    auto = {}
    for line in (base / "auto_axis1.tsv").read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            s, v, *_ = line.split("\t")
            auto[s] = v
    return recs, human, auto


def positive(h):
    return h["axis1"] == "×" or bool(h["mark"])


def main():
    which = sys.argv[1]
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
    recs, human, auto = load_stage2() if which == "stage2" else load_54()
    n = len(recs)
    say(f"# R2 検出器の当て：{'段階2 run_001（作りの段）' if which == 'stage2' else '5-4 run_002（試しの段）'}")
    say()
    say(f"- 記録 {n} 本。人の判定 {len(human)} 本。記録と人の判定の本の名前が同じか：{sorted(recs) == sorted(human)}")
    if sorted(recs) != sorted(human):
        bad.append(f"記録と人の判定の本が合わない：記録だけ {sorted(set(recs) - set(human))}、人だけ {sorted(set(human) - set(recs))}")

    rows, per = [], collections.defaultdict(lambda: collections.defaultdict(list))
    skipped_total = collections.Counter()
    for s, rec in recs.items():
        h = human.get(s, {"axis1": "?", "mark": "", "tags": "", "group": "?"})
        labels = f"{h['tags']}／{h['mark']}"
        res = d.run_all(rec)
        _, skipped = d.looked(d.normalize(rec))
        for _, why in skipped:
            skipped_total[why] += 1
        hits = [k for k, (v, _) in res.items() if v == d.HIT]
        num = number_check(rec)
        v = view(num, hits)
        rows.append((s, rec, h, res, hits, num, v))
        for det in d.DETECTORS:
            k = det.__name__
            if k not in res:
                cat = "対象外"
            else:
                r = res[k][0]
                mapped = d.human_positive(det, labels) and positive(h)
                if r == d.NA:
                    cat = "判定できない"
                elif r == d.HIT:
                    cat = "一致" if mapped else ("誤検出" if not positive(h) else "別の札")
                else:
                    cat = "見落とし" if mapped else "当たらず"
            per[k][cat].append(s)

    # ---- 確かめ ----
    say(f"- 見る呼び出しから外したもの：{dict(skipped_total) or '無し'}")
    a_diff = [(s, num, auto.get(s)) for s, _, _, _, _, num, _ in rows if num != auto.get(s)]
    say(f"- 数字の照合と、記録に残る自動の下書き（auto_axis1.tsv）の食い違い：{len(a_diff)} 本 {a_diff}")
    hp = sorted(s for s, _, h, *_ in rows if positive(h))
    say(f"- 人が×か印の本：{len(hp)} 本（×{sum(h['axis1'] == '×' for _, _, h, *_ in rows)}、"
        f"印{sum(bool(h['mark']) for _, _, h, *_ in rows)}、答えなし{sum(h['axis1'] == '答えなし' for _, _, h, *_ in rows)}）")
    for k, cats in per.items():
        tot = sum(len(v) for v in cats.values())
        if tot != n:
            bad.append(f"{k} の件数の合計 {tot} が本の数 {n} と合わない")
    say()

    # ---- 検出器ごと ----
    say("## 検出器ごと（件数の合計は本の数）")
    say()
    say("一致＝当たって、人も×か印で札がこの検出器に対応する。誤検出＝当たったが、人は○で印なし。別の札＝当たったが、人の×・印の札はこの検出器に対応しない。"
        "見落とし＝当たらなかったが、人の札がこの検出器に対応する。当たらず＝当たらず、人の札も対応しない。")
    say()
    say("| 検出器 | 当てる問 | " + " | ".join(CATS) + " | 計 |")
    say("|---|---|" + "---|" * (len(CATS) + 1))
    for det in d.DETECTORS:
        k = det.__name__
        cs = per[k]
        say(f"| {d.NAMES[k]}（`{k}`） | {'・'.join(det.TARGETS)} | " + " | ".join(str(len(cs[c])) for c in CATS)
            + f" | {sum(len(v) for v in cs.values())} |")
    say()
    say("### 本の名前（一致・誤検出・別の札・見落とし・判定できない）")
    say()
    for det in d.DETECTORS:
        k = det.__name__
        parts = [f"{c}：{'、'.join(per[k][c])}" for c in ["一致", "誤検出", "別の札", "見落とし", "判定できない"] if per[k][c]]
        if parts:
            say(f"- `{k}`：" + "／".join(parts))
    say()

    # ---- 本ごとの見立てと人 ----
    say("## 見立てと人の判定（本ごとの突き合わせ。合計は本の数）")
    say()
    vs = ["○", "印", "×", "答えなし", "判定できない"]
    hs = ["○", "印", "×", "答えなし"]
    cross = collections.Counter()
    for s, _, h, _, _, _, v in rows:
        hv = "印" if h["mark"] and h["axis1"] == "○" else h["axis1"]
        cross[(v, hv)] += 1
    say("| 見立て ＼ 人 | " + " | ".join(hs) + " | 計 |")
    say("|---|" + "---|" * (len(hs) + 1))
    for v in vs:
        say(f"| {v} | " + " | ".join(str(cross[(v, x)]) for x in hs) + f" | {sum(cross[(v, x)] for x in hs)} |")
    say(f"| 計 | " + " | ".join(str(sum(cross[(v, x)] for v in vs)) for x in hs) + f" | {sum(cross.values())} |")
    if sum(cross.values()) != n:
        bad.append(f"見立ての表の合計 {sum(cross.values())} が本の数 {n} と合わない")
    say()
    pos_view = {s for s, *_, v in rows if v in ("印", "×")}
    pos_h = set(hp)
    say(f"- 見立てが×か印で、人も×か印：{len(pos_view & pos_h)} 本／見立てだけ：{len(pos_view - pos_h)} 本 {sorted(pos_view - pos_h)}"
        f"／人だけ：{len(pos_h - pos_view)} 本 {sorted(pos_h - pos_view)}")
    say()
    say("| 本 | 人の軸1 | 人の印 | 人の札 | 数字の照合 | 当たった検出器 | 見立て |")
    say("|---|---|---|---|---|---|---|")
    for s, rec, h, res, hits, num, v in rows:
        say(f"| {s} | {h['axis1']} | {h['mark']} | {h['tags']} | {num} | {'、'.join(hits)} | {v} |")
    say()

    # ---- 根拠 ----
    say("## 当たった根拠（どの呼び出しのどこか）")
    say()
    for s, rec, h, res, hits, num, v in rows:
        for k in hits:
            say(f"- {s} `{k}`：{res[k][1].replace('|', '¦')}")
    d5 = [(s, d.d5_answer_traps(rec.get("final_answer"))) for s, rec, *_ in rows if rec["id"] == "D5"]
    say()
    say("## D5 の答えに出た罠の数（判定には使っていない。別の欄）")
    say()
    for s, t in d5:
        say(f"- {s}：{'、'.join(t) if t else '無し'}")
    say()
    say(f"確かめで合わない所：{len(bad)} 件")
    for b in bad:
        say(f"  × {b}")
    text = "\n".join(lines) + "\n"
    print(text)
    if out:
        p = HERE / out
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
