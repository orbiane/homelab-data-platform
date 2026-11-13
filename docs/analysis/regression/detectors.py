"""回帰の試験 第2段（R2）：過去の間違いの検出器。

答えの数字ではなく、道具の呼び出し（run_sql の SQL、query_metrics の引数、5-4 の mf query の文字）から、
知られた間違いを見つける。1つの間違いに1つの関数。入力は1本の記録を normalize() でそろえたもの、
出力は (判定, 根拠)。判定は HIT（当たった）／ MISS（当たらない）／ NA（判定できない）。

最初の版（コミット1）は、記録の calls の中身を見る前に、次の言葉だけから書いた：
  - docs/analysis/5-4/questions.md の「原因の札」と各問の「T2S がやりがち」「採点の注意」
  - docs/analysis/stage2/run_001/final_scores.tsv の tags・mark・note、scores.md の規則A〜C と「印」の節
  - docs/analysis/5-4/run_002/scores.md の「問ごと」と「印」の節
  - 列の名前は、5-4 の context_t2s_desc.txt と dbt_project の staging の SQL で確かめた
記録の形（欄の名前）は、記録を書いたコード（stage2/run_001/harness.py、5-4/run_001/harness.py）から取った。

使い方：import して使う（当てる台本は apply_stage2.py と apply_54.py）。
"""
import re
import shlex

HIT, MISS, NA = "当たった", "当たらない", "判定できない"

# ---------------------------------------------------------------------------
# 記録をそろえる
# ---------------------------------------------------------------------------
# そろえた呼び出し（1つの dict）：
#   seq, tool（run_sql / query_metrics / mf_query / ほか）, sql（SQL の本文。SL は None）,
#   metrics, group_by, where（SL の欄。リスト）, ok（結果が返ったか）, kind（段階2 の kind。5-4 は None）

def normalize(rec):
    """段階2 の記録（calls）と 5-4 の記録（attempts）を、同じ形の呼び出しのリストにする。"""
    if "calls" in rec:
        out = []
        for c in rec.get("calls") or []:
            tool = c["tool"].split("__")[-1]
            inp = c.get("input") or {}
            q = {"seq": c.get("seq"), "tool": tool, "sql": None, "metrics": [], "group_by": [], "where": [],
                 "kind": c.get("kind"), "ok": c.get("kind") == "ok"}
            if tool == "run_sql":
                q["sql"] = inp.get("sql") or ""
            elif tool == "query_metrics":
                q["metrics"] = list(inp.get("metrics") or [])
                q["group_by"] = list(inp.get("group_by") or [])
                q["where"] = list(inp.get("where") or [])
            out.append(q)
        return out
    # 5-4：答えは最後の attempt のクエリと結果から書かれた（run_001/harness.py の solve）。最後の1つだけを見る
    atts = rec.get("attempts") or []
    if not atts or atts[-1].get("query") is None:
        return []
    a = atts[-1]
    q = {"seq": len(atts), "tool": None, "sql": None, "metrics": [], "group_by": [], "where": [],
         "kind": None, "ok": bool(a.get("ok"))}
    if rec.get("side") == "t2s":
        q["tool"], q["sql"] = "run_sql", a["query"]
    else:
        q["tool"] = "mf_query"
        q.update(parse_mf(a["query"]))
    return [q]


def parse_mf(cmd):
    """mf query の文字から --metrics・--group-by・--where を取り出す。"""
    cmd = cmd.replace("\\\n", " ")
    lines = [l for l in cmd.splitlines() if l.strip() and not l.strip().startswith("#")]
    text = " ".join(lines)
    try:
        argv = shlex.split(text)
    except ValueError:
        argv = text.split()
    out = {"metrics": [], "group_by": [], "where": []}
    i = 0
    while i < len(argv):
        a = argv[i]
        name, eq, val = a.partition("=")
        if name in ("--metrics", "--group-by", "--where"):
            if not eq:
                val = argv[i + 1] if i + 1 < len(argv) else ""
                i += 1
            if name == "--where":
                out["where"].append(val)
            else:
                out["metrics" if name == "--metrics" else "group_by"] += [x.strip() for x in val.split(",") if x.strip()]
        i += 1
    return out


