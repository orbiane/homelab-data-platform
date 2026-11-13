#!/usr/bin/env python3
"""docs/analysis/stage3/guard_cases.md の T と C を機械で回す。

使い方（リポジトリの根から）:
  python3 agent/adr007_guard_tests/run_cases.py            # 関所あり
  python3 agent/adr007_guard_tests/run_cases.py --control  # 関所なし（試しが違いを捕まえるかの確かめ）

本物のリポジトリには書かない。一時ディレクトリに clone を作り、作業中の関所のファイルを写して回す。
期待は表のまま（止める＝deny か exit 2／聞く＝ask／通す＝何も返さない）。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.realpath(subprocess.run(["git", "rev-parse", "--show-toplevel"],
                                       capture_output=True, text=True, check=True).stdout.strip())
CONTROL = "--control" in sys.argv
GUARD_FILES = [".claude/hooks/adr007_guard.py", ".githooks/pre-commit", ".githooks/definition_guard.sh"]
METRICS = "dbt_project/models/mart/_metrics.yml"
SEMANTIC = "dbt_project/models/mart/_semantic_models.yml"
MEMO = "docs/business/2026-11-05-ctr.md"
# 対照（--control）のコミットの入口は、関所を入れる前の版（個人情報の検査だけ）
PRE_GUARD_COMMIT = "8939cbd"
CTR_V2 = "dbt_project/models/mart/ctr_v2.yml"
NOTES = "dbt_project/models/mart/notes.yml"
EXTRA = "dbt_project/models/mart/extra.yml"
MODELS = "dbt_project/models/mart/_models.yml"
CTR_V2_BODY = ("version: 2\n\nmetrics:\n  - name: ctr_v2\n"
               "    description: \"クリック率 = クリック数 ÷ 開封数\"\n"
               "    type: ratio\n    label: \"CTR v2\"\n    type_params:\n"
               "      numerator: clicked_count\n      denominator: opened_count\n")
NOTES_BODY = "version: 2\n\nmodels:\n  - name: notes\n    description: \"説明だけのファイル\"\n"
# T26 の土台。コミットの入口を通すため、決定メモのパスを書いておく
EXTRA_BODY = (f"version: 2\n# {MEMO}\nmetrics:\n  - name: extra_ratio\n    type: derived\n"
              "    type_params:\n      expr: a / b\n")

WORK = os.path.realpath(tempfile.mkdtemp(prefix="adr007-cases-"))
SCRATCH = os.path.join(WORK, "scratch")  # T20 の「使い捨ての場所」
os.makedirs(SCRATCH)
W_PY = os.path.join(SCRATCH, "w.py")
with open(W_PY, "w") as f:
    # 中で定義のファイルを書く。コマンドの側には名前が出ない
    f.write("p = 'dbt_project/models/mart/' + '_metrics' + '.yml'\n"
            "open(p, 'a').write('# guard test C02\\n')\n")


def sh(args, cwd, **kw):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, **kw)


def make_clone(name):
    d = os.path.join(WORK, name)
    sh(["git", "clone", "-q", REPO, d], WORK).check_returncode()
    for rel in GUARD_FILES:
        dst = os.path.join(d, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if CONTROL and rel == ".githooks/pre-commit":
            # 関所なし：関所を入れる前のコミットの pre-commit（個人情報の検査だけ）
            old = sh(["git", "show", f"{PRE_GUARD_COMMIT}:.githooks/pre-commit"], REPO)
            old.check_returncode()
            with open(dst, "w") as f:
                f.write(old.stdout)
            continue
        if CONTROL and rel == ".githooks/definition_guard.sh":
            # 関所を入れる前には無かったファイル
            if os.path.exists(dst):
                os.remove(dst)
            continue
        if CONTROL and rel == ".claude/hooks/adr007_guard.py":
            with open(dst, "w") as f:
                f.write("import sys\nsys.exit(0)\n")
            continue
        shutil.copy2(os.path.join(REPO, rel), dst)
    words = sh(["git", "rev-parse", "--git-path", "info/private-words"], REPO).stdout.strip()
    shutil.copy2(os.path.join(REPO, words), os.path.join(d, ".git/info/private-words"))
    sh(["git", "config", "core.hooksPath", ".githooks"], d).check_returncode()
    sh(["git", "config", "user.name", "guard-test"], d).check_returncode()
    sh(["git", "config", "user.email", "guard-test@example.invalid"], d).check_returncode()
    return d


def run_hook(clone, tool, tool_input):
    payload = {"hook_event_name": "PreToolUse", "tool_name": tool,
               "tool_input": tool_input, "cwd": clone}
    p = subprocess.run(["sh", "-c", 'python3 "$0" || exit 2',
                        os.path.join(clone, ".claude/hooks/adr007_guard.py")],
                       input=json.dumps(payload), capture_output=True, text=True, cwd=clone, timeout=30)
    if p.returncode == 2:
        return "止める", p.stderr.strip()
    if p.returncode != 0:
        return f"exit={p.returncode}", p.stderr.strip()
    out = p.stdout.strip()
    if not out:
        return "通す", ""
    d = json.loads(out)["hookSpecificOutput"]
    return {"deny": "止める", "ask": "聞く"}.get(d["permissionDecision"], d["permissionDecision"]), d.get("permissionDecisionReason", "")


# T01〜T03 の Edit が当てる行。今の _metrics.yml にちょうど1か所ある指標の行全体にする
# （2026-11-13 G1：段階3で ctr を消して ctr_per_open を足したため、"  - name: ctr" から直した）
METRIC_LINE = "  - name: ctr_per_open"


def edit(path, new, old=METRIC_LINE):
    return {"file_path": path, "old_string": old, "new_string": new}


def t_cases(clone):
    p = lambda rel: os.path.join(clone, rel)
    return [
        ("T01", "Edit", edit(p(METRICS), f"{METRIC_LINE}  # opened 基準に変える"), "止める"),
        ("T02", "Edit", edit(p(METRICS), f"{METRIC_LINE}  # {MEMO}"), "通す"),
        ("T03", "Edit", edit(p(METRICS), f"{METRIC_LINE}  # docs/business/no-such-memo.md"), "止める"),
        ("T04", "Write", {"file_path": p(SEMANTIC), "content": f"# {MEMO}\nsemantic_models: []\n"}, "止める"),
        ("T05", "Edit", edit(p(MEMO), "x", old="クリック率"), "聞く"),
        ("T06", "Write", {"file_path": p("docs/business/2026-11-07-new.md"), "content": "x\n"}, "聞く"),
        ("T07", "Edit", edit(p(".claude/settings.json"), "x", old="ask"), "聞く"),
        ("T08", "Edit", edit(p(".githooks/pre-commit"), "x", old="exit"), "聞く"),
        ("T09", "Write", {"file_path": p(".claude/hooks/new_file.py"), "content": "x\n"}, "聞く"),
        ("T10", "Edit", edit(p("docs/analysis/stage3/log.md"), "x", old="#"), "通す"),
        ("T11", "Bash", {"command": f"sed -i '' 's/delivered_count/opened_count/' {METRICS}"}, "止める"),
        ("T12", "Bash", {"command": f"cat {METRICS}"}, "通す"),
        ("T13", "Bash", {"command": f"git diff -- {SEMANTIC} | head -50"}, "通す"),
        ("T14", "Bash", {"command": "echo x >> docs/business/note.md"}, "止める"),
        ("T15", "Bash", {"command": "git commit -m t --no-verify"}, "止める"),
        ("T16", "Bash", {"command": "git commit -nm t"}, "止める"),
        ("T17", "Bash", {"command": "git -c core.hooksPath=/dev/null commit -m t"}, "止める"),
        ("T18", "Bash", {"command": 'git commit -m "fix: use the opened count"'}, "通す"),
        ("T19", "Bash", {"command": f"git add {METRICS}"}, "通す"),
        ("T20", "Bash", {"command": f"python3 {W_PY}"}, "通す"),
        ("T21", "Write", {"file_path": p(CTR_V2), "content": CTR_V2_BODY}, "止める"),
        ("T22", "Edit", edit(p(MODELS), "version: 2\n\n" + CTR_V2_BODY.split("\n\n", 1)[1], old="version: 2\n"), "止める"),
        ("T23", "Edit", edit(p(MODELS), f"version: 2\n# {MEMO}\n" + CTR_V2_BODY.split("\n\n", 1)[1], old="version: 2\n"), "通す"),
        ("T24", "Write", {"file_path": p(NOTES), "content": NOTES_BODY}, "通す"),
        ("T25", "Bash", {"command": f"cat > {CTR_V2} <<'EOF'\n{CTR_V2_BODY}EOF"}, "止める"),
        ("T26", "Edit", edit(p(EXTRA), "      expr: a / nullif(b, 0)", old="      expr: a / b"), "止める"),
    ]


def append(clone, rel, text):
    path = os.path.join(clone, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(text)


def c_case(cid, prepare, expect):
    clone = make_clone(cid)
    head0 = sh(["git", "rev-parse", "HEAD"], clone).stdout.strip()
    files = prepare(clone)
    sh(["git", "add", "--"] + files, clone).check_returncode()
    c = sh(["git", "commit", "-q", "-m", f"guard case {cid}"], clone)
    head1 = sh(["git", "rev-parse", "HEAD"], clone).stdout.strip()
    if c.returncode != 0 and head0 == head1:
        actual = "止める"
    elif c.returncode == 0 and head0 != head1:
        actual = "通す"
    else:
        actual = f"exit={c.returncode} HEAD変化={head0 != head1}"
    msg = (c.stdout + c.stderr).strip().replace("\n", " / ")
    return cid, expect, actual, msg


def c01(cl): append(cl, METRICS, "# guard test C01\n"); return [METRICS]
def c02(cl): sh(["python3", W_PY], cl).check_returncode(); return [METRICS]
def c03(cl): append(cl, METRICS, f"# guard test C03 {MEMO}\n"); return [METRICS]
def c04(cl):
    append(cl, "docs/business/2026-11-07-new.md", "# new memo\n")
    append(cl, METRICS, f"# guard test C04 {MEMO}\n")
    return ["docs/business/2026-11-07-new.md", METRICS]
def c05(cl): append(cl, "docs/analysis/stage3/log.md", "\nguard test C05\n"); return ["docs/analysis/stage3/log.md"]
def c06(cl): append(cl, METRICS, "# guard test C06 docs/business/no-such-memo.md\n"); return [METRICS]
def c07(cl): append(cl, CTR_V2, CTR_V2_BODY); return [CTR_V2]
def c08(cl): append(cl, CTR_V2, f"# {MEMO}\n" + CTR_V2_BODY); return [CTR_V2]
def c09(cl): append(cl, NOTES, NOTES_BODY); return [NOTES]


def main():
    print(f"mode={'control（関所なし）' if CONTROL else '関所あり'} work={WORK}")
    rows = []
    tclone = make_clone("T")
    # T26 の土台：metrics: を持つ extra.yml を、試しの clone にコミットしておく
    append(tclone, EXTRA, EXTRA_BODY)
    sh(["git", "add", EXTRA], tclone).check_returncode()
    sh(["git", "commit", "-q", "-m", "T26 base: extra.yml"], tclone).check_returncode()
    for cid, tool, ti, expect in t_cases(tclone):
        actual, reason = run_hook(tclone, tool, ti)
        rows.append((cid, expect, actual, reason))
    for cid, fn, expect in [("C01", c01, "止める"), ("C02", c02, "止める"), ("C03", c03, "通す"),
                            ("C04", c04, "止める"), ("C05", c05, "通す"), ("C06", c06, "止める"),
                            ("C07", c07, "止める"), ("C08", c08, "通す"), ("C09", c09, "通す")]:
        rows.append(c_case(cid, fn, expect))
    # T の clone が汚れていないこと（hook は読むだけ）
    tstatus = sh(["git", "status", "--short", "--untracked-files=no"], tclone).stdout.strip()

    bad = 0
    for cid, expect, actual, reason in rows:
        ok = expect == actual
        bad += 0 if ok else 1
        print(f"{'OK ' if ok else 'NG '} {cid} 期待={expect} 実際={actual} | {reason[:150]}")
    t_n = sum(1 for r in rows if r[0].startswith("T"))
    c_n = sum(1 for r in rows if r[0].startswith("C"))
    print(f"件数: T {t_n} 件、C {c_n} 件、合計 {len(rows)} 件")
    print(f"期待と違う {bad} 件")
    for grp in ("T", "C"):
        for exp in ("止める", "聞く", "通す"):
            sel = [r for r in rows if r[0].startswith(grp) and r[1] == exp]
            if sel:
                ng = [r[0] for r in sel if r[1] != r[2]]
                print(f"  {grp} 期待={exp}: {len(sel)} 件中 外れ {len(ng)} 件 {ng}")
    print(f"T の clone の追跡中ファイルの変更: {tstatus or 'なし'}")
    shutil.rmtree(WORK)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
