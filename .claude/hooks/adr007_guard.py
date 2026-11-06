#!/usr/bin/env python3
"""ADR-007 の道具の入口（Claude Code の PreToolUse hook）。

標準入力に hook の JSON を受け取り、次のどれかを返す。
  止める: permissionDecision "deny" の JSON（exit 0）
  聞く:   permissionDecision "ask" の JSON（exit 0）
  通す:   何も出さない（exit 0）。ふだんの承認の流れに進む
自分のエラーや時間切れでは exit 2（止める側に倒す）。

規則の番号は docs/decisions/ADR-007-definition-change-guard.md の R1〜R5。
"""
import json
import os
import re
import shlex
import signal
import subprocess
import sys

TIMEOUT_SEC = 5
TAG = "[ADR-007 関所]"

MEMO_RE = re.compile(r"docs/business/[A-Za-z0-9._-]+\.md")
DEF_NAMES = ("_metrics.yml", "_semantic_models.yml")
# 中身で定義と決めるキー（行頭。前の空白は許す）。dbt は models の下のどの名前の YAML でも受け付けるため
DEF_KEY_RE = re.compile(r"^[ \t]*(?:metrics|semantic_models)[ \t]*:", re.MULTILINE)
WRITE_TOOLS = ("Edit", "MultiEdit", "Write", "NotebookEdit")

# R5：Bash で守る場所を指す名前
PROTECTED_WORDS = ("_metrics.yml", "_semantic_models.yml", "docs/business",
                   ".claude/settings.json", ".claude/hooks", ".githooks")
# R5：dbt_project/models の下の YAML のパス（名前の違う新しい定義のファイルも守る）
MODELS_YAML_RE = re.compile(r"models/\S*\.ya?ml")
# R5：書き換えの印
WRITE_CMDS = ("tee", "sed", "perl", r"python[0-9.]*", "awk", "cp", "mv", "rm",
              "truncate", "dd", "ln", "patch")
WRITE_CMD_RE = re.compile(r"(?:^|[^A-Za-z0-9_.-])(?:%s)(?:[^A-Za-z0-9_.-]|$)" % "|".join(WRITE_CMDS))
GIT_WRITE_RE = re.compile(r"\bgit\b[^;&|]*\b(?:apply|checkout|restore)\b")
# > のうち、ファイルを書かないもの（2>&1、>/dev/null）は印にしない
HARMLESS_REDIRECT_RE = re.compile(r"[0-9]*>&[0-9-]+|[0-9]*>>?\s*/dev/null\b")
# git commit で、後ろに値を取る短いオプション
COMMIT_OPTS_WITH_VALUE = set("mFcCt")

HOW_TO_PASS = ("通すには：変える箇所の説明文に、HEAD にコミット済みの決定メモのパス "
               "`docs/business/<名前>.md` を書く。決定メモが無いなら、抜け道を探さずに止まって人に聞く。")


def on_timeout(signum, frame):
    sys.stderr.write(f"{TAG} hook が時間切れになったので止めます\n")
    sys.exit(2)


def log(decision, tool, detail, reason=""):
    path = os.environ.get("ADR007_GUARD_LOG")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"decision": decision, "tool": tool, "detail": detail,
                                "reason": reason}, ensure_ascii=False) + "\n")


def emit(decision, reason, tool, detail):
    log(decision, tool, detail, f"{TAG} {reason}")
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": f"{TAG} {reason}",
    }}, ensure_ascii=False))
    sys.exit(0)


def repo_root(cwd):
    out = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True, timeout=TIMEOUT_SEC)
    if out.returncode != 0:
        return None
    return os.path.realpath(out.stdout.strip())


def rel_to_root(path, cwd, root):
    if not os.path.isabs(path):
        path = os.path.join(cwd, path)
    # 新しいファイルは realpath で親だけ解決される。どちらでもリポジトリからの相対にする
    real = os.path.realpath(path)
    if root is None:
        return None
    if real == root or real.startswith(root + os.sep):
        return os.path.relpath(real, root).replace(os.sep, "/")
    return None


def has_def_key(text):
    return bool(text) and DEF_KEY_RE.search(text) is not None


def current_text(abspath):
    # まだ無いファイルは空として扱う。読めないなど、ほかのエラーは上に投げて止める側に倒す
    try:
        with open(abspath, encoding="utf-8", errors="replace") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def kind_of(rel, abspath="", new_text=""):
    if rel is None:
        return None
    base = rel.rsplit("/", 1)[-1]
    # 定義：名前が決まったものか、中身（書き込む文か今のファイル）に行頭の metrics:・semantic_models: があるもの
    if rel.startswith("dbt_project/models/") and base.endswith((".yml", ".yaml")):
        if base in DEF_NAMES or has_def_key(new_text) or has_def_key(current_text(abspath)):
            return "definition"
    if rel.startswith("docs/business/"):
        return "memo"
    if rel == ".claude/settings.json" or rel.startswith(".claude/hooks/") or rel.startswith(".githooks/"):
        return "guard"
    return None


def memo_in_head(root, memo):
    out = subprocess.run(["git", "-C", root, "cat-file", "-e", f"HEAD:{memo}"],
                         capture_output=True, timeout=TIMEOUT_SEC)
    return out.returncode == 0