# ---------------------------------------------------------------------------
# 見る呼び出しの規則（コミット1で決めた。あとから狭めない）
# ---------------------------------------------------------------------------
# - 結果が返った呼び出しだけ（段階2 は kind が ok、5-4 は ok が真）
# - 列や表を探すクエリ（information_schema、describe、show、pragma、duckdb_ の関数）は見ない
# - 例の行を見る下調べ（集計の関数が無く、limit が 20 以下）は見ない。
#   段階2 の scores.md の「印」の節に、`where not is_valid_contact_id … limit 10` のような下調べが6本あると書いてあるため
AGG = re.compile(r"\b(count|sum|avg|min|max|count_if|median|quantile\w*)\s*\(", re.I)
META = re.compile(r"information_schema|\bdescribe\b|\bshow\s|\bpragma\b|duckdb_\w+\s*\(", re.I)
LIMIT = re.compile(r"\blimit\s+(\d+)", re.I)


def is_sample(sql):
    m = LIMIT.search(sql)
    return bool(m) and int(m.group(1)) <= 20 and not AGG.search(sql)


def looked(queries):
    """見る呼び出し。外したものは、外した理由と一緒に返す。"""
    keep, skipped = [], []
    for q in queries:
        if not q["ok"]:
            continue
        if q["sql"] is not None:
            s = q["sql"]
            if META.search(s):
                skipped.append((q, "列や表を探すクエリ"))
                continue
            if is_sample(s):
                skipped.append((q, "例の行を見る下調べ（集計なし・limit 20 以下）"))
                continue
        keep.append(q)
    return keep, skipped


# ---------------------------------------------------------------------------
# SQL の小さな道具
# ---------------------------------------------------------------------------

def clean(sql):
    """コメントを外して小文字にする。文字列の中身は残す。"""
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    return sql.lower()


STOP = re.compile(r"\b(group\s+by|order\s+by|limit|having|qualify|window|union|except|intersect)\b|;")


def clauses(sql, kw="where"):
    """WHERE（または HAVING）の述語を、括弧の深さを見て切り出す。FILTER (WHERE …) の中は除く（別に filters() で取る）。
    段階2 の recount.py の正規表現は `)` で止まるので、`month(x) = 2 and year(x) = 2026` の year を落とす。ここでは深さを数える。"""
    s = clean(sql)
    out = []
    for m in re.finditer(rf"\b{kw}\b", s):
        before = s[:m.start()].rstrip()
        if kw == "where" and re.search(r"filter\s*\($", before):
            continue
        depth, i, start = 0, m.end(), m.end()
        while i < len(s):
            ch = s[i]
            if ch == "'":
                j = s.find("'", i + 1)
                i = len(s) if j < 0 else j + 1
                continue
            if ch == "(":
                depth += 1
            elif ch == ")":
                if depth == 0:
                    break
                depth -= 1
            elif depth == 0:
                st = STOP.match(s, i)
                if st and (i == 0 or not (s[i - 1].isalnum() or s[i - 1] == "_")):
                    break
            i += 1
        out.append(s[start:i])
    return out


def filters(sql):
    """FILTER (WHERE …) の中身"""
    s = clean(sql)
    out = []
    for m in re.finditer(r"filter\s*\(\s*where\b", s):
        depth, i = 0, m.end()
        while i < len(s):
            if s[i] == "(":
                depth += 1
            elif s[i] == ")":
                if depth == 0:
                    break
                depth -= 1
            i += 1
        out.append(s[m.end():i])
    return out


def short(text, n=160):
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n] + "…"


def ev(q, what):
    """根拠の文：どの呼び出しのどこか"""
    return f"#{q['seq']} {q['tool']}: {short(what)}"


REVENUE = re.compile(r"fct_revenue|revenue_monthly|stg_revenue|\brevenue\b", re.I)
SUM_AMOUNT = re.compile(r"sum\s*\(\s*(cast\s*\(\s*)?[\w.]*\b(revenue_amount|amount)\b", re.I)
EVENT_TABLE = re.compile(r"fct_message_event|message_event", re.I)
ACCOUNT_TABLE = r"[\w.\"]*(dim_account|account_master|stg_account\w*)"


def sqls(queries):
    return [q for q in queries if q["sql"] is not None]


def sls(queries):
    return [q for q in queries if q["tool"] in ("query_metrics", "mf_query")]


# ---------------------------------------------------------------------------
# 検出器。1つの関数が1つの知られた間違い。
# 各関数の TARGETS が当てる問（bank の問の ID）。LABELS は、人の判定の札・印のどの言葉をこの検出器に対応づけるか
# （コミット1で決めた。対応する言葉の無い×は、どの検出器の見落としにも数えない）
# ---------------------------------------------------------------------------

