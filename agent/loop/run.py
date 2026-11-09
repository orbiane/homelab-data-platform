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
  ロック（同時に1つ）→ JST 02:30〜03:30 は始めない → 1日に始めるのは8件まで →
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
import shutil
import signal
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
HOME = pathlib.Path.home()
LOOP_HOME = HOME / "homelab-loop"
JST = datetime.timezone(datetime.timedelta(hours=9))
QUIET_START, QUIET_END = datetime.time(2, 30), datetime.time(3, 30)
MAX_PER_DAY = 8
MAX_OPEN = 3
TIMEOUT_SEC = 90 * 60
MODEL, EFFORT, MAX_TURNS = "claude-opus-5-5", "medium", "80"
# 作業場所に、ふだんの作業場所への symlink として置く、git の外のデータ（読むだけ）
DATA_LINKS = ["dbt_project/warehouse.duckdb", "dbt_project/target", "data_generation/output"]
# 据え付けた写しと origin/main を比べるファイル
GUARD_FILES = [".claude/loop-settings.json", ".claude/hooks/loop_guard.py",
               "agent/loop/run.py", "agent/loop/pick.py", "agent/loop/prompt.md"]


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
            if e.get("kind") != "end":
                continue
            d = days.setdefault(e["at"][:10], {"runs": 0, "ids": [], "cost": 0.0, "minutes": 0.0, "fail": 0})
            d["runs"] += 1
            d["ids"].append(e.get("id", "?"))
            d["cost"] += e.get("total_cost_usd") or 0.0
            d["minutes"] += (e.get("wall_sec") or 0) / 60
            d["fail"] += 0 if e.get("exit_code") == 0 else 1
        lines = ["date\truns\tids\ttotal_cost_usd\tminutes\tnonzero_exit"]
        for day in sorted(days):
            d = days[day]
            lines.append(f"{day}\t{d['runs']}\t{','.join(d['ids'])}\t{d['cost']:.2f}\t{d['minutes']:.1f}\t{d['fail']}")
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


def claude_cmd(claude, wt, task_id):
    prompt = (ROOT / "agent/loop/prompt.md").read_text(encoding="utf-8").replace("<ID>", task_id)
    return [claude, "-p", prompt,
            "--setting-sources", "user",
            "--settings", str(ROOT / ".claude/loop-settings.json"),
            "--mcp-config", str(wt / ".mcp.json"), "--strict-mcp-config",
            "--permission-mode", "dontAsk", "--permission-prompts", "none",
            "--model", MODEL, "--effort", EFFORT, "--max-turns", MAX_TURNS,
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


def pick(wt, only):
    """(ID か None, 理由, 各行の状態) を返す。pick.py は据え付けた写しを、NEXT.md は origin/main のものを使う。"""
    sys.path.insert(0, str(ROOT / "agent/loop"))
    import pick as picker  # noqa: E402
    rows = picker.parse_table(git(wt, "show", "origin/main:NEXT.md"))
    prs = picker.fetch_prs(wt)
    table = {t: f"{k}/{s}" for (t, k, _), s in zip(rows, picker.statuses(rows, prs).values())}
    if not only:
        return (*picker.choose(rows, prs, MAX_OPEN), table)
    row = [r for r in rows if r[0] == only]
    if not row:
        return None, f"--only {only}：NEXT.md の表に無い", table
    st = picker.statuses(rows, prs)[only]
    if row[0][1] != "loop" or st != picker.NONE:
        return None, f"--only {only}：種類が {row[0][1]}、状態が {st}。種類 loop で PR の無い行だけを回す", table
    n_open = sum(1 for p in prs if p.get("state") == "OPEN" and p.get("headRefName", "").startswith("auto/"))
    if n_open >= MAX_OPEN:
        return None, f"--only {only}：開いているループの PR が {n_open} 件", table
    return only, f"--only {only}（依存は見ない。持ち主が手で選んだ）", table


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


def run_claude(cmd, wt, env, out_path, err_path):
    t0 = time.monotonic()
    with open(out_path, "w", encoding="utf-8") as out, open(err_path, "w", encoding="utf-8") as err:
        p = subprocess.Popen(cmd, cwd=wt, env=env, stdout=out, stderr=err, start_new_session=True)
        timed_out = False
        try:
            code = p.wait(timeout=TIMEOUT_SEC)
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only")
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
        log.event(kind="skip", mode=mode, reason="JST 02:30〜03:30 は始めない（毎晩の dbt build の前後）")
        return 0
    if not args.dry_run and log.started_today() >= MAX_PER_DAY:
        log.event(kind="skip", mode=mode, reason=f"今日はもう {MAX_PER_DAY} 件始めた")
        return 0

    stop = prepare_worktree(wt, args.dry_run)
    if stop:
        log.event(kind="stop", mode=mode, reason=stop)
        return 1
    drift = guard_drift(wt)
    task_id, why, table = pick(wt, args.only)
    if not task_id:
        log.event(kind="skip", mode=mode, reason=why, guard_drift=drift,
                  **({"table": table} if args.dry_run else {}))
        return 0

    claude = find_claude()
    cmd = claude_cmd(claude, wt, task_id)
    if args.dry_run:
        shown = [c if i != 2 else "<prompt.md>" for i, c in enumerate(cmd)]
        log.event(kind="dry-run", mode=mode, id=task_id, reason=why, guard_drift=drift, table=table,
                  cmd=" ".join(shown).replace(str(HOME), "~"))
        return 0

    version = subprocess.run([claude, "--version"], capture_output=True, text=True).stdout.strip()
    stamp = now().strftime("%Y%m%d-%H%M%S")
    day_dir = log.logs / stamp[:8]
    day_dir.mkdir(parents=True, exist_ok=True)
    out_path = day_dir / f"{stamp}-{task_id}.jsonl"
    err_path = day_dir / f"{stamp}-{task_id}.stderr.log"
    log.event(kind="start", mode=mode, id=task_id, reason=why, claude_version=version,
              guard_drift=drift, stream=str(out_path).replace(str(HOME), "~"))
    code, timed_out, wall = run_claude(cmd, wt, loop_env(claude), out_path, err_path)
    after_dirty = git(wt, "status", "--porcelain", check=False).strip()
    log.event(kind="end", mode=mode, id=task_id, exit_code=code, timed_out=timed_out,
              wall_sec=round(wall), claude_version=version,
              worktree_dirty_after=len(after_dirty.splitlines()) if after_dirty else 0,
              **read_result(out_path))
    log.write_daily()
    return 0 if code == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
