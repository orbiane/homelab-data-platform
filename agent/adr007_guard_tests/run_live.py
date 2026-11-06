#!/usr/bin/env python3
"""docs/analysis/stage3/guard_cases.md の L1〜L5 を、本物の claude -p に操作させて回す。

使い方（リポジトリの根から）: python3 agent/adr007_guard_tests/run_live.py
件ごとに一時ディレクトリへ clone を作る。作業中の関所のファイル（settings.json を含む）を写す。
そのうえで claude -p に、決まった道具の呼び出しを1回だけさせる。
権限はわざと広げる（acceptEdits と --allowedTools）。そうしておけば、止まったのは hook のせいだと言える。
hook の判定は、環境変数 ADR007_GUARD_LOG に hook が書く記録と、道具の結果に出る [ADR-007 関所] の文字で見る。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.realpath(subprocess.run(["git", "rev-parse", "--show-toplevel"],
                                       capture_output=True, text=True, check=True).stdout.strip())
COPY = [".claude/settings.json", ".claude/hooks/adr007_guard.py",
        ".githooks/pre-commit", ".githooks/definition_guard.sh"]
WORK = os.path.realpath(tempfile.mkdtemp(prefix="adr007-live-"))
MODEL = os.environ.get("LIVE_MODEL", "haiku")
TAG = "[ADR-007 関所]"


def sh(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def make_clone(name):
    d = os.path.join(WORK, name)
    sh(["git", "clone", "-q", REPO, d], WORK).check_returncode()
    for rel in COPY:
        os.makedirs(os.path.dirname(os.path.join(d, rel)), exist_ok=True)
        shutil.copy2(os.path.join(REPO, rel), os.path.join(d, rel))
    words = sh(["git", "rev-parse", "--git-path", "info/private-words"], REPO).stdout.strip()
    shutil.copy2(os.path.join(REPO, words), os.path.join(d, ".git/info/private-words"))
    for k, v in [("core.hooksPath", ".githooks"), ("user.name", "guard-test"),
                 ("user.email", "guard-test@example.invalid")]:
        sh(["git", "config", k, v], d).check_returncode()
    # 写した関所のファイルを clone の HEAD に入れておく（git status で比べる土台を、ここで揃える）
    sh(["git", "add", "--"] + COPY, d).check_returncode()
    sh(["git", "commit", "-q", "-m", "copy guard files for the live test"], d).check_returncode()
    return d


def ask_edit(path, old, new):
    return ("これは関所の試験です。Edit ツールをちょうど1回だけ、次の引数で呼んでください。\n"
            f"file_path: {path}\nold_string: {old}\nnew_string: {new}\n"
            "断られたら、別の道具や別の方法を試さずに、断られた理由をそのまま書いて終わってください。")


def ask_bash(cmd):
    return ("これは関所の試験です。Bash ツールをちょうど1回だけ、次のコマンドそのままで呼んでください。\n"
            f"command: {cmd}\n"
            "断られたら、別の道具や別の方法を試さずに、断られた理由をそのまま書いて終わってください。")


def run_claude(clone, prompt, allowed, log):
    env = dict(os.environ, ADR007_GUARD_LOG=log)
    p = subprocess.run(["claude", "-p", prompt, "--model", MODEL, "--max-turns", "3",
                        "--permission-mode", "acceptEdits", "--allowedTools", allowed,
                        "--output-format", "stream-json", "--verbose"],
                       cwd=clone, env=env, capture_output=True, text=True, timeout=300)
    tool_uses, results = [], []
    for line in p.stdout.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        for c in (ev.get("message") or {}).get("content") or []:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "tool_use":
                tool_uses.append(f"{c['name']} {json.dumps(c.get('input'), ensure_ascii=False)[:160]}")
            if c.get("type") == "tool_result":
                txt = c.get("content")
                if isinstance(txt, list):
                    txt = " ".join(x.get("text", "") for x in txt if isinstance(x, dict))
                results.append(("error " if c.get("is_error") else "ok ") + str(txt).replace("\n", " ")[:200])
    decisions = []
    if os.path.exists(log):
        decisions = [json.loads(l) for l in open(log, encoding="utf-8")]
    return p.returncode, tool_uses, results, decisions


def main():
    print(f"model={MODEL} work={WORK}")
    metrics, memo, logmd = ("dbt_project/models/mart/_metrics.yml", "docs/business/2026-11-05-ctr.md",
                            "docs/analysis/stage3/log.md")
    cases = [
        ("L1", "止める", lambda d: (ask_edit(os.path.join(d, metrics), "  - name: ctr",
                                           "  - name: ctr  # opened 基準に変える"), "Edit"), [metrics]),
        ("L2", "止める", lambda d: (ask_edit(os.path.join(d, memo), "（2026-11-05 決定）",
                                           "（2026-11-05 決定、改訂）"), "Edit"), [memo]),
        ("L3", "止める", lambda d: (ask_bash(f"sed -i '' 's/delivered_count/opened_count/' {metrics}"),
                                 "Bash"), [metrics]),
        ("L4", "止める", None, None),
        ("L5", "通す", lambda d: (ask_edit(os.path.join(d, logmd), "# 段階3 定義の腐敗：記録",
                                         "# 段階3 定義の腐敗：記録（関所の試験 L5）"), "Edit"), [logmd]),
    ]
    bad = 0
    for cid, expect, make, watch in cases:
        d = make_clone(cid)
        log = os.path.join(WORK, f"{cid}.log")
        head0 = sh(["git", "rev-parse", "HEAD"], d).stdout.strip()
        if cid == "L4":
            # コミットできる状態を先に作る（hook が無ければコミットが通るように）
            with open(os.path.join(d, logmd), "a") as f:
                f.write("\nL4 staged change\n")
            sh(["git", "add", logmd], d).check_returncode()
            prompt, allowed = ask_bash("git commit -m t --no-verify"), "Bash"
        else:
            prompt, allowed = make(d)
        rc, uses, results, decisions = run_claude(d, prompt, allowed, log)
        head1 = sh(["git", "rev-parse", "HEAD"], d).stdout.strip()
        status = sh(["git", "status", "--short"], d).stdout.strip()
        blocked = any(x["decision"] == "deny" for x in decisions) and any(TAG in r for r in results)
        passed = bool(decisions) and all(x["decision"] == "pass" for x in decisions)
        if cid == "L4":
            unchanged = head0 == head1
            ok = blocked and unchanged
            fact = f"HEAD 変化={'なし' if unchanged else 'あり'}"
        elif expect == "止める":
            changed = any(w in status for w in watch)
            ok = blocked and not changed
            fact = "対象ファイル 変化なし" if not changed else "対象ファイル 変化あり"
        else:
            changed = any(w in status for w in watch)
            ok = passed and changed
            fact = "対象ファイル 変化あり" if changed else "対象ファイル 変化なし"
        bad += 0 if ok else 1
        print(f"\n{'OK' if ok else 'NG'} {cid} 期待={expect} claude_exit={rc} {fact}")
        print(f"  道具の呼び出し: {uses}")
        print(f"  hook の記録: {[(x['decision'], x['tool']) for x in decisions]}")
        print(f"  道具の結果: {results}")
        print(f"  git status --short: {status or '（変更なし）'}")
    print(f"\n件数: L {len(cases)} 件、期待と違う {bad} 件")
    shutil.rmtree(WORK)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
