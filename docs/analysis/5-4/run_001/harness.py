"""5-4: SL 側と T2S 側を同じ LLM (ask-local, gpt-oss:120b) に解かせる。
LLM がクエリを書く -> ここで実行 -> 結果を LLM に返して日本語で答えさせる。
クエリがエラーなら1回だけ書き直させる。結果は runs/<side>_<id>.json に保存。
"""
import json, re, shlex, subprocess, sys, pathlib

HERE = pathlib.Path(__file__).parent
REPO = pathlib.Path.home() / "homelab-data-platform"
DBT = REPO / "dbt_project"
OUT = HERE / "runs"
OUT.mkdir(exist_ok=True)
TODAY = "2026-10-29"

QUESTIONS = [
    ("A1", "メッセージの種類ごとのクリック数を出して"),
    ("A3", "流入経路ごとの登録数は？"),
    ("B2", "配信数は全部でいくつ？"),
    ("B3", "クリック率はどのくらい？"),
    ("B4", "業種ごとの配信数"),
    ("B5", "2月の確定した売上（円）はいくら？"),
    ("C1", "売上の合計はいくら？"),
    ("C2", "契約プラン別に売上を比べたい"),
    ("C3", "4月の確定した売上（円）はいくら？"),
    ("D1", "開封率は？"),
    ("D2", "登録した人は何人？（重複なし）"),
    ("D5", "売上の最初の見積もりと確定値は、どれくらい違った？"),
    ("D6", "今月の売上は？"),
]

CONTEXT = {
    "t2s": (HERE / "context_t2s.txt").read_text(),
    "sl": (HERE / "context_sl.txt").read_text(),
}

ROUND1 = {
    "t2s": "あなたはデータアナリストです。今日は {today} です。下のスキーマの DuckDB に対して、質問に答えるための SQL を1本書いてください。\n"
           "SQL は ```sql と ``` で囲んだブロック1つだけで出してください。クエリを書かずに答える場合は、ブロックを出さずに理由を書いてください。\n\n"
           "{context}\n\n質問：{q}",
    "sl": "あなたはデータアナリストです。今日は {today} です。下のセマンティックレイヤーに対して、質問に答えるための mf query コマンドを1本書いてください。\n"
          "コマンドは ```bash と ``` で囲んだブロック1つだけで出してください。クエリを書かずに答える場合は、ブロックを出さずに理由を書いてください。\n\n"
          "{context}\n\n質問：{q}",
}
RETRY = "\n\n前回のクエリ：\n{query}\n\nエラー：\n{err}\n\n直したクエリを、同じ形式で1本だけ出してください。"
ROUND2 = ("あなたはデータアナリストです。今日は {today} です。質問に対してあなたが書いたクエリと、その実行結果を示します。"
          "これを見て、質問した人への答えを日本語で書いてください。\n\n質問：{q}\n\nクエリ：\n{query}\n\n実行結果：\n{result}")

SL_ALLOWED = {"--metrics", "--group-by", "--where", "--start-time", "--end-time",
              "--limit", "--order", "--decimals", "--quiet", "--explain"}


def ask(prompt):
    r = subprocess.run(["ask-local", prompt], stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        raise RuntimeError(f"ask-local failed: {r.stderr}")
    return r.stdout.strip()


def extract(side, text):
    lang = "sql" if side == "t2s" else "(?:bash|sh|shell)?"
    m = re.search(r"```" + lang + r"\s*\n(.*?)```", text, re.S)
    return m.group(1).strip() if m else None


def run_t2s(sql):
    r = subprocess.run(["duckdb", "-readonly", "warehouse.duckdb"],
                       input="SET enable_external_access=false;\n" + sql + "\n",
                       cwd=DBT, capture_output=True, text=True, timeout=120)
    ok = r.returncode == 0 and "Error" not in r.stderr
    return ok, (r.stdout + r.stderr).strip()


def clean_mf(text):
    keep = []
    for line in text.splitlines():
        if re.search(r"new version|update to version|pip install --upgrade|^\s*\$ pip", line):
            continue
        line = re.sub(r"[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏][^✔🕳]*", "", line)
        keep.append(line)
    return "\n".join(keep).strip()


def run_sl(cmd):
    cmd = cmd.replace("\\\n", " ")
    lines = [l for l in cmd.splitlines() if l.strip() and not l.strip().startswith("#")]
    if len(lines) != 1:
        return False, "コマンドは mf query を1行だけにしてください"
    argv = shlex.split(lines[0])
    if argv[:2] != ["mf", "query"]:
        return False, "mf query 以外のコマンドは実行できません"
    for a in argv[2:]:
        if a.startswith("--") and a.split("=")[0] not in SL_ALLOWED:
            return False, f"このオプションは使えません: {a}"
    r = subprocess.run([str(pathlib.Path.home() / ".local/bin/mf")] + argv[1:],
                       cwd=DBT, capture_output=True, text=True, timeout=300)
    out = clean_mf(r.stdout + r.stderr)
    return (r.returncode == 0 and "ERROR" not in out), out


def solve(side, qid, q):
    rec = {"side": side, "id": qid, "question": q, "attempts": []}
    prompt = ROUND1[side].format(today=TODAY, context=CONTEXT[side], q=q)
    for attempt in range(2):
        raw = ask(prompt)
        query = extract(side, raw)
        a = {"llm": raw, "query": query}
        rec["attempts"].append(a)
        if query is None:
            rec["final_answer"] = raw
            rec["no_query"] = True
            return rec
        ok, result = (run_t2s if side == "t2s" else run_sl)(query)
        a["ok"], a["result"] = ok, result
        if ok:
            break
        prompt = prompt + RETRY.format(query=query, err=result[-2000:])
    last = rec["attempts"][-1]
    rec["final_answer"] = ask(ROUND2.format(today=TODAY, q=q, query=last["query"],
                                            result=last["result"][-6000:]))
    return rec


if __name__ == "__main__":
    sides = sys.argv[1:] or ["t2s", "sl"]
    for side in sides:
        for qid, q in QUESTIONS:
            path = OUT / f"{side}_{qid}.json"
            if path.exists():
                continue
            rec = solve(side, qid, q)
            path.write_text(json.dumps(rec, ensure_ascii=False, indent=2))
            print(side, qid, "done", flush=True)