def new_text_of(tool, ti):
    if tool == "Edit":
        return ti.get("new_string", "")
    if tool == "MultiEdit":
        return "\n".join(e.get("new_string", "") for e in ti.get("edits", []))
    if tool == "Write":
        return ti.get("content", "")
    return ""


def check_file_tool(tool, ti, cwd):
    path = ti.get("file_path") or ti.get("notebook_path") or ""
    root = repo_root(cwd) or repo_root(os.path.dirname(os.path.abspath(path)) or cwd)
    rel = rel_to_root(path, cwd, root)
    abspath = path if os.path.isabs(path) else os.path.join(cwd, path)
    kind = kind_of(rel, abspath, new_text_of(tool, ti))
    if kind == "definition":
        if tool not in ("Edit", "MultiEdit"):
            emit("deny", f"R1：定義のファイル {rel} は Edit でだけ変えます（{tool} は止めます）。" + HOW_TO_PASS, tool, rel)
        memos = sorted(set(MEMO_RE.findall(new_text_of(tool, ti))))
        if not memos:
            emit("deny", f"R2：{rel} への書き込みに決定メモのパスがありません。" + HOW_TO_PASS, tool, rel)
        missing = [m for m in memos if not memo_in_head(root, m)]
        if missing:
            emit("deny", f"R2：決定メモ {', '.join(missing)} が HEAD にありません。" + HOW_TO_PASS, tool, rel)
        log("pass", tool, rel)
        sys.exit(0)
    if kind == "memo":
        # 2026-11-06 の人の判断で deny から ask に変えた（ADR-007「人の判断で変えた」）
        emit("ask", f"R3：決定メモの書き込みです。人が中身を読んで承認します（{rel}）", tool, rel)
    if kind == "guard":
        emit("ask", f"R4：守りそのもの {rel} の書き換えです。人の確認が要ります。", tool, rel)
    log("pass", tool, rel)
    sys.exit(0)


def commit_skips_hook(cmd):
    """git commit の短いオプションのまとまりに n があれば True。"""
    try:
        lexer = shlex.shlex(cmd, posix=True, punctuation_chars=";&|()")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        # 読み切れないときは、commit を含むなら止める側に倒す
        return re.search(r"\bcommit\b", cmd) is not None
    i = 0
    while i < len(tokens):
        if tokens[i] == "commit" and "git" in tokens[max(0, i - 6):i]:
            j = i + 1
            while j < len(tokens) and tokens[j] not in (";", "&&", "||", "|", "&", "(", ")"):
                t = tokens[j]
                if t.startswith("-") and not t.startswith("--") and len(t) > 1:
                    for k, ch in enumerate(t[1:]):
                        if ch == "n":
                            return True
                        if ch in COMMIT_OPTS_WITH_VALUE:
                            if k == len(t) - 2:
                                j += 1  # 値は次の語
                            break
                j += 1
            i = j
        else:
            i += 1
    return False


def check_bash(ti):
    cmd = ti.get("command", "")
    if re.search(r"--no-veri", cmd) or re.search(r"hookspath", cmd, re.IGNORECASE):
        emit("deny", "R5：git の hook を飛ばす書き方（--no-verify、core.hooksPath）は止めます。"
             "hook に止められたなら、飛ばさずに直すか、止まって人に聞く。", "Bash", cmd)
    if commit_skips_hook(cmd):
        emit("deny", "R5：git commit の -n（hook を飛ばす）は止めます。"
             "hook に止められたなら、飛ばさずに直すか、止まって人に聞く。", "Bash", cmd)
    names = [w for w in PROTECTED_WORDS if w in cmd] + MODELS_YAML_RE.findall(cmd)
    if names:
        stripped = HARMLESS_REDIRECT_RE.sub(" ", cmd)
        marks = []
        if ">" in stripped:
            marks.append(">")
        marks += [m.group(0).strip(" \t;|&()'\"`") for m in WRITE_CMD_RE.finditer(stripped)]
        marks += [m.group(0) for m in GIT_WRITE_RE.finditer(stripped)]
        if marks:
            emit("deny", f"R5：守る場所（{', '.join(names)}）と書き換えの印（{', '.join(marks)}）を"
                 "両方含む Bash は止めます。定義は Edit で、決定メモのパスを書いて変えます。"
                 "決定メモと守りそのものは、人が変えます。", "Bash", cmd)
    log("pass", "Bash", cmd)
    sys.exit(0)


def main():
    signal.signal(signal.SIGALRM, on_timeout)
    signal.alarm(TIMEOUT_SEC)
    data = json.load(sys.stdin)
    tool = data.get("tool_name", "")
    ti = data.get("tool_input") or {}
    cwd = data.get("cwd") or os.getcwd()
    if tool in WRITE_TOOLS:
        check_file_tool(tool, ti, cwd)
    if tool == "Bash":
        check_bash(ti)
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException as e:  # 自分のエラーは止める側に倒す
        sys.stderr.write(f"{TAG} hook 自身のエラーで止めます: {type(e).__name__}: {e}\n")
        sys.exit(2)
