#!/usr/bin/env python3
"""レビュー役の 1（機械の確かめ）。docs/agent/review.md の 1 の7項目を数え、表にする（L1、ADR-009 の決定8）。

使い方:
  python3 agent/loop/review_checks.py <PR番号> [--repo DIR] [--json]
  python3 agent/loop/review_checks.py --base REF --head REF --id ID [--repo DIR] [--json]
  python3 agent/loop/review_checks.py selftest

- PR番号のとき：gh pr view でブランチを調べ、git fetch して origin/main...origin/<ブランチ> を見る
- どの確かめも、見た件数と見つけた件数を出す。個人情報の検査は、見つけた行の場所と種類だけを出し、行の中身は出さない
  （表はそのまま公開の PR のコメントに入るため）
- 「直しが要る」に決める確かめ（仮決め L1-5）：1 変わってはいけない場所、2 NEXT.md、3 報告の見出し、
  5 bank のコミット、6 個人情報。4 仮決めの欄の欠けは表に出し、判定はモデルに任せる
- 個人情報の検査は、.githooks/scan.sh の scan_lines を、base の版のまま使う（PR の中の scan.sh は使わない）
"""
import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pick  # noqa: E402

PROTECTED_PREFIXES = ("docs/business/", ".claude/", ".githooks/", "data_generation/output/")
PROTECTED_FILES = ("data_generation/output.sha256",)
DEF_NAMES = ("_metrics.yml", "_semantic_models.yml")
DEF_CONTENT = re.compile(r"^[ \t]*(metrics|semantic_models)[ \t]*:", re.M)
BANK = "docs/analysis/regression/bank.json"
PROVISIONAL_FIELDS = ("日付", "決めたこと", "ほかの案", "選んだ理由", "止まる類ではないと判断した理由", "戻すときに直す所")
MUST_FIX = {1, 2, 3, 5, 6}


def git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=120)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} が失敗しました: {r.stderr.strip()}")
    return r.stdout


