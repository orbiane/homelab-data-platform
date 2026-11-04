"""段階2 run_001：軸4 の確定のための確かめ。axis_draft.py が「道具の返事に無い数」とした数を、1つずつ道具の返事から計算で出せるか調べる。

出せるとみなす計算（その本の道具の返事に出てくる数だけを材料にする。答えの中で出せると分かった数は、次の計算の材料に足す）。
単純なものから順に試し、最初に見つかった式を書く。
- 材料：返事の文から、日付（2025-11-16 など）と、英字と数字が混じった語（ID・列名）を外してから数を拾う
- 数え物ではない：答えの中の ID（英字と数字が混じった語）の一部として出てくる数
- 割合の合計：答えの「100%」
- そのまま：返事の数と同じ（答えの表記の桁で丸めて一致）
- 百分率・小数の数（答えで % が付く数か、小数点のある数）
  - 返事の 0〜1.5 の比を百分率にしたもの
  - 答えの中で出せた割合2つの和（例：31.5% + 39.1% = 70.6%）
  - a÷b×100。a・b は返事の数・出せた数・列全体の和の1つずつで、a < b。b は 100 より大きい数で、
    答えの中で出せた数と列全体の和を先に、どちらも大きい順に試す
  - 分子を2つの和にする割り算は試さない（試しで、計算違いの割合を偶然の一致で通したため。誤って「出せる」にするより、
    「出せない」にして人が読むほうがよい）
- 整数の数
  - 列全体の和：返事の表の1つの列の値を全部足したもの
  - 足し引き：a+b、a−b。a と b は 12 より大きい、返事の数・出せた数・列全体の和（小さい数を使うと、偶然の一致が増えるため）
  - 列の一部の和：12行以下の列から2つ以上の値を選んだ和（選んだ値を書き出す。長い列は、どんな数でも作れてしまうので調べない）
  - 平均：答えに出ている数1つを、返事の 2〜100 の整数（件数）で割ったもの
- 割り算（割合・平均）は、ほかの方法で出せる数を先に全部確定してから試す
- 列：返事の表の数の列。文字・真偽の列1つか2つの値（例：通貨が JPY で最新の版の行）で行を分けた列も作る。4000字で切れて JSON として読めない返事は、列名ごとに数を並べる
- 丸め：上で一致しないとき、答えで「約」「およそ」「万」「前後」などが付いた、1,000 以上で末尾に0が2つ以上ある数（例：約8,400、159万）は、
  末尾の0の桁の幅（ただし数の5%まで）で、そのまま・列全体の和・平均・2つの和の順に一致を見る。使ったときは方法に「丸め」と書く
偶然の一致はありうる（とくに小さい数と割り算）。式を全部書き出すので、人が読んで確かめる。

記録の返事は4000字で切れている。切れた返事を持つ本は、その印を出す（出せない数の理由の候補）。

使い方（リポジトリの直下で）: python3 docs/analysis/stage2/run_001/axis4_check.py
出力：axis4_check.tsv（このフォルダ）。1つの数ごとに1行（本、数、出せたか、方法）
"""
import bisect, importlib.util, itertools, json, pathlib, re

HERE = pathlib.Path(__file__).resolve().parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


axis_draft = _load("axis_draft_stage2", HERE / "axis_draft.py")
CUT = 4000


NUM = re.compile(r"-?\d+(?:\.\d+)?$")


def _tables(resp):
    """返事の JSON から表（行の並び）を取り出す。行は {列名: 値}。読めなければ空。"""
    try:
        obj = json.loads(resp)
    except ValueError:
        return []
    out = []
    if isinstance(obj.get("rows"), list) and obj.get("columns"):   # query_metrics
        out.append([dict(zip(obj["columns"], r)) for r in obj["rows"] if isinstance(r, list)])
    for res in obj.get("results") or []:   # run_sql（文ごとの結果）
        if isinstance(res, dict) and isinstance(res.get("rows"), list):
            out.append([r for r in res["rows"] if isinstance(r, dict)])
    return out


def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str) and NUM.match(v):
        return float(v)
    return None


def columns(resp):
    """返事の中の表を、列ごとの数の並びにする。
    - 表ごと・数の列ごとの並び。さらに、文字・真偽の列の値（例：通貨が JPY の行）で行を分けた並びも作る
    - JSON として読めない（4000字で切れた）返事は、正規表現で「列名: 数」を拾って列名ごとに並べる"""
    cols = []
    tables = _tables(resp or "")
    if tables:
        for rows in tables:
            if not rows:
                continue
            keys = list(rows[0])
            numk = [k for k in keys if any(_num(r.get(k)) is not None for r in rows)
                    and not any(isinstance(r.get(k), str) and _num(r.get(k)) is None for r in rows)]
            catk = [k for k in keys if k not in numk]
            for k in numk:
                cols.append([_num(r.get(k)) for r in rows if _num(r.get(k)) is not None])
                for cs in [(c,) for c in catk] + list(itertools.combinations(catk, 2)):   # 文字の列1つか2つの値で分ける
                    groups = {}
                    for r in rows:
                        if _num(r.get(k)) is not None:
                            groups.setdefault(json.dumps([r.get(c) for c in cs]), []).append(_num(r.get(k)))
                    cols += [g for g in groups.values() if 2 <= len(g) < len(rows)]
    else:
        bykey = {}
        for k, v in re.findall(r'"([A-Za-z_][\w]*)":"?(-?\d+(?:\.\d+)?)"?(?=[,}])', resp or ""):
            bykey.setdefault(k, []).append(float(v))
        cols = list(bykey.values())
    return [vals for vals in cols if len(vals) >= 2]


