#!/usr/bin/env python3
"""自律ループ専用の PreToolUse hook（L0。.claude/loop-settings.json でだけ使う）。

標準入力に hook の JSON を受け取り、Bash のコマンドを読んで、次を止める（exit 2、理由を stderr に）。
  P  git push のうち、`git push [-u] origin auto/<名前>` の形でないもの
     （行き先が auto/ で始まる名前1つでない、refspec に : や + がある、HEAD や main を含む、
       ほかのオプションや git の前置きのオプションがある、git の別名や send-pack で push する）
  G  gh の pr merge・api・repo・workflow（と、それらを別の名前で呼べる alias・extension）
  D  dbt のうち、--project-dir と --profiles-dir がどちらもちょうど1回ずつ power/dbt_project を
     指す形でないもの（cd してから打つ、DBT_PROJECT_DIR・DBT_PROFILES_DIR を同じ行で書く、も止める）
  X  launchctl・mf・duckdb を、パスや別の書き方で呼ぶもの（deny の規則は文字で当たるので、ここで補う）
通すときは何も出さずに exit 0（あとは権限の表が決める）。
自分のエラーや時間切れでは exit 2（止める側に倒す。ADR-007 と同じ）。

コマンドは、制御の記号（; && || | & ( ) と引用の外の改行）で区切って1つずつ読む。
sh -c・eval・$( )・` ` の中と、xargs・find -exec・timeout などのあとに続くコマンドも読む。
"""
import json
import os
import re
import shlex
import signal
import subprocess
import sys

TIMEOUT_SEC = 5
TAG = "[ループの関所]"
POWER_DIR = "power/dbt_project"
AUTO_REF_RE = re.compile(r"^auto/[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*$")
ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
SEPARATOR_CHARS = set(";&|()")
GUARDED = {"git", "gh", "dbt", "launchctl", "mf", "duckdb"}
BLOCKED_PROGRAMS = {"launchctl", "mf", "duckdb"}
# あとに続く語をコマンドとして走らせるもの。これより後ろに見張るコマンドの名前があれば、そこから読む
CARRIERS = {"command", "builtin", "exec", "nohup", "time", "noglob", "sudo", "doas", "xargs", "env",
            "nice", "timeout", "stdbuf", "caffeinate", "watch", "parallel", "flock", "script",
            "unbuffer", "chronic", "find", "-exec", "-execdir", "-ok", "-okdir"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish"}
GIT_GLOBAL_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path",
                         "--config-env", "--super-prefix"}
GIT_PUSH_LIKE = {"send-pack"}
GH_BLOCKED = {"api", "repo", "workflow", "alias", "extension", "ext"}
GH_FLAGS_WITH_VALUE = {"-R", "--repo", "--hostname"}


class Block(Exception):
    pass


def on_timeout(signum, frame):
    sys.stderr.write(f"{TAG} hook が時間切れになったので止めます\n")
    sys.exit(2)


def unquoted_newlines_to_semicolons(cmd):
    """引用の外の改行を ; に変える（shlex は改行をただの空白として読むため）。"""
    out, quote, esc = [], None, False
    for ch in cmd:
        if esc:
            esc = False
        elif ch == "\\" and quote != "'":
            esc = True
        elif quote:
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
        elif ch == "\n":
            out.append(" ; ")
            continue
        out.append(ch)
    return "".join(out)


def tokenize(cmd):
    lexer = shlex.shlex(unquoted_newlines_to_semicolons(cmd), posix=True, punctuation_chars=";&|()<>")
    lexer.whitespace_split = True
    return list(lexer)


def segments(tokens):
    """制御の記号で、単純なコマンドの並びに分ける。"""
    seg, out = [], []
    for t in tokens:
        if t and set(t) <= SEPARATOR_CHARS:
            if seg:
                out.append(seg)
            seg = []
        else:
            seg.append(t)
    if seg:
        out.append(seg)
    return out


def strip_redirects(seg):
    """< > >> 2> などと、その書き先を外す。"""
    out, skip = [], False
    for t in seg:
        if skip:
            skip = False
            continue
        if t and set(t) <= set("<>"):
            skip = True
            if out and out[-1].isdigit():  # 2> の 2
                out.pop()
            continue
        out.append(t)
    return out


