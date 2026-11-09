#!/usr/bin/env python3
"""自律ループの据え付け（L0）。持ち主が、ふだんの作業場所（このリポジトリの clone）の根から打つ。

使い方:
  python3 agent/loop/install.py worktree [--dry-run]           # ~/homelab-loop/wt を作り、git の外のデータを symlink で置く（excludes も行う）
  python3 agent/loop/install.py excludes [--dry-run]           # symlink を git の info/exclude に足す（作業場所を汚れて見せない）
  python3 agent/loop/install.py copy [--ref REF] [--dry-run]   # 守りのファイルを REF の版で ~/homelab-loop/bin に写す（既定 origin/main）
  python3 agent/loop/install.py plist [--dry-run]              # LaunchAgent の plist を ~/Library/LaunchAgents/ に書く（読み込みはしない）

どれも、すでにあるものは上書きせずに止まる（copy だけは、写しを REF の版に置き換える）。
plist の読み込み（launchctl）は、この台本ではしない。README の手順で、持ち主が手で行う。
"""
import argparse
import os
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
HOME = pathlib.Path.home()
LOOP_HOME = HOME / "homelab-loop"
WT = LOOP_HOME / "wt"
BIN = LOOP_HOME / "bin"
LABEL = "com.homelab-data-platform.loop"
PLIST = HOME / "Library" / "LaunchAgents" / f"{LABEL}.plist"
DATA_LINKS = ["dbt_project/warehouse.duckdb", "dbt_project/target", "data_generation/output"]
GUARD_FILES = [".claude/loop-settings.json", ".claude/hooks/loop_guard.py",
               "agent/loop/run.py", "agent/loop/pick.py", "agent/loop/prompt.md"]


def say(dry, msg):
    print(("（dry-run）" if dry else "") + msg.replace(str(HOME), "~"))


def git(*args):
    r = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"git {' '.join(args)} が失敗しました: {r.stderr.strip()}")
    return r.stdout


def cmd_worktree(dry):
    if WT.exists():
        sys.exit(f"{WT} はもうあります。作り直すなら、持ち主が `git worktree remove` してから".replace(str(HOME), "~"))
    for rel in DATA_LINKS:
        if not (REPO / rel).exists():
            sys.exit(f"ふだんの作業場所に {rel} がありません")
    say(dry, f"git fetch origin main")
    say(dry, f"git worktree add --detach {WT} origin/main")
    if not dry:
        LOOP_HOME.mkdir(exist_ok=True)
        git("fetch", "-q", "origin", "main")
        git("worktree", "add", "-q", "--detach", str(WT), "origin/main")
    for rel in DATA_LINKS:
        say(dry, f"ln -s {REPO / rel} {WT / rel}")
        if not dry:
            (WT / rel).parent.mkdir(parents=True, exist_ok=True)
            os.symlink(REPO / rel, WT / rel)
    cmd_excludes(dry)


def cmd_excludes(dry):
    """symlink を git に未追跡として見せない。.gitignore の `target/` のような末尾の / はディレクトリにしか当たらず、
    symlink には当たらないため。info/exclude は worktree どうしで共有され、コミットされない。"""
    path = REPO / git("rev-parse", "--git-path", "info/exclude").strip()
    have = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    for rel in DATA_LINKS:
        line = "/" + rel
        if line in have:
            continue
        say(dry, f"足す {line} → {path}")
        if not dry:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")


def cmd_copy(ref, dry):
    rev = git("rev-parse", "--short", ref).strip()
    for rel in GUARD_FILES:
        body = subprocess.run(["git", "-C", str(REPO), "show", f"{ref}:{rel}"], capture_output=True, text=True)
        if body.returncode != 0:
            sys.exit(f"{ref} に {rel} がありません")
        say(dry, f"写す {ref}（{rev}）:{rel} → {BIN / rel}")
        if not dry:
            (BIN / rel).parent.mkdir(parents=True, exist_ok=True)
            (BIN / rel).write_text(body.stdout, encoding="utf-8")
    if not dry:
        (BIN / "INSTALLED_FROM").write_text(f"{ref} {rev}\n", encoding="utf-8")
        (LOOP_HOME / "logs").mkdir(parents=True, exist_ok=True)


def cmd_plist(dry):
    if PLIST.exists():
        sys.exit(f"{PLIST} はもうあります（先に README の「外し方」で外す）".replace(str(HOME), "~"))
    claude = shutil.which("claude")
    if not claude:
        sys.exit("claude が PATH に見つかりません")
    path = ":".join(dict.fromkeys([os.path.dirname(claude), os.path.dirname(sys.executable),
                                   "/opt/homebrew/bin", str(HOME / ".local" / "bin"),
                                   "/usr/bin", "/bin", "/usr/sbin", "/sbin"]))
    text = (REPO / "agent/loop/launchd.plist.template").read_text(encoding="utf-8")
    text = text.replace("__PYTHON__", sys.executable).replace("__HOME__", str(HOME)).replace("__PATH__", path)
    say(dry, f"書く {PLIST}（python={sys.executable}、PATH={path}）")
    if not dry:
        PLIST.write_text(text, encoding="utf-8")
        (LOOP_HOME / "logs").mkdir(parents=True, exist_ok=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["worktree", "excludes", "copy", "plist"])
    ap.add_argument("--ref", default="origin/main")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.step == "worktree":
        cmd_worktree(a.dry_run)
    elif a.step == "excludes":
        cmd_excludes(a.dry_run)
    elif a.step == "copy":
        cmd_copy(a.ref, a.dry_run)
    else:
        cmd_plist(a.dry_run)


if __name__ == "__main__":
    main()