MAX_COL = 12   # 列の一部の和を調べる列の行数の上限（長い列は、どんな数でも和で作れてしまうため）
DATE = re.compile(r"\d{4}-\d{2}-\d{2}(?:[T ][\d:.]+)?")
MIXED = re.compile(r"\b(?=\w*[A-Za-z])(?=\w*\d)\w+")   # 英字と数字が混じった語（ID、列名）


def clean(text):
    """数を拾う前に、日付と、英字と数字が混じった語（ID など）を外す。数え物ではないため。"""
    return MIXED.sub(" ", DATE.sub(" ", text or ""))


def subset_witness(vals, x, tol):
    """1つの列から2つ以上の値を選んだ和が x に合うとき、選んだ値を返す。合わなければ None。"""
    vals = [v for v in vals if v > 0]
    if len(vals) < 2 or len(vals) > MAX_COL:
        return None
    half = len(vals) // 2
    left, right = vals[:half], vals[half:]

    def all_sums(part):
        out = {}
        for mask in range(1 << len(part)):
            s = sum(part[i] for i in range(len(part)) if mask >> i & 1)
            out.setdefault(round(s, 6), mask)
        return out

    ls, rs = all_sums(left), all_sums(right)
    rkeys = sorted(rs)
    for s1, m1 in ls.items():
        i = bisect.bisect_left(rkeys, x - tol - s1)
        while i < len(rkeys) and rkeys[i] <= x + tol - s1:
            m2 = rs[rkeys[i]]
            picked = [left[k] for k in range(len(left)) if m1 >> k & 1] + [right[k] for k in range(len(right)) if m2 >> k & 1]
            if len(picked) >= 2:
                return picked
            i += 1
    return None


def tol_of(x, text_value):
    """答えの表記の桁から、丸めの幅を決める。"""
    if "." in text_value:
        return 0.5 * 10 ** -len(text_value.split(".")[1]) + 1e-9
    return 0.5


APPROX_BEFORE = re.compile(r"(約|およそ|だいたい|ほぼ|≒|〜|~)\s*$")
APPROX_AFTER = re.compile(r"^\s*(万|前後|ほど|程度|くらい|ぐらい|強|弱|〜|~)")


def approx(x, ans):
    """答えの中で、x がおおよその数として書かれているか（前に「約」など、後ろに「万」「前後」など）。"""
    for m in re.finditer(r"\d[\d,]*(?:\.\d+)?", ans):
        s = m.group(0).replace(",", "")
        if s.count(".") > 1:
            continue
        v = float(s)
        after = ans[m.end():m.end() + 3]
        if after.startswith("万"):
            v *= 10000
        if abs(v - x) < 1e-6 and (APPROX_BEFORE.search(ans[max(0, m.start() - 4):m.start()])
                                  or APPROX_AFTER.match(after)):
            return True
    return False


def round_tol(x):
    """末尾の0の桁で丸めた（または切り捨てた）幅。ただし x の5%まで。"""
    s = str(int(x))
    k = len(s) - len(s.rstrip("0"))
    return min(10 ** k, 0.05 * x) if x >= 1000 and k >= 2 else None


def fmt(v):
    return f"{int(v):,}" if v == int(v) else f"{v:g}"