MONTH_ONLY = re.compile(r"\bmonth\s*\(|extract\s*\(\s*month\b|date_part\s*\(\s*'month'|datepart\s*\(\s*'month'|strftime\s*\([^)]*'%m'\s*\)")
HAS_YEAR = re.compile(r"\b(19|20)\d\d-\d\d|\byear\s*\(|extract\s*\(\s*year\b|date_part\s*\(\s*'year'|%y|\bbetween\b|\b(19|20)\d\d\b")


def year_less_month(rec, queries):
    """年を見ずに月で絞る（`month(revenue_month) = 2` だけで年が無い）。
    WHERE と HAVING の述語だけを見る。同じ述語に年を含む形（'2026-02-01' のような日付、year()、extract(year)、
    %Y、between、4桁の年）があれば当てない。SL の where は TimeDimension に日付を書くので、月だけの形は書けない"""
    seen = False
    for q in queries:
        if q["sql"] is not None:
            for kw in ("where", "having"):
                for c in clauses(q["sql"], kw):
                    if MONTH_ONLY.search(c):
                        seen = True
                        if not HAS_YEAR.search(c):
                            return HIT, ev(q, f"{kw} {c}")
        else:
            for w in q["where"]:
                seen = True
                if re.search(r"month", w, re.I) and not HAS_YEAR.search(w.lower()):
                    return HIT, ev(q, f"where {w}")
    if not queries:
        return NA, "見る呼び出しが無い"
    return MISS, "月で絞った述語に年がある" if seen else "月で絞る述語が無い"


year_less_month.TARGETS = ["B5", "C3", "D6"]
year_less_month.LABELS = r"(^|[／・])年($|[／・])|年を見ず"

FLAG = re.compile(r"\bis_valid_\w+")


def quality_flag(rec, queries):
    """品質フラグ（is_valid_*）を中身の列として読む：WHERE・HAVING で行を除く、または FILTER・CASE WHEN・
    count_if・sum で「有効な〜」として数える。SELECT にそのまま出す・group by に使うのは「見えるようにする」使い方なので当てない"""
    for q in sqls(queries):
        s = clean(q["sql"])
        for kw in ("where", "having"):
            for c in clauses(q["sql"], kw):
                m = FLAG.search(c)
                if m:
                    return HIT, ev(q, f"{kw} で絞った（{m.group(0)}）: {c}")
        for c in filters(q["sql"]):
            m = FLAG.search(c)
            if m:
                return HIT, ev(q, f"filter で数えた（{m.group(0)}）: {c}")
        m = re.search(r"\bwhen\s+(not\s+)?[\w.]*is_valid_\w+[^,]*", s) or \
            re.search(r"\b(count_if|sum|avg)\s*\(\s*(cast\s*\(\s*)?(not\s+)?[\w.]*is_valid_\w+[^)]*\)", s)
        if m:
            return HIT, ev(q, f"数えた: {m.group(0)}")
    for q in sls(queries):
        for w in q["where"]:
            if "is_valid" in w.lower():
                return HIT, ev(q, f"where {w}")
    if not queries:
        return NA, "見る呼び出しが無い"
    return MISS, "品質フラグで絞った・数えた呼び出しが無い"


quality_flag.TARGETS = ["A1", "A3", "B2", "B3", "D1"]
quality_flag.LABELS = r"品質フラグ"

FINALIZED = re.compile(r"\bis_finalized\b")


def unfinalized_excluded(rec, queries):
    """未確定の月を外す（is_finalized で絞って比べる）。売上の定義は未確定の月を含むので、
    「確定した売上」を聞いていない問（C1・C2・D6）に当てる。B5・C3 は確定で絞るのが正しいので当てない。
    WHERE で絞ったときだけ当てる。FILTER・CASE・group by で確定と未確定を分けて並べた答えは、規則B で○になりうるので当てない"""
    for q in sqls(queries):
        for c in clauses(q["sql"], "where"):
            if FINALIZED.search(c):
                return HIT, ev(q, f"where {c}")
    for q in sls(queries):
        for w in q["where"]:
            if "is_finalized" in w.lower():
                return HIT, ev(q, f"where {w}")
    if not queries:
        return NA, "見る呼び出しが無い"
    return MISS, "is_finalized で絞った呼び出しが無い"


unfinalized_excluded.TARGETS = ["C1", "C2", "D6"]
unfinalized_excluded.LABELS = r"確定の月だけ|is_finalized"


