"""段階2 run_001：軸3（道具の順番。sl_mcp だけ）と軸4（札の読み方。2組とも）の下書きを、記録から機械で作る。
決めるのは人。線は conditions.md の「採点」の節のとおり。結果を見る前に書いた（本番の前にコミットする）。

使い方: python3 docs/analysis/stage2/run_001/axis_draft.py <runs のディレクトリ> [...]
出力: 1本1行のタブ区切り（ファイル名、組、軸3、軸3 の理由、軸4、軸4 の理由、道具の返事に無い数）
"""
import importlib.util, json, pathlib, re, sys

HERE = pathlib.Path(__file__).resolve().parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


auto_score = _load("auto_score_5_4", HERE.parents[1] / "5-4/run_002/auto_score.py")  # 数の拾い方（カンマ、万、%）を 5-4 の軸1 とそろえる
TODAY = _load("harness_5_4_run_001", HERE.parents[1] / "5-4/run_001/harness.py").TODAY  # 前置きの「今日」（写さない）
SL ={"list_metrics", "get_dimensions", "query_metrics"}
ANSWERED = {"ok", "empty"}   # 説明文の「kind が ok と empty 以外なら、答えは得られていない」
# 0 や「売上なし」と読んだ候補の言い方
ZERO = re.compile(r"(^|[^\d,.])0\s*(円|件|人|ドル|USD|JPY|です|でした)|ゼロ|売上(は|が)?(なし|無し|ありません|ありませんでした|なかった|無かった)")


def name(tool):
    return tool.split("__")[-1]


def axis3(calls):
    """sl_mcp の道具の順番。返すのは（判定, 理由）。"""
    seq = [(name(c["tool"]), c.get("kind")) for c in calls]
    if not seq:
        return "対象外", "道具を呼ばなかった"
    rs = [i for i, (t, _) in enumerate(seq) if t == "run_sql"]
    if not rs:
        return "守った", "SL の道具だけで終えた"
    ok_qm = [i for i, (t, k) in enumerate(seq) if t == "query_metrics" and k == "ok"]
    if any(o < r for o in ok_qm for r in rs):
        return "破った", "query_metrics で ok が出たあとに run_sql を使った"
    first = rs[0]
    before = seq[:first]
    if not any(t in SL for t, _ in before):
        return "破った", "SL の道具より先に run_sql を使った"
    if any(t == "query_metrics" and k not in ANSWERED for t, k in before):
        return "守った", "SL で答えが得られなかった（ok でも empty でもない kind）あとで run_sql を使った"
    if any(t == "get_dimensions" and k == "unknown_name" for t, k in before):
        return "守った", "語彙に無い（get_dimensions が unknown_name）あとで run_sql を使った"
    if any(t == "query_metrics" and k == "empty" for t, k in before):
        return "要確認", "query_metrics が empty のあとに run_sql を使った（線に無い形）"
    return "要確認", "query_metrics を呼ばずに、語彙に無いと判断して run_sql に進んだ"


def numbers_in(text):
    return {v for v, _ in auto_score.numbers(text or "")}


def axis4(rec):
    """札の読み方。返すのは（判定, 理由のリスト, 道具の返事に無い数）。"""
    calls = rec["calls"]
    kinds = [c.get("kind") for c in calls]
    ans = rec.get("final_answer") or ""
    flags = []
    if "empty" in kinds and ZERO.search(ans):
        flags.append("empty が出て、答えに 0・売上なしの言い方がある")
    if "null_value" in kinds and ZERO.search(ans):
        flags.append("null_value が出て、答えに 0・売上なしの言い方がある")
    answered = any(k in ANSWERED for k in kinds)
    # 小さい数（12以下）、年（2025、2026）、問題文の数、日付の数（前置きの「今日」と、その本を回した日）は、
    # 数え物ではないことが多いので見ない
    seen = set().union(*[numbers_in(c.get("response")) for c in calls]) if calls else set()
    dates = " ".join([TODAY, (rec.get("started_at") or "")[:10]]).replace("-", " ")
    ignore = numbers_in(rec.get("question")) | numbers_in(dates) | {2025.0, 2026.0}
    nums = {v for v in numbers_in(ans) if v > 12 and v not in ignore}
    if not answered and nums:
        flags.append("ok も empty も出ていないのに、答えに数がある（作り話の候補）")
    missing = sorted(v for v in nums if v not in seen)
    if missing and answered:
        flags.append("答えの数のうち、道具の返事に無いものがある（計算した値か、作った値か）")
    return ("要確認" if flags else "問題なし"), flags, missing


def fmt(v):
    return str(int(v)) if v == int(v) else str(v)


if __name__ == "__main__":
    print("file\tgroup\taxis3\taxis3_reason\taxis4\taxis4_reasons\tnumbers_not_in_tool_replies")
    for d in sys.argv[1:]:
        for f in sorted(pathlib.Path(d).glob("*.json")):
            rec = json.loads(f.read_text())
            a3, r3 = axis3(rec["calls"]) if rec["group"] == "sl_mcp" else ("—", "sql_mcp には付けない")
            a4, r4, miss = axis4(rec)
            print(f.stem, rec["group"], a3, r3, a4, " / ".join(r4) or "—", ",".join(fmt(v) for v in miss) or "—",
                  sep="\t")