def body_of(seg):
    """先頭の変数の代入と `uv run [オプション]` を外した語の並び。"""
    i = 0
    while i < len(seg) and ASSIGN_RE.match(seg[i]):
        i += 1
    words = seg[i:]
    if words and os.path.basename(words[0]) in ("uv", "uvx"):
        j = 1
        if os.path.basename(words[0]) == "uv":
            if len(words) < 2 or words[1] != "run":
                return words
            j = 2
        while j < len(words) and words[j].startswith("-"):
            j += 2 if words[j] in ("--project", "--directory", "--with", "--python", "-p", "--from") else 1
        if j < len(words):
            return body_of(words[j:])
    return words


def git_alias(cwd, name):
    r = subprocess.run(["git", "-C", cwd, "config", "--get", f"alias.{name}"],
                       capture_output=True, text=True, timeout=TIMEOUT_SEC)
    return r.stdout.strip() if r.returncode == 0 else ""


def check_git(words, cwd):
    i, global_opts = 1, []
    while i < len(words) and words[i].startswith("-"):
        opt = words[i]
        global_opts.append(opt)
        if opt in GIT_GLOBAL_WITH_VALUE and i + 1 < len(words):
            global_opts.append(words[i + 1])
            i += 2
        else:
            i += 1
    joined = " ".join(global_opts)
    if re.search(r"alias\.|--config-env", joined):
        raise Block(f"P：git の前置きのオプションで別名を作る書き方（{joined}）は止めます。")
    if i >= len(words):
        return
    sub, args = words[i], words[i + 1:]
    if sub in GIT_PUSH_LIKE or (sub == "subtree" and "push" in args):
        raise Block(f"P：`git {sub}` は push と同じ働きをするので止めます。"
                    "push は `git push -u origin auto/<ID>` の形で打ちます。")
    if sub != "push":
        alias = git_alias(cwd, sub)
        if alias and (alias.startswith("!") or re.search(r"\b(?:push|send-pack)\b", alias)):
            raise Block(f"P：git の別名 `{sub}`（= {alias}）は push かシェルを呼びうるので止めます。"
                        "push は `git push -u origin auto/<ID>` の形で打ちます。")
        return
    if global_opts:
        raise Block(f"P：git push の前に git のオプション（{joined}）があります。"
                    "push は `git push -u origin auto/<ID>` の形だけ通します。")
    rest = [a for a in args if a not in ("-u", "--set-upstream")]
    opts = [a for a in rest if a.startswith("-")]
    if opts:
        raise Block(f"P：git push のオプション（{' '.join(opts)}）は通しません。"
                    "push は `git push -u origin auto/<ID>` の形だけ通します。")
    if len(rest) != 2 or rest[0] != "origin":
        raise Block(f"P：git push の行き先が `origin` と auto/ のブランチ1つではありません"
                    f"（{' '.join(args) or '指定なし'}）。push は `git push -u origin auto/<ID>` の形だけ通します。")
    ref = rest[1]
    if ":" in ref or "+" in ref:
        raise Block(f"P：refspec に `:` や `+` があります（{ref}）。ループは auto/ のブランチにだけ、そのままの名前で push します。")
    if "HEAD" in ref or "main" in ref:
        raise Block(f"P：push の行き先に HEAD か main が入っています（{ref}）。")
    if not AUTO_REF_RE.match(ref):
        raise Block(f"P：push の行き先が auto/ で始まるブランチの名前ではありません（{ref}）。")


def check_gh(words):
    pos, skip = [], False
    for w in words[1:]:
        if skip:
            skip = False
        elif w in GH_FLAGS_WITH_VALUE:
            skip = True
        elif not w.startswith("-"):
            pos.append(w)
    if not pos:
        return
    if pos[0] in GH_BLOCKED:
        raise Block(f"G：`gh {pos[0]}` はループでは使いません（マージ・GitHub の設定・別名での呼び出しを止めるため）。")
    if pos[0] == "pr" and len(pos) > 1 and pos[1] == "merge":
        raise Block("G：`gh pr merge` は止めます。マージは持ち主がします（ADR-008）。")


def flag_values(words, flag):
    vals = []
    for i, w in enumerate(words):
        if w == flag:
            vals.append(words[i + 1] if i + 1 < len(words) else "")
        elif w.startswith(flag + "="):
            vals.append(w.split("=", 1)[1])
    return vals