def orphan_dropped(rec, queries):
    """孤児の行を内部結合で落とす：dim_account と内部結合（join・inner join・カンマ）、dim_account を左にした left join、
    `in (select … dim_account)`・exists、結合した側の列の `is not null`。SL は定義が左結合なので判定できない"""
    if not sqls(queries):
        return NA, "SQL の呼び出しが無い（SL は定義が左結合）"
    for q in sqls(queries):
        s = clean(q["sql"])
        if not re.search(ACCOUNT_TABLE, s):
            continue
        for m in re.finditer(rf"(\b\w+\s+)?(\b\w+\s+)?\bjoin\s+{ACCOUNT_TABLE}", s):
            words = " ".join(w.strip() for w in (m.group(1) or "", m.group(2) or "") if w)
            if not re.search(r"\b(left|right|full|cross)\b", words):
                return HIT, ev(q, f"内部結合: {m.group(0)}")
        m = re.search(rf"\bfrom\s+{ACCOUNT_TABLE}(\s+(as\s+)?\w+)?\s+left\s+(outer\s+)?join\s+[\w.\"]*(message_event|revenue|subscription)", s)
        if m:
            return HIT, ev(q, f"dim_account を左にした left join: {m.group(0)}")
        m = re.search(rf"\bfrom\s+[\w.\"]*(message_event|revenue|subscription)\w*(\s+(as\s+)?\w+)?\s*,\s*{ACCOUNT_TABLE}", s)
        if m:
            return HIT, ev(q, f"カンマの結合: {m.group(0)}")
        for c in clauses(q["sql"], "where"):
            m = re.search(rf"\b(in|exists)\s*\(\s*select\b[^)]*{ACCOUNT_TABLE}", c) or \
                re.search(r"\b\w+\.(account_id|industry|plan_type|account_name|status)\s+is\s+not\s+null", c)
            if m:
                return HIT, ev(q, f"where {m.group(0)}")
    return MISS, "dim_account を内部結合した呼び出しが無い"


orphan_dropped.TARGETS = ["B4", "B5", "C2"]
orphan_dropped.LABELS = r"孤児"

LATEST = re.compile(r"is_latest_snapshot|max\s*\(\s*[\w.]*snapshot_date|row_number|\bqualify\b|arg_max|max_by|last_value|"
                    r"first_value|\brank\s*\(|dense_rank|snapshot_date\s*=\s*(date\s*)?'")


def snapshot_all(rec, queries):
    """snapshot を全部足す（多重計上）：売上の表で revenue_amount を sum し、最新の版に絞る仕組み
    （is_latest_snapshot、max(snapshot_date)、row_number・qualify など）が1つも無い。SL は定義が最新の版なので判定できない"""
    if not sqls(queries):
        return NA, "SQL の呼び出しが無い（SL は定義が最新の版）"
    seen = False
    for q in sqls(queries):
        s = clean(q["sql"])
        if REVENUE.search(s) and SUM_AMOUNT.search(s):
            seen = True
            if not LATEST.search(s):
                return HIT, ev(q, s)
    return MISS, "売上を足した呼び出しは、どれも最新の版に絞っている" if seen else "売上を足した呼び出しが無い"


snapshot_all.TARGETS = ["B5", "C1", "C2"]
snapshot_all.LABELS = r"snapshot"


def currency_mixed(rec, queries):
    """通貨を混ぜて足す：revenue_amount を足すのに、currency がクエリのどこにも無い（where でも group by でも filter でもない）。
    SL は revenue_amount を聞くのに、group_by にも where にも currency が無い"""
    seen = False
    for q in sqls(queries):
        s = clean(q["sql"])
        if REVENUE.search(s) and SUM_AMOUNT.search(s):
            seen = True
            if "currency" not in s:
                return HIT, ev(q, s)
    for q in sls(queries):
        if any("revenue_amount" in m for m in q["metrics"]):
            seen = True
            if not any("currency" in x.lower() for x in q["group_by"] + q["where"]):
                return HIT, ev(q, f"metrics {q['metrics']} group_by {q['group_by']} where {q['where']}")
    if not queries:
        return NA, "見る呼び出しが無い"
    return MISS, "売上を足した呼び出しは、どれも通貨を見ている" if seen else "売上を足した呼び出しが無い"


currency_mixed.TARGETS = ["C1", "C2", "D5", "D6"]
currency_mixed.LABELS = r"通貨"

