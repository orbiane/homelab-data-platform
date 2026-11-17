#!/usr/bin/env python3
"""自律ループの起動の台本（L0、ADR-008）。launchd が毎時起こす。

使い方:
  python3 run.py              # 定時の1回（launchd から）
  python3 run.py --dry-run    # 選ぶ ID と、起こすコマンドを出すだけ。作業場所も Claude も触らない
  python3 run.py --only M2    # 決まった1件を、手で1回だけ回す（依存は見ない。種類 loop と PR なしは見る）

守りのファイルの置き場所（ROOT）：この台本の2つ上のディレクトリ。据え付けると ~/homelab-loop/bin で、
そこには .claude/loop-settings.json、.claude/hooks/loop_guard.py、agent/loop/{run.py,pick.py,prompt.md} の写しがある。
作業場所（--worktree、既定 ~/homelab-loop/wt）は、毎回 origin/main に戻してから使うので、ループが作業場所で
これらを書き換えても、次の回の守りは変わらない（変えるには、持ち主が据え付け直す）。

1回の流れ:
  ロック（同時に1つ）→ JST 01:20〜03:30 は始めない → 1日に始めるのは8件まで →
  作業場所が汚れていたら止まる → git fetch して origin/main に戻す（detached）→
  pick.py で ID を決める（開いた auto/ の PR が3つ以上、または選べる行が無ければ、Claude を起こさずに終わる）→
  claude -p を、ループの表・dontAsk・90分の時間切れで起こす → 記録を ~/homelab-loop/logs/ に残す
"""
import argparse
import datetime
import fcntl
import json
import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
HOME = pathlib.Path.home()
LOOP_HOME = HOME / "homelab-loop"
JST = datetime.timezone(datetime.timedelta(hours=9))
# 毎晩の dbt build（JST 03:00）に、上限90分の回が重ならないように。起動は毎時23分なので、01:23 と 02:23 も始めない
# （指示書は 02:30〜03:30。持ち主の判断で 2026-11-10 に広げた）
QUIET_START, QUIET_END = datetime.time(1, 20), datetime.time(3, 30)
MAX_PER_DAY = 8
MAX_OPEN = 3
TIMEOUT_SEC = 90 * 60
MODEL, EFFORT, MAX_TURNS = "claude-opus-5-5", "medium", "80"
# 作業場所に、ふだんの作業場所への symlink として置く、git の外のデータ（読むだけ）
DATA_LINKS = ["dbt_project/warehouse.duckdb", "dbt_project/target", "data_generation/output"]
# 据え付けた写しと origin/main を比べるファイル
GUARD_FILES = [".claude/loop-settings.json", ".claude/hooks/loop_guard.py",
               "agent/loop/run.py", "agent/loop/pick.py", "agent/loop/prompt.md",
               # L1：レビュー役（install.py の GUARD_FILES と同じ並び）
               ".claude/review-settings.json", "agent/loop/review_checks.py", "agent/loop/review_prompt.md"]
# レビュー役（L1、docs/agent/review.md）
MAX_REVIEWS = 3              # 1回の起動でレビューする PR の数
REVIEW_TIMEOUT_SEC = 10 * 60  # 1つのレビューの上限
REVIEW_MAX_TURNS = "40"
DIFF_LIMIT = 60000           # 頼む文に貼る差分の上限（文字）。残りはレビュー役が git diff で見る


def now():
    return datetime.datetime.now(JST)


def git(wt, *args, check=True):
    r = subprocess.run(["git", "-C", str(wt), *args], capture_output=True, text=True, timeout=120)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} が失敗しました: {r.stderr.strip()}")
    return r.stdout