def check_dbt(words, ctx):
    if ctx["has_cd"]:
        raise Block("D：cd と dbt を同じコマンドに書かないでください。dbt は作業場所の根から、"
                    f"`--project-dir {POWER_DIR} --profiles-dir {POWER_DIR}` を付けて打ちます。")
    if ctx["dbt_env"]:
        raise Block("D：DBT_PROJECT_DIR・DBT_PROFILES_DIR を、dbt と同じコマンドに書かないでください。")
    for flag in ("--project-dir", "--profiles-dir"):
        vals = flag_values(words, flag)
        if vals != [POWER_DIR]:
            raise Block(f"D：dbt の {flag} は、ちょうど1回 `{POWER_DIR}` を指す形だけ通します（今は {vals or '指定なし'}）。"
                        "今の基準データの dbt_project/ には、ループは dbt を向けません（CLAUDE.md の守ること7）。")


def check_command(words, cwd, ctx, depth):
    prog = os.path.basename(words[0])
    # 中にコマンドを持つ語（$( ) と ` `）も読む
    for w in words:
        if "$(" in w or "`" in w:
            analyze(w.replace("$(", " ; ").replace(")", " ; ").replace("`", " ; "), cwd, depth + 1)
    if prog in SHELLS:
        for k, w in enumerate(words[1:], start=1):
            if re.match(r"^-[A-Za-z]*c[A-Za-z]*$", w) and k + 1 < len(words):
                analyze(words[k + 1], cwd, depth + 1)
                break
        return
    if prog == "eval":
        analyze(" ".join(words[1:]), cwd, depth + 1)
        return
    if prog == "git":
        check_git(words, cwd)
    elif prog == "gh":
        check_gh(words)
    elif prog == "dbt":
        check_dbt(words, ctx)
    elif prog in BLOCKED_PROGRAMS:
        raise Block(f"X：`{prog}` はループでは使いません（権限の表の deny と同じ。パスで呼んでも止めます）。")
    else:
        # xargs・find -exec・timeout などのあとに続く、見張るコマンドを読む
        carried = False
        for k, w in enumerate(words[1:], start=1):
            if os.path.basename(words[k - 1]) in CARRIERS or words[k - 1] in CARRIERS:
                carried = True
            if carried and os.path.basename(w) in GUARDED | SHELLS | {"eval"}:
                check_command(words[k:], cwd, ctx, depth + 1)
                return
        if os.path.basename(words[0]) in CARRIERS:
            for k, w in enumerate(words[1:], start=1):
                if os.path.basename(w) in GUARDED | SHELLS | {"eval"}:
                    check_command(words[k:], cwd, ctx, depth + 1)
                    return


def analyze(cmd, cwd, depth=0):
    if depth > 4:
        raise Block("入れ子が深すぎるので止めます。")
    try:
        tokens = tokenize(cmd)
    except ValueError as e:
        # 引用が閉じていないなど、読み切れないとき。見張る語があれば止める側に倒す
        if re.search(r"\b(?:push|gh|dbt|launchctl|mf|duckdb)\b", cmd):
            raise Block(f"コマンドを読み切れませんでした（{e}）。見張る語を含むので止めます。")
        return
    bodies = [b for b in (body_of(strip_redirects(s)) for s in segments(tokens)) if b]
    ctx = {"has_cd": any(os.path.basename(b[0]) in ("cd", "pushd") for b in bodies),
           "dbt_env": bool(re.search(r"DBT_PROJECT_DIR|DBT_PROFILES_DIR", cmd))}
    for words in bodies:
        check_command(words, cwd, ctx, depth)


def main():
    signal.signal(signal.SIGALRM, on_timeout)
    signal.alarm(TIMEOUT_SEC)
    data = json.load(sys.stdin)
    if data.get("tool_name") != "Bash":
        sys.exit(0)
    cmd = (data.get("tool_input") or {}).get("command", "")
    cwd = data.get("cwd") or os.getcwd()
    try:
        analyze(cmd, cwd)
    except Block as b:
        sys.stderr.write(f"{TAG} {b}\n")
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException as e:  # 自分のエラーは止める側に倒す
        sys.stderr.write(f"{TAG} hook 自身のエラーで止めます: {type(e).__name__}: {e}\n")
        sys.exit(2)