PAIRED = re.compile(r"(count\s*\([^)]*\)(\s*over\s*\([^)]*\))?|\b\w*(cnt|count|num|versions?|snaps?|n_\w+)\w*)\s*(=\s*2\b|>\s*1\b|>=\s*2\b)|"
                    r"snapshot_date\s*(<|>|<>|!=)\s*[\w.]*snapshot_date")
D5_TRAPS = {504859: "2026-02 の差 +504,859", 2852863: "5か月の差 +2,852,863", 5091741: "2026-02 の最初の見積もり 5,091,741"}


def d5_final_only(rec, queries):
    """確定値にだけある行を差に入れる（D5）：snapshot_date を見て売上を足すクエリに、2版ある組（account_id × revenue_month）に
    絞る条件（版の数 = 2・> 1、または2つの版の snapshot_date を比べる結合）が無い。正解の定義は2版ある 76 組。
    見る呼び出しのうち1つでも条件の無いものがあれば当てる。答えの罠の数（+504,859 など）は判定に使わず、別の欄（d5_answer_traps）に出す"""
    if not sqls(queries):
        return NA, "SQL の呼び出しが無い（SL は snapshot_date を切り口に持たない）"
    seen = False
    for q in sqls(queries):
        s = clean(q["sql"])
        if "snapshot_date" in s and SUM_AMOUNT.search(s):
            seen = True
            if not PAIRED.search(s):
                return HIT, ev(q, s)
    return MISS, "snapshot_date を見て足した呼び出しは、どれも2版ある組に絞っている" if seen else "snapshot_date を見て足した呼び出しが無い"


d5_final_only.TARGETS = ["D5"]
d5_final_only.LABELS = r"確定値にだけある行|確定値にしか無い|版の取り方"


def d5_answer_traps(answer):
    """D5 の答えに出た罠の数（判定には使わない。別の欄）"""
    nums = {int(x.replace(",", "")) for x in re.findall(r"\d[\d,]{3,}", answer or "")}
    return [v for k, v in D5_TRAPS.items() if k in nums]


ZERO = re.compile(r"(^|[^\d,.])0\s*円|ゼロ円|売上(金額)?(は|が)\s*(0|ゼロ)(\s|円|$|で|。|、)|(売上|売り上げ)が(全く|まったく)?(なかった|無かった)|"
                  r"(または|もしくは)\s*「?0|0\s*」?\s*(または|もしくは)")


def empty_as_zero(rec, queries):
    """空の結果を 0 と読む（答えの文から）：「0 円」「売上は 0」「売上が無かった」、0 を別の読み方と並べる"""
    ans = rec.get("final_answer") or ""
    m = ZERO.search(ans)
    if m:
        i = m.start()
        return HIT, f"答え: …{short(ans[max(0, i - 40): i + 40], 100)}…"
    return MISS, "答えに 0 円・売上なしの読み方が無い"


empty_as_zero.TARGETS = ["C3", "D6"]
empty_as_zero.LABELS = r"空の結果"

CANON = {"delivered", "opened", "clicked", "blocked", "failed"}


def enum_mixed(rec, queries):
    """不正な event_type を混ぜる、または存在しない値で数える：event_type に lower()・upper()・ilike を使う、
    event_type と比べる値に正規の5値（delivered・opened・clicked・blocked・failed）以外がある。SL は定義が値を決めているので判定できない"""
    if not sqls(queries):
        return NA, "SQL の呼び出しが無い（SL は定義が event_type の値を決めている）"
    for q in sqls(queries):
        s = clean(q["sql"])
        m = re.search(r"\b(lower|upper)\s*\(\s*[\w.]*event_type|event_type\s+(not\s+)?ilike", s)
        if m:
            return HIT, ev(q, m.group(0))
        raw = re.sub(r"--[^\n]*", " ", q["sql"])
        for m in re.finditer(r"event_type\s*(=|<>|!=|\bin\b)\s*(\([^)]*\)|'[^']*')", raw, re.I):
            vals = re.findall(r"'([^']*)'", m.group(2))
            bad = [v for v in vals if v not in CANON]
            if bad:
                return HIT, ev(q, f"{m.group(0)}（正規でない値 {bad}）")
    return MISS, "event_type を正規の値だけで比べている"


enum_mixed.TARGETS = ["A1", "B2", "B3", "D1"]
enum_mixed.LABELS = r"enum|存在しない値|LOWER"


