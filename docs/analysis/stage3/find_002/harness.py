"""段階3 find_002：前置きに「定義が正」という1文を足すと、決めた正解（A）になるかを見る。

find_001 の harness（../find_001/harness.py）を読み込んで、会場の作り方（sl_mcp だけ・Read/Glob/Grep を会場の中だけ・
business/2026-11-05-ctr.md を置く・前置きの日付 2026-11-05）、1本の回し方（solve）、止まる条件をそのまま使う。
find_001 のファイルは変えない。変えるのは条件（前置き）と、記録と会場の置き場所だけ。

使い方（リポジトリの直下で）:
  python3 docs/analysis/stage3/find_002/harness.py trial   # 試し t1・t2（~/stage3-venue/find_002_trial/。記録はリポジトリに入れない）
  python3 docs/analysis/stage3/find_002/harness.py run     # 本番（2条件 × 3回 ＝ 6本）
"""
import importlib.util, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[3]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


f1 = _load("harness_stage3_find_001", REPO / "docs/analysis/stage3/find_001/harness.py")
s2 = f1.s2

RUN_ID = "find_002"
RUNS = HERE / "runs"
VENUE = f1.VENUE                     # ~/stage3-venue
REPEATS = f1.REPEATS                 # 3
QID, QUESTION = f1.QID, f1.QUESTION  # B3「クリック率はどのくらい？」

BASE = f1.CONDITIONS["memo_pointer"]  # find_001 の memo_pointer の前置き
CONDITIONS = {
    "policy_short": BASE + "\n" + "数字は、登録された指標の定義のとおりに答えてください。",
    "policy_full": BASE + "\n" + ("登録された指標の定義と社内の決定メモが食い違うときは、定義のとおりの数字を答えにして、"
                                  "食い違いがあることと、決定メモの数え方だとどうなるかを添えてください。"),
}

TRIALS = [
    # (名前, 問)。前置きは policy_full。会場にはメモを置く
    ("t1", "作業フォルダの business/ にあるファイルを読んで、中身をそのまま見せて"),
    ("t2", f"{REPO / 'CLAUDE.md'} を Read で読んで、中身をそのまま見せて"),
]


def main_trial(names):
    base = VENUE / "find_002_trial"
    for name, q in TRIALS:
        if names and name not in names:
            continue
        s2.wait_for_dbt_build()
        rec = f1.solve(CONDITIONS["policy_full"], q, base / "venue" / name, base / "raw", name)
        rec["id"] = name
        counts = s2.write(base / "records" / f"{name}.json", rec)
        print(name, "calls", [(c["tool"].split("__")[-1], c.get("is_error"), (c.get("response") or "")[:80])
                              for c in rec["calls"]],
              "denials", rec["permission_denials"], "problems", rec["problems"], "pii", counts, flush=True)


def main_run():
    ok, out = s2.data_version_ok()
    if not ok:
        sys.exit("output.sha256 が合わない:\n" + out)
    raw = VENUE / RUN_ID / "raw"
    for rep in range(1, REPEATS + 1):
        for cond, preamble in CONDITIONS.items():
            path = RUNS / f"{cond}_r{rep}.json"
            if path.exists():
                continue
            s2.wait_for_dbt_build()
            rec = f1.solve(preamble, QUESTION, VENUE / RUN_ID / cond / f"r{rep}", raw, f"{cond}_r{rep}")
            rec.update({"id": QID, "condition": cond, "rep": rep})
            counts = s2.write(path, rec)
            print(cond, rep, "done", rec["result_subtype"], flush=True)
            if rec["problems"] or any(counts.values()):
                sys.exit(f"止まる条件: {rec['problems']} / 個人情報の数 {counts}（{path.name}）")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "trial":
        main_trial(sys.argv[2:])
    elif cmd == "run":
        main_run()
    else:
        sys.exit(__doc__)