def explain(x, tol, known, cols, ratios, preferred, kind, pcts=frozenset()):
    """x を出す計算を、単純なものから順に探して、式で返す。無ければ None。
    known：返事の数と、答えの中で出せた数。cols：返事の表の列。ratios が真のときだけ割り算を試す。
    preferred：割合の分母として先に試す数（答えの中で出せた数と、列全体の和）。
    kind：'pct'（百分率・小数）、'int'（整数）、'round'（末尾の0で丸めた整数）。
    偶然の一致を減らすため、足し引き・割り算の材料は 12 より大きい数に限り、大きい数の組から試す。"""
    for k in known:
        if abs(k - x) <= tol:
            return f"そのまま {fmt(k)}"
    colsums = {sum(v): "列全体の和 " + " + ".join(fmt(t) for t in v) for v in cols if len(v) >= 2}
    big = sorted((k for k in known if k > 12), reverse=True)
    pool = sorted(set(big) | {s for s in colsums if s > 12}, reverse=True)   # 足し引きの材料（列全体の和も入れる）

    def name(v):
        return fmt(v) if v in known else f"（{colsums[v]}）"

    if kind == "pct":
        for k in known:
            if 0 < k <= 1.5 and abs(k * 100 - x) <= tol:
                return f"{fmt(k)} を百分率にした"
        shares = sorted(k for k in known & set(preferred) & pcts if 0 < k < 100)   # 答えの中で出せた割合（% 付き）どうしの和
        for a, b in itertools.combinations(shares, 2):
            if abs(a + b - x) <= tol:
                return f"{fmt(a)} + {fmt(b)}（割合の和）"
        if not ratios:
            return None
        # a÷b×100。分子は1つの数で、分子 < 分母。分母は 100 より大きい数で、答えに出た数・列全体の和を先に、どちらも大きい順に
        pref = sorted((b for b in set(preferred) | set(colsums) if b > 100), reverse=True)
        dens = pref + [b for b in pool if b > 100 and b not in pref]
        for b in dens:
            lo, hi = (x - tol) * b / 100, (x + tol) * b / 100
            for a in pool:
                if lo <= a <= hi and a < b:
                    return f"{name(a)} ÷ {name(b)} ×100"
        return None
    for s, how in colsums.items():
        if abs(s - x) <= tol:
            return how
    if kind == "round":
        how = average(x, tol, known, preferred)
        if how:
            return how
    for a, b in itertools.combinations_with_replacement(pool, 2):
        if abs(a + b - x) <= tol:
            return f"{name(b)} + {name(a)}"
    if kind == "int":
        for a, b in itertools.permutations(pool, 2):
            if abs(a - b - x) <= tol:
                return f"{name(a)} − {name(b)}"
        for vals in cols:
            picked = subset_witness(vals, x, tol)
            if picked:
                return "列の一部の和 " + " + ".join(fmt(v) for v in picked)
    if not ratios:
        return None
    return average(x, tol, known, preferred)


def average(x, tol, known, preferred):
    """整数は、答えに出ている数を 2〜100 の件数で割った平均だけを見る（割合や2つの和の割り算は偶然の一致が多い）。"""
    for a in sorted((k for k in preferred if k > 12), reverse=True):
        for b in sorted(k for k in known if 2 <= k <= 100 and k == int(k)):
            if abs(a / b - x) <= tol:
                return f"{fmt(a)} ÷ {fmt(b)}（平均）"
    return None


def check(rec):
    _, _, missing = axis_draft.axis4(rec)
    calls = rec["calls"]
    base = set()
    cols = []
    for c in calls:
        resp = c.get("response") or ""
        base |= {v for v, _ in axis_draft.auto_score.numbers(clean(resp))}
        cols += columns(resp)
    truncated = sum(1 for c in calls if len(c.get("response") or "") >= CUT - 10)
    ans = rec.get("final_answer") or ""
    # 答えの中で、英字と数字が混じった語（ID など）の一部として出てくる数は、数え物ではない
    in_ids = {v for tok in MIXED.findall(ans) for v, _ in axis_draft.auto_score.numbers(re.sub(r"[A-Za-z_]", " ", tok))}
    # 答えの中での表記（小数の桁）を拾う
    shown = {}
    for m in re.finditer(r"\d[\d,]*(?:\.\d+)?", ans):
        s = m.group(0).replace(",", "")
        if s.count(".") <= 1:
            shown.setdefault(float(s), s)
    pcts = {v for v, is_pct in axis_draft.auto_score.numbers(ans) if is_pct}
    known = set(base)
    in_answer = {v for v, _ in axis_draft.auto_score.numbers(ans)} & known   # 答えに出ていて、返事にもある数
    result = {x: "数え物ではない（答えの中の ID の一部）" for x in missing if x in in_ids}
    result.update({x: "割合の合計（100%）" for x in missing if x == 100 and x in pcts})
    todo = [x for x in missing if x not in result]
    for ratios in (False, True):   # 先に割り算なしで出せる数を確定し、そのあと割り算を足す
        changed = True
        while todo and changed:   # 出せた数を材料に足して、出せなくなるまで繰り返す
            changed = False
            for x in list(todo):
                text_value = shown.get(x, fmt(x).replace(",", ""))
                kind = "pct" if (x in pcts or "." in text_value) else "int"
                tol = tol_of(x, text_value) if "." in text_value or kind == "int" else 0.5
                how = explain(x, tol, known, cols, ratios, set(result) | in_answer, kind, pcts)
                if how:
                    result[x] = how
                    known.add(x)
                    todo.remove(x)
                    changed = True
    for x in list(todo):   # 丸めの一致（最後に、ほかの方法で出せなかった数で、答えで「約」などが付いた数だけ）
        rt = round_tol(x) if approx(x, ans) else None
        how = explain(x, rt, known, cols, True, set(result) | in_answer, "round") if rt else None
        if how:
            result[x] = "丸め：" + how
            todo.remove(x)
    return [(x, x in result, result.get(x, "出せない")) for x in sorted(missing)], truncated


def main():
    lines = ["file\tnumber\tderivable\thow\ttruncated_replies"]
    for f in sorted((HERE / "runs").glob("*.json")):
        rec = json.loads(f.read_text())
        rows, trunc = check(rec)
        for x, ok, how in rows:
            lines.append(f"{f.stem}\t{fmt(x)}\t{'出せる' if ok else '出せない'}\t{how}\t{trunc}")
    (HERE / "axis4_check.tsv").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