class Log:
    def __init__(self, logs):
        self.logs = logs
        logs.mkdir(parents=True, exist_ok=True)

    def event(self, **kw):
        kw = {"at": now().isoformat(timespec="seconds"), **kw}
        with open(self.logs / "runs.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(kw, ensure_ascii=False) + "\n")
        print(json.dumps(kw, ensure_ascii=False))

    def started_today(self):
        today = now().date().isoformat()
        n = 0
        path = self.logs / "runs.jsonl"
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get("kind") == "start" and e.get("at", "").startswith(today):
                    n += 1
        return n

    def write_daily(self):
        """1日1行の要約（daily.tsv）を、runs.jsonl から作り直す。"""
        days = {}
        path = self.logs / "runs.jsonl"
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("kind") not in ("end", "review"):
                continue
            d = days.setdefault(e["at"][:10], {"runs": 0, "ids": [], "cost": 0.0, "minutes": 0.0, "fail": 0,
                                               "reviews": 0, "review_cost": 0.0})
            if e["kind"] == "review":  # L1：レビュー役。1日の上限（start の数）には数えない
                d["reviews"] += 1
                d["review_cost"] += e.get("total_cost_usd") or 0.0
                continue
            d["runs"] += 1
            d["ids"].append(e.get("id", "?"))
            d["cost"] += e.get("total_cost_usd") or 0.0
            d["minutes"] += (e.get("wall_sec") or 0) / 60
            d["fail"] += 0 if e.get("exit_code") == 0 else 1
        lines = ["date\truns\tids\ttotal_cost_usd\tminutes\tnonzero_exit\treviews\treview_cost_usd"]
        for day in sorted(days):
            d = days[day]
            lines.append(f"{day}\t{d['runs']}\t{','.join(d['ids'])}\t{d['cost']:.2f}\t{d['minutes']:.1f}\t{d['fail']}"
                         f"\t{d['reviews']}\t{d['review_cost']:.2f}")
        (self.logs / "daily.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def find_claude():
    for cand in (os.environ.get("HOMELAB_LOOP_CLAUDE"), shutil.which("claude")):
        if cand and os.access(cand, os.X_OK):
            return cand
    raise RuntimeError("claude が見つかりません（launchd の plist の PATH か HOMELAB_LOOP_CLAUDE を確かめる）")


def loop_env(claude):
    """claude に渡す環境。PATH は最小限（claude、この python、Homebrew、~/.local/bin の dbt、OS の道具）。"""
    env = dict(os.environ)
    path = [os.path.dirname(claude), os.path.dirname(sys.executable), "/opt/homebrew/bin",
            str(HOME / ".local" / "bin"), "/usr/bin", "/bin", "/usr/sbin", "/sbin"]
    env["PATH"] = ":".join(dict.fromkeys(path))
    env["HOMELAB_LOOP_ROOT"] = str(ROOT)
    return env


CONT_MARK = "<!-- 続き -->"


def loop_prompt(task_id, cont=None):
    """prompt.md の前置き。続き（決め・直し・途中）のときだけ、印より後ろの節を、種類と渡す文で埋めて足す。"""
    text = (ROOT / "agent/loop/prompt.md").read_text(encoding="utf-8")
    head, _, tail = text.partition(CONT_MARK)
    if not cont:
        return head.rstrip().replace("<ID>", task_id) + "\n"
    trigger = cont.get("trigger") or "（無し。PR の本文の最初の行が「途中」）"
    return (head.rstrip() + "\n\n" + tail.strip()).replace("<ID>", task_id).replace(
        "<MODE>", cont["mode"]).replace("<PR>", str(cont["pr"])).replace(
        "<BRANCH>", cont["branch"]).replace("<TRIGGER>", trigger) + "\n"


def claude_cmd(claude, wt, task_id, cont=None):
    prompt = loop_prompt(task_id, cont)
    # data_generation/output は、ふだんの作業場所への symlink。実体が作業場所の外なので、そのままでは
    # `cd data_generation/output && shasum ...`（loop.md の 1 の 2）の cd が承認の要る cd になり、dontAsk で断られる。
    # 実体を追加の作業場所にすると、cd は読むだけの扱いになる。Edit の allow は ./** だけなので、そこへの書き込みは断られたまま
    data_dir = os.path.realpath(wt / "data_generation/output")
    return [claude, "-p", prompt,
            "--add-dir", data_dir,
            "--setting-sources", "user",
            "--settings", str(ROOT / ".claude/loop-settings.json"),
            "--mcp-config", str(wt / ".mcp.json"), "--strict-mcp-config",
            "--permission-mode", "dontAsk", "--permission-prompts", "none",
            "--model", MODEL, "--effort", EFFORT, "--max-turns", MAX_TURNS,
            "--output-format", "stream-json", "--verbose"]


def review_cmd(claude, prompt):
    """レビュー役の起動。読むだけの表（review-settings.json）、MCP なし、dontAsk。"""
    return [claude, "-p", prompt,
            "--setting-sources", "user",
            "--settings", str(ROOT / ".claude/review-settings.json"),
            "--strict-mcp-config",
            "--permission-mode", "dontAsk", "--permission-prompts", "none",
            "--model", MODEL, "--effort", EFFORT, "--max-turns", REVIEW_MAX_TURNS,
            "--output-format", "stream-json", "--verbose"]


def guard_drift(wt):
    """据え付けた写しと origin/main の版が違うファイルの一覧。"""
    out = []
    for rel in GUARD_FILES:
        r = subprocess.run(["git", "-C", str(wt), "show", f"origin/main:{rel}"], capture_output=True, text=True)
        mine = (ROOT / rel).read_text(encoding="utf-8") if (ROOT / rel).exists() else None
        if r.returncode != 0:
            out.append(f"{rel}（origin/main に無い）")
        elif r.stdout != mine:
            out.append(f"{rel}（origin/main と違う）")
    return out


sys.path.insert(0, str(ROOT / "agent/loop"))
import pick as picker  # noqa: E402


def pick(wt, only, logs):
    """(ID か None, 理由, 各行の状態, 続きの情報か None) を返す。pick.py は据え付けた写しを、NEXT.md は origin/main のものを使う。"""
    rows = picker.parse_table(git(wt, "show", "origin/main:NEXT.md"))
    prs = picker.fetch_prs(wt)
    table = {t: f"{k}/{s}" for (t, k, _), s in zip(rows, picker.statuses(rows, prs).values())}
    if not only:
        posted, runs = picker.load_records(logs)
        got = picker.choose_next(rows, prs, posted, runs, MAX_OPEN)
        cont = got if got["mode"] != picker.NEW and got["id"] else None
        return got["id"], f"[{got['mode']}] {got['why']}", table, cont
    row = [r for r in rows if r[0] == only]
    if not row:
        return None, f"--only {only}：NEXT.md の表に無い", table, None
    st = picker.statuses(rows, prs)[only]
    if row[0][1] != "loop" or st != picker.NONE:
        return None, f"--only {only}：種類が {row[0][1]}、状態が {st}。種類 loop で PR の無い行だけを回す", table, None
    n_open = sum(1 for p in prs if p.get("state") == "OPEN" and p.get("headRefName", "").startswith("auto/"))
    if n_open >= MAX_OPEN:
        return None, f"--only {only}：開いているループの PR が {n_open} 件", table, None
    return only, f"--only {only}（依存は見ない。持ち主が手で選んだ）", table, None


def checkout_branch(wt, branch):
    """続きの回：作業場所を、その PR のブランチの最新に乗せる（ループの表は既存のブランチへの switch を許さないので、台本がやる）。

    手元に同じ名前のブランチがあり、origin と違う（手元にだけあるコミットがありうる）ときは、乗せずに止まる理由を返す。
    """
    git(wt, "fetch", "-q", "origin", branch)
    local = git(wt, "rev-parse", "-q", "--verify", f"refs/heads/{branch}", check=False).strip()
    remote = git(wt, "rev-parse", f"origin/{branch}").strip()
    if local and local != remote:
        return f"手元のブランチ {branch}（{local[:7]}）が origin（{remote[:7]}）と違う。乗せずに止まる"
    git(wt, "switch", "-q", "-C", branch, f"origin/{branch}")
    return None


def prepare_worktree(wt, dry_run):
    if not (wt / ".git").exists():
        raise RuntimeError(f"作業場所 {wt} がありません（README の据え付けの手順）")
    dirty = git(wt, "status", "--porcelain").strip()
    if dirty:
        return f"作業場所に消えていない変更がある（{len(dirty.splitlines())} 件）。何もせずに止まる"
    missing = [p for p in DATA_LINKS if not (wt / p).exists()]
    if missing:
        return f"作業場所に git の外のデータが無い：{missing}"
    git(wt, "fetch", "-q", "origin", "main")
    if not dry_run:
        git(wt, "switch", "-q", "--detach", "origin/main")
    return None


def run_claude(cmd, wt, env, out_path, err_path, timeout=TIMEOUT_SEC):
    t0 = time.monotonic()
    with open(out_path, "w", encoding="utf-8") as out, open(err_path, "w", encoding="utf-8") as err:
        p = subprocess.Popen(cmd, cwd=wt, env=env, stdout=out, stderr=err, start_new_session=True)
        timed_out = False
        try:
            code = p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(p.pid, signal.SIGINT)  # SIGINT はその回の turn を終わらせる（headless の説明書）
            try:
                code = p.wait(timeout=60)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGTERM)
                code = p.wait(timeout=60)
    return code, timed_out, time.monotonic() - t0


def read_result(out_path):
    result = None
    for line in out_path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "result":
            result = e
    if not result:
        return {}
    return {"result_subtype": result.get("subtype"), "is_error": result.get("is_error"),
            "total_cost_usd": result.get("total_cost_usd"), "duration_ms": result.get("duration_ms"),
            "num_turns": result.get("num_turns"),
            "permission_denials": len(result.get("permission_denials") or [])}


def read_reply(out_path):
    """stream-json の result の文（レビュー役の返事）。"""
    reply = ""
    for line in out_path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "result":
            reply = e.get("result") or ""
    return reply


def order_text(wt, task_id):
    """その ID の指示書。docs/orders/<ID>-*.md か、NEXT.md の「小さな作業」の ### <ID> の節（origin/main の版）。"""
    names = git(wt, "ls-tree", "--name-only", "origin/main", "docs/orders/").splitlines()
    hit = [n for n in names if n.rsplit("/", 1)[-1].startswith(f"{task_id}-")]
    if hit:
        return hit[0], git(wt, "show", f"origin/main:{hit[0]}")
    nxt = git(wt, "show", "origin/main:NEXT.md")
    m = re.search(rf"^### {re.escape(task_id)}\b.*?(?=^### |^## |\Z)", nxt, re.M | re.S)
    if m:
        return "NEXT.md の「小さな作業」", m.group(0)
    return "（無し）", "（この ID の指示書は無い。NEXT.md の表の行ではない）"


def reviewed_heads(logs):
    """台本がもうレビューを出した (PR, 先頭のコミット) と、失敗した回数。"""
    done, failed = set(), {}
    for e in picker.read_jsonl(logs / "reviews.jsonl"):
        key = (e.get("pr"), e.get("head"))
        if e.get("kind") == "posted":
            done.add(key)
        elif e.get("kind") == "failed":
            failed[key] = failed.get(key, 0) + 1
    return done, failed


def review_targets(wt, logs, only_pr=None):
    """まだ台本のレビューが無い、開いたループの PR（先頭のコミットごと）。番号の小さい順に MAX_REVIEWS まで。"""
    prs = picker.fetch_prs(wt)
    done, failed = reviewed_heads(logs)
    out, skipped = [], []
    for p in sorted(prs, key=lambda p: p["number"]):
        if p.get("state") != "OPEN" or not p.get("headRefName", "").startswith("auto/"):
            continue
        if only_pr is not None and p["number"] != only_pr:
            continue
        key = (p["number"], p.get("headRefOid"))
        if key in done:
            continue
        if failed.get(key, 0) >= 2:
            skipped.append(f"#{p['number']}（同じ先頭のコミットで2回失敗）")
            continue
        out.append(p)
    return out[:MAX_REVIEWS], skipped


def review_one(p, wt, claude, log, day_dir, stamp):
    """1つの PR をレビューし、コメントを出す。記録は reviews.jsonl と runs.jsonl（kind review）。"""
    import review_checks as rc  # noqa: E402
    n, branch, head = p["number"], p["headRefName"], p.get("headRefOid", "")
    res = rc.for_pr(n, wt)
    task_id = res["id"]
    # 作業場所を PR の先頭に乗せる（レビュー役の Read・git show が PR の中身を見るように）。次の回は prepare_worktree が戻す
    if git(wt, "status", "--porcelain").strip():
        return {"kind": "failed", "pr": n, "head": head, "reason": "作業場所が汚れている"}
    git(wt, "switch", "-q", "--detach", res["head"])
    order_path, order = order_text(wt, task_id)
    prov = rc.show(wt, res["head"], f"docs/agent/provisional/{task_id}.md") or "（無し）"
    diff = git(wt, "diff", "--no-color", f"origin/main...{res['head']}")
    if len(diff) > DIFF_LIMIT:
        diff = diff[:DIFF_LIMIT] + f"\n…（{len(diff)} 文字のうち {DIFF_LIMIT} 文字まで。残りは git diff で見る）"
    prompt = (ROOT / "agent/loop/review_prompt.md").read_text(encoding="utf-8")
    for k, v in {"<<PR>>": f"#{n}", "<<BRANCH>>": branch, "<<HEAD>>": res["head_sha"][:7], "<<ID>>": task_id,
                 "<<CHECKS>>": rc.to_markdown(res), "<<BODY>>": p.get("body") or "（空）",
                 "<<ORDER_PATH>>": order_path, "<<ORDER>>": order, "<<PROVISIONAL>>": prov,
                 "<<DIFF>>": diff}.items():
        prompt = prompt.replace(k, v)
    out_path = day_dir / f"{stamp}-review-{n}.jsonl"
    err_path = day_dir / f"{stamp}-review-{n}.stderr.log"
    code, timed_out, wall = run_claude(review_cmd(claude, prompt), wt, loop_env(claude), out_path, err_path,
                                       REVIEW_TIMEOUT_SEC)
    result = read_result(out_path)
    rec = {"pr": n, "head": head, "id": task_id, "exit_code": code, "timed_out": timed_out,
           "wall_sec": round(wall), "must_fix": res["must_fix"],
           "stream": str(out_path).replace(str(HOME), "~"), **result}
    reply = read_reply(out_path)
    if code != 0 or timed_out or not reply.strip():
        return {"kind": "failed", **rec, "reason": "レビュー役が返事を返さなかった（終了コード・時間切れ・空）"}
    verdict, text, notes = rc.build_comment(reply, res, home=str(HOME))
    leaks = rc.scan_text(wt, "origin/main", text.splitlines(),
                         [f"コメント:{i + 1}" for i in range(len(text.splitlines()))])
    if leaks:
        return {"kind": "failed", **rec, "reason": f"コメントに個人情報らしい行（{len(leaks)} 件）。出さない", "leaks": leaks}
    body_path = day_dir / f"{stamp}-review-{n}.comment.md"
    body_path.write_text(text, encoding="utf-8")
    r = subprocess.run(["gh", "pr", "comment", str(n), "--body-file", str(body_path)],
                       cwd=wt, capture_output=True, text=True, timeout=60)
    url = (r.stdout.strip().splitlines() or [""])[-1]
    if r.returncode != 0 or "#issuecomment-" not in url:
        return {"kind": "failed", **rec, "reason": f"gh pr comment が失敗した：{r.stderr.strip()[:200]}"}
    return {"kind": "posted", **rec, "verdict": verdict, "url": url, "notes": notes}


def run_reviews(wt, log, dry_run, only_pr):
    targets, skipped = review_targets(wt, log.logs, only_pr)
    if dry_run or not targets:
        log.event(kind="review-plan", dry_run=dry_run, targets=[f"#{p['number']} {p.get('headRefOid', '')[:7]}"
                                                                 for p in targets], skipped=skipped)
        return 0
    claude = find_claude()
    stamp = now().strftime("%Y%m%d-%H%M%S")
    day_dir = log.logs / stamp[:8]
    day_dir.mkdir(parents=True, exist_ok=True)
    bad = 0
    for p in targets:
        try:
            rec = review_one(p, wt, claude, log, day_dir, stamp)
        except Exception as e:  # 1つの失敗で、ほかの PR のレビューを止めない
            rec = {"kind": "failed", "pr": p["number"], "head": p.get("headRefOid"), "reason": f"台本の例外：{e}"}
        rec = {"at": now().isoformat(timespec="seconds"), **rec}
        with open(log.logs / "reviews.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        log.event(**{**rec, "kind": "review", "result": rec["kind"]})
        bad += rec["kind"] != "posted"
    log.write_daily()
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only")
    ap.add_argument("--review-only", action="store_true", help="ループの1件は進めず、レビューだけをする")
    ap.add_argument("--review-pr", type=int, help="レビューする PR をこの番号だけにする（試し用）")
    ap.add_argument("--no-review", action="store_true", help="レビューをしない")
    ap.add_argument("--worktree", default=str(LOOP_HOME / "wt"))
    ap.add_argument("--logs", default=str(LOOP_HOME / "logs"))
    args = ap.parse_args()
    wt = pathlib.Path(os.path.expanduser(args.worktree))
    log = Log(pathlib.Path(os.path.expanduser(args.logs)))
    mode = "dry-run" if args.dry_run else ("only" if args.only else "scheduled")

    LOOP_HOME.mkdir(exist_ok=True)
    lock = open(LOOP_HOME / "run.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log.event(kind="skip", mode=mode, reason="ほかの回が動いている（ロック）")
        return 0

    t = now().time()
    if QUIET_START <= t < QUIET_END:
        log.event(kind="skip", mode=mode, reason="JST 01:20〜03:30 は始めない（毎晩の dbt build に重ならないように）")
        return 0
    stop = prepare_worktree(wt, args.dry_run)
    if stop:
        log.event(kind="stop", mode=mode, reason=stop)
        return 1

    code = 0
    if not args.review_only:
        code = loop_once(args, wt, log, mode)
    # ループの1回のあと（1件を選ばなかった回も）、まだレビューしていない PR をレビューする（L1、review.md）。
    # ループの回が作業場所を汚したまま終わったら、レビューはしない（次の回の prepare_worktree が止まって知らせる）
    if not args.no_review:
        if not args.dry_run and git(wt, "status", "--porcelain", check=False).strip():
            log.event(kind="review-plan", dry_run=False, targets=[], skipped=["作業場所が汚れているので、レビューしない"])
        else:
            code = max(code, run_reviews(wt, log, args.dry_run, args.review_pr))
    return code


def loop_once(args, wt, log, mode):
    """ループの1件（新しい行か、続き）。返すのは終了コード。"""
    if not args.dry_run and log.started_today() >= MAX_PER_DAY:
        log.event(kind="skip", mode=mode, reason=f"今日はもう {MAX_PER_DAY} 件始めた")
        return 0
    drift = guard_drift(wt)
    task_id, why, table, cont = pick(wt, args.only, log.logs)
    if not task_id:
        log.event(kind="skip", mode=mode, reason=why, guard_drift=drift,
                  **({"table": table} if args.dry_run else {}))
        return 0
    cont_kw = {"cont": cont["mode"], "pr": cont["pr"], "branch": cont["branch"]} if cont else {}

    claude = find_claude()
    cmd = claude_cmd(claude, wt, task_id, cont)
    if args.dry_run:
        shown = [c if i != 2 else "<prompt.md>" for i, c in enumerate(cmd)]
        log.event(kind="dry-run", mode=mode, id=task_id, reason=why, guard_drift=drift, table=table,
                  cmd=" ".join(shown).replace(str(HOME), "~"), **cont_kw)
        return 0
    if cont:
        stop = checkout_branch(wt, cont["branch"])
        if stop:
            log.event(kind="stop", mode=mode, id=task_id, reason=stop, **cont_kw)
            return 1

    version = subprocess.run([claude, "--version"], capture_output=True, text=True).stdout.strip()
    stamp = now().strftime("%Y%m%d-%H%M%S")
    day_dir = log.logs / stamp[:8]
    day_dir.mkdir(parents=True, exist_ok=True)
    out_path = day_dir / f"{stamp}-{task_id}.jsonl"
    err_path = day_dir / f"{stamp}-{task_id}.stderr.log"
    log.event(kind="start", mode=mode, id=task_id, reason=why, claude_version=version,
              guard_drift=drift, stream=str(out_path).replace(str(HOME), "~"), **cont_kw)
    code, timed_out, wall = run_claude(cmd, wt, loop_env(claude), out_path, err_path)
    after_dirty = git(wt, "status", "--porcelain", check=False).strip()
    log.event(kind="end", mode=mode, id=task_id, exit_code=code, timed_out=timed_out,
              wall_sec=round(wall), claude_version=version,
              worktree_dirty_after=len(after_dirty.splitlines()) if after_dirty else 0,
              **read_result(out_path), **cont_kw)
    if cont:
        sync_pr_body(wt, log, cont, task_id)
    log.write_daily()
    return 0 if code == 0 else 1


def sync_pr_body(wt, log, cont, task_id):
    """続きの回のあと、PR の本文を、ブランチの最新の報告に置き換える（仮決め L1-8）。

    ループの表は gh pr edit を許さない。本文の最初の行の「途中」を外したかどうかを、次の回の pick が読めるように、台本がやる。
    """
    git(wt, "fetch", "-q", "origin", cont["branch"], check=False)
    report = subprocess.run(["git", "-C", str(wt), "show", f"origin/{cont['branch']}:docs/agent/reports/{task_id}.md"],
                            capture_output=True, text=True)
    if report.returncode != 0:
        log.event(kind="pr-body", pr=cont["pr"], result="skip", reason="ブランチに報告が無い")
        return
    body_path = log.logs / f"pr-{cont['pr']}-body.md"
    body_path.write_text(report.stdout, encoding="utf-8")
    r = subprocess.run(["gh", "pr", "edit", str(cont["pr"]), "--body-file", str(body_path)],
                       cwd=wt, capture_output=True, text=True, timeout=60)
    log.event(kind="pr-body", pr=cont["pr"], result="ok" if r.returncode == 0 else "failed",
              status_line=picker.body_status_line(report.stdout)[:80], stderr=r.stderr.strip()[:200])


if __name__ == "__main__":
    sys.exit(main())