def dedupe(rec, queries):
    """定義が含めている重複を除く：配信の表で select distinct・count(distinct …) を使う。SL は判定できない"""
    if not sqls(queries):
        return NA, "SQL の呼び出しが無い"
    for q in sqls(queries):
        s = clean(q["sql"])
        if EVENT_TABLE.search(s):
            m = re.search(r"select\s+distinct\b[^;]{0,80}|count\s*\(\s*distinct\b[^)]*\)", s)
            if m:
                return HIT, ev(q, m.group(0))
    return MISS, "配信の表で distinct を使っていない"


dedupe.TARGETS = ["B2", "B3"]
dedupe.LABELS = r"重複"


def long_format(rec, queries):
    """縦持ち：配信の表の行を、event_type を見ずに数える（count があり、event_type がクエリのどこにも無い）。SL は判定できない"""
    if not sqls(queries):
        return NA, "SQL の呼び出しが無い"
    for q in sqls(queries):
        s = clean(q["sql"])
        if EVENT_TABLE.search(s) and re.search(r"\bcount\s*\(", s) and "event_type" not in s:
            return HIT, ev(q, s)
    return MISS, "配信の表を数えた呼び出しは、どれも event_type を見ている"


long_format.TARGETS = ["B2", "B3", "D1"]
long_format.LABELS = r"縦持ち"


def u_prefix(rec, queries):
    """contact_id の U プレフィックスをそろえずに人数を数える（D2）：count(distinct contact_id) があり、
    そろえる式（'U' ||、concat、like 'U%'、ltrim、replace、regexp_replace、substr）がクエリに無い。SL は判定できない"""
    if not sqls(queries):
        return NA, "SQL の呼び出しが無い"
    seen = False
    for q in sqls(queries):
        s = clean(q["sql"])
        if re.search(r"count\s*\(\s*distinct\s+[\w.]*contact_id\s*\)", s):
            seen = True
            if not re.search(r"'u'\s*\|\||concat\s*\(|like\s+'u%'|ltrim\s*\(|replace\s*\(|regexp_\w+\s*\(|substr\w*\s*\(", s):
                return HIT, ev(q, s)
    return MISS, "そろえてから数えている" if seen else "count(distinct contact_id) が無い"


u_prefix.TARGETS = ["D2"]
u_prefix.LABELS = r"U プレフィックス"


def empty_rows_dropped(rec, queries):
    """業種などが空の行を捨てる（B4）：where に industry is not null・industry <> '' などがある。SL は判定できない"""
    if not sqls(queries):
        return NA, "SQL の呼び出しが無い"
    for q in sqls(queries):
        for c in clauses(q["sql"], "where"):
            m = re.search(r"[\w.]*industry\s+is\s+not\s+null|[\w.]*industry\s*(<>|!=)\s*''", c)
            if m:
                return HIT, ev(q, f"where {m.group(0)}")
    return MISS, "業種の空を捨てる述語が無い"


empty_rows_dropped.TARGETS = ["B4"]
empty_rows_dropped.LABELS = r"空の行"


DETECTORS = [year_less_month, quality_flag, unfinalized_excluded, orphan_dropped, snapshot_all, currency_mixed,
             d5_final_only, empty_as_zero, enum_mixed, dedupe, long_format, u_prefix, empty_rows_dropped]
NAMES = {
    "year_less_month": "年を見ずに月で絞る",
    "quality_flag": "品質フラグで行を除く・数える",
    "unfinalized_excluded": "未確定の月を外す",
    "orphan_dropped": "孤児の行を内部結合で落とす",
    "snapshot_all": "snapshot を全部足す",
    "currency_mixed": "通貨を混ぜて足す",
    "d5_final_only": "確定値にだけある行を差に入れる（D5）",
    "empty_as_zero": "空の結果を 0 と読む",
    "enum_mixed": "不正な・存在しない event_type",
    "dedupe": "定義の含める重複を除く",
    "long_format": "縦持ちの行をそのまま数える",
    "u_prefix": "U プレフィックスをそろえずに数える",
    "empty_rows_dropped": "業種が空の行を捨てる",
}


def run_all(rec):
    """1本の記録に、問に当てる検出器をすべて当てる。{名前: (判定, 根拠)}。当てない問は入れない"""
    queries, _ = looked(normalize(rec))
    out = {}
    for d in DETECTORS:
        if rec["id"] in d.TARGETS:
            out[d.__name__] = d(rec, queries)
    return out


def human_positive(det, labels_text):
    """人の判定の札・印の言葉（tags と mark をつないだもの）が、この検出器に対応するか"""
    return bool(re.search(det.LABELS, labels_text or ""))
