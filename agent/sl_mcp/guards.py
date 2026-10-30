"""sl_mcp の判定と実行の部品。MCP に依存しないので、check.py から直接呼んで確かめられる。

- 語彙（指標・切り口）の確かめ、where の {{ }} の確かめ、build の時間帯の判定
- mf と duckdb の呼び出し（1つずつ順に処理する）と、返事の種類（kind）の決め方
"""
import datetime
import json
import os
import pathlib
import re
import subprocess
import threading

REPO = pathlib.Path(__file__).resolve().parents[2]
DBT = REPO / "dbt_project"
MANIFEST = DBT / "target" / "semantic_manifest.json"
WAREHOUSE = DBT / "warehouse.duckdb"
HOME = pathlib.Path.home()
MF = HOME / ".local" / "bin" / "mf"
DUCKDB = pathlib.Path("/opt/homebrew/bin/duckdb")

JST = datetime.timezone(datetime.timedelta(hours=9))
GRAINS = {"day", "week", "month", "quarter", "year"}
MAX_ROWS = 1000

# 外のプロセスが DB を開いていて開けなかったときの文（使い捨ての DuckDB ファイルで取った本物の文の一部）
BUSY_MARKS = ("Could not set lock on file", "Conflicting lock is held")
MF_EMPTY_MARK = "Query returned an empty result set"

# mf と duckdb の呼び出しを、サーバーの中で同時に走らせない
_RUN_LOCK = threading.Lock()


# ---- build の時間帯 ----

def in_maintenance(now=None):
    # 5-4 のハーネス（run_002/harness.py の wait_for_dbt_build）と同じ。JST 02:50 以上 03:15 未満
    now = (now or datetime.datetime.now(JST)).astimezone(JST)
    return now.hour == 2 and now.minute >= 50 or now.hour == 3 and now.minute < 15


MAINTENANCE_MESSAGE = ("JST 02:50〜03:15 は、毎晩 JST 03:00 の dbt build（warehouse と定義を作り直す）と"
                       "重なるので、問い合わせを断っています。03:15 を過ぎてから問い合わせてください。")


# ---- 語彙 ----

def load_manifest():
    return json.loads(MANIFEST.read_text())


def metrics_from_manifest():
    # description は足さず削らず、そのまま返す
    return [{"name": m["name"], "description": m.get("description")} for m in load_manifest()["metrics"]]


def time_dimension_suffixes():
    names = set()
    for sm in load_manifest()["semantic_models"]:
        for d in sm.get("dimensions", []):
            if d["type"].lower() == "time":
                names.add(d["name"])
    return names


def is_time_dimension(name, suffixes):
    return name == "metric_time" or name.split("__")[-1] in suffixes


def strip_grain(name):
    head, sep, tail = name.rpartition("__")
    if sep and tail in GRAINS:
        return head
    return name


def where_has_braces(where):
    return "{{" in where and "}}" in where


WHERE_NAME = re.compile(r"\b(Dimension|TimeDimension|Entity|Metric)\(\s*['\"]([^'\"]+)['\"]")


def names_in_where(where):
    return [(fn, name) for fn, name in WHERE_NAME.findall(where)]


# ---- 出力の整え方 ----

_SPINNER = re.compile(r"[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏][^✔🕳]*")


def clean_mf(text):
    # run_001/harness.py の clean_mf と同じ（新しい版の案内と、回る表示を取る）。ホームは ~ にする
    keep = []
    for line in text.replace("\r", "\n").splitlines():
        if re.search(r"new version|update to version|pip install --upgrade|^\s*\$ pip", line):
            continue
        line = _SPINNER.sub("", line)
        keep.append(line)
    return hide_home("\n".join(keep).strip())


def hide_home(text):
    # ホームのパスは ~ に、DuckDB の鍵のエラー文の「by user 名前」の名前は消す
    text = text.replace(str(HOME), "~")
    return re.sub(r"\bby user [A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*", "by user (名前は省略)", text)


def all_null(rows):
    """行が1行以上あり、渡した値がすべて空（None）なら True。"""
    return len(rows) > 0 and all(v is None for row in rows for v in row)


def _value(cell):
    cell = cell.strip()
    if cell == "":
        return None
    if re.fullmatch(r"-?\d+", cell):
        return int(cell)
    if re.fullmatch(r"-?\d+\.\d*(e-?\d+)?", cell):
        return float(cell)
    return cell


def parse_mf_table(text):
    """mf の表（見出し・----・行）を columns と rows に分ける。表が無ければ ([], [])。"""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if i > 0 and re.fullmatch(r"-+(\s+-+)*", line.strip()) and line.strip():
            spans = [m.span() for m in re.finditer(r"-+", line)]
            header = lines[i - 1]
            columns = [header[a:(spans[j + 1][0] if j + 1 < len(spans) else len(header))].strip()
                       for j, (a, _) in enumerate(spans)]
            rows = []
            rest = lines[i + 1:]
            if not rest or not rest[0].strip():
                # group-by なしで値が空のとき、mf は見出しと ---- のあとに空の1行を出す
                # （clean_mf の strip で、その空の行は消えていることがある）
                return columns, [[None] * len(columns)]
            for row in rest:
                if not row.strip():
                    break
                cells = [row[a:(spans[j + 1][0] if j + 1 < len(spans) else len(row))]
                         for j, (a, _) in enumerate(spans)]
                rows.append([_value(c) for c in cells])
            return columns, rows
    return [], []


def is_busy(text):
    return all(mark in text for mark in BUSY_MARKS)


# ---- 実行 ----

def mf_env():
    env = dict(os.environ)
    # DBT_PROFILES_DIR が無いときは、ホームの .dbt を使う
    env.setdefault("DBT_PROFILES_DIR", str(HOME / ".dbt"))
    return env


def run_mf(args, timeout=300):
    with _RUN_LOCK:
        r = subprocess.run([str(MF)] + args, cwd=DBT, env=mf_env(),
                           capture_output=True, text=True, timeout=timeout)
    return r.returncode, clean_mf(r.stdout + r.stderr)


def list_dimensions(metrics):
    code, out = run_mf(["list", "dimensions", "--metrics", ",".join(metrics)])
    if code != 0:
        return None, out
    return [line[2:].strip() for line in out.splitlines() if line.startswith("• ")], out


def duckdb_argv(db_path):
    # -safe：外のファイルへのアクセスを切り、設定を固め、.shell や .output などのドットコマンドも止める
    # -readonly：読み取り専用で開く。-no-init：~/.duckdbrc を読まない。-bail：最初のエラーで止める
    return [str(DUCKDB), "-safe", "-no-init", "-bail", "-readonly", "-json", str(db_path)]


def run_duckdb(sql, db_path=None, timeout=120):
    with _RUN_LOCK:
        r = subprocess.run(duckdb_argv(db_path or WAREHOUSE), input=sql + "\n", cwd=DBT,
                           capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr


def parse_duckdb_json(stdout):
    """-json の出力（文ごとに1つの配列）を、文ごとの行のリストにする。"""
    results, i, dec = [], 0, json.JSONDecoder()
    s = stdout.strip()
    while i < len(s):
        value, end = dec.raw_decode(s, i)
        results.append(value)
        i = end
        while i < len(s) and s[i].isspace():
            i += 1
    return results