def show(repo, ref, path):
    r = subprocess.run(["git", "-C", str(repo), "show", f"{ref}:{path}"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def changed_files(repo, base, head):
    """[(状態, パス)]。merge-base からの差分（PR の画面と同じ見え方）。"""
    out = git(repo, "diff", "--name-status", "--no-renames", "-z", f"{base}...{head}")
    parts = [p for p in out.split("\0") if p]
    return [(parts[i], parts[i + 1]) for i in range(0, len(parts) - 1, 2)]


def is_definition(repo, mb, head, path):
    """ADR-007 の定義のファイル：models の下の yml で、名前が決まったものか、base か head の中身に行頭の metrics:・semantic_models:。"""
    if not (path.startswith("dbt_project/models/") and re.search(r"\.ya?ml$", path)):
        return False
    if path.rsplit("/", 1)[-1] in DEF_NAMES:
        return True
    return any(DEF_CONTENT.search(show(repo, ref, path) or "") for ref in (mb, head))


def check_protected(repo, mb, head, files):
    hits = [p for _, p in files
            if p.startswith(PROTECTED_PREFIXES) or p in PROTECTED_FILES or is_definition(repo, mb, head, p)]
    return len(files), hits


def check_report(repo, head, task_id):
    path = f"docs/agent/reports/{task_id}.md"
    text = show(repo, head, path)
    if text is None:
        return 10, [f"{path} が無い"]
    missing = [f"## {n}." for n in range(1, 11) if not re.search(rf"^##[ \t]*{n}\.", text, re.M)]
    return 10, missing


def check_provisional(repo, head, task_id):
    path = f"docs/agent/provisional/{task_id}.md"
    text = show(repo, head, path)
    if text is None:
        return 0, []
    sections = re.split(rf"^(?=##[ \t]+{re.escape(task_id)}-\d+)", text, flags=re.M)[1:]
    missing = []
    for sec in sections:
        title = sec.splitlines()[0].strip("# ").strip()
        for f in PROVISIONAL_FIELDS:
            if not re.search(rf"^[ \t]*-[ \t]*{f}[ \t]*[：:]", sec, re.M):
                missing.append(f"{title.split()[0]} の「{f}」")
    return len(sections), missing


def check_bank(repo, base, head):
    out = git(repo, "log", "--format=%H%x09%s", f"{base}..{head}", "--", BANK)
    commits = [l.split("\t", 1) for l in out.splitlines() if l]
    bad = []
    for sha, subject in commits:
        names = [n for n in git(repo, "show", "--name-only", "--format=", sha).splitlines() if n]
        if not subject.startswith("expected:"):
            bad.append(f"{sha[:7]} のメッセージが expected: で始まらない")
        if names != [BANK]:
            bad.append(f"{sha[:7]} が bank のほかに {len(names) - (BANK in names)} 個のファイルを変えている")
    return len(commits), bad


def scan_text(repo, base, txt, loc):
    """行の並び txt（場所は loc）に、base の scan.sh の scan_lines を当てる。返すのは ["場所 [種類]"]。行の中身は返さない。"""
    scan = show(repo, base, ".githooks/scan.sh")
    if scan is None:
        return ["base に scan.sh が無いので検査できない"]
    with tempfile.TemporaryDirectory() as d:
        d = pathlib.Path(d)
        (d / "scan.sh").write_text(scan, encoding="utf-8")
        (d / "txt").write_text("".join(t + "\n" for t in txt), encoding="utf-8")
        (d / "loc").write_text("".join(x + "\n" for x in loc), encoding="utf-8")
        r = subprocess.run(["sh", "-c", '. "$1"; scan_lines review "$2" "$3"', "_",
                            str(d / "scan.sh"), str(d / "txt"), str(d / "loc")],
                           cwd=repo, capture_output=True, text=True, timeout=60)
    hits = []
    for line in r.stdout.splitlines():
        m = re.match(r"^  \[([^\]]+)\] (\S+?): ", line)
        if m:
            hits.append(f"{m.group(2)} [{m.group(1)}]")
    if r.returncode != 0 and not hits:
        hits.append("検査が失敗した：" + (r.stdout.strip().splitlines() or [r.stderr.strip()])[-1])
    return hits


def check_personal(repo, base, head):
    """足した行に、base の scan.sh の scan_lines を当てる。返すのは (見た行の数, ["場所 [種類]"])。"""
    diff = git(repo, "diff", "--no-color", "--no-ext-diff", "--text", "-U0", f"{base}...{head}")
    txt, loc, path, lineno = [], [], None, 0
    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            lineno = int(m.group(1)) if m else 0
        elif line.startswith("+") and path:
            txt.append(line[1:])
            loc.append(f"{path}:{lineno}")
            lineno += 1
    return len(txt), scan_text(repo, base, txt, loc)


def run_checks(repo, base, head, task_id):
    repo = pathlib.Path(repo)
    mb = git(repo, "merge-base", base, head).strip()
    files = changed_files(repo, base, head)
    rows = []

    def add(n, name, seen, found):
        rows.append({"n": n, "name": name, "seen": seen, "found": found})

    add(1, "変わってはいけない場所", *check_protected(repo, mb, head, files))
    add(2, "NEXT.md", len(files), [p for _, p in files if p == "NEXT.md"])
    add(3, f"報告 docs/agent/reports/{task_id}.md の見出し（10項目）", *check_report(repo, head, task_id))
    add(4, f"仮決め docs/agent/provisional/{task_id}.md の欄（節ごとに6つ）", *check_provisional(repo, head, task_id))
    add(5, "bank を変えたコミット（expected: で始まり、bank だけ）", *check_bank(repo, base, head))
    add(6, "足した行の個人情報（scan.sh）", *check_personal(repo, base, head))
    add(7, "変わったファイル", len(files), [f"{s} {p}" for s, p in files])
    must_fix = [r["n"] for r in rows if r["n"] in MUST_FIX and r["found"]]
    return {"base": base, "head": head, "id": task_id, "head_sha": git(repo, "rev-parse", head).strip(),
            "rows": rows, "must_fix": must_fix}


def to_markdown(res):
    lines = ["| # | 確かめ | 見た件数 | 見つけた件数 | 見つけたもの |", "|---|---|---|---|---|"]
    for r in res["rows"]:
        found = r["found"]
        shown = "、".join(f"`{f}`" if r["n"] in (1, 2, 7) else f for f in found[:20])
        if len(found) > 20:
            shown += f" ほか {len(found) - 20} 件"
        count = "—" if r["n"] == 7 else len(found)
        lines.append(f"| {r['n']} | {r['name']} | {r['seen']} | {count} | {shown or '無し'} |")
    mf = res["must_fix"]
    lines.append("")
    lines.append(f"機械の確かめで直しが要る：{'あり（' + '・'.join(map(str, mf)) + '）' if mf else '無し'}")
    return "\n".join(lines)


def build_comment(reply, res, home=None):
    """レビュー役の返事から、PR に出すコメントを作る（review.md の 3）。返すのは (判定, 本文, 直した点の一覧)。

    - 1行目は台本が付ける：`レビュー: <判定>（<先頭のコミットの短い ID>）`（pick.REVIEW_LINE の形）
    - 返事の最初の行が「判定: <3つのどれか>」でなければ、判定は「持ち主の決めが要る」にする（仮決め L1-6）
    - 機械の確かめで直しが要るのに「マージしてよい」と返したら、「直しが要る」にする
    - 本文の中の「決め:」で始まる行は、頭に「（引用）」を付ける（持ち主の決めに見えないように。ADR-009 の K9）
    - ホームディレクトリは ~ に置き換える
    """
    notes = []
    lines = (reply or "").strip().splitlines()
    m = re.match(r"^判定[:：]\s*(\S+)\s*$", lines[0].strip()) if lines else None
    verdict = m.group(1) if m and m.group(1) in pick.VERDICTS else None
    if verdict is None:
        verdict = "持ち主の決めが要る"
        notes.append("レビュー役の返事の1行目が「判定: …」の形でなかったので、持ち主の決めが要る、にした")
        body_lines = lines
    else:
        body_lines = lines[1:]
    if res["must_fix"] and verdict == "マージしてよい":
        verdict = "直しが要る"
        notes.append("機械の確かめで直しが要るので、レビュー役の「マージしてよい」を「直しが要る」にした")
    # ユーザーの設定の出力の形（説明の枠 `★ Insight ───` 〜 `───`）は、コメントに載せない（L1 の試しで #13 に出た）
    kept, in_box = [], False
    for line in body_lines:
        s = line.strip().strip("`")
        if not in_box and s.startswith("★"):
            in_box = True
            continue
        if in_box:
            if s and set(s) <= set("─-"):
                in_box = False
            continue
        kept.append(line)
    if in_box:  # 閉じていない枠は、取り除かずに元に戻す（中身を黙って消さない）
        kept = body_lines
    elif len(kept) != len(body_lines):
        notes.append("レビュー役の返事にあった説明の枠を取り除いた")
    fixed = []
    for line in kept:
        if line.lstrip().startswith(pick.DECISION_PREFIXES):
            line = "（引用）" + line.lstrip()
        if home:
            line = line.replace(home, "~")
        fixed.append(line)
    body = "\n".join(fixed).strip() or "- （レビュー役の返事が空だった）"
    out = [f"レビュー: {verdict}（{res['head_sha'][:7]}）", "", body]
    if notes:
        out += ["", *[f"- 台本の注：{n}" for n in notes]]
    out += ["", "<details><summary>機械の確かめの表（agent/loop/review_checks.py）</summary>", "",
            to_markdown(res), "", "</details>", "",
            "---", "_台本 `agent/loop/run.py` が、レビュー役（`claude -p`、読むだけの権限）の返事から出したコメント。"
            "マージは持ち主がする_"]
    return verdict, "\n".join(out) + "\n", notes


def task_id_of(branch, repo):
    """ブランチ名から ID。auto/<ID> の後ろに -名前 が付くときは、NEXT.md の表にある最も長い ID を選ぶ。"""
    rest = branch.split("/", 1)[1] if "/" in branch else branch
    ids = [r[0] for r in pick.parse_table(show(repo, "origin/main", "NEXT.md") or "")]
    for i in sorted(ids, key=len, reverse=True):
        if rest == i or rest.startswith(i + "-"):
            return i if rest == i else rest  # 表の行の続きの名前（例 L1-trial）は、報告もその名前で書く
    return rest


def for_pr(number, repo):
    r = subprocess.run(["gh", "pr", "view", str(number), "--json", "headRefName,baseRefName"],
                       cwd=repo, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"gh pr view {number} が失敗しました: {r.stderr.strip()}")
    d = json.loads(r.stdout)
    git(repo, "fetch", "-q", "origin", d["baseRefName"], d["headRefName"])
    return run_checks(repo, f"origin/{d['baseRefName']}", f"origin/{d['headRefName']}",
                      task_id_of(d["headRefName"], repo))


# ---------------------------------------------------------------- selftest

def selftest():
    """使い捨ての clone に作り物のブランチを作り、それぞれの確かめが拾うことを見る。終わったら clone を消す。"""
    src = pathlib.Path(git(HERE, "rev-parse", "--show-toplevel").strip())
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="review-checks-selftest-"))
    clone = tmp / "repo"
    bad = 0
    try:
        git(tmp, "clone", "-q", "--no-hardlinks", "--branch", "main", str(src), str(clone))
        git(clone, "config", "user.name", "selftest")
        git(clone, "config", "user.email", "selftest@example.invalid")
        word = "zqxselftestword"  # 検査語の作り物。本物の検査語のファイルは写さない
        (clone / ".git/info/private-words").write_text(word + "\n", encoding="utf-8")
        git(clone, "update-ref", "refs/remotes/origin/main", "main")

        def report(task_id, skip=()):
            heads = [f"## {n}. 見出し\n\n無し\n" for n in range(1, 11) if n not in skip]
            return f"<!-- 注意書き -->\n# {task_id} の報告\n\n" + "\n".join(heads)

        def branch(name, files, message="作り物", extra_commits=()):
            git(clone, "switch", "-q", "-c", name, "main")
            for commit_files, msg in [(files, message), *extra_commits]:
                for rel, text in commit_files.items():
                    p = clone / rel
                    p.parent.mkdir(parents=True, exist_ok=True)
                    if text is None:
                        p.unlink()
                    else:
                        p.write_text(text, encoding="utf-8")
                git(clone, "add", "-A")
                git(clone, "commit", "-q", "-m", msg)
            git(clone, "switch", "-q", "main")

        rep = {"docs/agent/reports/T1.md": report("T1")}
        # 個人情報の作り物は、ソースに検査で当たる形を残さないよう、実行時に組み立てる
        home = "/" + "Users" + "/someone/x"
        lan = ".".join(["192", "168", "1", "23"])
        mac = ":".join(["0a"] * 6)
        bank_text = (clone / BANK).read_text(encoding="utf-8").replace("\n", "\n ", 1)
        models = clone / "dbt_project/models"
        other_yml = next((p for p in sorted(models.rglob("*.yml"))
                          if p.name not in DEF_NAMES and DEF_CONTENT.search(p.read_text(encoding="utf-8"))), None)
        prot = {".claude/settings.json": "{}\n", "docs/business/x.md": "x\n",
                "dbt_project/models/marts/_metrics.yml": "metrics: []\n"}
        if other_yml is not None:
            prot[str(other_yml.relative_to(clone))] = other_yml.read_text(encoding="utf-8") + "# 足した\n"
        # 名前が違っても、中身に行頭の semantic_models: があれば定義（新しいファイル）
        prot["dbt_project/models/marts/defs_by_content.yml"] = "semantic_models:\n  - name: x\n"
        prov_ok = "## T1-1 決めた\n\n" + "".join(f"- {f}：x\n" for f in PROVISIONAL_FIELDS)
        prov_ng = prov_ok + "\n## T1-2 欠けた\n\n" + "".join(f"- {f}：x\n" for f in PROVISIONAL_FIELDS[:-1])

        cases = [
            # (名前, ブランチ, ファイル, 追加のコミット, メッセージ, 拾うはずの確かめ)
            ("何も無い（報告と仮決めがそろった PR）", "auto/T1-ok",
             {**rep, "docs/agent/provisional/T1.md": prov_ok}, (), "作り物", set()),
            ("変わってはいけない場所（.claude・決定メモ・名前で決まる定義・中身で決まる定義）",
             "auto/T1-prot", {**rep, **prot}, (), "作り物", {1}),
            ("NEXT.md の変更", "auto/T1-next", {**rep, "NEXT.md": "x\n"}, (), "作り物", {2}),
            ("報告の見出しの欠け（7 が無い）", "auto/T1-head", {"docs/agent/reports/T1.md": report("T1", skip=(7,))},
             (), "作り物", {3}),
            ("報告が無い", "auto/T1-norep", {"docs/agent/other.md": "x\n"}, (), "作り物", {3}),
            ("仮決めの欄の欠け", "auto/T1-prov", {**rep, "docs/agent/provisional/T1.md": prov_ng}, (), "作り物", {4}),
            ("bank を expected: でないコミットで変えた", "auto/T1-bank1", {**rep, BANK: bank_text}, (), "数字を直す", {5}),
            ("bank を expected: のコミットで変えたが、ほかのファイルも変えた", "auto/T1-bank2",
             rep, (({BANK: bank_text, "docs/x.md": "x\n"}, "expected: B3 を直す"),), "作り物", {5}),
            ("bank を expected: のコミットで bank だけ変えた（拾わない）", "auto/T1-bank3",
             rep, (({BANK: bank_text}, "expected: B3 を直す"),), "作り物", set()),
            ("個人情報の行（ホームの絶対パス・家の LAN・MAC・検査語）", "auto/T1-pii",
             {**rep, "docs/agent/notes.md": f"a {home}\nb {lan}\nc {mac}\nd {word}\ne 127.0.0.1\n"}, (), "作り物", {6}),
        ]
        for name, br, files, extra, msg, expect in cases:
            branch(br, files, msg, extra)
            res = run_checks(clone, "main", br, "T1")
            got = {r["n"] for r in res["rows"] if r["n"] != 7 and r["found"]}
            ok = got == expect
            if br == "auto/T1-pii":
                n6 = next(r for r in res["rows"] if r["n"] == 6)
                ok = ok and len(n6["found"]) == 4 and not any(word in f or lan in f for f in n6["found"])
                name += f"（見た行 {n6['seen']}、見つけた行 {len(n6['found'])}。127.0.0.1 は拾わず、行の中身を出さない）"
            if br == "auto/T1-prot":
                n1 = next(r for r in res["rows"] if r["n"] == 1)
                ok = ok and len(n1["found"]) == len(prot)
                name += f"（見つけた {len(n1['found'])}／作った {len(prot)}）"
            bad += 0 if ok else 1
            print(f"{'OK ' if ok else 'NG '} {name}: 期待={sorted(expect)} 実際={sorted(got)}")
        # 表の形
        md = to_markdown(run_checks(clone, "main", "auto/T1-pii", "T1"))
        ok = word not in md and lan not in md and "| 6 |" in md
        bad += 0 if ok else 1
        print(f"{'OK ' if ok else 'NG '} 表に、個人情報の行の中身が出ない")
        # コメントの組み立て（build_comment）
        clean = run_checks(clone, "main", "auto/T1-ok", "T1")
        dirty = run_checks(clone, "main", "auto/T1-next", "T1")
        sha7 = clean["head_sha"][:7]
        for name, reply, res, expect in [
            ("返事の判定をそのまま使う", "判定: マージしてよい\n\n- 確かめたこと：x", clean, "マージしてよい"),
            ("1行目の形が違えば、持ち主の決めが要る", "マージしてよいと思います", clean, "持ち主の決めが要る"),
            ("3つ以外の判定も、持ち主の決めが要る", "判定: 承認", clean, "持ち主の決めが要る"),
            ("機械の確かめで直しが要るのに、マージしてよい → 直しが要る", "判定: マージしてよい", dirty, "直しが要る"),
        ]:
            verdict, text, _ = build_comment(reply, res)
            first = text.splitlines()[0]
            m = pick.REVIEW_LINE.match(first)
            ok = verdict == expect and m is not None and m.group(1) == expect and m.group(2) == res["head_sha"][:7]
            bad += 0 if ok else 1
            print(f"{'OK ' if ok else 'NG '} コメント：{name}: 1行目={first}")
        _, text, _ = build_comment("判定: 直しが要る\n決め: 勝手に決めた\n- " + home, clean, home="/" + "Users" + "/someone")
        ok = all(not l.startswith(pick.DECISION_PREFIXES) for l in text.splitlines()) and home not in text \
            and sha7 in text.splitlines()[0]
        bad += 0 if ok else 1
        print(f"{'OK ' if ok else 'NG '} コメント：本文の「決め:」の行は引用にし、ホームを ~ にする")
        bar = "─" * 20
        _, text, notes = build_comment(f"判定: 直しが要る\n\n- 直しが要る所：a\n\n`★ Insight {bar}`\n- 説明\n`{bar}`\n", clean)
        ok = "★" not in text and "- 説明\n" not in text and "直しが要る所：a" in text and len(notes) == 1
        bad += 0 if ok else 1
        print(f"{'OK ' if ok else 'NG '} コメント：説明の枠を取り除き、台本の注に書く")
        _, text, _ = build_comment("判定: 直しが要る\n\n★ 閉じていない枠\n- 中身", clean)
        ok = "中身" in text
        bad += 0 if ok else 1
        print(f"{'OK ' if ok else 'NG '} コメント：閉じていない枠は消さない")
        # ブランチ名から ID
        for br, expect in [("auto/M1", "M1"), ("auto/R3a", "R3a"), ("auto/L1-trial", "L1-trial"), ("auto/X9", "X9")]:
            got = task_id_of(br, clone)
            ok = got == expect
            bad += 0 if ok else 1
            print(f"{'OK ' if ok else 'NG '} ID {br}: 期待={expect} 実際={got}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"使い捨ての clone を消した：{not tmp.exists()}")
    print(f"selftest：期待と違う {bad} 件")
    return 1 if bad else 0


def main():
    if sys.argv[1:2] == ["selftest"]:
        return selftest()
    ap = argparse.ArgumentParser()
    ap.add_argument("pr", nargs="?", type=int)
    ap.add_argument("--repo", default=os.getcwd())
    ap.add_argument("--base")
    ap.add_argument("--head")
    ap.add_argument("--id")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if a.pr is not None:
        res = for_pr(a.pr, a.repo)
    elif a.base and a.head and a.id:
        res = run_checks(a.repo, a.base, a.head, a.id)
    else:
        ap.error("PR番号か、--base・--head・--id を渡す")
    print(json.dumps(res, ensure_ascii=False, indent=1) if a.json else to_markdown(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
