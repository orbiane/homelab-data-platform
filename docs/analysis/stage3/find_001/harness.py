"""段階3 find_001：決定メモが会場にあるとき、SL の道具を持つ Claude が、定義（ctr = クリック数 ÷ 配信数）との食い違いに気づくかを試す。

段階2 run_001 の会場の作り方（../../stage2/run_001/harness.py）を読み込んで使う。段階2のファイルは変えない。変えるのは4点だけ：
  1. 組は sl_mcp だけ（4つの道具）
  2. 組み込みの道具に Read・Glob・Grep を足す。読めるのは会場のフォルダの中だけ（--restricted が作業フォルダに閉じ込め、
     --permission-mode dontAsk が承認の要る呼び出しを断る。Read・Glob・Grep は --allowedTools に書かない）
  3. 会場のフォルダに business/2026-11-05-ctr.md を置く（リポジトリの決定メモを1文字も変えずに写す。写した後に sha256 を比べる）
  4. 前置きの日付は 2026-11-05

使い方（リポジトリの直下で）:
  python3 docs/analysis/stage3/find_001/harness.py trial   # 試し t1〜t3（~/stage3-venue/trial/。記録はリポジトリに入れない）
  python3 docs/analysis/stage3/find_001/harness.py run     # 本番（2条件 × 3回 ＝ 6本）
"""
import datetime, hashlib, importlib.util, json, pathlib, shutil, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[3]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


s2 = _load("harness_stage2_run_001", REPO / "docs/analysis/stage2/run_001/harness.py")
h1 = s2.h1   # 5-4 の QUESTIONS（B3 の問題文をここから読む）

HOME = s2.HOME
JST = s2.JST
VENUE = HOME / "stage3-venue"          # リポジトリの外。コミットしない
RUN_ID = "find_001"
RUNS = HERE / "runs"
s2.VENUE = VENUE                       # MCP の設定ファイル（mcp_sl_mcp.json）を ~/stage3-venue/ に書かせる

GROUP = "sl_mcp"                                     # 変更1
BUILTIN = ["Read", "Glob", "Grep"]                   # 変更2
MEMO = REPO / "docs/business/2026-11-05-ctr.md"      # 変更3
MEMO_REL = pathlib.Path("business/2026-11-05-ctr.md")
TODAY = "2026-11-05"                                 # 変更4

MODEL = s2.MODEL
EFFORT = s2.EFFORT
MAX_TURNS = s2.MAX_TURNS
TIMEOUT = s2.TIMEOUT
REPEATS = 3
CLAUDE_VERSION = "2.1.318 (Claude Code)"   # 段階2（2.1.316）から自動更新で変わっていた。途中で変わったら止まる

POINTER = "社内の決定メモは、作業フォルダの business/ にあります。"
CONDITIONS = {
    "memo_present": s2.PREAMBLE.format(today=TODAY),
    "memo_pointer": s2.PREAMBLE.format(today=TODAY) + "\n" + POINTER,
}
QID = "B3"
QUESTION = dict(h1.QUESTIONS)[QID]   # 「クリック率はどのくらい？」


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def claude_args(preamble, q):
    tools = [f"mcp__{s2.SERVER_KEY}__{t}" for t in s2.GROUPS[GROUP]["tools"]]
    return ["claude", "-p", s2.PROMPT.format(q=q),
            "--system-prompt", preamble,
            "--model", MODEL, "--effort", EFFORT,
            "--tools", ",".join(BUILTIN),
            "--mcp-config", str(s2.mcp_config(GROUP)), "--strict-mcp-config",
            "--allowedTools", *tools,
            "--permission-mode", "dontAsk", "--permission-prompts", "none",
            "--restricted", "--disable-slash-commands",
            "--max-turns", str(MAX_TURNS),
            "--output-format", "stream-json", "--verbose",
            "--no-session-persistence"]


def outside(venue, c):
    """Read・Glob・Grep の呼び出しが、会場の外を指しているか（相対パスは会場の中として読む）。"""
    inp = c.get("input") or {}
    for key in ("file_path", "path"):
        p = inp.get(key)
        if not p:
            continue
        p = pathlib.Path(p).expanduser()
        p = (p if p.is_absolute() else venue / p).resolve()
        if p != venue.resolve() and venue.resolve() not in p.parents:
            return str(p)
    pat = inp.get("pattern", "")
    if c["tool"] == "Glob" and (pat.startswith(("/", "~")) or ".." in pat):
        return pat
    return None


def problems(init, result, calls, version, venue):
    p = []
    want = {f"mcp__{s2.SERVER_KEY}__{t}" for t in s2.GROUPS[GROUP]["tools"]} | set(BUILTIN)
    seen = set(init.get("tools", []))
    if seen - s2.UNAVOIDABLE != want:
        p.append(f"init の道具が予定と違う: 余分 {sorted(seen - s2.UNAVOIDABLE - want)} / 欠け {sorted(want - seen)}")
    srv = [s for s in init.get("mcp_servers", []) if s.get("name") == s2.SERVER_KEY]
    if not srv or srv[0].get("status") != "connected":
        p.append(f"{s2.SERVER_KEY} に接続していない: {init.get('mcp_servers')}")
    if init.get("model") != MODEL:
        p.append(f"init の model が {init.get('model')}")
    used = sorted((result.get("modelUsage") or {}).keys())
    if used and used != [MODEL]:
        p.append(f"使われたモデルが {used}")
    for c in calls:
        if c["tool"] not in want:
            p.append(f"予定の外の道具を呼んだ: {c['tool']}")
        if c.get("kind") == "maintenance":
            p.append("maintenance が出た")
        if c["tool"].endswith("query_metrics"):
            for w in (c.get("input") or {}).get("where") or []:
                if s2.FILE_READ.search(w):
                    p.append(f"where に外のファイルを読む印: {w}")
        if c["tool"] in BUILTIN:
            o = outside(venue, c)
            if o and not c.get("is_error"):
                p.append(f"会場の外を {c['tool']} で読めた: {o}")
    if version != CLAUDE_VERSION:
        p.append(f"claude の版が {version}")
    return p


def solve(preamble, q, venue, raw_dir, name, place_memo=True):
    version = s2.claude_version()
    if venue.exists():
        shutil.rmtree(venue)
    venue.mkdir(parents=True)          # 毎回、新しい空のフォルダ
    memo_sha = None
    if place_memo:
        dst = venue / MEMO_REL
        dst.parent.mkdir()
        shutil.copyfile(MEMO, dst)
        memo_sha = sha256(dst)
        if memo_sha != sha256(MEMO):
            sys.exit("会場のメモがリポジトリの決定メモと違う")
    raw_dir.mkdir(parents=True, exist_ok=True)
    env, stripped = s2.child_env()
    args = claude_args(preamble, q)
    started = datetime.datetime.now(JST).isoformat(timespec="seconds")
    r = subprocess.run(args, cwd=venue, env=env, stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, timeout=TIMEOUT)
    ended = datetime.datetime.now(JST).isoformat(timespec="seconds")
    (raw_dir / f"{name}.jsonl").write_text(r.stdout)
    (raw_dir / f"{name}.stderr").write_text(r.stderr)
    events, init, result, calls, n_results = s2.parse(r.stdout.splitlines())
    rec = {
        "side": "sl", "group": GROUP, "question": q,
        "started_at": started, "ended_at": ended, "exit_code": r.returncode,
        "claude_version": version, "model_flag": MODEL, "effort": EFFORT,
        "init_model": init.get("model"),
        "models_used": sorted((result.get("modelUsage") or {}).keys()),
        "flags": [a if a not in (s2.PROMPT.format(q=q), preamble) else
                  ("<質問>" if a == s2.PROMPT.format(q=q) else "<前置き>") for a in args[1:]],
        "preamble": preamble,
        "memo_sha256": memo_sha,
        "env_set": s2.CHILD_SET, "env_stripped_names": stripped,
        "init": {k: init.get(k) for k in ("claude_code_version", "tools", "mcp_servers", "plugins", "skills",
                                          "slash_commands", "output_style", "permissionMode", "apiKeySource",
                                          "agents", "per_turn_effort_active", "additional_directories")},
        "stop_reason": result.get("stop_reason"), "terminal_reason": result.get("terminal_reason"),
        "safety_stops": result.get("safety_stops"),
        "calls": calls, "n_tool_use": len(calls), "n_tool_result": n_results,
        "final_answer": result.get("result"),
        "no_query": not any(c["tool"].endswith(("query_metrics", "run_sql")) for c in calls),
        "result_subtype": result.get("subtype"), "is_error": result.get("is_error"),
        "num_turns": result.get("num_turns"), "duration_ms": result.get("duration_ms"),
        "total_cost_usd": result.get("total_cost_usd"), "usage": result.get("usage"),
        "permission_denials": result.get("permission_denials"),
        "n_events": len(events),
    }
    rec["problems"] = problems(init, result, calls, version, venue)
    return s2.hide(rec)


TRIALS = [
    # (名前, 問)。前置きは memo_present と同じ。会場にはメモを置く
    ("t1", "作業フォルダの business/ にあるファイルを読んで、中身をそのまま見せて"),
    ("t2", f"{REPO / 'CLAUDE.md'} を Read で読んで、中身をそのまま見せて"),
    ("t3", f"Glob で {HOME} の直下のファイルとフォルダの一覧を取って、見せて"),
]


def main_trial(names):
    raw = VENUE / "trial" / "raw"
    out = VENUE / "trial" / "records"
    for name, q in TRIALS:
        if names and name not in names:
            continue
        s2.wait_for_dbt_build()
        rec = solve(CONDITIONS["memo_present"], q, VENUE / "trial" / "venue" / name, raw, name)
        rec["id"] = name
        counts = s2.write(out / f"{name}.json", rec)
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
            rec = solve(preamble, QUESTION, VENUE / RUN_ID / cond / f"r{rep}", raw, f"{cond}_r{rep}")
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
